import sys, json, h5py, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
ROM, SSC, RED, GREY = "#1F4E79", "#D9822B", "#B22222", "#9AA0A6"
f = h5py.File(sys.argv[1], "r")["runs"]
def L(k):
    g = f[k]["L"]; a = lambda n: np.array(g[n]).T
    return dict(t=a("t").ravel() / 3600, q=a("q").ravel(), H=a("H").ravel(), n=a("n").ravel(), run=a("pump_run"),
                vib=a("vib_p"), trip=a("pump_trip"), kw=a("pump_kw").sum(1), Tin=a("max_in").ravel())
fig, ax = plt.subplots(2, 3, figsize=(12, 6.2))
for i, md in enumerate(["haempc", "empc"]):
    r, s = L(md + "_rom"), L(md + "_simscape")
    name = "PI-HA-EMPC" if md == "haempc" else "EMPC (health-blind)"
    a = ax[i, 0]
    a.plot(r["t"], r["q"], color=ROM, lw=1.6, label="reduced-order hydraulics")
    a.plot(s["t"], s["q"], color=SSC, lw=1, ls="--", label="Simscape Fluids in the loop")
    a.set_ylabel("loop flow (L/s)"); a.set_title(f"{name}: CHW loop flow")
    a2 = ax[i, 1]
    a2.plot(r["t"], r["vib"][:, 0] * (r["run"][:, 0] > 0), color=ROM, lw=1.6)
    a2.plot(s["t"], s["vib"][:, 0] * (s["run"][:, 0] > 0), color=SSC, lw=1, ls="--")
    a2.axhline(4.5, color=GREY, lw=0.8, ls=":"); a2.text(3.3, 4.65, "ISO zone C", color=GREY, fontsize=7)
    a2.axhline(7.1, color=RED, lw=0.8, ls=":"); a2.text(3.3, 7.25, "zone D (trip)", color=RED, fontsize=7)
    a2.set_ylabel("P-01 vibration while running (mm/s)"); a2.set_title(f"{name}: faulty pump P-01")
    for d, c in ((r, ROM), (s, SSC)):
        k = np.where((d["run"][:, 0] == 0) & (d["trip"][:, 0] == 0) & (d["t"] > 0.2))[0]
        kt = np.where(np.diff(d["trip"][:, 0]) > 0)[0]
        if len(k): a2.axvline(d["t"][k[0]], color=c, lw=0.8)
        if len(kt) and d["run"][kt[0], 0] > 0: a2.plot(d["t"][kt[0] + 1], 7.1, "x", color=RED, ms=8, mew=2)
    a3 = ax[i, 2]
    ev = s["t"][np.where(np.diff(s["run"][:, 0]) != 0)[0][0] + 1]
    w = (r["t"] > ev - 0.1) & (r["t"] < ev + 0.15); ws = (s["t"] > ev - 0.1) & (s["t"] < ev + 0.15)
    m = lambda t: (t - ev) * 60
    a3.plot(m(r["t"][w]), r["q"][w], color=ROM, lw=1.6, marker=".", ms=3); a3.plot(m(s["t"][ws]), s["q"][ws], color=SSC, lw=1, ls="--", marker=".", ms=3)
    a3.set_ylabel("loop flow (L/s)"); a3.set_xlabel("minutes from P-01 stop")
    b3 = a3.twinx(); b3.plot(m(r["t"][w]), r["H"][w], color=ROM, lw=0.8, alpha=0.5); b3.plot(m(s["t"][ws]), s["H"][ws], color=SSC, lw=0.8, ls=":", alpha=0.8)
    b3.set_ylabel("header dp (kPa), thin lines", fontsize=7); b3.spines["top"].set_visible(False)
    a3.set_title(f"{name}: pump-switch transient (10 s log)"); a3.set_ylim(4.25, 4.97); b3.set_ylim(148, 188)
    a3.text(0.03, 0.06, "planned changeover: bumpless in both models" if md == "haempc" else
            "trip: flow dip 4.32 L/s (Simscape) vs 4.66 L/s (ROM)", transform=a3.transAxes, fontsize=7)
    for a_ in ax[i][:2]: a_.set_xlabel("time (h)")
ax[0, 0].legend(fontsize=7, frameon=False, loc="lower right")
ax[0, 1].text(0.02, 0.86, "vertical lines: changeover\n2.38 h (Simscape) / 2.45 h (ROM)", transform=ax[0, 1].transAxes, fontsize=7)
ax[1, 1].text(0.02, 0.86, "x: unplanned trip, both models at 2.85 h", transform=ax[1, 1].transAxes, fontsize=7, color=RED)
fig.suptitle("Pump-bearing fault, Pune, seed 1: Simscape Fluids hydraulics in the closed loop vs the reduced-order model", fontsize=10)
fig.tight_layout(); fig.savefig("figs/fig_ssc_loop.png", dpi=150)

T = pd.read_csv(sys.argv[2])
lab = {"empc": "EMPC\n(no health)", "ha_noActions": "health in MPC\nonly", "ha_actionsOnly": "health actions\nonly",
       "ha_noHI": "no HI", "ha_noRUL": "no RUL", "ha_noPrecool": "no pre-cool", "haempc": "full\nPI-HA-EMPC"}
order = list(lab)
fig, ax = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
for a, sc in zip(ax, ["pump", "chiller"]):
    t = T[(T.scenario == sc) & T["mode"].isin(order)].set_index("mode").loc[order]
    col = [RED if m in ("empc", "ha_noActions") else (ROM if m in ("haempc", "ha_actionsOnly") else GREY) for m in order]
    a.bar(range(len(order)), 100 * t.trip_rate, color=col)
    a.errorbar(range(len(order)), 100 * t.trip_rate, yerr=[100 * (t.trip_rate - t.ci_lo), 100 * (t.ci_hi - t.trip_rate)], fmt="none", ecolor="k", lw=0.8, capsize=3)
    for j, (k, n) in enumerate(zip(t.runs_with_trip, t.runs)): a.text(j, 100 * t.trip_rate.iloc[j] + 3, f"{k}/{n}", ha="center", fontsize=7)
    a.set_xticks(range(len(order))); a.set_xticklabels([lab[m] for m in order], fontsize=7)
    a.set_title(f"{sc} degradation (both climates, 10 seeds)"); a.set_ylim(0, 112)
ax[0].set_ylabel("runs with an unplanned trip (%)")
fig.suptitle("E3b: which part of PI-HA-EMPC prevents the trips? (Wilson 95 % CI)", fontsize=10)
fig.tight_layout(); fig.savefig("figs/fig_E3b_components.png", dpi=150)
print("ok")
