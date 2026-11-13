"""TwinCore — composes plant (or external source), virtual instrumentation,
intelligence and alarms into one authoritative, sequenced snapshot.

A single snapshot object (with ``seq`` and ``sim_time_s``) is produced per
publish cycle and fanned out unchanged to the 3D frontend (WebSocket),
historian, flat tag API (Ignition) and OPC UA adapter.  That is the
mechanism that prevents inconsistent values between consumers (8A-F).
"""
from __future__ import annotations

import datetime as _dt
import time
from copy import deepcopy

from .alarms import AlarmManager
from .instrumentation import Instrumentation
from .intelligence import HealthEngine
from .plant import Plant
from .registry import REGISTRY_VERSION
from .workorders import WorkOrderManager

SCHEMA = "dcx.snapshot/1"
SIM_EPOCH = _dt.datetime(2026, 11, 9, 0, 0, 0)  # sim clock origin (local time)


class TwinCore:
    HEALTH_EVERY_S = 5.0

    def __init__(self, seed: int = 7, start_hour: float = 10.0, plant: Plant | None = None):
        self.plant = plant or Plant(seed=seed, start_hour=start_hour)
        self.instr = Instrumentation(seed + 4)
        self.health = HealthEngine(self.plant.internal_params())
        self.alarms = AlarmManager(lambda: self.plant.sp)
        self.seq = 0
        self.comm = {"plant": "OK", "ai": "OK", "historian": "OK", "opcua": "DISABLED"}
        self.source = {"id": "surrogate-01", "type": "surrogate", "model": Plant.MODEL_ID,
                       "model_version": Plant.MODEL_VERSION, "registry_version": REGISTRY_VERSION,
                       "label": "DATACORE-X reduced-order Python surrogate (stand-in for MATLAB/Simulink)"}
        self.mode = "LIVE"
        self._h, self._d = {}, {}
        self._last_health_t = -1e9
        self._measured = {}
        self.external_truth: dict | None = None
        # health-aware discrete action (same rule as the MATLAB PI-HA-EMPC supervisor):
        # change over a degrading duty pump when its HI < 25 or its RUL < 15 min
        self.ha_policy = {"enabled": True, "hi_below": 25.0, "rul_below_min": 15.0, "fault_codes": ["F01"]}
        self.ha_actions: list[dict] = []
        self._ha_done: set[str] = set()
        self.wo = WorkOrderManager(self.clock)
        self._refresh(force=True)

    def clock(self, t: float) -> str:
        return (SIM_EPOCH + _dt.timedelta(hours=self.plant.start_hour, seconds=t)).isoformat(timespec="seconds")

    def _health_policy(self, t: float):
        if not self.ha_policy.get("enabled") or self.external_truth is not None:
            return
        pumps = ("P-01", "P-02", "P-03")
        for p in pumps:
            h = self._h.get(p) or {}
            st = self._measured.get(p, {}).get("state")
            if p in self._ha_done and h.get("fault_code") is None and st == "RUNNING":
                self._ha_done.discard(p)            # repaired and back in service
            # act on bearing degradation only (as the MATLAB supervisor does): a changeover does not cure
            # cavitation (a system NPSH problem) and is not warranted for a slow efficiency loss
            if st != "RUNNING" or p in self._ha_done or h.get("fault_code") not in self.ha_policy["fault_codes"]:
                continue
            rul_min = None if h.get("rul_h") is None else 60.0 * h["rul_h"]
            trig_hi = h.get("hi", 100.0) < self.ha_policy["hi_below"]
            trig_rul = rul_min is not None and rul_min < self.ha_policy["rul_below_min"]
            if not (trig_hi or trig_rul):
                continue
            spare = [q for q in pumps if q != p and self._measured.get(q, {}).get("state") in ("STANDBY", "STOPPED")
                     and not self.plant.pump[q]["tripped"]]
            if not spare:
                continue
            ok, _ = self.plant.apply_command({"command": "pump_changeover", "asset": p, "value": spare[0]})
            if ok:
                why = (f"HI {h['hi']:.0f} < {self.ha_policy['hi_below']:.0f}" if trig_hi
                       else f"RUL {rul_min:.0f} min < {self.ha_policy['rul_below_min']:.0f} min")
                text = f"Health-aware changeover {p} -> {spare[0]} ({why}, fault {h.get('fault')})"
                self.plant._event("HEALTH_AWARE_CHANGEOVER", p, text)
                self.ha_actions.append({"asset": p, "t": round(t, 1), "clock": self.clock(t), "text": text})
                self._ha_done.add(p)

    # ------------------------------------------------------------------
    def _refresh(self, force=False):
        truth = self.plant.truth() if self.external_truth is None else self.external_truth
        if self.external_truth is None:
            self._measured = self.instr.measure(truth, self.plant)
        else:
            self._measured = Instrumentation.passthrough(truth.get("assets", {}))
        t = self.sim_time
        if force or t - self._last_health_t >= self.HEALTH_EVERY_S:
            if self.comm.get("ai") == "OK":
                self._h, self._d = self.health.update(self._measured, t)
                self._health_policy(t)
            self.alarms.evaluate(self._measured, self._h, self._d, self.comm, t)
            if self.external_truth is None:
                self.wo.update(t, self._h, self._measured, self.ha_actions, self.plant.replay_status())
            self._last_health_t = t

    @property
    def sim_time(self) -> float:
        if self.external_truth is not None:
            return float(self.external_truth.get("sim_time_s", 0.0))
        return self.plant.t

    def advance(self, sim_seconds: float, dt: float = 1.0):
        n = int(round(sim_seconds / dt))
        for _ in range(n):
            self.plant.step(dt)
            if self.plant.t - self._last_health_t >= self.HEALTH_EVERY_S:
                self._refresh(force=True)
        self._refresh()

    def ingest_external(self, doc: dict):
        self.external_truth = doc
        self.source = {"id": doc.get("source_id", "matlab-01"), "type": "external",
                       "model": doc.get("model", "MATLAB/Simulink"), "model_version": doc.get("model_version", "?"),
                       "registry_version": REGISTRY_VERSION, "label": "MATLAB/Simulink via DATACORE-X bridge"}
        self._refresh(force=True)

    # ------------------------------------------------------------------
    def snapshot(self, compact: bool = False) -> dict:
        self.seq += 1
        t = self.sim_time
        truth = self.plant.truth() if self.external_truth is None else self.external_truth.get("assets", {})
        fac_src = truth.get("_facility", {}) if self.external_truth is None else self.external_truth.get("facility", {})
        fac = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in fac_src.items() if not k.startswith("_")}
        assets = {}
        for aid, rec in self._measured.items():
            a = {"state": rec["state"], "v": rec["v"]}
            if rec.get("q"):
                a["q"] = rec["q"]
            if aid in self._h:
                h = self._h[aid]
                a["health"] = h if not compact else {k: h[k] for k in ("hi", "fault", "fault_code", "prob", "rul_h",
                                                                        "rul_lo_h", "rul_hi_h", "confidence", "recommendation")}
            if aid in self._d:
                a["diag"] = self._d[aid]
            assets[aid] = a
        snap = {
            "schema": SCHEMA, "seq": self.seq, "sim_time_s": round(t, 1),
            "sim_clock": (SIM_EPOCH + _dt.timedelta(hours=self.plant.start_hour, seconds=t)).isoformat(timespec="seconds"),
            "wall_ts": time.time(), "mode": self.mode, "source": self._source_now(), "facility": fac,
            "setpoints": dict(self.plant.sp), "assets": assets, "alarms": self.alarms.active(),
            "faults_injected": [f.to_dict(t) for f in self.plant.faults if f.sev(t) > 0 or f.stage(t) == "pending"],
            "comm": dict(self.comm),
        }
        rp = self.plant.replay_status() if self.external_truth is None else []
        if rp:
            snap["replay"] = rp
        wl = self.wo.listing()
        snap["workorders"] = {"open": sum(1 for w in wl if w["status"] != "CLOSED"),
                              "items": [{k: w.get(k) for k in ("wo_id", "asset", "title", "priority", "status", "health_index",
                                                               "rul_h", "due_clock")} for w in wl[:10]]}
        if not compact:
            snap["events"] = self.plant.events[-15:]
            snap["airflow"] = {"bus_source": fac_src.get("_bus_source", "utility")}
        return snap

    def _source_now(self) -> dict:
        src = dict(self.source)
        rp = self.plant.replay_status() if self.external_truth is None else []
        if rp:
            src["type"] = f"{src['type']} + replay"
            src["label"] = (f"{src['label']}; {rp[0]['asset']} bearing vibration replayed from measured data: "
                            f"{rp[0]['title']}")
        return src

    def truth_record(self) -> dict:
        """Ground truth (for historian / evaluation only — never shown as measured)."""
        o = self.plant.truth()
        return {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                for k, v in o.items()}

    def clone(self) -> "TwinCore":
        return deepcopy(self)
