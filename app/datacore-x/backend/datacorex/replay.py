"""Measured-data replay: drive a pump's bearing vibration from a real run-to-failure record.

A replay profile (``replay_profiles/<id>.json``) holds the RMS vibration velocity (10-1000 Hz, mm/s)
of a real bearing, computed from its raw accelerometer data with the DATACORE-X vibration toolkit
(``pdm/dcx_vib.py`` / ``matlab/vibration/vib_features.m``), one value per measurement snapshot,
from installation to failure.

In the twin, fault kind ``pump_bearing_replay`` adds the profile's *measured increase* over its own
healthy baseline to the pump's modelled healthy vibration:

    vib_pump(t) = vib_healthy_model(speed) + (v_measured(tau) - v_measured_baseline)

where ``tau`` is the bearing's accumulated *running* time multiplied by a time-compression factor.
The bearing ages only while the pump runs: if the pump is changed over, the replay pauses, as a
stopped machine does not wear. When ``tau`` reaches the end of the record (the bearing's recorded
failure) while the pump is still running, the pump trips. Everything else in the twin stays simulated.

Both quantities are RMS velocity in the ISO 10816 / 20816 band, so the ISO zone limits used by the
alarms keep their meaning. The source test rig is not a CHW pump: this is real bearing degradation
applied to the pump's vibration sensor, not a recorded pump failure.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

DIR = Path(__file__).resolve().parent / "replay_profiles"


def available() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.json"))


@lru_cache(maxsize=8)
def load(pid: str) -> dict:
    d = json.loads((DIR / f"{pid}.json").read_text(encoding="utf-8"))
    d["_t"] = np.asarray(d["t_s"], dtype=float)
    d["_v"] = np.asarray(d["vrms_mms"], dtype=float)
    d["_k"] = np.asarray(d["kurtosis"], dtype=float)
    return d


def sample(pid: str, tau_s: float) -> dict:
    """Measured values at bearing-life time tau_s (seconds of the original record)."""
    d = load(pid)
    tau = min(max(tau_s, 0.0), d["life_s"])
    v = float(np.interp(tau, d["_t"], d["_v"]))
    k = float(np.interp(tau, d["_t"], d["_k"]))
    return {"excess_mms": max(0.0, v - d["baseline_vrms_mms"]), "vrms_mms": v, "kurtosis": k,
            "life_frac": tau / d["life_s"], "ended": tau_s >= d["life_s"]}


def describe(pid: str) -> dict:
    d = load(pid)
    return {k: d[k] for k in ("id", "title", "source", "bearing", "condition", "sensor", "quantity", "life_s",
                              "baseline_vrms_mms")}
