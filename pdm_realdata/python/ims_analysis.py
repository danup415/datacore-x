"""NASA IMS run-to-failure tests: early warning, false alarms, envelope diagnosis and RUL.

Input: ims_features_t*.csv written by matlab/vibration/ims_extract.m (the MATLAB toolkit).
Ground truth (IMS readme): test 1 - bearing 3 inner race, bearing 4 roller element; test 2 - bearing 1
outer race; test 3 - bearing 3 outer race. All other bearings did not fail (8 healthy bearings).

Health indicator: RMS acceleration over the bearing's own first 50 snapshots (causal moving median of
9 snapshots); alarm when it stays above max(1.5, 1 + 6 sigma_baseline) for 3 snapshots - the same rule
as the FEMTO benchmark, fixed before looking at IMS.
Envelope alarm: any defect band >= 6 dB above its healthy median for 3 snapshots (fault type unused).
Diagnosis: at the end of life (last 5 % of snapshots), the defect frequency with the highest median
envelope SNR (BPFO outer race, BPFI inner race, 2xBSF rolling element).
RUL: leave-one-failed-bearing-out exponential model on ln(indicator) after the alarm, growth rate prior
from the other failed bearings (the FEMTO method). Reported as MAE in hours over the post-alarm period,
against a naive 'mean post-alarm life of the other bearings' predictor.
"""
import glob
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
from dcx_paths import DATA, RES
FAILED = {(1, 3): "inner race", (1, 4): "roller element", (2, 1): "outer race", (3, 3): "outer race"}
EXPECT = {"inner race": "BPFI", "outer race": "BPFO", "roller element": "BSF"}


def load():
    fs = sorted(glob.glob(os.path.join(DATA, "ims_features_t*.csv")))
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    d["time"] = pd.to_datetime(d["time"])
    return d


def indicator(g, base_n=50):
    r = g["rms_g"].values
    base = np.median(r[:base_n])
    sig = 1.4826 * np.median(np.abs(r[:base_n] / base - 1))
    sm = pd.Series(r / base).rolling(9, min_periods=1).median().values
    thr = max(1.5, 1 + 6 * sig)
    above = sm > thr
    al = next((i for i in range(2, len(sm)) if above[i] and above[i - 1] and above[i - 2]), None)
    return sm, thr, al


def envelope_alarm(g, base_n=50, rise_db=6.0):
    """First snapshot where any defect band (BPFO, BPFI, 2xBSF) sits >= rise_db above its own healthy
    median for 3 consecutive (smoothed) snapshots. Fault type is not used: the band that fires is the
    diagnosis."""
    first = None
    band = None
    for c in ("BPFO", "BPFI", "BSF"):
        x = pd.Series(g[f"{c}_snr"].values).rolling(9, min_periods=1).median().values
        base = np.median(x[:base_n])
        above = x >= base + rise_db
        i = next((i for i in range(2, len(x)) if above[i] and above[i - 1] and above[i - 2]), None)
        if i is not None and (first is None or i < first):
            first, band = i, c
    return first, band


def main():
    d = load()
    rows, traj = [], {}
    for (t, b), g in d.groupby(["test", "bearing"]):
        g = g.sort_values("time")
        sm, thr, al = indicator(g)
        hrs = (g["time"] - g["time"].iloc[0]).dt.total_seconds().values / 3600
        end = hrs[-1]
        k = max(5, int(0.05 * len(g)))
        snr = {c: float(np.median(g[f"{c}_snr"].values[-k:])) for c in ("BPFO", "BPFI", "BSF")}
        snr0 = {c: float(np.median(g[f"{c}_snr"].values[:50])) for c in ("BPFO", "BPFI", "BSF")}
        rise = {c: snr[c] - snr0[c] for c in snr}
        diag = max(rise, key=rise.get)
        failed = (t, b) in FAILED
        ea, eb = envelope_alarm(g)
        rows.append({"env_alarm_h": None if ea is None else round(hrs[ea], 1),
                     "env_lead_h": None if ea is None else round(end - hrs[ea], 1), "env_band": eb,"test": t, "bearing": b, "failed": failed, "mode": FAILED.get((t, b), "none"),
                     "duration_h": round(end, 1), "alarm_h": None if al is None else round(hrs[al], 1),
                     "lead_h": None if al is None else round(end - hrs[al], 1),
                     "end_ratio": round(float(np.median(sm[-k:])), 2),
                     "diag_band": diag, "snr_rise_db": {c: round(v, 1) for c, v in rise.items()},
                     "diag_correct": (EXPECT[FAILED[(t, b)]] == diag) if failed else None})
        traj[(t, b)] = (hrs, sm, al)
    R = pd.DataFrame(rows)
    # ---- RUL, leave one failed bearing out
    rul = []
    keys = [k for k in FAILED if k in traj]
    for kx in keys:
        others = [k for k in keys if k != kx and traj[k][2] is not None]
        rates, posts = [], []
        for k in others:
            h, s, a = traj[k]
            rates.append(np.log(max(np.median(s[-5:]), 1.01 * s[a]) / s[a]) / max(h[-1] - h[a], 1e-3))
            posts.append(h[-1] - h[a])
        h, s, a = traj[kx]
        if a is None:
            rul.append({"test": kx[0], "bearing": kx[1], "note": "no alarm"})
            continue
        if not rates:
            rul.append({"test": kx[0], "bearing": kx[1], "note": "no other failed bearing to learn from"})
            continue
        Rf = np.median([np.median(traj[k][1][-5:]) for k in others])
        bm, bsd = np.mean(rates), max(np.std(rates), 1e-3)
        err_m, err_n = [], []
        for i in range(a + 3, len(h)):
            x = h[a:i + 1] - h[a]
            y = np.log(np.maximum(s[a:i + 1], 1e-6))
            if len(x) > 2:
                bls = np.polyfit(x, y, 1)[0]
                s2 = max(np.var(y - np.polyval(np.polyfit(x, y, 1), x)), 1e-4)
                sxx = np.sum((x - x.mean()) ** 2) + 1e-9
                bpost = (bm / bsd ** 2 + bls * sxx / s2) / (1 / bsd ** 2 + sxx / s2)
            else:
                bpost = bm
            bpost = max(bpost, min(rates))
            pred = min(max((np.log(Rf) - np.log(max(s[i], 1e-6))) / bpost, 0.0), max(posts))
            true = h[-1] - h[i]
            naive = max(np.mean(posts) - (h[i] - h[a]), 0.0)
            err_m.append(abs(pred - true)); err_n.append(abs(naive - true))
        rul.append({"test": kx[0], "bearing": kx[1], "post_alarm_h": round(h[-1] - h[a], 1),
                    "mae_model_h": round(float(np.mean(err_m)), 1), "mae_naive_h": round(float(np.mean(err_n)), 1)})
    # a healthy bearing alarming after a failed bearing on the same shaft has alarmed is propagation
    # (the rig's four bearings share one shaft), not a false alarm
    first_fail = R[R.failed].groupby("test")["alarm_h"].min().to_dict()
    def kind(r):
        if r.failed or r.alarm_h is None or pd.isna(r.alarm_h):
            return None
        f = first_fail.get(r.test)
        return "propagated" if f is not None and not pd.isna(f) and r.alarm_h >= f else "false"
    R["healthy_alarm"] = R.apply(kind, axis=1)
    first_env = R[R.failed].groupby("test")["env_alarm_h"].min().to_dict()
    def ekind(r):
        if r.failed or r.env_alarm_h is None or pd.isna(r.env_alarm_h):
            return None
        f = first_env.get(r.test)
        return "propagated" if f is not None and not pd.isna(f) and r.env_alarm_h >= f else "false"
    R["healthy_env_alarm"] = R.apply(ekind, axis=1)
    for r in rows:
        q = R[(R.test == r["test"]) & (R.bearing == r["bearing"])].iloc[0]
        r["healthy_alarm"], r["healthy_env_alarm"] = q["healthy_alarm"], q["healthy_env_alarm"]
        if r["failed"]:
            r["env_band_correct"] = r["env_band"] == EXPECT[r["mode"]] if r["env_band"] else None
    healthy = R[~R.failed]
    fail = R[R.failed]
    out = {"bearings": rows, "rul": rul,
           "summary": {"failed_alarmed": int(fail.alarm_h.notna().sum()), "failed": int(len(fail)),
                       "healthy_false_alarms": int((healthy.healthy_alarm == "false").sum()),
                       "healthy_propagated_alarms": int((healthy.healthy_alarm == "propagated").sum()), "healthy": int(len(healthy)),
                       "diag_correct": int(fail.diag_correct.sum()), "lead_h": fail.lead_h.tolist(),
                       "env_failed_alarmed": int(fail.env_alarm_h.notna().sum()), "env_lead_h": fail.env_lead_h.tolist(),
                       "env_false_alarms": int((healthy.healthy_env_alarm == "false").sum()),
                       "env_propagated_alarms": int((healthy.healthy_env_alarm == "propagated").sum())}}
    json.dump(out, open(os.path.join(RES, "ims_results.json"), "w"), indent=1, default=str)
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))
    print(pd.DataFrame(rul).to_string(index=False))
    print(json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
