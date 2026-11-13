"""E3b component ablation summary: merges runs_paper.csv (haempc, empc, E3) with runs_ablation2.csv."""
import sys, json
import numpy as np, pandas as pd
from statsmodels.stats.proportion import proportion_confint

paper, abl = sys.argv[1], sys.argv[2]
d = pd.concat([pd.read_csv(paper), pd.read_csv(abl)], ignore_index=True)
d = d[(d.workload == "diurnal") & (d.scenario != "normal") & (d.rul_scale == 1.0)]
order = ["empc", "ha_none", "ha_noActions", "ha_actionsOnly", "ha_noHI", "ha_noRUL", "ha_noPrecool", "haempc"]
d = d[d["mode"].isin(order)]
out = []
for (sc, md), g in d.groupby(["scenario", "mode"]):
    n = len(g); k = int(g.unplanned_trips.gt(0).sum())
    lo, hi = proportion_confint(k, n, method="wilson")
    out.append(dict(scenario=sc, mode=md, runs=n, runs_with_trip=k, trip_rate=k / n, ci_lo=lo, ci_hi=hi,
                    zoneCD_s=g.risk_zoneCD_s.mean(), energy_kwh=g.energy_kwh.mean(), peak_inlet_c=g.peak_inlet_c.mean(),
                    t_above_27_s=g.t_above_27_s.mean(), changeover=g.pump_changeover.mean(),
                    lead_transfer=g.chiller_lead_transfer.mean(), precool_min=g.precool_min.mean()))
T = pd.DataFrame(out)
T["mode"] = pd.Categorical(T["mode"], order, ordered=True)
T = T.sort_values(["scenario", "mode"])
print(T.round(3).to_string(index=False))

# sanity: ha_none must equal empc on the same keys
k = lambda r: f"{r.climate}|{r.scenario}|{r.seed}"
e = d[d["mode"] == "empc"].assign(k=lambda x: x.apply(k, axis=1)).set_index("k")
z = d[d["mode"] == "ha_none"].assign(k=lambda x: x.apply(k, axis=1)).set_index("k")
cols = ["energy_kwh", "peak_inlet_c", "unplanned_trips", "risk_zoneCD_s", "mean_chws_sp"]
diff = (z[cols] - e.loc[z.index, cols]).abs().max()
print("ha_none vs empc max abs diff:\n", diff)

# paired energy difference vs full haempc on the same seeds
h = d[d["mode"] == "haempc"].assign(k=lambda x: x.apply(lambda r: f"{r.climate}|{r.scenario}|{r.seed}", axis=1)).drop_duplicates("k").set_index("k")
pair = {}
for md in ["ha_noActions", "ha_actionsOnly"]:
    a = d[d["mode"] == md].assign(k=lambda x: x.apply(lambda r: f"{r.climate}|{r.scenario}|{r.seed}", axis=1)).set_index("k")
    dd = 100 * (a.energy_kwh - h.loc[a.index, "energy_kwh"]) / h.loc[a.index, "energy_kwh"]
    pair[md] = dict(mean_pct=float(dd.mean()), max_abs_pct=float(dd.abs().max()))
print(pair)
json.dump(dict(table=json.loads(T.to_json(orient="records")), sanity_none_vs_empc=diff.to_dict(), energy_vs_haempc=pair),
          open("abl2_results.json", "w"), indent=1, default=str)
T.to_csv("abl2_table.csv", index=False)
