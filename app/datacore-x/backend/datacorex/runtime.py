"""Live runtime: paces the twin, publishes one sequenced snapshot per cycle to
every consumer, processes supervisory commands with acknowledgement, runs
isolated what-if scenarios, and exposes communication-health diagnostics."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .core import TwinCore
from .historian import Historian
from .registry import IGN_FOLDER, asset_index, registry_document
from .scenarios import ScenarioManager, apply_scenario, run_isolated

ROLE_RANK = {"viewer": 0, "operator": 1, "engineer": 2}
COMMAND_ROLE = {
    "set_setpoint": "engineer", "maintenance_complete": "engineer",
    "pump_start": "operator", "pump_stop": "operator", "pump_changeover": "operator",
    "crah_enable": "operator", "crah_disable": "operator", "chiller_lead": "operator", "reset_trip": "operator",
}


class LiveRuntime:
    def __init__(self, seed: int = 7, speed: float = 1.0, publish_hz: float = 1.0,
                 historian_path: str | None = None, warmup_s: float = 600):
        self.lock = threading.RLock()
        self.core = TwinCore(seed=seed)
        self.core.advance(warmup_s)  # settle controllers before first publish
        self.speed = speed
        self.publish_hz = publish_hz
        self.hist = Historian(historian_path)
        self.scen = ScenarioManager()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.clients: set = set()
        self.latest: dict | None = None
        self.commands: dict[str, dict] = {}
        self._confirm: list[tuple[str, callable, float]] = []
        self.comm_loss_until = 0.0
        self.paused = False
        self.stats = {"started_wall": time.time(), "ticks": 0, "last_tick_ms": 0.0, "dropped_sends": 0}
        self.opcua = None
        self.external_mode = os.environ.get("DCX_SOURCE", "surrogate") == "external"
        self.external_last_wall = 0.0
        self.external_cmd_queue: list[dict] = []
        self.reg = asset_index()
        self.publish()

    # ------------------------------------------------------------------
    def tick(self):
        t0 = time.perf_counter()
        with self.lock:
            if not self.paused and not self.external_mode:
                self.core.advance(self.speed / self.publish_hz)
            if self.external_mode:
                stale = time.time() - self.external_last_wall > 5.0
                self.core.comm["plant"] = "STALE" if stale else "OK"
            self.core.comm["historian"] = "OK" if self.hist.ok else "ERROR"
            self._check_confirmations()
            snap = self.publish()
        self.stats["ticks"] += 1
        self.stats["last_tick_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return snap

    def publish(self):
        snap = self.core.snapshot()
        snap["commands"] = sorted(self.commands.values(), key=lambda c: -c["received_wall"])[:12]
        snap["runtime"] = {"speed": self.speed, "publish_hz": self.publish_hz, "paused": self.paused,
                           "external_mode": self.external_mode}
        truth = self.core.truth_record() if self.core.external_truth is None else None
        self.hist.write(snap, truth)
        self.latest = snap
        if self.opcua is not None:
            try:
                self.opcua.publish(snap)
                self.core.comm["opcua"] = "OK"
            except Exception:  # pragma: no cover
                self.core.comm["opcua"] = "ERROR"
        return snap

    @property
    def comm_loss_active(self):
        return time.time() < self.comm_loss_until

    # ------------------------------------------------------------------
    # Commands with acknowledgement
    # ------------------------------------------------------------------
    def submit_command(self, body: dict, user: str, role: str) -> dict:
        cid = body.get("client_cmd_id") or ("CMD-" + uuid.uuid4().hex[:8])
        rec = {"id": cid, "command": body.get("command"), "asset": body.get("asset"), "name": body.get("name"),
               "value": body.get("value"), "user": user, "role": role, "received_wall": time.time(),
               "status": "RECEIVED", "reason": None, "seq_received": self.latest["seq"] if self.latest else None,
               "seq_confirmed": None}
        self.commands[cid] = rec
        need = COMMAND_ROLE.get(rec["command"], "engineer")
        if ROLE_RANK.get(role, -1) < ROLE_RANK[need]:
            rec.update(status="REJECTED", reason=f"role '{role}' not permitted (requires {need})")
        elif self.external_mode:
            rec.update(status="FORWARDED", reason="queued for external simulation (MATLAB bridge)")
            self.external_cmd_queue.append(rec)
        else:
            with self.lock:
                ok, reason = self.core.plant.apply_command(body)
            rec.update(status="ACCEPTED" if ok else "REJECTED", reason=reason)
            if ok:
                pred = self._predicate(body)
                self._confirm.append((cid, pred, time.time() + 15.0))
        self.hist.log_command(rec)
        self._trim_commands()
        return rec

    def _trim_commands(self):
        if len(self.commands) > 200:
            for k in sorted(self.commands, key=lambda k: self.commands[k]["received_wall"])[:50]:
                self.commands.pop(k, None)

    def _predicate(self, b):
        c, a = b.get("command"), b.get("asset")
        st = lambda x: self.core._measured.get(x, {}).get("state")
        if c == "pump_start":
            return lambda: st(a) == "RUNNING"
        if c == "pump_stop":
            return lambda: st(a) in ("STOPPED", "STANDBY")
        if c == "pump_changeover":
            return lambda: st(b.get("value")) == "RUNNING" and st(a) in ("STOPPED", "STANDBY")
        if c == "crah_disable":
            return lambda: st(a) == "STANDBY"
        if c == "crah_enable":
            return lambda: st(a) == "RUNNING"
        if c == "set_setpoint":
            return lambda: abs(self.core.plant.sp[b["name"]] - float(b["value"])) < 1e-9
        if c in ("maintenance_complete", "reset_trip"):
            return lambda: st(a) != "TRIPPED"
        return lambda: True

    def _check_confirmations(self):
        keep = []
        for cid, pred, deadline in self._confirm:
            rec = self.commands.get(cid)
            if rec is None:
                continue
            try:
                ok = pred()
            except Exception:
                ok = False
            if ok:
                rec.update(status="EXECUTED", seq_confirmed=(self.latest["seq"] + 1) if self.latest else None,
                           reason=rec["reason"] + " — confirmed by process feedback")
                self.hist.log_command(rec)
            elif time.time() > deadline:
                rec.update(status="TIMEOUT", reason="no confirming process feedback within 15 s")
                self.hist.log_command(rec)
            else:
                keep.append((cid, pred, deadline))
        self._confirm = keep

    # ------------------------------------------------------------------
    # Scenarios
    # ------------------------------------------------------------------
    def approve_and_run(self, rid: str, user: str) -> str:
        run_id = self.scen.new_run(rid, user)
        req = self.scen.requests[rid]
        with self.lock:
            snapshot_core = self.core.clone()
        if req.get("clean_start"):
            # what-if from a fault-free copy: only the isolated copy is changed, never the live plant
            pl = snapshot_core.plant
            pl.clear_faults(None)
            for d in (pl.pump, pl.crah, pl.chiller):
                for v in d.values():
                    v["tripped"] = False
        run = self.scen.runs[run_id]

        def job():
            run["status"] = "RUNNING"
            try:
                res = run_isolated(snapshot_core, req["scenario_id"], req["params"], req["horizon_s"],
                                   progress=lambda p: run.__setitem__("progress", round(p, 3)))
                run.update(status="COMPLETED", result=res, progress=1.0)
                req["status"] = "EXECUTED"
            except Exception as e:  # pragma: no cover
                run.update(status="FAILED", error=repr(e))
                req["status"] = "FAILED"
        run["future"] = self.pool.submit(job)
        return run_id

    def apply_to_live(self, run_id: str, user: str):
        run = self.scen.runs[run_id]
        if run["status"] != "COMPLETED":
            raise ValueError("run not completed")
        req = self.scen.requests[run["request_id"]]
        with self.lock:
            apply_scenario(self.core, req["scenario_id"], req["params"], tag=":live")
        run["applied_to_live"] = True
        self.scen._log("APPLY_LIVE", run_id=run_id, user=user)

    def clear_live_faults(self, user):
        with self.lock:
            self.core.plant.clear_faults(None)
            for d in (self.core.plant.pump, self.core.plant.crah, self.core.plant.chiller):
                for v in d.values():
                    v["tripped"] = False
        self.scen._log("CLEAR_LIVE", user=user)

    # ------------------------------------------------------------------
    # Flat tag view for Ignition (same seq as every other consumer)
    # ------------------------------------------------------------------
    def flat_tags(self, snap=None) -> dict:
        snap = snap or self.latest
        tags = {}
        for aid, a in snap["assets"].items():
            reg = self.reg.get(aid)
            if not reg:
                continue
            base = f"[DATACORE_X]{IGN_FOLDER.get(reg['type'], 'Misc')}/{aid.replace('-', '_')}"
            q = a.get("q", {})
            for tg in reg["tags"]:
                tags[tg["path"]] = {"v": a["v"].get(tg["key"]), "unit": tg["unit"],
                                    "q": q.get(tg["key"], "GOOD"), "ts": snap["wall_ts"]}
            tags[f"{base}/State"] = {"v": a["state"], "unit": "", "q": "GOOD", "ts": snap["wall_ts"]}
            if "health" in a:
                for k in ("hi", "prob", "rul_h"):
                    tags[f"{base}/Health/{k}"] = {"v": a["health"][k], "unit": "", "q": "GOOD", "ts": snap["wall_ts"]}
                tags[f"{base}/Health/fault"] = {"v": a["health"]["fault"], "unit": "", "q": "GOOD", "ts": snap["wall_ts"]}
        for k, v in snap["facility"].items():
            tags[f"[DATACORE_X]Facility/{k}"] = {"v": v, "unit": "", "q": "GOOD", "ts": snap["wall_ts"]}
        sysv = {"Seq": snap["seq"], "Sim_Time_s": snap["sim_time_s"], "Sim_Clock": snap["sim_clock"],
                "Source": snap["source"]["type"], **{f"Comm_{k}": v for k, v in snap["comm"].items()}}
        for k, v in sysv.items():
            tags[f"[DATACORE_X]System/{k}"] = {"v": v, "unit": "", "q": "GOOD", "ts": snap["wall_ts"]}
        return {"seq": snap["seq"], "sim_time_s": snap["sim_time_s"], "tags": tags}

    # ------------------------------------------------------------------
    async def run_forever(self):
        period = 1.0 / self.publish_hz
        nxt = time.monotonic()
        while True:
            nxt += period
            snap = await asyncio.to_thread(self.tick)
            if not self.comm_loss_active:
                msg = json.dumps({"type": "snapshot", "data": snap}, separators=(",", ":"))
                dead = []
                for ws in list(self.clients):
                    try:
                        await asyncio.wait_for(ws.send_text(msg), timeout=2.0)
                    except Exception:
                        dead.append(ws)
                        self.stats["dropped_sends"] += 1
                for ws in dead:
                    self.clients.discard(ws)
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))

    def registry(self):
        return registry_document()
