"""What-if scenario catalogue and isolated executor (8A-D, blueprint §5.3).

Workflow: REQUEST (operator) -> PENDING_APPROVAL -> APPROVED (operator /
engineer) -> RUNNING (isolated deep copy of the live twin: baseline branch
and scenario branch from the identical initial state) -> COMPLETED with
frames + before/after KPI comparison.  Optionally an engineer may APPLY the
approved scenario to the live twin.  The live simulation is never touched by
a what-if run.
"""
from __future__ import annotations

import time
import uuid

from .core import TwinCore

RACK_IDS = [f"R-{i:02d}" for i in range(1, 9)]

CATALOGUE = [
    {"id": "S01", "title": "Increase IT workload", "fault": None,
     "params": {"increase_pct": {"type": "number", "min": 5, "max": 60, "default": 40, "unit": "%"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 300, "unit": "s"}},
     "description": "Scales all rack utilisation; cooling and electrical plant must respond."},
    {"id": "S02", "title": "Simulate rack overheating", "fault": "rack hotspot",
     "params": {"rack": {"type": "enum", "options": RACK_IDS, "default": "R-06"},
                "extra_kw": {"type": "number", "min": 1, "max": 10, "default": 6, "unit": "kW"},
                "ramp_s": {"type": "number", "min": 0, "max": 900, "default": 120, "unit": "s"}},
     "description": "Adds load to one rack and introduces local exhaust short-circuit (missing blanking panels)."},
    {"id": "S03", "title": "Reduce pump efficiency", "fault": "PUMP_EFF",
     "params": {"pump": {"type": "enum", "options": ["P-01", "P-02", "P-03"], "default": "P-01"},
                "drop_pct": {"type": "number", "min": 5, "max": 40, "default": 25, "unit": "%"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 600, "unit": "s"}},
     "description": "Impeller wear: hydraulic efficiency reduction at unchanged head."},
    {"id": "S04", "title": "Introduce pump cavitation", "fault": "F02",
     "params": {"pump": {"type": "enum", "options": ["P-01", "P-02", "P-03"], "default": "P-01"},
                "severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.8, "unit": "-"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 600, "unit": "s"}},
     "description": "Head loss and broadband vibration from insufficient NPSH."},
    {"id": "S05", "title": "Disable a CRAH unit", "fault": "trip",
     "params": {"crah": {"type": "enum", "options": ["CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04"], "default": "CRAH-02"}},
     "description": "CRAH fan trip; remaining units must absorb airflow and coil duty."},
    {"id": "S06", "title": "Degrade chiller performance", "fault": "F06",
     "params": {"chiller": {"type": "enum", "options": ["CH-01", "CH-02"], "default": "CH-01"},
                "severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.8, "unit": "-"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 900, "unit": "s"}},
     "description": "COP (up to -30 %) and capacity (up to -25 %) degradation."},
    {"id": "S07", "title": "Simulate utility power failure", "fault": "utility",
     "params": {"duration_s": {"type": "number", "min": 30, "max": 1800, "default": 600, "unit": "s"}},
     "description": "Grid loss: UPS ride-through, generator start, ATS transfer, mechanical restart, chiller anti-recycle."},
    {"id": "S08", "title": "Switch to UPS (battery) operation", "fault": None,
     "params": {"scope": {"type": "enum", "options": ["DCX", "UPS-A", "UPS-B"], "default": "DCX"},
                "duration_s": {"type": "number", "min": 30, "max": 1800, "default": 900, "unit": "s"}},
     "description": "Planned transfer of UPS to battery (discharge test) with utility healthy."},
    {"id": "S09", "title": "Introduce battery degradation", "fault": "F08",
     "params": {"battery": {"type": "enum", "options": ["BAT-A", "BAT-B"], "default": "BAT-A"},
                "severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.8, "unit": "-"},
                "discharge_test": {"type": "bool", "default": True}},
     "description": "Capacity loss and internal-resistance rise; optional discharge test reveals reduced runtime."},
    {"id": "S10", "title": "Change workload placement", "fault": None,
     "params": {"strategy": {"type": "enum", "options": ["concentrate_row_a", "concentrate_edges", "spread_even"],
                             "default": "concentrate_row_a"}},
     "description": "Migrates workload between racks at constant total utilisation."},
    {"id": "S11", "title": "Pump bearing degradation (flagship)", "fault": "F01",
     "params": {"pump": {"type": "enum", "options": ["P-01", "P-02", "P-03"], "default": "P-01"},
                "severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.9, "unit": "-"},
                "ramp_s": {"type": "number", "min": 60, "max": 3600, "default": 1200, "unit": "s"}},
     "description": "Developing bearing fault -> vibration/current signatures -> detection -> changeover decision."},
    {"id": "S12", "title": "Heat-exchanger fouling", "fault": "F05",
     "params": {"severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.8, "unit": "-"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 600, "unit": "s"}},
     "description": "Economiser effectiveness loss; more load transferred to chiller."},
    {"id": "S13", "title": "Cooling-tower degradation", "fault": "F07",
     "params": {"tower": {"type": "enum", "options": ["CT-01", "CT-02"], "default": "CT-01"},
                "severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.8, "unit": "-"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 600, "unit": "s"}},
     "description": "Approach increase from fill fouling / fan drive issues."},
    {"id": "S14", "title": "Rack inlet sensor drift", "fault": "F09",
     "params": {"rack": {"type": "enum", "options": RACK_IDS, "default": "R-03"},
                "bias_k": {"type": "number", "min": 1, "max": 8, "default": 4, "unit": "K"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 300, "unit": "s"}},
     "description": "Measurement bias only — physical temperature unchanged; twin residual should flag it."},
    {"id": "S15", "title": "CRAH fan imbalance", "fault": "F03",
     "params": {"crah": {"type": "enum", "options": ["CRAH-01", "CRAH-02", "CRAH-03", "CRAH-04"], "default": "CRAH-01"},
                "severity": {"type": "number", "min": 0.1, "max": 1.0, "default": 0.8, "unit": "-"},
                "ramp_s": {"type": "number", "min": 0, "max": 1800, "default": 600, "unit": "s"}},
     "description": "1x running-speed vibration growth."},
    {"id": "S16", "title": "Cooling pump failure (trip)", "fault": "F10",
     "params": {"pump": {"type": "enum", "options": ["P-01", "P-02", "P-03"], "default": "P-01"}},
     "description": "Duty pump trip; PLC redundancy logic should start the standby pump."},
    {"id": "S17", "title": "Real bearing replay (measured run-to-failure data)", "fault": "F01",
     "params": {"pump": {"type": "enum", "options": ["P-01", "P-02", "P-03"], "default": "P-01"},
                "profile": {"type": "enum", "options": ["FEMTO-B1_1", "FEMTO-B1_3"], "default": "FEMTO-B1_1"},
                "compress": {"type": "number", "min": 1, "max": 40, "default": 8, "unit": "x"}},
     "description": "Replays the measured vibration of a real bearing (FEMTO/PRONOSTIA, IEEE PHM 2012) from new to "
                    "failure on the pump's vibration sensor, time-compressed. The bearing ages only while the pump "
                    "runs; if it reaches its recorded failure while running, the pump trips."},
]
CAT = {s["id"]: s for s in CATALOGUE}

PLACEMENT = {
    "concentrate_row_a": {r: (1.7 if i < 4 else 0.3) for i, r in enumerate(RACK_IDS)},
    "concentrate_edges": {r: (1.8 if r in ("R-01", "R-04", "R-05", "R-08") else 0.2) for r in RACK_IDS},
    "spread_even": {r: 1.0 for r in RACK_IDS},
}


def resolve_params(sid: str, params: dict | None) -> dict:
    spec = CAT[sid]["params"]
    out = {}
    params = params or {}
    for k, d in spec.items():
        v = params.get(k, d["default"])
        if d["type"] == "number":
            v = float(v)
            if not d["min"] <= v <= d["max"]:
                raise ValueError(f"{k}={v} outside [{d['min']}, {d['max']}]")
        elif d["type"] == "enum":
            if v not in d["options"]:
                raise ValueError(f"{k}={v} not in {d['options']}")
        elif d["type"] == "bool":
            v = bool(v)
        out[k] = v
    unknown = set(params) - set(spec)
    if unknown:
        raise ValueError(f"unknown parameters {sorted(unknown)}")
    return out


def apply_scenario(core: TwinCore, sid: str, p: dict, tag: str = ""):
    pl = core.plant
    fid = lambda k: f"{sid}{tag}:{k}"
    if sid == "S01":
        pl.inject("it_load_increase", "DCX", p["increase_pct"] / 100, ramp_s=p["ramp_s"], fault_id=fid("it"))
    elif sid == "S02":
        pl.inject("rack_overheat", p["rack"], 1.0, ramp_s=p["ramp_s"], fault_id=fid("rack"), extra_kw=p["extra_kw"])
    elif sid == "S03":
        pl.inject("pump_efficiency", p["pump"], 1.0, ramp_s=p["ramp_s"], fault_id=fid("eff"), drop=p["drop_pct"] / 100)
    elif sid == "S04":
        pl.inject("pump_cavitation", p["pump"], p["severity"], ramp_s=p["ramp_s"], fault_id=fid("cav"))
    elif sid == "S05":
        pl.inject("crah_trip", p["crah"], 1.0, fault_id=fid("crah"))
    elif sid == "S06":
        pl.inject("chiller_degradation", p["chiller"], p["severity"], ramp_s=p["ramp_s"], fault_id=fid("ch"))
    elif sid == "S07":
        pl.inject("utility_failure", "TX-01", 1.0, duration_s=p["duration_s"], fault_id=fid("grid"))
    elif sid == "S08":
        pl.inject("ups_battery_mode", p["scope"], 1.0, duration_s=p["duration_s"], fault_id=fid("ups"))
    elif sid == "S09":
        pl.inject("battery_degradation", p["battery"], p["severity"], ramp_s=120, fault_id=fid("bat"))
        if p["discharge_test"]:
            pl.inject("ups_battery_mode", "UPS-A" if p["battery"] == "BAT-A" else "UPS-B", 1.0,
                      onset_s=180, duration_s=1200, fault_id=fid("test"))
    elif sid == "S10":
        pl.inject("workload_placement", "DCX", 1.0, fault_id=fid("place"), weights=PLACEMENT[p["strategy"]])
    elif sid == "S11":
        pl.inject("pump_bearing", p["pump"], p["severity"], ramp_s=p["ramp_s"], fault_id=fid("brg"))
    elif sid == "S12":
        pl.inject("hx_fouling", "HX-01", p["severity"], ramp_s=p["ramp_s"], fault_id=fid("hx"))
    elif sid == "S13":
        pl.inject("tower_degradation", p["tower"], p["severity"], ramp_s=p["ramp_s"], fault_id=fid("ct"))
    elif sid == "S14":
        pl.inject("sensor_drift", p["rack"], 1.0, ramp_s=p["ramp_s"], fault_id=fid("drift"), tag="inlet_c", bias=p["bias_k"])
    elif sid == "S15":
        pl.inject("fan_imbalance", p["crah"], p["severity"], ramp_s=p["ramp_s"], fault_id=fid("imb"))
    elif sid == "S16":
        pl.inject("pump_trip", p["pump"], 1.0, fault_id=fid("trip"))
    elif sid == "S17":
        pl.inject("pump_bearing_replay", p["pump"], 1.0, fault_id=fid("replay"),
                  profile=p["profile"], compress=float(p["compress"]))
    else:
        raise KeyError(sid)


def compact_frame(snap: dict) -> dict:
    return {"t": snap["sim_time_s"], "clock": snap["sim_clock"], "facility": snap["facility"],
            "assets": snap["assets"], "alarms": snap["alarms"], "faults_injected": snap["faults_injected"],
            "source": {"type": snap["source"].get("type")}, "workorders": {"open": snap.get("workorders", {}).get("open", 0)},
            **({"replay": snap["replay"]} if snap.get("replay") else {})}


def kpis(frames: list[dict], dt: float) -> dict:
    f0, f1 = frames[0]["facility"], frames[-1]["facility"]
    max_in = [fr["facility"]["max_inlet_c"] for fr in frames]
    cool = sum(fr["facility"]["cooling_power_kw"] for fr in frames[1:]) * dt / 3600
    E = f1["energy_kwh"] - f0["energy_kwh"]
    Eit = f1["it_energy_kwh"] - f0["it_energy_kwh"]
    socs = [min(fr["assets"].get("BAT-A", {}).get("v", {}).get("soc_pct", 100) or 100,
                fr["assets"].get("BAT-B", {}).get("v", {}).get("soc_pct", 100) or 100) for fr in frames]
    chws = [fr["facility"]["chws_c"] for fr in frames]
    health_end = {a: v["health"]["hi"] for a, v in frames[-1]["assets"].items() if "health" in v}
    health_min = {}
    for fr in frames:
        for a, v in fr["assets"].items():
            if "health" in v:
                health_min[a] = min(health_min.get(a, 100.0), v["health"]["hi"])
    worst = min(health_min.items(), key=lambda kv: kv[1]) if health_min else ("-", 100)
    return {
        "peak_max_inlet_c": round(max(max_in), 2),
        "time_inlet_above_27_s": round(sum(dt for x in max_in if x > 27.0), 0),
        "facility_energy_kwh": round(E, 2), "it_energy_kwh": round(Eit, 2),
        "cooling_energy_kwh": round(cool, 2),
        "energy_pue": round(E / Eit, 3) if Eit > 0 else None,
        "peak_chws_c": round(max(chws), 2), "min_battery_soc_pct": round(min(socs), 1),
        "worst_asset": worst[0], "worst_asset_min_hi": round(worst[1], 1),
        "peak_active_alarms": max(len(fr["alarms"]) for fr in frames),
        "critical_alarms": len({a["id"] for fr in frames for a in fr["alarms"] if a["priority"] == "CRITICAL"}),
        "health_end": health_end, "health_min": {k: round(v, 1) for k, v in health_min.items()},
    }


def compare(kb: dict, ks: dict) -> list[dict]:
    rows = []
    spec = [("peak_max_inlet_c", "Peak rack inlet", "°C", "lower"),
            ("time_inlet_above_27_s", "Time any inlet > 27 °C", "s", "lower"),
            ("facility_energy_kwh", "Facility energy", "kWh", "lower"),
            ("cooling_energy_kwh", "Cooling energy", "kWh", "lower"),
            ("it_energy_kwh", "IT energy served", "kWh", "info"),
            ("energy_pue", "Energy-weighted PUE", "-", "lower"),
            ("peak_chws_c", "Peak CHW supply", "°C", "lower"),
            ("min_battery_soc_pct", "Minimum battery SoC", "%", "higher"),
            ("worst_asset_min_hi", "Worst asset Health Index", "-", "higher"),
            ("peak_active_alarms", "Peak active alarms", "-", "lower"),
            ("critical_alarms", "Critical alarms raised", "-", "lower")]
    for k, label, unit, better in spec:
        b, s = kb.get(k), ks.get(k)
        d = None if (b is None or s is None) else round(s - b, 3)
        worse = None
        if d is not None and better != "info" and abs(d) > 1e-6:
            worse = (d > 0) if better == "lower" else (d < 0)
        rows.append({"key": k, "label": label, "unit": unit, "baseline": b, "scenario": s, "delta": d, "worse": worse})
    rows.append({"key": "worst_asset", "label": "Worst asset", "unit": "", "baseline": kb["worst_asset"],
                 "scenario": ks["worst_asset"], "delta": None, "worse": None})
    return rows


def state_changes(fb: dict, fs: dict) -> list[dict]:
    out = []
    for a, v in fs["assets"].items():
        sb = fb["assets"].get(a, {}).get("state")
        if sb != v.get("state"):
            out.append({"asset": a, "baseline": sb, "scenario": v.get("state")})
    return out


def run_isolated(live: TwinCore, sid: str, params: dict, horizon_s: float = 1800, frame_every_s: float = 10,
                 progress=None) -> dict:
    t_wall = time.time()
    base = live.clone()
    scen = live.clone()
    for c in (base, scen):
        c.mode = "SCENARIO"
        c.source = dict(c.source, label=c.source["label"] + " — isolated what-if instance")
    apply_scenario(scen, sid, params, tag=":whatif")
    fb, fs = [compact_frame(base.snapshot(compact=True))], [compact_frame(scen.snapshot(compact=True))]
    n = int(horizon_s / frame_every_s)
    for i in range(n):
        base.advance(frame_every_s)
        scen.advance(frame_every_s)
        fb.append(compact_frame(base.snapshot(compact=True)))
        fs.append(compact_frame(scen.snapshot(compact=True)))
        if progress and i % 10 == 0:
            progress((i + 1) / n)
    kb, ks = kpis(fb, frame_every_s), kpis(fs, frame_every_s)
    return {"scenario_id": sid, "params": params, "horizon_s": horizon_s, "frame_every_s": frame_every_s,
            "start_sim_time_s": live.sim_time, "wall_runtime_s": round(time.time() - t_wall, 2),
            "kpi_baseline": kb, "kpi_scenario": ks, "comparison": compare(kb, ks),
            "state_changes_end": state_changes(fb[-1], fs[-1]),
            "frames": {"baseline": fb, "scenario": fs}}


class ScenarioManager:
    def __init__(self):
        self.requests: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.audit: list[dict] = []

    def _log(self, what, **kw):
        self.audit.append({"wall_ts": time.time(), "event": what, **kw})
        self.audit = self.audit[-500:]

    def request(self, sid, params, user, role, horizon_s=1800, clean_start=False):
        if sid not in CAT:
            raise KeyError(f"unknown scenario {sid}")
        p = resolve_params(sid, params)
        if not 60 <= float(horizon_s) <= 7200:
            raise ValueError("horizon_s must be within [60, 7200]")
        rid = "REQ-" + uuid.uuid4().hex[:8]
        r = {"request_id": rid, "scenario_id": sid, "title": CAT[sid]["title"], "params": p,
             "horizon_s": float(horizon_s), "clean_start": bool(clean_start), "status": "PENDING_APPROVAL", "requested_by": user,
             "requested_role": role, "requested_at": time.time(), "approved_by": None, "run_id": None,
             "description": CAT[sid]["description"]}
        self.requests[rid] = r
        self._log("REQUEST", request_id=rid, user=user, scenario=sid)
        return r

    def new_run(self, rid, user):
        r = self.requests[rid]
        if r["status"] != "PENDING_APPROVAL":
            raise ValueError(f"request is {r['status']}")
        run_id = "RUN-" + uuid.uuid4().hex[:8]
        r.update(status="APPROVED", approved_by=user, approved_at=time.time(), run_id=run_id)
        self.runs[run_id] = {"run_id": run_id, "request_id": rid, "status": "QUEUED", "progress": 0.0, "result": None,
                             "error": None, "applied_to_live": False}
        self._log("APPROVE", request_id=rid, run_id=run_id, user=user)
        return run_id

    def reject(self, rid, user, reason=""):
        r = self.requests[rid]
        if r["status"] != "PENDING_APPROVAL":
            raise ValueError(f"request is {r['status']}")
        r.update(status="REJECTED", approved_by=user, reason=reason)
        self._log("REJECT", request_id=rid, user=user, reason=reason)
        return r
