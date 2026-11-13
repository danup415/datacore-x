"""Record a replay dataset from the *actual* surrogate twin for the standalone
3D demo (no backend required).  Every value in the file was produced by the
same TwinCore code path the live service uses; the demo labels its data
source as this recorded run.

    python -m datacorex.tools.record_replay --out ../dist/replay.json

Encoding is columnar (asset -> key -> array) to keep the file small.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ..core import TwinCore
from ..registry import registry_document
from ..scenarios import CATALOGUE, apply_scenario, compare, kpis, resolve_params, state_changes, compact_frame

HEALTH_KEYS = ("hi", "prob", "rul_h", "rul_lo_h", "rul_hi_h", "confidence")


class Encoder:
    def __init__(self):
        self.strings: list[str] = []
        self.sidx: dict[str, int] = {}

    def s(self, x):
        x = "" if x is None else str(x)
        if x not in self.sidx:
            self.sidx[x] = len(self.strings)
            self.strings.append(x)
        return self.sidx[x]

    def encode(self, frames: list[dict]) -> dict:
        out = {"t": [f["t"] if "t" in f else f["sim_time_s"] for f in frames],
               "clock": [self.s(f.get("clock") or f.get("sim_clock")) for f in frames],
               "facility": {}, "values": {}, "states": {}, "health": {}, "diag": {}, "alarms": [], "faults": []}
        for k in frames[0]["facility"]:
            out["facility"][k] = [f["facility"].get(k) for f in frames]
        for aid, a0 in frames[0]["assets"].items():
            out["states"][aid] = [self.s(f["assets"][aid]["state"]) for f in frames]
            out["values"][aid] = {k: [f["assets"][aid]["v"].get(k) for f in frames] for k in a0["v"]}
            qs = [f["assets"][aid].get("q") for f in frames]
            if any(qs):
                out.setdefault("quality", {})[aid] = [self.s(json.dumps(q)) if q else 0 for q in qs]
            if "health" in a0:
                h = {k: [f["assets"][aid]["health"].get(k) for f in frames] for k in HEALTH_KEYS}
                h["fault"] = [self.s(f["assets"][aid]["health"].get("fault")) for f in frames]
                h["fault_code"] = [self.s(f["assets"][aid]["health"].get("fault_code")) for f in frames]
                h["recommendation"] = [self.s(f["assets"][aid]["health"].get("recommendation")) for f in frames]
                out["health"][aid] = h
            if "diag" in a0:
                ds = [f["assets"][aid].get("diag", {}) for f in frames]
                out["diag"][aid] = {k: [d.get(k) for d in ds] for k in ("twin_inlet_est_c", "residual_k", "delta_t_k", "model_confidence")}
                out["diag"][aid]["finding"] = [self.s(d.get("finding")) for d in ds]
        for f in frames:
            out["alarms"].append(self.s(json.dumps([{k: a[k] for k in ("id", "priority", "asset", "text", "state", "t_active")}
                                                     for a in f["alarms"]])))
            out["faults"].append(self.s(json.dumps([{k: x[k] for k in ("fault_id", "kind", "asset", "severity_now", "stage")}
                                                     for x in f["faults_injected"]])))
        return out


def run_branch(core: TwinCore, horizon: float, every: float):
    frames = [compact_frame(core.snapshot(compact=True))]
    for _ in range(int(horizon / every)):
        core.advance(every)
        frames.append(compact_frame(core.snapshot(compact=True)))
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/replay.json")
    ap.add_argument("--live-minutes", type=float, default=30)
    ap.add_argument("--live-every", type=float, default=3)
    ap.add_argument("--horizon", type=float, default=1800)
    ap.add_argument("--every", type=float, default=30)
    a = ap.parse_args()
    t0 = time.time()
    enc = Encoder()
    core = TwinCore(seed=7)
    core.advance(900)
    start = core.clone()

    # ---- recorded live run: flagship storyline -------------------------
    live = core.clone()
    apply_scenario(live, "S11", resolve_params("S11", {"ramp_s": 1200, "severity": 0.9}), tag=":rec")
    live.plant.inject("rack_overheat", "R-06", 0.6, onset_s=600, ramp_s=240, fault_id="REC:R-06", extra_kw=4.0)
    live_frames = run_branch(live, a.live_minutes * 60, a.live_every)

    # ---- what-if runs (shared baseline from identical initial state) -----
    base_frames = run_branch(start.clone(), a.horizon, a.every)
    kb = kpis(base_frames, a.every)
    scen = {}
    for s in CATALOGUE:
        c = start.clone()
        c.mode = "SCENARIO"
        p = resolve_params(s["id"], {})
        apply_scenario(c, s["id"], p, tag=":whatif")
        fr = run_branch(c, a.horizon, a.every)
        ks = kpis(fr, a.every)
        scen[s["id"]] = {"params": p, "kpi_scenario": ks, "comparison": compare(kb, ks),
                         "state_changes_end": state_changes(base_frames[-1], fr[-1]), "frames": enc.encode(fr)}
        print(f"  {s['id']} done")
    doc = {
        "format": "dcx.replay/1",
        "meta": {"generated_wall": time.time(), "generator": "datacorex.tools.record_replay",
                 "model": live.source, "seed": 7,
                 "live_story": "Recorded live run from the DATACORE-X surrogate twin: P-01 bearing degradation (S11, "
                               "severity 0.9, 20 min ramp) from t=0 and a developing R-06 hotspot from t=10 min.",
                 "what_if": f"{len(CATALOGUE)} scenarios, horizon {a.horizon:.0f} s, frame {a.every:.0f} s, shared baseline"},
        "registry": registry_document(),
        "catalogue": CATALOGUE,
        "live": enc.encode(live_frames),
        "baseline": {"kpi": kb, "frames": enc.encode(base_frames)},
        "scenarios": scen,
        "strings": enc.strings,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB) in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
