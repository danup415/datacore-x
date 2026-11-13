"""Virtual instrumentation (Subsystem 06).

Converts plant ground truth into *measured* values: additive Gaussian noise
per measurement class, quantisation to the registry's display resolution,
and sensor fault effects (F09 drift, hard failure -> quality BAD).  The 3D
twin, SCADA and AI only ever see measured values; ground truth is kept
separately by the historian for honest evaluation (blueprint §12.3).
"""
from __future__ import annotations

import numpy as np

from .registry import assets

# relative (fraction) and absolute noise by engineering unit
NOISE = {
    "°C": (0.0, 0.05), "kW": (0.004, 0.01), "%": (0.0, 0.15), "L/s": (0.006, 0.0),
    "kPa": (0.005, 0.2), "mm/s": (0.02, 0.02), "A": (0.005, 0.1), "V": (0.001, 0.0),
    "m³/s": (0.01, 0.0), "kVA": (0.004, 0.0), "Hz": (0.0, 0.004), "K": (0.0, 0.07),
    "-": (0.004, 0.0), "kW/K": (0.01, 0.0), "m/s": (0.01, 0.0), "mΩ": (0.005, 0.0),
    "min": (0.0, 0.0), "s": (0.0, 0.0), "kWh": (0.0, 0.0),
}
NO_NOISE_KEYS = {"source_code", "run_s", "runtime_min", "soh_pct", "capacity_kw", "wetbulb_c"}


class Instrumentation:
    def __init__(self, seed: int = 11):
        self.rng = np.random.default_rng(seed)
        self.defs = {a["id"]: a["tags"] for a in assets()}

    def measure(self, truth: dict, plant) -> dict:
        """Return ``{asset_id: {"state", "v": {...}, "q": {...}}}``."""
        out = {}
        drift = {}
        failed = set()
        for f in getattr(plant, "faults", []):
            s = f.sev(plant.t)
            if s <= 0:
                continue
            if f.kind == "sensor_drift":
                key = f.params.get("tag", "inlet_c")
                drift[(f.asset, key)] = drift.get((f.asset, key), 0.0) + s * float(f.params.get("bias", 4.0))
            elif f.kind == "sensor_fail":
                failed.add((f.asset, f.params.get("tag", "inlet_c")))
        for aid, tags in self.defs.items():
            tv = truth.get(aid)
            if tv is None or not tags:
                continue
            v, q = {}, {}
            for tg in tags:
                k = tg["key"]
                x = tv.get(k)
                if x is None:
                    v[k] = None
                    q[k] = "NOT_PROVIDED"
                    continue
                if (aid, k) in failed:
                    v[k] = None
                    q[k] = "BAD"
                    continue
                rel, ab = NOISE.get(tg["unit"], (0.0, 0.0))
                if k not in NO_NOISE_KEYS and x != 0:
                    x = x + self.rng.standard_normal() * (abs(x) * rel + ab)
                x += drift.get((aid, k), 0.0)
                v[k] = round(float(x), tg["decimals"])
            rec = {"state": tv.get("state", "UNKNOWN"), "v": v}
            if q:
                rec["q"] = q
            out[aid] = rec
        return out

    @staticmethod
    def passthrough(external_assets: dict) -> dict:
        """External sources (MATLAB/Simulink) already publish virtual-sensor
        values; validate shape only."""
        out = {}
        for aid, rec in external_assets.items():
            out[aid] = {"state": rec.get("state", "UNKNOWN"), "v": dict(rec.get("values", {}))}
            if rec.get("quality"):
                out[aid]["q"] = dict(rec["quality"])
        return out
