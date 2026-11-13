"""FEMTO / PRONOSTIA (IEEE PHM 2012) remaining-useful-life benchmark under the official protocol.

Training: the 6 learning bearings only. Test: the 11 test bearings, predicted at the official
truncation point (end of Test_set). Score: the official asymmetric accuracy function, against the
official actual RULs (Table 3 of the challenge document).

Health indicator (the same idea as the DATACORE-X pump estimator):
  r(t)  = moving median (9 snapshots = 90 s) of horizontal RMS acceleration / healthy baseline
          (baseline = median of the first 60 snapshots = first 10 min)
  HI(t) = 100 * (1 - clip((r - 1) / (R_fail - 1), 0, 1)),  R_fail learned from the training bearings
  alarm = r above max(1.5, 1 + 6 sigma_baseline) for 3 consecutive snapshots

RUL methods
  naive      mean life of the training bearings minus elapsed time (floored at 10 % of it)
  linear     DATACORE-X twin method: linear trend of r over the last 5 min extrapolated to R_fail
  expo       exponential degradation after the alarm: ln r = a + b (t - t_alarm), with a Bayesian
             prior on the growth rate b learned from the training bearings (conjugate normal update)
  hybrid     expo if the alarm has fired by the truncation point, otherwise the median of the
             training bearings' alarm-to-failure times
  Bounds (all learned from the 6 training bearings only): growth rate >= the smallest training rate;
  RUL <= the longest training alarm-to-failure time. These bounds were added after a first run gave
  unbounded estimates (up to 2e6 s); no parameter was tuned on the test bearings.
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
from dcx_paths import RES
ACT_RUL = {"Bearing1_3": 5730, "Bearing1_4": 339, "Bearing1_5": 1610, "Bearing1_6": 1460, "Bearing1_7": 7570,
           "Bearing2_3": 7530, "Bearing2_4": 1390, "Bearing2_5": 3090, "Bearing2_6": 1290, "Bearing2_7": 580,
           "Bearing3_3": 820}
TRUNC = {"Bearing1_3": 1802, "Bearing1_4": 1139, "Bearing1_5": 2302, "Bearing1_6": 2302, "Bearing1_7": 1502,
         "Bearing2_3": 1202, "Bearing2_4": 612, "Bearing2_5": 2002, "Bearing2_6": 572, "Bearing2_7": 172,
         "Bearing3_3": 352}                                   # number of snapshots in Test_set
TRAIN = ["Bearing1_1", "Bearing1_2", "Bearing2_1", "Bearing2_2", "Bearing3_1", "Bearing3_2"]
DT = 10.0


def score(act, pred):
    er = 100.0 * (act - pred) / act
    return float(np.exp(-np.log(0.5) * er / 5) if er <= 0 else np.exp(np.log(0.5) * er / 20)), float(er)


def indicator(g):
    r = g["rms_g"].values
    base = np.median(r[:60])
    sig = 1.4826 * np.median(np.abs(r[:60] / base - 1))
    sm = pd.Series(r / base).rolling(9, min_periods=1).median().values      # causal smoothing
    thr = max(1.5, 1 + 6 * sig)
    above = sm > thr
    alarm = None
    for i in range(2, len(sm)):
        if above[i] and above[i - 1] and above[i - 2]:
            alarm = i
            break
    return sm, thr, alarm


def learn(df):
    rf, durs, rates = [], [], []
    for b in TRAIN:
        g = df[df.bearing == b].sort_values("idx")
        sm, thr, al = indicator(g)
        rf.append(np.median(sm[-5:]))
        T = len(sm) * DT
        if al is not None:
            durs.append(T - al * DT)
            rates.append(np.log(max(sm[-5:].mean(), thr * 1.01) / thr) / max(T - al * DT, DT))
    prior = {"R_fail": float(np.median(rf)), "R_fail_each": [float(x) for x in rf],
             "life_mean_s": float(np.mean([len(df[df.bearing == b]) * DT for b in TRAIN])),
             "alarm_to_fail_s": [float(x) for x in durs], "b_mean": float(np.mean(rates)),
             "b_sd": float(np.std(rates, ddof=1)) if len(rates) > 1 else float(np.mean(rates)),
             "b_min": float(np.min(rates)), "cap_s": float(np.max(durs)), "fallback_s": float(np.median(durs))}
    return prior


def predict(sm, thr, alarm, n, P):
    t_now = (n - 1) * DT
    out = {}
    out["naive"] = max(P["life_mean_s"] - t_now, 0.1 * P["life_mean_s"])
    k = sm[max(0, n - 30):n]
    tt = np.arange(len(k)) * DT
    slope = np.polyfit(tt, k, 1)[0] if len(k) > 3 else 0.0
    out["linear"] = min((P["R_fail"] - sm[n - 1]) / slope, P["cap_s"]) if slope > 1e-6 and sm[n - 1] < P["R_fail"] else np.nan
    if alarm is not None and alarm < n:
        y = np.log(np.maximum(sm[alarm:n], 1e-6))
        x = (np.arange(alarm, n) - alarm) * DT
        # conjugate normal update of the growth rate b (intercept fixed by least squares)
        if len(x) > 2:
            b_ls = np.polyfit(x, y, 1)[0]
            resid = y - np.polyval(np.polyfit(x, y, 1), x)
            s2 = max(np.var(resid), 1e-4)
            sxx = np.sum((x - x.mean()) ** 2) + 1e-9
            prec = 1 / P["b_sd"] ** 2 + sxx / s2
            b = (P["b_mean"] / P["b_sd"] ** 2 + b_ls * sxx / s2) / prec
        else:
            b = P["b_mean"]
        b = max(b, P["b_min"])                                   # bounds learned from training only
        out["expo"] = min(max((np.log(P["R_fail"]) - np.log(max(sm[n - 1], 1e-6))) / b, 0.0), P["cap_s"])
    else:
        out["expo"] = np.nan
    cons = P["fallback_s"]
    out["hybrid"] = out["expo"] if not np.isnan(out["expo"]) else cons
    # linear method falls back to the same conservative prior when there is no rising trend
    if np.isnan(out["linear"]):
        out["linear"] = cons
    out["expo"] = out["expo"] if not np.isnan(out["expo"]) else cons
    return out


def main():
    df = pd.read_csv(os.path.join(RES, "femto_features.csv.gz"))
    P = learn(df)
    rows = []
    for b in sorted(ACT_RUL):
        g = df[df.bearing == b].sort_values("idx")
        sm, thr, al = indicator(g)
        n = TRUNC[b]
        pr = predict(sm, thr, al, n, P)
        r = {"bearing": b, "actual_rul_s": ACT_RUL[b], "alarm_before_cut": al is not None and al < n,
             "alarm_time_s": None if al is None else al * DT, "life_s": len(sm) * DT}
        for m, v in pr.items():
            A, er = score(ACT_RUL[b], v)
            r[f"{m}_rul_s"] = float(v)
            r[f"{m}_er_pct"] = er
            r[f"{m}_A"] = A
        rows.append(r)
    R = pd.DataFrame(rows)
    summary = {m: {"score": float(R[f"{m}_A"].mean()), "mean_abs_er_pct": float(R[f"{m}_er_pct"].abs().mean()),
                   "late_predictions": int((R[f"{m}_er_pct"] < 0).sum())}
               for m in ("naive", "linear", "expo", "hybrid")}
    # early warning on all 17 bearings: alarm lead time before end of life, and alarms in the first half
    ew = []
    for b, g in df.groupby("bearing"):
        sm, thr, al = indicator(g.sort_values("idx"))
        T = len(sm) * DT
        ew.append({"bearing": b, "life_s": T, "alarm_s": None if al is None else al * DT,
                   "lead_s": None if al is None else T - al * DT, "lead_frac": None if al is None else (T - al * DT) / T})
    EW = pd.DataFrame(ew)
    R.to_csv(os.path.join(RES, "femto_rul_results.csv"), index=False)
    EW.to_csv(os.path.join(RES, "femto_early_warning.csv"), index=False)
    out = {"prior": P, "summary": summary,
           "early_warning": {"alarmed": int(EW.alarm_s.notna().sum()), "n": len(EW),
                             "median_lead_s": float(EW.lead_s.median()),
                             "median_lead_frac": float(EW.lead_frac.median())}}
    json.dump(out, open(os.path.join(RES, "femto_summary.json"), "w"), indent=1)
    pd.set_option("display.width", 200)
    print(R[["bearing", "actual_rul_s", "alarm_before_cut", "naive_rul_s", "linear_rul_s", "expo_rul_s", "hybrid_rul_s",
             "naive_er_pct", "hybrid_er_pct"]].round(0).to_string(index=False))
    print(json.dumps(out["summary"], indent=1)); print(json.dumps(out["early_warning"])); print(json.dumps(P))
    print(EW.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
