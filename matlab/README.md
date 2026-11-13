# DATACORE-X — Health-aware economic MPC for data-centre cooling (MATLAB/Simulink)

MathWorks Excellence in Innovation project **#196 Optimal Data Center Cooling**. The DATACORE-X research platform extends it.

> All results come from simulation of a hypothetical 8-rack facility. Component parameters are design assumptions or have been calibrated against public reference data, as stated below. Nothing here has been validated against a physical plant.

## Problem statement

Data-centre cooling has to keep IT inlet air inside the ASHRAE recommended envelope (≤ 27 °C) at minimum energy and carbon. Conventional thermostatic control holds fixed, conservative setpoints and ignores the condition of the equipment. When a pump bearing or a chiller degrades, the result is either wasted energy or an unplanned trip.

## Solution approach

| Layer | MATLAB / Simulink implementation |
|---|---|
| Facility plant | `DCX_Facility.slx`: Simulink model built programmatically by `model/dcx_build_model.m`. Subsystems: IT racks (thermal RC), air side (4 CRAH, plenum, contained cold aisle, recirculation), CHW hydraulics (parallel pumps vs. valve-dependent system curve), CHW plant (economiser HX, 2 chillers with Carnot-fraction map, 2 cooling towers), electrical (transformer, generator/ATS, 2N UPS + Li-ion strings, A/B PDUs), CO₂ accounting |
| Control & sequencing | **Stateflow chart `ATS_Sequence`** (parallel Generator / ATS state machines, authoritative for bus and generator state) feeding the PLC subsystem (trips, UPS modes, duty/standby pumps, chiller lead/lag with 180 s start-up, interlocked operator commands) and 7 Discrete PID Controller blocks (baseline) |
| Hydraulic validation | `simscape/DCX_CHW_Hydraulics_SSC.slx`: Simscape Fluids (Isothermal Liquid) CHW network (2 centrifugal pumps, isolation restrictions, 4 CRAH branches of DN40 pipe + coil + control valve) used to validate and recalibrate the reduced-order system curve |
| Instrumentation | Virtual-sensor subsystem producing the 217 registry data points with noise, quantisation, drift and failure (generated from the asset registry) |
| Fault injection | 21 fault types with incipient → severe ramps (`params/dcx_fault_table.m`) |
| Predictive maintenance | Physics-residual features, bagged-tree classifiers, Isolation Forest, and exponential / linear degradation-model RUL (Statistics & ML, Predictive Maintenance Toolbox) |
| Supervisory control | System-identified prediction model (`ssest` / `n4sid`, order chosen on held-out data), economic MPC (MPC Toolbox), and **PI-HA-EMPC**: health-scaled MV slew limits, RUL-triggered pre-cooling, and degradation-aware pump changeover / chiller pre-start + lead transfer |
| Digital-twin integration | `SCADA_Bridge` block (extrinsic): publishes to the DATACORE-X service (3D twin, historian, OPC UA, Ignition) and applies approved operator commands with PLC acknowledgement |

## Verification

* **Simulink vs. Python reference twin:** 42/42 checks pass over 6 scenarios × 7 signals, including the utility-outage scenario sequenced by the Stateflow chart. Mean error is below 0.001 K and below 0.01 % of power (`tests/dcx_xverify.m`; results in `tests/xverify_simulink_results.csv`).
* **MATLAB reference stepper vs. Python:** 42/42 checks pass (`tests/xverify_stepper_results.csv`). The stepper uses the same domain functions and is used for bulk data generation (about 8× faster).
* **Stateflow ATS chart vs. PLC logic:** `tests/dcx_test_ats_chart.m` drives the chart and the `dcx_plc` sequence with the same utility pattern. The pattern covers a long outage, a short outage before the generator is up, re-loss during cooldown, and re-loss during the retransfer wait. Result: 0 mismatches over 899 steps.
* **Reduced-order hydraulics vs. Simscape Fluids** (`simscape/dcx_validate_hydraulics.m`): 41 operating points, covering speed 0.5–1.0, 1–2 pumps, valve opening 0.15–1.0, and unequal valve sets.

  | System curve | Max flow error | RMS flow error | Max pump-dp error |
  |---|---|---|---|
  | Single-term, Δp − Hs = k₀/v² · q² (design profile, Python parity) | 14.3 % | 8.8 % | 6.5 kPa |
  | Two-term, Δp − Hs = (k_f + k_v/v²) · q², fitted to Simscape (calibrated profile) | 7.1 % | 1.6 % | 3.1 kPa |

  The single-term law scales pipe and coil losses with valve opening, so it under-predicts flow at part opening. The fitted values are k_f = 1.62 and k_v = 4.36 kPa/(L/s)², with k_f + k_v ≈ k₀ = 6.0. The remaining 7 % maximum error occurs with unequal valve openings, which the mean-opening aggregation cannot represent.
* **Live co-simulation:** the Simulink model drives the 3D twin through `/api/external/snapshot`. Operator commands round-trip through the Simulink PLC, including interlock rejections.

## Calibration (`params/dcx_calibrate.m`, then `simscape/dcx_validate_hydraulics`)

| Item | Reference | Result |
|---|---|---|
| Chiller map | ASHRAE 90.1 Table 6.8.1-3: water-cooled positive displacement < 75 tons, Path A, FL 0.750 and IPLV 0.600 kW/ton at AHRI 550/590 conditions | η_c = 0.511, part-load coefficient 0.552; both ratings reproduced exactly |
| Cooling-tower fan | ASHRAE 90.1 Table 6.8.1-7: propeller/axial open-circuit tower ≥ 40.2 gpm/hp at 95/85/75 °F | The tower's rated duty from the DCX approach model is 251 kW / 171 gpm per tower. The code-minimum fan for that duty is 3.53 kW. The previous 5.5 kW fan gave 25.8 gpm/hp, which is below the minimum. |
| CHW pumping | ASHRAE 90.1 Appendix G, G3.1.3.10: 22 W/gpm at design flow | Design point 93 gpm, 2.03 kW, 22.0 W/gpm; pump curve kept |
| CRAH fan | 90.1 fan power limitation, VAV Option 1: hp ≤ cfm × 0.0015 | 7,946 cfm per unit, allowance 8.9 kW, model 5.5 kW; compliant, kept |
| CHW system curve | Simscape Fluids network (above) | Two-term law, k_f = 1.62, k_v = 4.36 |
| Grid emission factor | CEA CO₂ Baseline Database v20.0 (Dec 2024), FY 2023-24 weighted average | 0.727 kg CO₂/kWh (was an assumed 0.716) |
| Ambient | Pune 2025 hourly dry bulb and RH from the Open-Meteo historical archive; wet bulb by Stull (2011) | Wet bulb max 25.5 °C, mean 19.2 °C |

`dcx_params('Profile',"calibrated")` applies all of these. `"design"` keeps exact parity with the Python twin.

## Key results

See `pdm/models/` and `control/results/<profile>/`.

**MPC prediction model** (`control/dcx_ident.m`; 48 h excitation, 70/30 split, held-out NRMSE fit):

* Calibrated profile: `ssest` order 4, with a fit of 83.6 % on max inlet and 74.8 % on facility power. The previous model (24 h, order 8) scored 78.7 % / 58.9 %.
* All candidates (orders 4–12, `ssest` and `n4sid`) scored within 1.5 points of each other. The improvement therefore comes from the longer record, not the model order (`control/ident_calibrated_log.txt`).
* Design profile: `n4sid` order 8, 77.1 % / 68.8 %.

**Supervisory control (6 h afternoon peak, +20 % IT ramp, mean of 3 seeds; calibrated profile):**

| Scenario | Controller | Facility energy (kWh) | Cooling energy (kWh) | CO₂ (kg) | PUE | Peak inlet (°C) | Time > 27 °C | Unplanned trips |
|---|---|---|---|---|---|---|---|---|
| normal | Baseline (fixed SP + PI) | 872.5 | 144.6 | 634.3 | 1.322 | 25.09 | 0 s | 0 |
| normal | EMPC | 846.5 | 118.8 | 615.4 | 1.283 | 26.61 | 0 s | 0 |
| normal | PI-HA-EMPC | 846.5 | 118.8 | 615.4 | 1.283 | 26.61 | 0 s | 0 |
| chiller degradation → trip | Baseline | 877.3 | 149.4 | 637.8 | 1.330 | 25.83 | 0 s | 1 |
| chiller degradation → trip | EMPC | 849.2 | 121.5 | 617.3 | 1.287 | 26.82 | 0 s | 1 |
| chiller degradation → trip | PI-HA-EMPC | 848.2 | 120.5 | 616.7 | 1.286 | 26.61 | 0 s | **0** |
| pump bearing → trip | Baseline | 872.5 | 144.7 | 634.3 | 1.322 | 25.09 | 0 s | 1 |
| pump bearing → trip | EMPC | 846.6 | 118.9 | 615.5 | 1.283 | 26.61 | 0 s | 1 |
| pump bearing → trip | PI-HA-EMPC | 846.6 | 118.9 | 615.5 | 1.283 | 26.61 | 0 s | **0** |

* **EMPC vs. the thermostatic baseline:**
  * Facility energy is 3.0 % lower, a saving of 25.9 kWh per 6 h. Paired by seed, all three seeds fall within ±0.2 kWh of this.
  * Cooling energy is 17.8 % lower.
  * CO₂ is 18.9 kg lower per 6 h, at 0.727 kg/kWh.
  * Rack inlet stays ≤ 27 °C throughout.
* **PI-HA-EMPC vs. EMPC:**
  * The unplanned trip is avoided in both fault scenarios: by a pump changeover, and by a chiller pre-start followed by a lead transfer.
  * In the chiller scenario it also uses 0.95 kWh less (paired, consistent across seeds) and the peak inlet is 0.21 K lower.
  * In the pump scenario the energy difference is negligible.
* The between-seed standard deviation of energy is about 12.5 kWh. It comes from the seed-dependent IT load, so comparisons are paired by seed.
* Design profile (Python-parity plant): EMPC reduces facility energy by 3.9 % and cooling energy by 23.9 % (normal scenario), with the same trip-avoidance result (`control/results/design/`).

**Fault diagnosis (held-out runs, split by run; 120 runs; design profile):**

| Asset class | Sensor-only macro-F1 | Sensor + physics-residual macro-F1 | Rule-based estimator v0 | Isolation Forest recall / specificity |
|---|---|---|---|---|
| CHW pumps (F01, F02, efficiency) | 0.993 | **1.000** | 0.907 | 0.25 / 0.99 |
| CRAH fans (F03, F04, blockage) | 0.955 | **0.991** | 0.831 | 0.78 / 0.996 |
| Chiller / HX / towers (F06, F05, F07) | 0.639 | **0.981** | 0.973 | 0.01 / 0.997 |

**RUL (pump bearing, failure = 7.1 mm/s, 4 held-out run-to-failure runs):** the exponential degradation model gives RMSE 18.5 min (13.5 min over the last half of life) with 90 % CI coverage of 0.97. The linear model gives RMSE 18.0 min with coverage 0.89.

## Repository structure

```
matlab/
  params/   dcx_params, dcx_fault_table, dcx_initial_state, dcx_calibrate (+ dcx_calibration.mat)
  plant/    dcx_racks, dcx_air, dcx_hydraulics, dcx_chwplant, dcx_electrical,
            dcx_plc, dcx_faults, dcx_disturbance, dcx_sensors (generated), dcx_sim_matlab
  model/    dcx_build_model, dcx_add_ats_chart (Stateflow), dcx_model_data, dcx_run_model, DCX_Facility.slx
  simscape/ dcx_build_hydraulics_ssc, dcx_validate_hydraulics, DCX_CHW_Hydraulics_SSC.slx, results/
  bridge/   dcx_bridge_tick, dcx_live, dcx_start_backend
  pdm/      dcx_gen_dataset, dcx_features, dcx_train_models, dcx_rul
  control/  dcx_ident, dcx_design_mpc, DcxSupervisor, dcx_experiments
  tests/    dcx_xverify (+ Python reference traces, result CSVs), dcx_test_ats_chart
  docs/     model diagrams (top level, Stateflow chart, Simscape network)
```

## How to run

```matlab
cd matlab; dcx_startup                    % paths
dcx_build_model                           % builds DCX_Facility.slx
R = dcx_xverify(@(P,FT,T) dcx_run_model(P,FT,T));   % 42 verification checks
A = dcx_test_ats_chart;                   % Stateflow chart vs PLC logic
C = dcx_calibrate;                        % chiller, tower, pumps, CRAH, CEA factor, Pune weather
Rh = dcx_validate_hydraulics;             % Simscape Fluids check + system-curve fit (run design first)
Rh2 = dcx_validate_hydraulics('Profile',"calibrated");
D = dcx_gen_dataset; R6 = dcx_train_models; Rr = dcx_rul;
M = dcx_ident('Hours',48,'Method',"auto",'Orders',[4 6 8 10 12],'Profile',"calibrated");
Rc = dcx_experiments('Profile',"calibrated");
dcx_live('Speed',5)                       % live 3D twin at http://localhost:8000
```

## How generative AI was used

Claude (Anthropic) was used as an engineering assistant to draft and refactor the MATLAB/Python code, the build scripts and the verification tests, working against the author's specifications. Every result above was produced by running the code in MATLAB R2024a, and every claim was checked against those outputs. Errors found during this process are recorded in the commit history: for example, a numerical oscillation from actuator-free PI loops, a stale-risk bug in the health-aware supervisor, and an unrealistic instant standby-chiller start.

## Limitations

* Simulation only. The component models are reduced-order (multi-fidelity, blueprint §12). Simscape Fluids is used offline to validate and calibrate the CHW hydraulics; it is not part of the closed-loop plant.
* Calibration uses code-minimum and baseline reference values (ASHRAE 90.1 and Appendix G), not certified data for specific products. Replace them with AHRI-certified data sheets once equipment is selected.
* The identified MPC prediction model has a held-out fit of about 84 % for inlet temperature and about 75 % for power. The 0.2 K back-off on the inlet constraint covers this model error.
* The CO₂ account treats the generator as carbon-free; generator fuel is logged separately.
* Degradation is time-compressed, so RUL is reported in simulation minutes.
* The diagnosis task is easier in simulation than in the field: the plant is deterministic apart from sensor noise.
