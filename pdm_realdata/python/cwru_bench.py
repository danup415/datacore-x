"""CWRU bearing fault classification with leak-free evaluation.

Data: 12 kHz drive-end accelerometer, all drive-end fault files (inner race IR, ball B, outer race OR,
sizes 0.007-0.028 in, outer race at 3/6/12 o'clock) and the 4 normal-baseline files.
The normal-baseline files were recorded at 48 kHz: they are decimated to 12 kHz first, otherwise a
model can tell 'normal' apart by sampling rate alone.

Windows: 4096 samples (0.34 s, ~10 shaft revolutions), non-overlapping.
Classes: Normal, IR, B, OR.
Features: dcx_vib.features (time-domain, band energies, envelope SNR at BPFO / BPFI / 2xBSF / FTF).

Evaluations
  random   windows shuffled 70/30 (the common, leaky protocol: windows of one recording on both sides)
  load     leave-one-motor-load-out (train on 3 loads, test on the 4th; 4 folds)
  size     leave-one-fault-size-out (train on two of 0.007/0.014/0.021 in, test on the third; 0.028 in
           tested once, with the 0.021 in fold; normal baseline: one load file held out per fold)
Classifiers
  rf       random forest on the physics features
  rule     training-free envelope rule: the defect frequency with the highest envelope SNR wins if it
           exceeds 10 dB, else Normal (no fitting at all)
Metric: macro-F1 with a 95 % cluster bootstrap over recordings (files), 2000 resamples.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.signal import decimate
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, confusion_matrix

sys.path.insert(0, os.path.dirname(__file__))
import dcx_vib as V  # noqa: E402

from dcx_paths import DATA as _D, RES
DATA = os.path.join(_D, "raw", "cwru")
HERE = os.path.dirname(__file__)
FS = 12000.0
WIN = 4096
RPM_NOM = {0: 1797, 1: 1772, 2: 1750, 3: 1730}
GEOM = dict(n=9, d=0.3126, D=1.537, theta_deg=0.0)          # SKF 6205-2RS JEM (drive end)
CLASSES = ["Normal", "IR", "B", "OR"]
FEATS = ["rms_g", "crest", "kurtosis", "skewness", "e_lo", "e_mid", "e_hi",
         "BPFO_snr", "BPFI_snr", "BSF_snr", "FTF_snr"]


def files():
    out = []
    for f in sorted(os.listdir(DATA)):
        m = re.match(r"12k_Drive_End_(IR|B|OR)(\d{3})(@\d+)?_(\d)_(\d+)\.mat", f)
        if m:
            out.append(dict(file=f, cls=m.group(1), size=int(m.group(2)), pos=m.group(3) or "", load=int(m.group(4)), id=m.group(5)))
        m = re.match(r"normal_(\d)_(\d+)\.mat", f)
        if m:
            out.append(dict(file=f, cls="Normal", size=0, pos="", load=int(m.group(1)), id=m.group(2)))
    return out


def load_signal(meta):
    m = loadmat(os.path.join(DATA, meta["file"]))
    k = [k for k in m if k.endswith("DE_time")][0]
    x = m[k].ravel().astype(float)
    if meta["cls"] == "Normal":
        x = decimate(x, 4, ftype="fir", zero_phase=True)        # 48 kHz -> 12 kHz
    rk = [k for k in m if k.endswith("RPM")]
    rpm = float(np.ravel(m[rk[0]])[0]) if rk else RPM_NOM[meta["load"]]
    return x, rpm


def extract():
    rows = []
    for meta in files():
        x, rpm = load_signal(meta)
        fr = V.bearing_freqs(rpm=rpm, **GEOM)
        for w in range(len(x) // WIN):
            F = V.features(x[w * WIN:(w + 1) * WIN], FS, fr)
            rows.append({**meta, "win": w, "rpm": rpm, **{k: F[k] for k in FEATS}})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "cwru_features.csv.gz"), index=False)
    return df


def rule(df):
    snr = df[["BPFO_snr", "BPFI_snr", "BSF_snr"]].values
    k = np.argmax(snr, axis=1)
    lab = np.array(["OR", "IR", "B"])[k]
    return np.where(snr.max(axis=1) > 10.0, lab, "Normal")


def boot_f1(y, p, groups, B=2000, seed=0):
    rng = np.random.default_rng(seed)
    g = np.asarray(groups)
    ug = np.unique(g)
    idx = {u: np.where(g == u)[0] for u in ug}
    vals = []
    for _ in range(B):
        s = np.concatenate([idx[u] for u in rng.choice(ug, len(ug), replace=True)])
        vals.append(f1_score(y[s], p[s], labels=CLASSES, average="macro", zero_division=0))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def evaluate(df):
    res = {}
    X = df[FEATS].values
    y = df["cls"].values
    grp = df["file"].values

    def fit_pred(tr, te):
        clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, random_state=0, n_jobs=2)
        clf.fit(X[tr], y[tr])
        return clf.predict(X[te])

    folds = {}
    rng = np.random.default_rng(1)
    perm = rng.permutation(len(df))
    cut = int(0.7 * len(df))
    folds["random"] = [(perm[:cut], perm[cut:])]
    folds["load"] = [(np.where(df.load != L)[0], np.where(df.load == L)[0]) for L in range(4)]
    sz = []
    for i, S in enumerate((7, 14, 21)):
        held_normal = df["cls"].eq("Normal") & df.load.eq(i)
        te = ((df["size"] == S) | ((df["size"] == 28) & (S == 21)) | held_normal).values
        tr = ((df["size"] != S) & (df["size"] != 28) & ~held_normal).values
        sz.append((np.where(tr)[0], np.where(te)[0]))
    folds["size"] = sz
    rule_pred = rule(df)
    for name, fl in folds.items():
        yt, yp, yr, gg = [], [], [], []
        for tr, te in fl:
            yt.append(y[te]); yp.append(fit_pred(tr, te)); yr.append(rule_pred[te]); gg.append(grp[te])
        yt, yp, yr, gg = map(np.concatenate, (yt, yp, yr, gg))
        res[name] = {
            "rf_macro_f1": float(f1_score(yt, yp, labels=CLASSES, average="macro")), "rf_ci": boot_f1(yt, yp, gg),
            "rule_macro_f1": float(f1_score(yt, yr, labels=CLASSES, average="macro")), "rule_ci": boot_f1(yt, yr, gg),
            "n_windows": int(len(yt)), "n_files": int(len(np.unique(gg))),
            "rf_confusion": confusion_matrix(yt, yp, labels=CLASSES).tolist(),
            "rule_confusion": confusion_matrix(yt, yr, labels=CLASSES).tolist()}
    return res


def main():
    p = os.path.join(RES, "cwru_features.csv.gz")
    df = pd.read_csv(p) if os.path.exists(p) else extract()
    print(df.groupby("cls").agg(files=("file", "nunique"), windows=("win", "size")))
    res = evaluate(df)
    json.dump(res, open(os.path.join(RES, "cwru_results.json"), "w"), indent=1)
    for k, v in res.items():
        print(f"{k:7s} RF macro-F1 {v['rf_macro_f1']:.3f} [{v['rf_ci'][0]:.3f}, {v['rf_ci'][1]:.3f}]   "
              f"rule {v['rule_macro_f1']:.3f} [{v['rule_ci'][0]:.3f}, {v['rule_ci'][1]:.3f}]   "
              f"({v['n_windows']} windows, {v['n_files']} files)")
        print("   RF confusion (rows true N/IR/B/OR):", v["rf_confusion"])
        print("   rule confusion:", v["rule_confusion"])


if __name__ == "__main__":
    main()
