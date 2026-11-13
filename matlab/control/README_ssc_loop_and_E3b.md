# Simscape Fluids in the closed loop, and the E3b component ablation

## 1. Simscape Fluids hydraulics in the closed loop

`control/DcxSscCosim.m` co-simulates the Simscape Fluids (Isothermal Liquid) chilled-water network `simscape/DCX_CHW_Hydraulics_SSC.slx` with the plant stepper (`plant/dcx_sim_matlab.m`, new optional `HydHook` argument).

- **Each 10 s step:** the network advances from its saved operating point with three inputs from the plant: the VFD speed (set by the DP PI loop), the pump run states (PLC duty/standby, supervisor changeover, trips) and the four CRAH valve openings.
- **What Simscape replaces:** its header DP, loop flow and per-pump flows replace the reduced-order hydraulics. The DP controller regulates on the Simscape pressure, the coils use the Simscape flow, and pump power is recomputed from the Simscape flows.

Run it (about 10 min on the laptop):

```matlab
dcx_startup; R = dcx_ssc_loop();      % pump-bearing fault, Pune, seed 1, 6 h; PI-HA-EMPC and EMPC
```

Results are in `control/results/ssc_loop/`, including `ssc_loop.json` and `fig_ssc_loop.png`.

| Controller | Hydraulics | Unplanned trip | Changeover | Zone C/D exposure | Energy |
|---|---|---|---|---|---|
| PI-HA-EMPC | reduced-order | none | 2.45 h | 1580 s | 816.46 kWh |
| PI-HA-EMPC | Simscape in loop | none | 2.38 h | 1340 s | 816.46 kWh |
| EMPC | reduced-order | at 2.85 h | – | 3020 s | 816.49 kWh |
| EMPC | Simscape in loop | at 2.85 h | – | 3020 s | 816.49 kWh |

**How closely the two models agree:**
- The DP is held at its 180 kPa setpoint in both.
- Mean loop flow differs by 0.1 %, and facility power by under 0.01 %.
- The trip transient differs: the flow dips to 4.32 L/s with Simscape against 4.66 L/s in the reduced model, which filters the flow. The planned changeover is bumpless in both.

**Why the changeover comes 4 min earlier with Simscape:** the trigger is sensitive to tiny perturbations, not the models disagreeing. Scaling the reduced-model flow by 1.001 moves its changeover to exactly 2.38 h / 1340 s. Changes of ±0.1–0.2 % shift it by up to ±5 min.

**Scope:** this covers the hydraulics only, in one scenario. The thermal side remains the reduced-order model.

## 2. E3b: which part of PI-HA-EMPC prevents the trips?

There are three new `DcxSupervisor` modes:

| Mode | What it keeps |
|---|---|
| `ha_noActions` | health inside the MPC only (HI-scaled move bounds and pre-cooling); no changeover or lead transfer |
| `ha_actionsOnly` | a health-blind MPC plus the discrete actions |
| `ha_none` | every health input off; a sanity check that must equal `empc` |

Run it:

```matlab
dcx_study('Plan',"ablation2",'Workers',0)      % 86 runs, about 25 min
```

Results are in `results/study/runs_ablation2.csv`. The summary is produced by `abl2.py`.

| Variant (both climates, both faults, 10 seeds) | Runs with an unplanned trip | Zone C/D exposure | Energy |
|---|---|---|---|
| EMPC | 34/40 | 25.1 min | 816.6 kWh |
| health in the MPC only | 34/40 | 25.1 min | 818.2 kWh (+0.2 %) |
| discrete actions only | 0/40 | 12.2 min | 816.3 kWh |
| full PI-HA-EMPC | 0/40 | 12.2 min | 816.4 kWh |

**Sanity check:** `ha_none` reproduced EMPC exactly in all 6 paired runs.

**Conclusion:** in these scenarios all of the trip avoidance comes from the health-triggered supervisory actions. The health terms inside the MPC gave no protection. In one marginal case (Frankfurt, chiller fault, seed 4), the HI-scaled move bounds without pre-cooling contributed to a trip that the actions-only variant avoided.

The paper is updated accordingly: abstract, §6 credibility, §7.3 with the E3b subsection, Table 6, Figures 1 and 5, discussion, limitations and conclusions. The previous version is kept as `paper/main_before_E3b.tex`.
