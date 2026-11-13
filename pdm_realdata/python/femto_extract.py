"""Extract per-snapshot condition indicators for all 17 FEMTO/PRONOSTIA run-to-failure bearings.

Uses the horizontal accelerometer (column 5), the full life of the 6 learning bearings and the
11 'Full_Test_Set' bearings. Output: femto_features.csv (one row per 0.1 s snapshot, every 10 s).
"""
import os
import re
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import dcx_vib as V  # noqa: E402

from dcx_paths import DATA as _D, RES
ROOT = os.path.join(_D, "raw", "femto")
FS = 25600.0
RPM = {1: 1800, 2: 1650, 3: 1500}
GEOM = dict(n=13, d=3.5, D=25.6, theta_deg=0.0)          # challenge document, Appendix A.1


def read_acc(path):
    with open(path) as fh:
        first = fh.readline()
    sep = ";" if ";" in first else ","
    a = pd.read_csv(path, header=None, sep=sep).values
    t = a[0, 0] * 3600 + a[0, 1] * 60 + a[0, 2] + a[0, 3] * 1e-6
    return t, a[:, 4].astype(float), a[:, 5].astype(float)


def one(args):
    split, bearing, fname, idx = args
    cond = int(bearing[7])
    freqs = V.bearing_freqs(rpm=RPM[cond], **GEOM)
    t, h, v = read_acc(os.path.join(ROOT, split, bearing, fname))
    F = V.features(h, FS, freqs)
    Fv = V.features(v, FS, freqs, band=(F["band_lo"], F["band_hi"]))
    row = {"split": split, "bearing": bearing, "cond": cond, "idx": idx, "t_clock": t,
           "peak_abs_g": float(max(np.abs(h).max(), np.abs(v).max()))}
    row.update({k: F[k] for k in F})
    row.update({"v_" + k: Fv[k] for k in ("rms_g", "kurtosis", "vrms_mms")})
    return row


def main():
    jobs = []
    for split in ("Learning_set", "Full_Test_Set"):
        for b in sorted(os.listdir(os.path.join(ROOT, split))):
            files = sorted(f for f in os.listdir(os.path.join(ROOT, split, b)) if f.startswith("acc_"))
            for f in files:
                jobs.append((split, b, f, int(re.findall(r"\d+", f)[0])))
    print(len(jobs), "snapshots", flush=True)
    with Pool(2) as p:
        rows = p.map(one, jobs, chunksize=200)
    df = pd.DataFrame(rows).sort_values(["bearing", "idx"])
    # elapsed time from the first snapshot (clock wraps at midnight in some runs)
    out = []
    for b, g in df.groupby("bearing"):
        tc = g["t_clock"].values.copy()
        for i in range(1, len(tc)):
            while tc[i] < tc[i - 1] - 1:
                tc[i:] += 86400
        g = g.assign(t_s=tc - tc[0])
        out.append(g)
    df = pd.concat(out)
    df.to_csv(os.path.join(RES, "femto_features.csv.gz"), index=False)
    print(df.groupby("bearing").agg(n=("idx", "size"), life_s=("t_s", "max"), peak=("peak_abs_g", "max")))


if __name__ == "__main__":
    main()
