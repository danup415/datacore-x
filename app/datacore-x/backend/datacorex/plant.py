"""DATACORE-X reduced-order surrogate plant (L1 + L2 of the six-layer architecture).

This is a *reduced-order, physics-based* model of the reference facility
(8 racks, 4 CRAH, 2x100 % chillers, 2+1 CHW pumps, waterside economiser HX,
2 cooling towers, transformer, generator, LV switchgear, 2N UPS + batteries,
A/B PDUs).  It exists so the 3D twin, SCADA bridge, historian and AI layer can
be developed and validated end-to-end before (and independently of) the
MATLAB/Simulink facility model.  When the Simulink model publishes through the
MATLAB bridge (``source='external'``) it replaces this surrogate as the
authoritative state source; every consumer is unchanged because both speak the
same registry-defined snapshot schema.

Model fidelity follows Section 12 of the blueprint: thermal RC racks and
zones, effectiveness-NTU coils/HX, pump/system curve hydraulics, Carnot-
fraction chiller performance map, approach-based towers, system-level power
flow with efficiency curves, equivalent-circuit batteries.  All parameters are
*design assumptions* for a hypothetical facility, not measured data.

Integration: explicit Euler, dt = 1 s (all time constants >= 15 s).
"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np

from .registry import asset_index
from . import replay as _replay

CP_AIR = 1.006      # kJ/kg/K
RHO_AIR = 1.18      # kg/m3
CP_W = 4.186        # kJ/kg/K  (1 L/s water ~ 1 kg/s)
ABS_HUMIDITY = 0.0085  # kg/kg, assumed constant in the data hall

RACKS = [f"R-{i:02d}" for i in range(1, 9)]
CRAHS = [f"CRAH-0{i}" for i in range(1, 5)]
PUMPS = ["P-01", "P-02", "P-03"]
CHILLERS = ["CH-01", "CH-02"]
TOWERS = ["CT-01", "CT-02"]
GPU_RACKS = {"R-04", "R-08"}


# ---------------------------------------------------------------------------
class PI:
    def __init__(self, kp, ki, lo, hi, u0=0.0, direct=True):
        self.kp, self.ki, self.lo, self.hi = kp, ki, lo, hi
        self.i = u0
        self.sign = 1.0 if direct else -1.0

    def step(self, err, dt, ff=0.0):
        e = self.sign * err
        u_unsat = ff + self.kp * e + self.i
        u = min(self.hi, max(self.lo, u_unsat))
        # conditional integration anti-windup
        if (u == u_unsat) or (u_unsat > self.hi and e < 0) or (u_unsat < self.lo and e > 0):
            self.i += self.ki * e * dt
            self.i = min(self.hi, max(self.lo - self.hi, self.i))
        return u


@dataclass
class Fault:
    """A fault injection. Severity ramps 0 -> ``severity`` (incipient ->
    developing -> severe) over ``ramp_s`` starting ``onset_s`` after ``t0``."""
    fault_id: str
    kind: str
    asset: str
    severity: float = 1.0
    t0: float = 0.0
    onset_s: float = 0.0
    ramp_s: float = 0.0
    duration_s: float | None = None
    params: dict = field(default_factory=dict)

    def sev(self, t: float) -> float:
        tt = t - self.t0 - self.onset_s
        if tt < 0:
            return 0.0
        if self.duration_s is not None and tt > self.duration_s:
            return 0.0
        if self.ramp_s <= 0:
            return self.severity
        return self.severity * min(1.0, tt / self.ramp_s)

    def stage(self, t: float) -> str:
        s = self.sev(t) / max(self.severity, 1e-9)
        if s <= 0:
            return "pending" if t < self.t0 + self.onset_s else "ended"
        return "incipient" if s < 0.34 else ("developing" if s < 0.75 else "severe")

    def to_dict(self, t: float) -> dict:
        return {"fault_id": self.fault_id, "kind": self.kind, "asset": self.asset,
                "severity_now": round(self.sev(t), 3), "severity_final": self.severity,
                "stage": self.stage(t), "t0": self.t0, "onset_s": self.onset_s,
                "ramp_s": self.ramp_s, "duration_s": self.duration_s, "params": self.params}


# ---------------------------------------------------------------------------
class Plant:
    """Complete facility surrogate. ``step(dt)`` advances the physics,
    ``truth()`` returns ground-truth asset values keyed exactly like the
    registry data points."""

    MODEL_ID = "dcx-surrogate-rom"
    MODEL_VERSION = "1.0.0"

    def __init__(self, seed: int = 7, start_hour: float = 10.0, util_noise: bool = True):
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.t = 0.0
        self.start_hour = start_hour
        self.reg = asset_index()
        self.faults: list[Fault] = []
        self.events: list[dict] = []

        # ---- operator setpoints -------------------------------------------
        self.sp = {"supply_air_c": 22.0, "chws_c": 18.0, "dp_kpa": 180.0,
                   "tower_leaving_c": 21.0, "max_inlet_c": 25.0}
        # ---- IT workload ---------------------------------------------------
        self.u_base = {r: float(v) for r, v in zip(RACKS, self.rng.uniform(0.55, 0.72, 8))}
        self.u_ou = {r: 0.0 for r in RACKS}
        self.it_scale = 1.0
        self.util_noise = util_noise
        self.placement = {r: 1.0 for r in RACKS}
        # ---- air-side states -----------------------------------------------
        self.T_out = {r: 35.0 for r in RACKS}
        self.T_in = {r: 23.0 for r in RACKS}
        self.T_ha = 34.0
        self.T_pl = 22.0
        self.T_ca = 22.2
        self.crah = {c: {"run": True, "enabled": True, "tripped": False, "speed": 0.55,
                         "valve": 0.6, "restart": 0.0} for c in CRAHS}
        self.crah_fan_pi = PI(0.05, 0.002, -0.3, 0.5, 0.0)
        self.crah_valve_pi = {c: PI(0.05, 0.004, 0.05, 1.0, 0.6) for c in CRAHS}
        # ---- water side -------------------------------------------------------
        self.pump = {p: {"duty": p != "P-03", "run": p != "P-03", "tripped": False,
                         "restart": 0.0, "standby_timer": 0.0} for p in PUMPS}
        self.pump_speed = 0.75
        self.pump_pi = PI(0.0010, 0.0002, 0.30, 1.0, 0.75)
        self.H = 180.0
        self.q_chw = 4.5
        self.T_chws = 18.0
        self.T_chwr = 24.0
        self.chiller = {c: {"lead": c == "CH-01", "run": c == "CH-01", "tripped": False,
                            "restart": 1e6 if c == "CH-01" else 0.0, "hi_plr_timer": 0.0, "cop": 7.0, "Q": 0.0, "P": 0.0,
                            "force": False}
                        for c in CHILLERS}
        self.tower = {c: {"run": True, "speed": 0.5, "tripped": False} for c in TOWERS}
        self.tower_pi = PI(0.12, 0.004, 0.0, 1.0, 0.5)
        self.T_ctl = 21.0
        self.q_cw = 9.0
        # ---- electrical -------------------------------------------------------
        self.grid_ok = True
        self.gen = {"state": "STOPPED", "timer": 0.0, "run_s": 0.0, "fuel": 92.0}
        self.bus_source = "utility"
        self.ats_timer = 0.0
        self.retransfer_timer = 0.0
        self.mech_restart_timer = 1e6
        self.ups = {u: {"mode": "DOUBLE_CONVERSION", "out_ok": True, "walkin": 0.0} for u in ("UPS-A", "UPS-B")}
        self.bat = {b: {"soc": 1.0, "temp": 24.0, "I": 0.0, "V": 0.0} for b in ("BAT-A", "BAT-B")}
        self.tx_wind = 55.0
        # ---- accumulators -------------------------------------------------------
        self.energy_kwh = 0.0
        self.it_energy_kwh = 0.0
        self._out: dict = {}
        self._compute(0.0)  # populate outputs

    # ======================================================================
    # Faults & commands
    # ======================================================================
    def inject(self, kind, asset, severity=1.0, onset_s=0.0, ramp_s=0.0, duration_s=None,
               fault_id=None, **params) -> Fault:
        f = Fault(fault_id or f"{kind}:{asset}:{len(self.faults)}", kind, asset, float(severity),
                  self.t, float(onset_s), float(ramp_s), duration_s, params)
        if fault_id:   # re-applying the same scenario replaces its fault instead of stacking a duplicate
            self.faults = [x for x in self.faults if x.fault_id != fault_id]
        self.faults.append(f)
        self._event("FAULT_INJECTED", asset, f"{kind} severity {severity}")
        return f

    def clear_faults(self, asset: str | None = None):
        self.faults = [f for f in self.faults if asset is not None and f.asset != asset]

    def sev(self, kind: str, asset: str | None = None) -> float:
        s = 0.0
        for f in self.faults:
            if f.kind == kind and (asset is None or f.asset == asset):
                s = max(s, f.sev(self.t))
        return s

    def _fault_param(self, kind, asset, key, default):
        for f in self.faults:
            if f.kind == kind and f.asset == asset and f.sev(self.t) > 0:
                return f.params.get(key, default)
        return default

    def _replay_excess(self, p: str) -> float:
        """Measured vibration increase (mm/s) of a replayed real bearing on pump p, 0 if none."""
        for f in self.faults:
            if f.kind == "pump_bearing_replay" and f.asset == p and f.sev(self.t) > 0:
                return _replay.sample(f.params["profile"], f.params.get("_run_s", 0.0) * f.params.get("compress", 1.0))["excess_mms"]
        return 0.0

    def replay_status(self) -> list[dict]:
        out = []
        for f in self.faults:
            if f.kind == "pump_bearing_replay" and f.sev(self.t) > 0:
                tau = f.params.get("_run_s", 0.0) * f.params.get("compress", 1.0)
                smp = _replay.sample(f.params["profile"], tau)
                out.append({"asset": f.asset, "profile": f.params["profile"], "compress": f.params.get("compress", 1.0),
                            "bearing_life_elapsed_s": round(tau, 1), "life_frac": round(smp["life_frac"], 4),
                            "measured_vrms_mms": round(smp["vrms_mms"], 3), "measured_kurtosis": round(smp["kurtosis"], 2),
                            "ended": smp["ended"], **{k: v for k, v in _replay.describe(f.params["profile"]).items()
                                                      if k in ("title", "source", "bearing")}})
        return out

    def _event(self, kind, asset, text):
        self.events.append({"t": round(self.t, 1), "kind": kind, "asset": asset, "text": text})
        self.events = self.events[-200:]

    def apply_command(self, cmd: dict) -> tuple[bool, str]:
        """Supervisory command entry point (PLC layer with interlocks)."""
        c = cmd.get("command")
        a = cmd.get("asset")
        v = cmd.get("value")
        if c == "set_setpoint":
            limits = {"supply_air_c": (18.0, 27.0), "chws_c": (12.0, 22.0), "dp_kpa": (100.0, 260.0),
                      "tower_leaving_c": (16.0, 29.0), "max_inlet_c": (20.0, 27.0)}
            name = cmd.get("name")
            if name not in limits:
                return False, f"unknown setpoint '{name}'"
            lo, hi = limits[name]
            if v is None or not (lo <= float(v) <= hi):
                return False, f"value outside engineering limits [{lo}, {hi}]"
            self.sp[name] = float(v)
            self._event("SETPOINT", "DCX", f"{name} -> {v}")
            return True, "setpoint applied"
        if c in ("pump_start", "pump_stop", "pump_changeover"):
            if a not in PUMPS:
                return False, "asset is not a CHW pump"
            if c == "pump_start":
                if self.pump[a]["tripped"]:
                    return False, "INTERLOCK: pump tripped — reset required"
                self.pump[a]["duty"] = True
                self.pump[a]["run"] = True
                self._event("PUMP_START", a, "operator start")
                return True, "pump started"
            if c == "pump_stop":
                running = [p for p in PUMPS if self.pump[p]["run"] and p != a]
                if not running:
                    return False, "INTERLOCK: cannot stop the last running CHW pump"
                self.pump[a]["duty"] = False
                self.pump[a]["run"] = False
                self._event("PUMP_STOP", a, "operator stop")
                return True, "pump stopped"
            # changeover: start target (value = standby pump id), stop 'a'
            tgt = v
            if tgt not in PUMPS or tgt == a:
                return False, "changeover target must be another CHW pump"
            if self.pump[tgt]["tripped"]:
                return False, "INTERLOCK: target pump tripped"
            self.pump[tgt].update(duty=True, run=True)
            self.pump[a].update(duty=False, run=False)
            self._event("PUMP_CHANGEOVER", a, f"{a} -> {tgt}")
            return True, f"changeover {a} -> {tgt} executed"
        if c in ("crah_enable", "crah_disable"):
            if a not in CRAHS:
                return False, "asset is not a CRAH"
            if c == "crah_disable":
                n = sum(1 for x in CRAHS if self.crah[x]["run"] and x != a)
                if n < 2:
                    return False, "INTERLOCK: minimum two CRAH units must remain in service"
                self.crah[a]["enabled"] = False
                self._event("CRAH_DISABLE", a, "operator disable")
                return True, "CRAH disabled"
            if self.crah[a]["tripped"]:
                return False, "INTERLOCK: CRAH tripped — reset required"
            self.crah[a]["enabled"] = True
            self._event("CRAH_ENABLE", a, "operator enable")
            return True, "CRAH enabled"
        if c == "chiller_lead":
            if a not in CHILLERS:
                return False, "asset is not a chiller"
            for ch in CHILLERS:
                self.chiller[ch]["lead"] = ch == a
            self._event("CHILLER_LEAD", a, "lead chiller selected")
            return True, "lead chiller changed"
        if c in ("reset_trip", "maintenance_complete"):
            if a not in self.reg:
                return False, "unknown asset"
            active = [f for f in self.faults if f.asset == a and f.sev(self.t) > 0]
            if c == "reset_trip" and any(f.kind.endswith("_trip") for f in active):
                return False, "INTERLOCK: trip cause still present — complete maintenance first"
            if c == "maintenance_complete":
                self.clear_faults(a)
                if a in self.bat:
                    self.bat[a]["temp"] = min(self.bat[a]["temp"], 26.0)
            for d in (self.pump, self.crah, self.chiller, self.tower):
                if a in d:
                    d[a]["tripped"] = False
            self._event(c.upper(), a, "maintenance/reset by operator")
            return True, "maintenance recorded; asset returned to service" if c == "maintenance_complete" else "trip reset"
        return False, f"unsupported command '{c}'"

    # ======================================================================
    # Boundary conditions
    # ======================================================================
    def hour_of_day(self, t=None):
        t = self.t if t is None else t
        return (self.start_hour + t / 3600.0) % 24.0

    def wetbulb(self):
        h = self.hour_of_day()
        return 17.0 - 3.0 * math.cos(2 * math.pi * (h - 5.0) / 24.0)  # Pune, November (assumed)

    def drybulb(self):
        h = self.hour_of_day()
        return 23.5 - 6.0 * math.cos(2 * math.pi * (h - 5.0) / 24.0)

    # ======================================================================
    # Simulation step
    # ======================================================================
    def step(self, dt: float = 1.0):
        self.t += dt
        self._compute(dt)

    def _compute(self, dt: float):
        t = self.t
        o: dict = {}
        sp = self.sp
        wb = self.wetbulb()

        # ------------------------------------------------------------------
        # Discrete fault effects (trips / grid)
        # ------------------------------------------------------------------
        for p in PUMPS:
            if self.sev("pump_trip", p) > 0 and not self.pump[p]["tripped"]:
                self.pump[p]["tripped"] = True
                self.pump[p]["run"] = False
                self._event("TRIP", p, "pump motor protection trip")
        # measured-data replay: the replayed bearing ages only while its pump runs (see replay.py)
        for f in self.faults:
            if f.kind != "pump_bearing_replay" or f.sev(t) <= 0:
                continue
            p = f.asset
            running = self.pump[p]["run"] and not self.pump[p]["tripped"]
            if running and dt > 0:
                f.params["_run_s"] = f.params.get("_run_s", 0.0) + dt
            smp = _replay.sample(f.params["profile"], f.params.get("_run_s", 0.0) * f.params.get("compress", 1.0))
            f.params["_life_frac"] = round(smp["life_frac"], 4)
            if smp["ended"] and running:
                self.pump[p]["tripped"] = True
                self.pump[p]["run"] = False
                self._event("TRIP", p, f"bearing failure: end of replayed run-to-failure record ({f.params['profile']})")
        for c in CRAHS:
            if self.sev("crah_trip", c) > 0 and not self.crah[c]["tripped"]:
                self.crah[c]["tripped"] = True
                self._event("TRIP", c, "CRAH fan trip")
        for c in CHILLERS:
            if self.sev("chiller_trip", c) > 0 and not self.chiller[c]["tripped"]:
                self.chiller[c]["tripped"] = True
                self._event("TRIP", c, "chiller safety trip")
        grid_now = self.sev("utility_failure", "TX-01") <= 0
        if grid_now != self.grid_ok:
            self._event("UTILITY", "TX-01", "utility restored" if grid_now else "UTILITY FAILURE")
        self.grid_ok = grid_now

        # ------------------------------------------------------------------
        # Electrical source logic: generator + ATS (PLC sequence)
        # ------------------------------------------------------------------
        g = self.gen
        if not self.grid_ok:
            self.retransfer_timer = 0.0
            if g["state"] in ("STOPPED", "COOLDOWN"):
                g["state"], g["timer"] = "STARTING", 0.0
                self._event("GEN", "GEN-01", "start command (utility lost)")
            if g["state"] == "STARTING":
                g["timer"] += dt
                if g["timer"] >= 10.0:
                    g["state"] = "RUNNING"
                    self._event("GEN", "GEN-01", "generator at rated V/f")
            if self.bus_source == "utility":
                self.bus_source = "none"
                self.ats_timer = 0.0
                self.mech_restart_timer = 0.0
            if self.bus_source == "none" and g["state"] == "RUNNING":
                self.ats_timer += dt
                if self.ats_timer >= 2.0:
                    self.bus_source = "generator"
                    self._event("ATS", "SWG-01", "transferred to generator")
        else:
            if self.bus_source == "none":
                self.bus_source = "utility"
            if self.bus_source == "generator":
                self.retransfer_timer += dt
                if self.retransfer_timer >= 60.0:
                    self.bus_source = "utility"  # closed-transition retransfer
                    g["state"], g["timer"] = "COOLDOWN", 0.0
                    self._event("ATS", "SWG-01", "retransferred to utility")
            if g["state"] == "COOLDOWN":
                g["timer"] += dt
                if g["timer"] >= 120.0:
                    g["state"] = "STOPPED"
            if g["state"] == "STARTING":
                g["state"] = "STOPPED"
        if g["state"] in ("RUNNING", "COOLDOWN"):
            g["run_s"] += dt
        bus_ok = self.bus_source != "none"
        if bus_ok:
            self.mech_restart_timer += dt
        else:
            self.mech_restart_timer = 0.0
        mech_ready = bus_ok and self.mech_restart_timer >= 3.0  # staggered restart

        # ------------------------------------------------------------------
        # UPS / battery
        # ------------------------------------------------------------------
        forced_batt = self.sev("ups_battery_mode", "DCX") > 0  # facility-wide transfer test
        for u, b in (("UPS-A", "BAT-A"), ("UPS-B", "BAT-B")):
            st = self.ups[u]
            in_ok = bus_ok and not forced_batt and self.sev("ups_battery_mode", u) <= 0
            if in_ok:
                st["walkin"] = min(1.0, st["walkin"] + dt / 5.0) if self.bus_source == "generator" else 1.0
            else:
                st["walkin"] = 0.0
            if not st["out_ok"]:
                if in_ok:
                    st["out_ok"] = True
                    self._event("UPS", u, "output restored")
            st["mode"] = "DOUBLE_CONVERSION" if (in_ok and st["walkin"] >= 1.0) else "BATTERY"
            if self.bat[b]["soc"] <= 0.01 and st["mode"] == "BATTERY":
                if st["out_ok"]:
                    self._event("UPS", u, "battery exhausted — OUTPUT OFF")
                st["out_ok"] = False
            if not st["out_ok"]:
                st["mode"] = "OUTPUT_OFF"
        path_ok = {"A": self.ups["UPS-A"]["out_ok"], "B": self.ups["UPS-B"]["out_ok"]}
        it_powered = path_ok["A"] or path_ok["B"]

        # ------------------------------------------------------------------
        # IT workload and rack power
        # ------------------------------------------------------------------
        h = self.hour_of_day()
        diurnal = 0.10 * math.sin(2 * math.pi * (h - 9.0) / 24.0)
        scale = self.it_scale * (1.0 + self.sev("it_load_increase", None))
        place = dict(self.placement)
        if self.sev("workload_placement", None) > 0:
            w = self._fault_param("workload_placement", "DCX", "weights", None)
            if w:
                place = {r: float(w.get(r, 1.0)) for r in RACKS}
        # utilisation before placement, then redistribute at constant total (water-filling)
        u_raw = {}
        for r in RACKS:
            if dt > 0 and self.util_noise:
                self.u_ou[r] += -self.u_ou[r] * dt / 300.0 + 0.02 * math.sqrt(2 * dt / 300.0) * self.rng.standard_normal()
            u_raw[r] = min(1.0, max(0.05, (self.u_base[r] + diurnal + self.u_ou[r]) * scale))
        U = sum(u_raw.values())
        if any(abs(w - 1.0) > 1e-9 for w in place.values()):
            alloc = {r: 0.0 for r in RACKS}
            free = set(RACKS)
            rem = U
            for _ in range(8):
                wsum = sum(place[r] for r in free)
                if not free or wsum <= 0 or rem <= 1e-9:
                    break
                capped = set()
                for r in free:
                    alloc[r] += rem * place[r] / wsum
                rem = 0.0
                for r in list(free):
                    if alloc[r] > 1.0:
                        rem += alloc[r] - 1.0
                        alloc[r] = 1.0
                        capped.add(r)
                free -= capped
            u_place = {r: max(0.05, alloc[r]) for r in RACKS}
        else:
            u_place = u_raw
        rack_P, rack_m = {}, {}
        for r in RACKS:
            u = u_place[r]
            # server thermal protection: throttle above 35 °C inlet
            if self.T_in[r] > 35.0:
                u *= max(0.3, 1.0 - 0.12 * (self.T_in[r] - 35.0))
            extra = self.sev("rack_overheat", r) * self._fault_param("rack_overheat", r, "extra_kw", 6.0)
            P = (3.0 + 13.0 * u + extra) if it_powered else 0.0
            rack_P[r] = P
            rack_m[r] = P / (CP_AIR * 12.0) if P > 0 else 0.0  # server fans hold ~12 K rise
            o[r] = {"state": "RUNNING" if it_powered else "NO_POWER",
                    "cpu_util": u * 100 if it_powered else 0.0,
                    "gpu_util": (min(100.0, u * 112) if r in GPU_RACKS else 0.0) if it_powered else 0.0,
                    "power_kw": P, "heat_kw": P, "airflow_m3s": rack_m[r] / RHO_AIR}
        P_it = sum(rack_P.values())
        m_rack = sum(rack_m.values())

        # ------------------------------------------------------------------
        # CRAH units (air side)
        # ------------------------------------------------------------------
        crah_m, crah_sup, crah_Q = {}, {}, {}
        running = []
        for c in CRAHS:
            st = self.crah[c]
            st["run"] = st["enabled"] and not st["tripped"] and mech_ready
            if st["run"]:
                running.append(c)
        n_run = max(1, len(running))
        m_max = 4.5
        max_in = max(self.T_in.values())
        ff = 1.15 * m_rack / (n_run * m_max) if running else 0.0
        trim = self.crah_fan_pi.step(max_in - sp["max_inlet_c"], dt) if dt > 0 else 0.0
        speed_cmd = min(1.0, max(0.30, ff + trim))
        # hydraulic share: valve-weighted
        vsum = sum(self.crah[c]["valve"] for c in running) or 1.0
        for c in CRAHS:
            st = self.crah[c]
            block = self.sev("crah_filter_blockage", c) * 0.5
            if st["run"]:
                st["speed"] += (speed_cmd - st["speed"]) * min(1.0, dt / 8.0)
            else:
                st["speed"] += (0.0 - st["speed"]) * min(1.0, dt / 6.0)
            m = st["speed"] * m_max * (1 - block)
            q_j = self.q_chw * (st["valve"] / vsum) if st["run"] else 0.0
            NTU = 2.4 * (max(st["valve"], 1e-3) ** 0.7) * (max(q_j, 1e-3) / 1.6) ** 0.35
            eps = min(0.95, 1 - math.exp(-NTU)) if (st["run"] and self.q_chw > 0.05) else 0.0
            Tsup = self.T_ha - eps * (self.T_ha - self.T_chws)
            Q = m * CP_AIR * (self.T_ha - Tsup)
            if st["run"] and dt > 0:
                cmd = self.crah_valve_pi[c].step(Tsup - sp["supply_air_c"], dt)
                st["valve"] += (cmd - st["valve"]) * min(1.0, dt / 8.0)  # actuator time constant
            crah_m[c], crah_sup[c], crah_Q[c] = m, Tsup, Q
            imb = self.sev("fan_imbalance", c)
            brg = self.sev("fan_bearing", c)
            s = st["speed"]
            vib = (0.8 * s + 6.0 * imb * s * s + 4.5 * brg ** 1.3 + 0.08 * self.rng.standard_normal() * s) if s > 0.05 else 0.0
            fan_kw = 5.5 * s ** 3 * (1 + 0.18 * brg) * (1 + 0.6 * block)
            state = "RUNNING" if st["run"] else ("TRIPPED" if st["tripped"] else ("NO_POWER" if not mech_ready else "STANDBY"))
            o[c] = {"state": state, "fan_speed_pct": s * 100, "airflow_m3s": m / RHO_AIR,
                    "supply_c": Tsup if st["run"] else self.T_ha, "return_c": self.T_ha,
                    "valve_pct": st["valve"] * 100 if st["run"] else 0.0, "chw_flow_ls": q_j,
                    "coil_kw": Q, "fan_kw": fan_kw, "vib_mms": max(0.0, vib),
                    "_eps": eps}
        m_crah = sum(crah_m.values())

        # ------------------------------------------------------------------
        # Thermal zones and racks (multi-zone RC)
        # ------------------------------------------------------------------
        if m_crah > 1e-3:
            T_mix = sum(crah_m[c] * crah_sup[c] for c in CRAHS) / m_crah
            self.T_pl += (T_mix - self.T_pl) * min(1.0, dt / 20.0)
        else:
            self.T_pl += (self.T_ha - self.T_pl) * min(1.0, dt / 240.0)
        deficit = max(0.0, 1.0 - m_crah / m_rack) if m_rack > 0 else 0.0
        T_ca_target = (1 - deficit) * self.T_pl + deficit * self.T_ha
        self.T_ca += (T_ca_target - self.T_ca) * min(1.0, dt / 15.0)

        cr_pos = {c: self.reg[c]["pos"] for c in CRAHS}
        for r in RACKS:
            px, _, pz = self.reg[r]["pos"]
            wsum = wrun = 0.0
            for c in CRAHS:
                d2 = (px - cr_pos[c][0]) ** 2 + (pz - cr_pos[c][2]) ** 2
                w = 1.0 / d2
                wsum += w
                wrun += w * (crah_m[c] / (m_max * 0.55) if crah_m[c] > 0 else 0.0)
            local = min(1.0, wrun / wsum)
            edge = 1.0 if px in (5.8, 8.2) else 0.0
            # perforated-tile delivery is ~uniform (m_crah/8); dense racks starve and draw hot-aisle air
            tile_m = m_crah / len(RACKS)
            def_i = max(0.0, 1.0 - tile_m / rack_m[r]) if rack_m[r] > 0 else 0.0
            recirc = 0.02 + 0.10 * (1 - local) + 0.45 * def_i * (1 + 0.5 * edge)
            recirc = min(0.9, recirc)
            # local exhaust short-circuit (missing blanking panels / blocked front door)
            r_self = 0.32 * self.sev("rack_overheat", r)
            Tin_target = (1 - recirc - r_self) * self.T_ca + recirc * self.T_ha + r_self * self.T_out[r]
            recirc += r_self
            self.T_in[r] += (Tin_target - self.T_in[r]) * min(1.0, dt / 10.0)
            if dt > 0:
                C_r = 60.0  # kJ/K rack + server thermal mass
                dT = (rack_P[r] - rack_m[r] * CP_AIR * (self.T_out[r] - self.T_in[r])) / C_r
                if rack_P[r] <= 0:
                    dT = (self.T_ha - self.T_out[r]) / 300.0
                self.T_out[r] += dT * dt
            o[r]["inlet_c"] = self.T_in[r]
            o[r]["outlet_c"] = self.T_out[r]
            o[r]["_recirc"] = recirc
        if dt > 0:
            C_ha = 900.0  # kJ/K room air + structure participating
            bypass = max(0.0, m_crah - m_rack)
            q_in = sum(rack_m[r] * CP_AIR * (self.T_out[r] - self.T_ha) for r in RACKS)
            q_in += bypass * CP_AIR * (self.T_pl - self.T_ha)
            q_in += 0.35 * (self.drybulb() + 4 - self.T_ha)  # envelope
            if m_rack <= 0:
                q_in += m_crah * CP_AIR * (self.T_pl - self.T_ha)
            self.T_ha += q_in / C_ha * dt

        # ------------------------------------------------------------------
        # CHW pumps + hydraulics (PLC duty/standby + DP control)
        # ------------------------------------------------------------------
        for p in PUMPS:
            st = self.pump[p]
            if st["duty"] and not st["tripped"]:
                st["run"] = True
        n_duty_ok = sum(1 for p in PUMPS if self.pump[p]["duty"] and not self.pump[p]["tripped"])
        if n_duty_ok < 2:
            for p in PUMPS:
                st = self.pump[p]
                if not st["duty"] and not st["tripped"]:
                    st["standby_timer"] += dt
                    if st["standby_timer"] >= 5.0:
                        st["duty"] = st["run"] = True
                        st["standby_timer"] = 0.0
                        self._event("AUTO_START", p, "standby pump auto-start (PLC redundancy logic)")
                    break
        run_p = [p for p in PUMPS if self.pump[p]["run"] and not self.pump[p]["tripped"] and mech_ready]
        H0, kp_, Hs = 320.0, 2.2, 40.0
        vmean = (sum(self.crah[c]["valve"] for c in running) / len(running)) if running else 0.15
        ks = 6.0 / max(0.15, vmean) ** 2
        a_p = {p: 1.0 - 0.28 * self.sev("pump_cavitation", p) for p in PUMPS}
        n = self.pump_speed
        if run_p:
            if dt > 0:
                cmd = self.pump_pi.step(sp["dp_kpa"] - self.H, dt)
                self.pump_speed += (cmd - self.pump_speed) * min(1.0, dt / 5.0)  # VFD ramp
            n = self.pump_speed
            lo, hi = Hs, max(a_p[p] * H0 * n * n for p in run_p)
            if hi <= lo:
                Hsol, qs = lo, {p: 0.0 for p in run_p}
            else:
                for _ in range(40):
                    mid = 0.5 * (lo + hi)
                    qsum = sum(math.sqrt(max(0.0, (a_p[p] * H0 * n * n - mid) / kp_)) for p in run_p)
                    qsys = math.sqrt(max(0.0, (mid - Hs) / ks))
                    if qsum > qsys:
                        lo = mid
                    else:
                        hi = mid
                Hsol = 0.5 * (lo + hi)
                qs = {p: math.sqrt(max(0.0, (a_p[p] * H0 * n * n - Hsol) / kp_)) for p in run_p}
            cav = sum(self.sev("pump_cavitation", p) for p in run_p)
            Hsol *= 1 + 0.03 * cav * self.rng.standard_normal()
            self.H = Hsol
            self.q_chw += (max(0.0, sum(qs.values())) - self.q_chw) * min(1.0, dt / 3.0)  # fluid inertia
        else:
            self.H += (0.0 - self.H) * min(1.0, dt / 3.0)
            self.q_chw += (0.0 - self.q_chw) * min(1.0, dt / 4.0)
            qs = {}
        for p in PUMPS:
            st = self.pump[p]
            q = qs.get(p, 0.0)
            is_run = p in run_p
            nn = n if is_run else 0.0
            brg = self.sev("pump_bearing", p)
            cav = self.sev("pump_cavitation", p)
            effd = self.sev("pump_efficiency", p) * self._fault_param("pump_efficiency", p, "drop", 0.25)
            eta_bep = 0.72 * (1 - effd) * (1 - 0.06 * brg)
            if is_run and nn > 0.05:
                x = q / (nn * 5.0)
                eta = max(0.15, eta_bep * (1 - 0.8 * (x - 1) ** 2))
                P = q * self.H / 1000.0 / eta + 0.05 * brg
                vib = 0.9 + 1.3 * nn * nn + 6.0 * brg ** 1.5 + 3.5 * cav + abs(0.15 * self.rng.standard_normal() * (0.3 + 2 * cav))
                vib += self._replay_excess(p)
                cur = P * 1000 / (math.sqrt(3) * 415 * 0.85 * 0.90)
            else:
                eta, P, vib, cur = 0.0, 0.0, 0.0, 0.0
            state = "RUNNING" if is_run else ("TRIPPED" if st["tripped"] else
                                              ("NO_POWER" if not mech_ready else ("STANDBY" if not st["duty"] else "STOPPED")))
            o[p] = {"state": state, "speed_pct": nn * 100, "flow_ls": q, "head_kpa": self.H if is_run else 0.0,
                    "power_kw": P, "eff_pct": eta * 100, "vib_mms": vib, "current_a": cur}

        # ------------------------------------------------------------------
        # Chilled water thermal loop: coils -> return -> HX -> chillers -> supply
        # ------------------------------------------------------------------
        Q_coils = sum(crah_Q.values())
        C_chw = CP_W * max(self.q_chw, 0.05)
        T_ret_target = self.T_chws + Q_coils / C_chw if self.q_chw > 0.05 else self.T_chwr
        self.T_chwr += (T_ret_target - self.T_chwr) * min(1.0, dt / 40.0)
        # condenser-water / tower
        cw_on = mech_ready
        q_cw = self.q_cw if cw_on else 0.0
        C_cw = CP_W * max(q_cw, 0.05)
        foul = self.sev("hx_fouling", "HX-01")
        Q_hx = 0.0
        eps_hx = 0.0
        if cw_on and self.q_chw > 0.05 and self.T_ctl < self.T_chwr - 1.0:
            Cmin = min(C_chw, C_cw)
            eps_hx = 0.72 * (1 - 0.85 * foul)
            Q_hx = eps_hx * Cmin * (self.T_chwr - self.T_ctl)
        T_after_hx = self.T_chwr - Q_hx / C_chw
        T_cwe = self.T_ctl + (Q_hx / C_cw if cw_on else 0.0)
        o["HX-01"] = {"state": "RUNNING" if Q_hx > 0 else "BYPASS", "duty_kw": Q_hx,
                      "effectiveness_pct": eps_hx * 100, "chw_in_c": self.T_chwr, "chw_out_c": T_after_hx,
                      "cw_in_c": self.T_ctl, "cw_out_c": T_cwe,
                      "ua_kwk": (eps_hx * min(C_chw, C_cw) if Q_hx > 0 else 0.0)}
        # chiller staging (lead/lag)
        lead = next((c for c in CHILLERS if self.chiller[c]["lead"]), CHILLERS[0])
        lag = [c for c in CHILLERS if c != lead][0]
        lead_ok = not self.chiller[lead]["tripped"] and mech_ready
        need_lag = (not lead_ok) or self.chiller[lead]["hi_plr_timer"] >= 120.0
        self.chiller[lead]["run"] = lead_ok
        self.chiller[lag]["run"] = (need_lag or self.chiller[lag].get("force", False)) and not self.chiller[lag]["tripped"] and mech_ready
        for c in CHILLERS:  # start-up timer runs only while the chiller is commanded on
            st = self.chiller[c]
            st["restart"] = st["restart"] + dt if st["run"] else 0.0
        avail = [c for c in CHILLERS if self.chiller[c]["run"] and self.chiller[c]["restart"] >= 180.0]
        Q_req = max(0.0, C_chw * (T_after_hx - sp["chws_c"])) if self.q_chw > 0.05 else 0.0
        T_leave = T_after_hx
        Q_ch_tot = P_ch_tot = 0.0
        share = Q_req / len(avail) if avail else 0.0
        cdeg_all = {}
        for c in CHILLERS:
            st = self.chiller[c]
            cdeg = self.sev("chiller_degradation", c)
            cdeg_all[c] = cdeg
            cap = 160.0 * (1 - 0.012 * (T_cwe - 24.0)) * (1 - 0.25 * cdeg)
            if c in avail:
                Qc = min(share, cap)
                plr = Qc / 160.0
                T_ev = sp["chws_c"] - 2.0 + 273.15
                T_cd = T_cwe + 5.5 + 273.15
                plr_f = 1 - 0.35 * (1 - max(plr, 0.15)) ** 2
                cop = min(12.0, 0.40 * T_ev / max(3.0, T_cd - T_ev) * plr_f * (1 - 0.30 * cdeg))
                Pc = Qc / cop if Qc > 0 else 3.0
                st["hi_plr_timer"] = st["hi_plr_timer"] + dt if plr > 0.95 else 0.0
            else:
                Qc, plr, cop, Pc = 0.0, 0.0, 0.0, 0.0
                st["hi_plr_timer"] = 0.0
            st.update(Q=Qc, P=Pc, cop=cop)
            Q_ch_tot += Qc
            P_ch_tot += Pc
            if st["tripped"]:
                state = "TRIPPED"
            elif not mech_ready:
                state = "NO_POWER"
            elif st["run"] and st["restart"] < 180.0:
                state = "STARTING"
            elif st["run"]:
                state = "RUNNING"
            else:
                state = "STANDBY"
            o[c] = {"state": state, "load_kw": Qc, "plr_pct": plr * 100, "cop": cop, "power_kw": Pc,
                    "chwr_c": T_after_hx, "cwe_c": T_cwe, "capacity_kw": cap,
                    "cwl_c": T_cwe + ((Qc + Pc) / C_cw if cw_on else 0.0)}
        if self.q_chw > 0.05:
            T_leave = T_after_hx - Q_ch_tot / C_chw
            self.T_chws += (T_leave - self.T_chws) * min(1.0, dt / 60.0)
        else:
            self.T_chws += (self.T_ha - 6.0 - self.T_chws) * min(1.0, dt / 1800.0)
        for c in CHILLERS:
            o[c]["chws_c"] = T_leave if c in avail else T_after_hx

        # cooling towers
        Q_rej = Q_hx + Q_ch_tot + P_ch_tot
        run_t = [c for c in TOWERS if mech_ready and not self.tower[c]["tripped"]]
        if dt > 0 and run_t:
            spd = self.tower_pi.step(self.T_ctl - sp["tower_leaving_c"], dt)
        else:
            spd = 0.0
        leav = []
        for c in TOWERS:
            st = self.tower[c]
            st["run"] = c in run_t
            st["speed"] += ((spd if st["run"] else 0.0) - st["speed"]) * min(1.0, dt / 10.0)
            deg = self.sev("tower_degradation", c)
            Qi = Q_rej / len(run_t) if run_t else 0.0
            app = 3.0 * (max(Qi, 1.0) / 90.0) ** 0.6 / (0.15 + 0.85 * st["speed"]) ** 0.7 * (1 + 1.6 * deg)
            tgt = (wb + app) if (st["run"] and cw_on) else self.drybulb()
            st.setdefault("T_l", self.T_ctl)
            st["T_l"] += (tgt - st["T_l"]) * min(1.0, dt / 90.0)
            if st["run"]:
                leav.append(st["T_l"])
            o[c] = {"state": "RUNNING" if st["run"] else ("NO_POWER" if not mech_ready else "STOPPED"),
                    "fan_speed_pct": st["speed"] * 100, "fan_kw": 5.5 * st["speed"] ** 3,
                    "heat_rej_kw": Qi, "approach_k": st["T_l"] - wb, "wetbulb_c": wb,
                    "leaving_c": st["T_l"], "entering_c": self.T_ctl + (Q_rej / C_cw if cw_on else 0.0)}
        self.T_ctl = sum(leav) / len(leav) if leav else self.T_ctl + (self.drybulb() - self.T_ctl) * min(1.0, dt / 90.0)

        # ------------------------------------------------------------------
        # Electrical power flow
        # ------------------------------------------------------------------
        P_crah = sum(o[c]["fan_kw"] for c in CRAHS)
        P_pump = sum(o[p]["power_kw"] for p in PUMPS)
        P_tower = sum(o[c]["fan_kw"] for c in TOWERS)
        P_cwp = 3.2 if cw_on else 0.0
        P_light = 4.0 if bus_ok else 0.0
        P_cool = P_ch_tot + P_pump + P_tower + P_cwp + P_crah
        P_mech = P_cool + P_light
        # PDU split
        both = path_ok["A"] and path_ok["B"]
        shareA = 0.5 if both else (1.0 if path_ok["A"] else 0.0)
        shareB = 1.0 - shareA if it_powered else 0.0
        pdu_out = {"PDU-A": P_it * shareA, "PDU-B": P_it * shareB}
        P_pdu_loss = 0.0
        for pdu, sh in (("PDU-A", shareA), ("PDU-B", shareB)):
            ph = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
            for r in RACKS:
                ph[self.reg[r]["phase"]] += rack_P[r] * sh
            I = {k: v * 1000 / 240.0 for k, v in ph.items()}
            mean_I = sum(I.values()) / 3
            imb = (max(I.values()) - mean_I) / mean_I * 100 if mean_I > 0.1 else 0.0
            loss = 0.015 * pdu_out[pdu]
            P_pdu_loss += loss
            o[pdu] = {"state": "ENERGISED" if sh > 0 else "DE-ENERGISED", "load_kw": pdu_out[pdu],
                      "load_pct": pdu_out[pdu] / 150.0 * 100, "current_l1_a": I["L1"],
                      "current_l2_a": I["L2"], "current_l3_a": I["L3"], "imbalance_pct": imb}
        P_ups_in_total = 0.0
        P_ups_loss = 0.0
        for u, b, pdu in (("UPS-A", "BAT-A", "PDU-A"), ("UPS-B", "BAT-B", "PDU-B")):
            st = self.ups[u]
            Pout = pdu_out[pdu] * 1.015 if st["out_ok"] else 0.0
            x = Pout / 150.0
            eta = 0.965 - 0.07 * math.exp(-x / 0.12) if Pout > 0 else 0.0
            loss = Pout * (1 / eta - 1) if eta > 0 else 0.0
            P_ups_loss += loss
            bs = self.bat[b]
            sohf = 1 - 0.40 * self.sev("battery_degradation", b)
            rf = 1 + 1.6 * self.sev("battery_degradation", b)
            cap_ah = 60.0 * sohf
            R = 0.060 * rf
            Voc = 160 * (3.0 + 0.35 * bs["soc"])
            I = 0.0
            Pch = 0.0
            if st["mode"] == "BATTERY":
                Pdc = (Pout + loss) * 1000.0
                disc = Voc * Voc - 4 * R * Pdc
                I = (Voc - math.sqrt(max(disc, 0.0))) / (2 * R) if disc > 0 else Voc / (2 * R)
                Pin = 0.0
            elif st["mode"] == "DOUBLE_CONVERSION":
                if bs["soc"] < 0.999:
                    I = -min(0.15 * cap_ah, 0.15 * cap_ah * max(0.05, (1 - bs["soc"]) / 0.05))
                    Pch = -I * Voc / 1000.0 / 0.95
                Pin = Pout + loss + Pch
            else:
                Pin = 0.0
            if dt > 0:
                bs["soc"] = min(1.0, max(0.0, bs["soc"] - I * dt / (3600.0 * cap_ah)))
                heat = I * I * R / 1000.0 + 0.8 * self.sev("battery_overheat", b)
                bs["temp"] += (heat - 0.04 * (bs["temp"] - 24.0)) / 180.0 * dt
            V = Voc - I * R
            bs["I"], bs["V"] = I, V
            P_exp = max(1.0, (Pout + loss)) if Pout > 0 else max(1.0, P_it * 0.5)
            runtime = bs["soc"] * cap_ah * 160 * 3.2 / 1000.0 / P_exp * 60.0
            P_ups_in_total += Pin
            o[u] = {"state": st["mode"], "load_kw": Pout, "load_pct": x * 100, "eff_pct": eta * 100,
                    "losses_kw": loss, "input_v": 415.0 if (bus_ok and st["mode"] != "BATTERY") else (0.0 if not bus_ok else 415.0),
                    "output_v": 415.0 if st["out_ok"] else 0.0, "_pin": Pin}
            o[b] = {"state": "DISCHARGING" if I > 0.5 else ("CHARGING" if I < -0.5 else "FLOAT"),
                    "soc_pct": bs["soc"] * 100, "soh_pct": sohf * 100, "voltage_v": V, "current_a": I,
                    "temp_c": bs["temp"], "runtime_min": runtime, "rint_mohm": R * 1000}
        P_bus = P_mech + P_ups_in_total
        on_util = self.bus_source == "utility"
        tx_load_kva = P_bus / 0.95 if on_util else 0.0
        lx = tx_load_kva / 500.0
        tx_loss = (0.9 + 4.5 * lx * lx) if self.grid_ok else 0.0
        if dt > 0:
            self.tx_wind += ((30.0 + 55.0 * lx ** 1.6) - self.tx_wind) * min(1.0, dt / 600.0)
        o["TX-01"] = {"state": "ENERGISED" if self.grid_ok else "DE-ENERGISED", "load_kva": tx_load_kva,
                      "load_pct": lx * 100, "losses_kw": tx_loss, "winding_c": self.tx_wind,
                      "lv_voltage_v": (415.0 - 6.0 * lx) if self.grid_ok else 0.0}
        gen_P = P_bus if self.bus_source == "generator" else 0.0
        if dt > 0 and gen_P > 0:
            g["fuel"] = max(0.0, g["fuel"] - gen_P * dt / 3600.0 * 0.27 / 1200.0 * 100)  # 1200 L tank, 0.27 L/kWh
        o["GEN-01"] = {"state": g["state"], "power_kw": gen_P,
                       "frequency_hz": 50.0 + (0.05 * self.rng.standard_normal() if g["state"] == "RUNNING" else 0.0) if g["state"] in ("RUNNING", "COOLDOWN") else 0.0,
                       "fuel_pct": g["fuel"], "run_s": g["run_s"]}
        Vbus = {"utility": 415.0 - 6.0 * lx, "generator": 412.0, "none": 0.0}[self.bus_source]
        o["SWG-01"] = {"state": {"utility": "ON_UTILITY", "generator": "ON_GENERATOR", "none": "DEAD_BUS"}[self.bus_source],
                       "bus_voltage_v": Vbus, "bus_current_a": P_bus * 1000 / (math.sqrt(3) * 415 * 0.95) if bus_ok else 0.0,
                       "frequency_hz": 50.0 if bus_ok else 0.0, "mech_load_kw": P_mech,
                       "source_code": {"none": 0, "utility": 1, "generator": 2}[self.bus_source]}

        # ------------------------------------------------------------------
        # Zones, pipes, facility KPIs
        # ------------------------------------------------------------------
        def rh(T):
            ps = 0.6112 * math.exp(17.62 * T / (243.12 + T))
            pw = ABS_HUMIDITY * 101.325 / (0.622 + ABS_HUMIDITY)
            return min(100.0, pw / ps * 100)
        o["ZONE-CA"] = {"state": "MONITORED", "temp_c": self.T_ca, "rh_pct": rh(self.T_ca)}
        o["ZONE-HA"] = {"state": "MONITORED", "temp_c": self.T_ha, "rh_pct": rh(self.T_ha)}
        area = math.pi * 0.05 ** 2
        o["PIPE-CHWS"] = {"state": "FLOWING" if self.q_chw > 0.1 else "NO_FLOW", "flow_ls": self.q_chw,
                          "temp_c": self.T_chws, "velocity_ms": self.q_chw / 1000 / area}
        o["PIPE-CHWR"] = {"state": "FLOWING" if self.q_chw > 0.1 else "NO_FLOW", "flow_ls": self.q_chw,
                          "temp_c": self.T_chwr, "velocity_ms": self.q_chw / 1000 / area}
        o["PIPE-CW"] = {"state": "FLOWING" if q_cw > 0.1 else "NO_FLOW", "flow_ls": q_cw,
                        "temp_c": T_cwe, "velocity_ms": q_cw / 1000 / (math.pi * 0.0625 ** 2)}
        P_loss = P_ups_loss + P_pdu_loss + tx_loss
        P_fac = P_it + P_cool + P_loss + P_light
        if dt > 0:
            self.energy_kwh += P_fac * dt / 3600.0
            self.it_energy_kwh += P_it * dt / 3600.0
        o["_facility"] = {
            "it_load_kw": P_it, "facility_power_kw": P_fac, "cooling_power_kw": P_cool,
            "elec_losses_kw": P_loss, "pue": P_fac / P_it if P_it > 1 else 0.0,
            "max_inlet_c": max(self.T_in.values()), "chws_c": self.T_chws, "chwr_c": self.T_chwr,
            "wetbulb_c": wb, "energy_kwh": self.energy_kwh, "it_energy_kwh": self.it_energy_kwh,
            "_coil_kw": Q_coils, "_chiller_kw": P_ch_tot, "_bus_source": self.bus_source,
            "_hour": self.hour_of_day(),
        }
        self._out = o

    # ======================================================================
    def truth(self) -> dict:
        return self._out

    def clone(self) -> "Plant":
        """Isolated copy for what-if execution (cannot disturb the live twin)."""
        c = deepcopy(self)
        return c

    def internal_params(self) -> dict:
        """Nominal (healthy) parameters exposed to the intelligence layer's
        physics-residual models. Faults are *not* exposed."""
        return {"pump_H0": 320.0, "pump_kp": 2.2, "pump_q_bep": 5.0, "pump_eta_bep": 0.72,
                "crah_m_max": 4.5, "hx_eps": 0.72, "tower_app_nom": 3.0, "chiller_cop_carnot_frac": 0.40,
                "bat_cap_ah": 60.0, "bat_r_ohm": 0.060, "chws_sp": self.sp["chws_c"]}
