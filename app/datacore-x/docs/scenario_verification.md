# DATACORE-X scenario and physics cross-verification

Generated 2026-11-10 17:51 against http://localhost:8000; horizon 1800 s per what-if; values are the twin's published (measured) values.

**Result: 670/670 checks pass.**

## Scenarios

| ID | Scenario | Parameters (defaults) | Checks passed |
|---|---|---|---|
| S01 | Increase IT workload | {"increase_pct": 40.0, "ramp_s": 300.0} | 40/40 |
| S02 | Simulate rack overheating | {"rack": "R-06", "extra_kw": 6.0, "ramp_s": 120.0} | 40/40 |
| S03 | Reduce pump efficiency | {"pump": "P-01", "drop_pct": 25.0, "ramp_s": 600.0} | 40/40 |
| S04 | Introduce pump cavitation | {"pump": "P-01", "severity": 0.8, "ramp_s": 600.0} | 38/38 |
| S05 | Disable a CRAH unit | {"crah": "CRAH-02"} | 40/40 |
| S06 | Degrade chiller performance | {"chiller": "CH-01", "severity": 0.8, "ramp_s": 900.0} | 39/39 |
| S07 | Simulate utility power failure | {"duration_s": 600.0} | 42/42 |
| S08 | Switch to UPS (battery) operation | {"scope": "DCX", "duration_s": 900.0} | 40/40 |
| S09 | Introduce battery degradation | {"battery": "BAT-A", "severity": 0.8, "discharge_test": true} | 40/40 |
| S10 | Change workload placement | {"strategy": "concentrate_row_a"} | 39/39 |
| S11 | Pump bearing degradation (flagship) | {"pump": "P-01", "severity": 0.9, "ramp_s": 1200.0} | 39/39 |
| S12 | Heat-exchanger fouling | {"severity": 0.8, "ramp_s": 600.0} | 39/39 |
| S13 | Cooling-tower degradation | {"tower": "CT-01", "severity": 0.8, "ramp_s": 600.0} | 38/38 |
| S14 | Rack inlet sensor drift | {"rack": "R-03", "bias_k": 4.0, "ramp_s": 300.0} | 39/39 |
| S15 | CRAH fan imbalance | {"crah": "CRAH-01", "severity": 0.8, "ramp_s": 600.0} | 40/40 |
| S16 | Cooling pump failure (trip) | {"pump": "P-01"} | 41/41 |

## Live twin physics (36/36)

| Check | Result | Detail |
|---|---|---|
| IT load = sum of rack power | pass | 94.428 vs 94.540 kW (err 0.1 %, tol 3 %) |
| R-01 heat = electrical power | pass | 11.880 vs 11.920 kW (|err| 0.040, tol 0.3) |
| R-02 heat = electrical power | pass | 12.580 vs 12.660 kW (|err| 0.080, tol 0.3) |
| R-03 heat = electrical power | pass | 12.650 vs 12.620 kW (|err| 0.030, tol 0.3) |
| R-04 heat = electrical power | pass | 11.030 vs 11.050 kW (|err| 0.020, tol 0.3) |
| R-05 heat = electrical power | pass | 11.190 vs 11.250 kW (|err| 0.060, tol 0.3) |
| R-06 heat = electrical power | pass | 12.100 vs 12.080 kW (|err| 0.020, tol 0.3) |
| R-07 heat = electrical power | pass | 10.470 vs 10.470 kW (|err| 0.000, tol 0.3) |
| R-08 heat = electrical power | pass | 12.400 vs 12.490 kW (|err| 0.090, tol 0.3) |
| R-01 outlet - inlet = Q/(m cp) | pass | 12.000 vs 11.701 K (|err| 0.299, tol 1.5) |
| R-02 outlet - inlet = Q/(m cp) | pass | 11.880 vs 11.842 K (|err| 0.038, tol 1.5) |
| R-03 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.748 K (|err| 0.202, tol 1.5) |
| R-04 outlet - inlet = Q/(m cp) | pass | 11.970 vs 11.835 K (|err| 0.135, tol 1.5) |
| R-05 outlet - inlet = Q/(m cp) | pass | 11.850 vs 11.869 K (|err| 0.019, tol 1.5) |
| R-06 outlet - inlet = Q/(m cp) | pass | 11.870 vs 12.018 K (|err| 0.148, tol 1.5) |
| R-07 outlet - inlet = Q/(m cp) | pass | 11.760 vs 11.610 K (|err| 0.150, tol 1.5) |
| R-08 outlet - inlet = Q/(m cp) | pass | 11.840 vs 11.875 K (|err| 0.035, tol 1.5) |
| CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.100 vs 25.775 kW (err 2.6 %, tol 15 %) |
| CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.466 kW (err 0.6 %, tol 15 %) |
| CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.000 vs 26.024 kW (err 3.9 %, tol 15 %) |
| CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.721 kW (err 1.6 %, tol 15 %) |
| P-01 shaft power = q H / eta | pass | 0.570 vs 0.553 kW (err 3.1 %, tol 10 %) |
| P-02 shaft power = q H / eta | pass | 0.570 vs 0.561 kW (err 1.5 %, tol 10 %) |
| CH-01 power = load / COP | pass | 6.900 vs 6.868 kW (err 0.5 %, tol 6 %) |
| CH-01 COP plausible (2-12) | pass | COP 8.59 |
| cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.718 vs 12.720 kW (err 0.0 %, tol 8 %) |
| facility power = IT + cooling + losses + lighting | pass | 117.715 vs 117.715 kW (err 0.0 %, tol 2 %) |
| PUE = facility / IT | pass | 1.247 vs 1.247  (err 0.0 %, tol 1 %) |
| PUE plausible (1.0-2.5) | pass | PUE 1.247 |
| max inlet = max rack inlet | pass | 25.027 vs 25.100 °C (|err| 0.073, tol 0.4) |
| CHW plant duty = rho cp q (Tr - Ts) | pass | 100.600 vs 100.676 kW (err 0.1 %, tol 15 %) |
| CRAH coil duty = CHW plant duty (quasi-steady) | pass | 100.700 vs 100.600 kW (err 0.1 %, tol 20 %) |
| PDU A + B load = IT load | pass | 94.440 vs 94.428 kW (err 0.0 %, tol 5 %) |
| CT-01 approach plausible (0.5-10 K) | pass | 4.56 K |
| CT-02 approach plausible (0.5-10 K) | pass | 4.59 K |
| all key temperatures finite and in 5-60 °C | pass | min 18.0, max 36.9 °C |

## Scenario checks

| Scope | Check | Result | Detail |
|---|---|---|---|
| S01 | IT load increased (>= +20 % at end) | pass | 93.9 -> 120.9 kW |
| S01 | cooling power increased | pass | 12.8 -> 15.8 kW |
| S01 | facility power increased by more than IT increase x 1.0 | pass | dFac 31.3 kW vs dIT 27.0 kW |
| S01 | baseline branch free of this scenario's faults | pass | isolation |
| S01/physics | IT load = sum of rack power | pass | 120.879 vs 120.810 kW (err 0.1 %, tol 3 %) |
| S01/physics | R-01 heat = electrical power | pass | 15.540 vs 15.550 kW (|err| 0.010, tol 0.3) |
| S01/physics | R-02 heat = electrical power | pass | 15.960 vs 16.000 kW (|err| 0.040, tol 0.3) |
| S01/physics | R-03 heat = electrical power | pass | 15.340 vs 15.330 kW (|err| 0.010, tol 0.3) |
| S01/physics | R-04 heat = electrical power | pass | 14.300 vs 14.400 kW (|err| 0.100, tol 0.3) |
| S01/physics | R-05 heat = electrical power | pass | 14.600 vs 14.530 kW (|err| 0.070, tol 0.3) |
| S01/physics | R-06 heat = electrical power | pass | 15.960 vs 16.030 kW (|err| 0.070, tol 0.3) |
| S01/physics | R-07 heat = electrical power | pass | 13.330 vs 13.190 kW (|err| 0.140, tol 0.3) |
| S01/physics | R-08 heat = electrical power | pass | 15.670 vs 15.780 kW (|err| 0.110, tol 0.3) |
| S01/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.000 vs 11.713 K (|err| 0.287, tol 1.5) |
| S01/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.140 vs 11.846 K (|err| 0.294, tol 1.5) |
| S01/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.080 vs 11.821 K (|err| 0.259, tol 1.5) |
| S01/physics | R-04 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.775 K (|err| 0.175, tol 1.5) |
| S01/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.130 vs 11.951 K (|err| 0.179, tol 1.5) |
| S01/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.060 vs 11.597 K (|err| 0.463, tol 1.5) |
| S01/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.950 vs 12.055 K (|err| 0.105, tol 1.5) |
| S01/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.910 vs 11.694 K (|err| 0.216, tol 1.5) |
| S01/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 32.200 vs 32.477 kW (err 0.9 %, tol 15 %) |
| S01/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 32.300 vs 33.041 kW (err 2.2 %, tol 15 %) |
| S01/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 32.000 vs 33.330 kW (err 4.0 %, tol 15 %) |
| S01/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 32.200 vs 32.422 kW (err 0.7 %, tol 15 %) |
| S01/physics | P-01 shaft power = q H / eta | pass | 0.570 vs 0.568 kW (err 0.3 %, tol 10 %) |
| S01/physics | P-02 shaft power = q H / eta | pass | 0.550 vs 0.574 kW (err 4.1 %, tol 10 %) |
| S01/physics | CH-01 power = load / COP | pass | 8.000 vs 7.976 kW (err 0.3 %, tol 6 %) |
| S01/physics | CH-01 COP plausible (2-12) | pass | COP 8.40 |
| S01/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 15.775 vs 15.770 kW (err 0.0 %, tol 8 %) |
| S01/physics | facility power = IT + cooling + losses + lighting | pass | 148.556 vs 148.556 kW (err 0.0 %, tol 2 %) |
| S01/physics | PUE = facility / IT | pass | 1.229 vs 1.229  (err 0.0 %, tol 1 %) |
| S01/physics | PUE plausible (1.0-2.5) | pass | PUE 1.229 |
| S01/physics | max inlet = max rack inlet | pass | 25.020 vs 25.020 °C (|err| 0.000, tol 0.4) |
| S01/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 129.600 vs 129.743 kW (err 0.1 %, tol 15 %) |
| S01/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 128.700 vs 129.600 kW (err 0.7 %, tol 20 %) |
| S01/physics | PDU A + B load = IT load | pass | 120.760 vs 120.879 kW (err 0.1 %, tol 5 %) |
| S01/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.24 K |
| S01/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.42 K |
| S01/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S02 | R-06 power +6 kW | pass | 6.030 vs 6.000 kW (|err| 0.030, tol 1.5) |
| S02 | R-06 inlet rises (recirculation) | pass | 24.80 -> 27.81 °C |
| S02 | R-06 outlet rises | pass | 36.75 -> 39.79 °C |
| S02 | baseline branch free of this scenario's faults | pass | isolation |
| S02/physics | IT load = sum of rack power | pass | 100.041 vs 100.070 kW (err 0.0 %, tol 3 %) |
| S02/physics | R-01 heat = electrical power | pass | 11.980 vs 11.870 kW (|err| 0.110, tol 0.3) |
| S02/physics | R-02 heat = electrical power | pass | 12.880 vs 12.880 kW (|err| 0.000, tol 0.3) |
| S02/physics | R-03 heat = electrical power | pass | 11.900 vs 11.980 kW (|err| 0.080, tol 0.3) |
| S02/physics | R-04 heat = electrical power | pass | 11.070 vs 11.110 kW (|err| 0.040, tol 0.3) |
| S02/physics | R-05 heat = electrical power | pass | 11.370 vs 11.230 kW (|err| 0.140, tol 0.3) |
| S02/physics | R-06 heat = electrical power | pass | 18.420 vs 18.550 kW (|err| 0.130, tol 0.3) |
| S02/physics | R-07 heat = electrical power | pass | 10.330 vs 10.240 kW (|err| 0.090, tol 0.3) |
| S02/physics | R-08 heat = electrical power | pass | 12.180 vs 12.210 kW (|err| 0.030, tol 0.3) |
| S02/physics | R-01 outlet - inlet = Q/(m cp) | pass | 11.970 vs 11.661 K (|err| 0.309, tol 1.5) |
| S02/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.140 vs 11.921 K (|err| 0.219, tol 1.5) |
| S02/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.100 vs 11.597 K (|err| 0.503, tol 1.5) |
| S02/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.130 vs 11.578 K (|err| 0.552, tol 1.5) |
| S02/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.050 vs 11.847 K (|err| 0.203, tol 1.5) |
| S02/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.980 vs 11.949 K (|err| 0.031, tol 1.5) |
| S02/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.000 vs 11.835 K (|err| 0.165, tol 1.5) |
| S02/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.990 vs 11.926 K (|err| 0.064, tol 1.5) |
| S02/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 27.500 vs 27.570 kW (err 0.3 %, tol 15 %) |
| S02/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 27.200 vs 27.341 kW (err 0.5 %, tol 15 %) |
| S02/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 27.300 vs 28.630 kW (err 4.6 %, tol 15 %) |
| S02/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 27.400 vs 28.378 kW (err 3.4 %, tol 15 %) |
| S02/physics | P-01 shaft power = q H / eta | pass | 0.450 vs 0.447 kW (err 0.8 %, tol 10 %) |
| S02/physics | P-02 shaft power = q H / eta | pass | 0.440 vs 0.451 kW (err 2.3 %, tol 10 %) |
| S02/physics | CH-01 power = load / COP | pass | 6.200 vs 6.199 kW (err 0.0 %, tol 6 %) |
| S02/physics | CH-01 COP plausible (2-12) | pass | COP 8.05 |
| S02/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 32.739 vs 32.620 kW (err 0.4 %, tol 8 %) |
| S02/physics | facility power = IT + cooling + losses + lighting | pass | 143.725 vs 143.725 kW (err 0.0 %, tol 2 %) |
| S02/physics | PUE = facility / IT | pass | 1.437 vs 1.437  (err 0.0 %, tol 1 %) |
| S02/physics | PUE plausible (1.0-2.5) | pass | PUE 1.437 |
| S02/physics | max inlet = max rack inlet | pass | 27.825 vs 27.810 °C (|err| 0.015, tol 0.4) |
| S02/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 109.500 vs 110.555 kW (err 1.0 %, tol 15 %) |
| S02/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 109.400 vs 109.500 kW (err 0.1 %, tol 20 %) |
| S02/physics | PDU A + B load = IT load | pass | 100.350 vs 100.041 kW (err 0.3 %, tol 5 %) |
| S02/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.30 K |
| S02/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.25 K |
| S02/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 39.8 °C |
| S03 | P-01 efficiency drop ~25 % | pass | 0.250 vs 0.250  (|err| 0.000, tol 0.05) |
| S03 | P-01 power increases | pass | 0.57 -> 0.76 kW |
| S03 | loop flow essentially unchanged | pass | 3.450 vs 3.450 L/s (|err| 0.000, tol 0.4) |
| S03 | baseline branch free of this scenario's faults | pass | isolation |
| S03/physics | IT load = sum of rack power | pass | 93.999 vs 93.710 kW (err 0.3 %, tol 3 %) |
| S03/physics | R-01 heat = electrical power | pass | 12.090 vs 11.950 kW (|err| 0.140, tol 0.3) |
| S03/physics | R-02 heat = electrical power | pass | 12.870 vs 12.830 kW (|err| 0.040, tol 0.3) |
| S03/physics | R-03 heat = electrical power | pass | 11.900 vs 11.900 kW (|err| 0.000, tol 0.3) |
| S03/physics | R-04 heat = electrical power | pass | 10.940 vs 11.030 kW (|err| 0.090, tol 0.3) |
| S03/physics | R-05 heat = electrical power | pass | 11.150 vs 11.210 kW (|err| 0.060, tol 0.3) |
| S03/physics | R-06 heat = electrical power | pass | 12.450 vs 12.470 kW (|err| 0.020, tol 0.3) |
| S03/physics | R-07 heat = electrical power | pass | 10.300 vs 10.190 kW (|err| 0.110, tol 0.3) |
| S03/physics | R-08 heat = electrical power | pass | 12.170 vs 12.130 kW (|err| 0.040, tol 0.3) |
| S03/physics | R-01 outlet - inlet = Q/(m cp) | pass | 11.950 vs 12.081 K (|err| 0.131, tol 1.5) |
| S03/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.767 K (|err| 0.183, tol 1.5) |
| S03/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.040 vs 11.693 K (|err| 0.347, tol 1.5) |
| S03/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.120 vs 11.413 K (|err| 0.707, tol 1.5) |
| S03/physics | R-05 outlet - inlet = Q/(m cp) | pass | 11.960 vs 11.545 K (|err| 0.415, tol 1.5) |
| S03/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.920 vs 11.627 K (|err| 0.293, tol 1.5) |
| S03/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.850 vs 11.834 K (|err| 0.016, tol 1.5) |
| S03/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.970 vs 12.001 K (|err| 0.031, tol 1.5) |
| S03/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.400 vs 25.317 kW (err 0.3 %, tol 15 %) |
| S03/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.677 kW (err 1.5 %, tol 15 %) |
| S03/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.200 vs 25.632 kW (err 1.7 %, tol 15 %) |
| S03/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.976 kW (err 2.6 %, tol 15 %) |
| S03/physics | P-01 shaft power = q H / eta | pass | 0.760 vs 0.765 kW (err 0.7 %, tol 10 %) |
| S03/physics | P-02 shaft power = q H / eta | pass | 0.560 vs 0.561 kW (err 0.2 %, tol 10 %) |
| S03/physics | CH-01 power = load / COP | pass | 6.900 vs 6.966 kW (err 0.9 %, tol 6 %) |
| S03/physics | CH-01 COP plausible (2-12) | pass | COP 8.57 |
| S03/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 13.045 vs 13.000 kW (err 0.3 %, tol 8 %) |
| S03/physics | facility power = IT + cooling + losses + lighting | pass | 117.594 vs 117.594 kW (err 0.0 %, tol 2 %) |
| S03/physics | PUE = facility / IT | pass | 1.251 vs 1.251  (err 0.0 %, tol 1 %) |
| S03/physics | PUE plausible (1.0-2.5) | pass | PUE 1.251 |
| S03/physics | max inlet = max rack inlet | pass | 25.035 vs 25.020 °C (|err| 0.015, tol 0.4) |
| S03/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.200 vs 101.771 kW (err 0.6 %, tol 15 %) |
| S03/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 101.200 vs 101.200 kW (err 0.0 %, tol 20 %) |
| S03/physics | PDU A + B load = IT load | pass | 93.740 vs 93.999 kW (err 0.3 %, tol 5 %) |
| S03/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.10 K |
| S03/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.24 K |
| S03/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S04 | P-01 vibration increases (broadband) | pass | 1.58 -> 4.72 mm/s |
| S04 | P-01 delivered flow reduced (head loss) | pass | 1.72 -> 0.00 L/s |
| S04 | baseline branch free of this scenario's faults | pass | isolation |
| S04/physics | IT load = sum of rack power | pass | 93.797 vs 93.820 kW (err 0.0 %, tol 3 %) |
| S04/physics | R-01 heat = electrical power | pass | 11.830 vs 11.880 kW (|err| 0.050, tol 0.3) |
| S04/physics | R-02 heat = electrical power | pass | 12.860 vs 12.850 kW (|err| 0.010, tol 0.3) |
| S04/physics | R-03 heat = electrical power | pass | 11.830 vs 11.810 kW (|err| 0.020, tol 0.3) |
| S04/physics | R-04 heat = electrical power | pass | 11.090 vs 11.180 kW (|err| 0.090, tol 0.3) |
| S04/physics | R-05 heat = electrical power | pass | 11.120 vs 11.090 kW (|err| 0.030, tol 0.3) |
| S04/physics | R-06 heat = electrical power | pass | 12.580 vs 12.490 kW (|err| 0.090, tol 0.3) |
| S04/physics | R-07 heat = electrical power | pass | 10.330 vs 10.340 kW (|err| 0.010, tol 0.3) |
| S04/physics | R-08 heat = electrical power | pass | 12.190 vs 12.180 kW (|err| 0.010, tol 0.3) |
| S04/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.020 vs 11.878 K (|err| 0.142, tol 1.5) |
| S04/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.910 vs 11.850 K (|err| 0.060, tol 1.5) |
| S04/physics | R-03 outlet - inlet = Q/(m cp) | pass | 11.930 vs 11.821 K (|err| 0.109, tol 1.5) |
| S04/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.000 vs 11.763 K (|err| 0.237, tol 1.5) |
| S04/physics | R-05 outlet - inlet = Q/(m cp) | pass | 11.990 vs 11.809 K (|err| 0.181, tol 1.5) |
| S04/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.100 vs 11.923 K (|err| 0.177, tol 1.5) |
| S04/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.100 vs 11.868 K (|err| 0.232, tol 1.5) |
| S04/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.714 K (|err| 0.236, tol 1.5) |
| S04/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.400 vs 25.270 kW (err 0.5 %, tol 15 %) |
| S04/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 25.380 kW (err 0.5 %, tol 15 %) |
| S04/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.000 vs 26.012 kW (err 3.9 %, tol 15 %) |
| S04/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.200 vs 26.283 kW (err 4.1 %, tol 15 %) |
| S04/physics | P-02 shaft power = q H / eta | pass | 0.880 vs 0.877 kW (err 0.3 %, tol 10 %) |
| S04/physics | CH-01 power = load / COP | pass | 6.900 vs 7.006 kW (err 1.5 %, tol 6 %) |
| S04/physics | CH-01 COP plausible (2-12) | pass | COP 8.55 |
| S04/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.632 vs 12.550 kW (err 0.7 %, tol 8 %) |
| S04/physics | facility power = IT + cooling + losses + lighting | pass | 116.967 vs 116.967 kW (err 0.0 %, tol 2 %) |
| S04/physics | PUE = facility / IT | pass | 1.247 vs 1.247  (err 0.0 %, tol 1 %) |
| S04/physics | PUE plausible (1.0-2.5) | pass | PUE 1.247 |
| S04/physics | max inlet = max rack inlet | pass | 25.040 vs 25.040 °C (|err| 0.000, tol 0.4) |
| S04/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.900 vs 100.972 kW (err 0.9 %, tol 15 %) |
| S04/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 101.100 vs 101.900 kW (err 0.8 %, tol 20 %) |
| S04/physics | PDU A + B load = IT load | pass | 94.050 vs 93.797 kW (err 0.3 %, tol 5 %) |
| S04/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.18 K |
| S04/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.12 K |
| S04/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S05 | CRAH-02 tripped / stopped | pass | state TRIPPED, fan 0.00 kW |
| S05 | remaining CRAH fans speed up | pass | 39.4 -> 53.4 % |
| S05 | max rack inlet held at/below 27 °C by the fan-trim loop | pass | 25.04 -> 24.98 °C |
| S05 | remaining coils absorb the duty | pass | 102.000 vs 101.200 kW (err 0.8 %, tol 15 %) |
| S05 | baseline branch free of this scenario's faults | pass | isolation |
| S05/physics | IT load = sum of rack power | pass | 94.792 vs 94.900 kW (err 0.1 %, tol 3 %) |
| S05/physics | R-01 heat = electrical power | pass | 11.750 vs 11.780 kW (|err| 0.030, tol 0.3) |
| S05/physics | R-02 heat = electrical power | pass | 12.630 vs 12.450 kW (|err| 0.180, tol 0.3) |
| S05/physics | R-03 heat = electrical power | pass | 12.570 vs 12.450 kW (|err| 0.120, tol 0.3) |
| S05/physics | R-04 heat = electrical power | pass | 11.110 vs 10.990 kW (|err| 0.120, tol 0.3) |
| S05/physics | R-05 heat = electrical power | pass | 11.350 vs 11.360 kW (|err| 0.010, tol 0.3) |
| S05/physics | R-06 heat = electrical power | pass | 12.290 vs 12.350 kW (|err| 0.060, tol 0.3) |
| S05/physics | R-07 heat = electrical power | pass | 10.650 vs 10.640 kW (|err| 0.010, tol 0.3) |
| S05/physics | R-08 heat = electrical power | pass | 12.930 vs 12.880 kW (|err| 0.050, tol 0.3) |
| S05/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.060 vs 11.685 K (|err| 0.375, tol 1.5) |
| S05/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.840 vs 11.930 K (|err| 0.090, tol 1.5) |
| S05/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.110 vs 11.900 K (|err| 0.210, tol 1.5) |
| S05/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.060 vs 11.906 K (|err| 0.154, tol 1.5) |
| S05/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.110 vs 11.723 K (|err| 0.387, tol 1.5) |
| S05/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.920 vs 11.879 K (|err| 0.041, tol 1.5) |
| S05/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.150 vs 11.716 K (|err| 0.434, tol 1.5) |
| S05/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.020 vs 11.941 K (|err| 0.079, tol 1.5) |
| S05/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 34.100 vs 34.428 kW (err 1.0 %, tol 15 %) |
| S05/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 33.900 vs 34.443 kW (err 1.6 %, tol 15 %) |
| S05/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 34.000 vs 35.335 kW (err 3.8 %, tol 15 %) |
| S05/physics | P-01 shaft power = q H / eta | pass | 0.550 vs 0.532 kW (err 3.4 %, tol 10 %) |
| S05/physics | P-02 shaft power = q H / eta | pass | 0.550 vs 0.543 kW (err 1.4 %, tol 10 %) |
| S05/physics | CH-01 power = load / COP | pass | 6.700 vs 6.826 kW (err 1.8 %, tol 6 %) |
| S05/physics | CH-01 COP plausible (2-12) | pass | COP 8.38 |
| S05/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 13.819 vs 13.790 kW (err 0.2 %, tol 8 %) |
| S05/physics | facility power = IT + cooling + losses + lighting | pass | 119.203 vs 119.202 kW (err 0.0 %, tol 2 %) |
| S05/physics | PUE = facility / IT | pass | 1.258 vs 1.258  (err 0.0 %, tol 1 %) |
| S05/physics | PUE plausible (1.0-2.5) | pass | PUE 1.258 |
| S05/physics | max inlet = max rack inlet | pass | 24.977 vs 24.940 °C (|err| 0.037, tol 0.4) |
| S05/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 103.100 vs 103.015 kW (err 0.1 %, tol 15 %) |
| S05/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.000 vs 103.100 kW (err 1.1 %, tol 20 %) |
| S05/physics | PDU A + B load = IT load | pass | 95.420 vs 94.792 kW (err 0.7 %, tol 5 %) |
| S05/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.12 K |
| S05/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.19 K |
| S05/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S06 | CH-01 COP reduced (severity 0.8 -> expected about -24 %) | pass | COP 8.60 -> 6.54 (-24 %) |
| S06 | chiller electrical power increases | pass | 7.00 -> 9.10 kW |
| S06 | baseline branch free of this scenario's faults | pass | isolation |
| S06/physics | IT load = sum of rack power | pass | 93.982 vs 93.890 kW (err 0.1 %, tol 3 %) |
| S06/physics | R-01 heat = electrical power | pass | 11.940 vs 11.930 kW (|err| 0.010, tol 0.3) |
| S06/physics | R-02 heat = electrical power | pass | 13.000 vs 12.980 kW (|err| 0.020, tol 0.3) |
| S06/physics | R-03 heat = electrical power | pass | 12.030 vs 11.910 kW (|err| 0.120, tol 0.3) |
| S06/physics | R-04 heat = electrical power | pass | 11.110 vs 11.120 kW (|err| 0.010, tol 0.3) |
| S06/physics | R-05 heat = electrical power | pass | 11.000 vs 10.890 kW (|err| 0.110, tol 0.3) |
| S06/physics | R-06 heat = electrical power | pass | 12.410 vs 12.500 kW (|err| 0.090, tol 0.3) |
| S06/physics | R-07 heat = electrical power | pass | 10.340 vs 10.330 kW (|err| 0.010, tol 0.3) |
| S06/physics | R-08 heat = electrical power | pass | 12.260 vs 12.230 kW (|err| 0.030, tol 0.3) |
| S06/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.060 vs 11.747 K (|err| 0.313, tol 1.5) |
| S06/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.840 vs 11.979 K (|err| 0.139, tol 1.5) |
| S06/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.080 vs 11.821 K (|err| 0.259, tol 1.5) |
| S06/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.090 vs 11.875 K (|err| 0.215, tol 1.5) |
| S06/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.090 vs 11.697 K (|err| 0.393, tol 1.5) |
| S06/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.060 vs 11.629 K (|err| 0.431, tol 1.5) |
| S06/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.970 vs 12.013 K (|err| 0.043, tol 1.5) |
| S06/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.960 vs 11.823 K (|err| 0.137, tol 1.5) |
| S06/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.596 kW (err 1.2 %, tol 15 %) |
| S06/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.200 vs 25.750 kW (err 2.1 %, tol 15 %) |
| S06/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.686 kW (err 1.5 %, tol 15 %) |
| S06/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.587 kW (err 1.1 %, tol 15 %) |
| S06/physics | P-01 shaft power = q H / eta | pass | 0.580 vs 0.559 kW (err 3.8 %, tol 10 %) |
| S06/physics | P-02 shaft power = q H / eta | pass | 0.580 vs 0.564 kW (err 2.9 %, tol 10 %) |
| S06/physics | CH-01 power = load / COP | pass | 9.100 vs 9.098 kW (err 0.0 %, tol 6 %) |
| S06/physics | CH-01 COP plausible (2-12) | pass | COP 6.54 |
| S06/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 15.080 vs 15.080 kW (err 0.0 %, tol 8 %) |
| S06/physics | facility power = IT + cooling + losses + lighting | pass | 119.621 vs 119.621 kW (err 0.0 %, tol 2 %) |
| S06/physics | PUE = facility / IT | pass | 1.273 vs 1.273  (err 0.0 %, tol 1 %) |
| S06/physics | PUE plausible (1.0-2.5) | pass | PUE 1.273 |
| S06/physics | max inlet = max rack inlet | pass | 25.037 vs 25.030 °C (|err| 0.007, tol 0.4) |
| S06/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.300 vs 101.252 kW (err 0.0 %, tol 15 %) |
| S06/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 101.100 vs 101.300 kW (err 0.2 %, tol 20 %) |
| S06/physics | PDU A + B load = IT load | pass | 93.670 vs 93.982 kW (err 0.3 %, tol 5 %) |
| S06/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.15 K |
| S06/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.11 K |
| S06/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S07 | utility lost -> bus on generator at some point | pass | source codes seen [0, 1, 2] |
| S07 | generator ran | pass | GEN-01 RUNNING seen |
| S07 | UPS batteries rode through the gap (SoC dipped) | pass | min SoC 99.1 % |
| S07 | IT load never interrupted | pass | min IT 94.6 kW |
| S07 | utility restored and retransferred by end | pass | end source 1 |
| S07 | baseline branch free of this scenario's faults | pass | isolation |
| S07/physics | IT load = sum of rack power | pass | 95.616 vs 95.590 kW (err 0.0 %, tol 3 %) |
| S07/physics | R-01 heat = electrical power | pass | 12.260 vs 12.340 kW (|err| 0.080, tol 0.3) |
| S07/physics | R-02 heat = electrical power | pass | 12.410 vs 12.490 kW (|err| 0.080, tol 0.3) |
| S07/physics | R-03 heat = electrical power | pass | 12.970 vs 12.970 kW (|err| 0.000, tol 0.3) |
| S07/physics | R-04 heat = electrical power | pass | 11.060 vs 11.030 kW (|err| 0.030, tol 0.3) |
| S07/physics | R-05 heat = electrical power | pass | 11.260 vs 11.190 kW (|err| 0.070, tol 0.3) |
| S07/physics | R-06 heat = electrical power | pass | 12.600 vs 12.520 kW (|err| 0.080, tol 0.3) |
| S07/physics | R-07 heat = electrical power | pass | 10.840 vs 10.730 kW (|err| 0.110, tol 0.3) |
| S07/physics | R-08 heat = electrical power | pass | 12.280 vs 12.320 kW (|err| 0.040, tol 0.3) |
| S07/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.000 vs 11.660 K (|err| 0.340, tol 1.5) |
| S07/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.160 vs 11.564 K (|err| 0.596, tol 1.5) |
| S07/physics | R-03 outlet - inlet = Q/(m cp) | pass | 11.990 vs 11.911 K (|err| 0.079, tol 1.5) |
| S07/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.160 vs 11.761 K (|err| 0.399, tol 1.5) |
| S07/physics | R-05 outlet - inlet = Q/(m cp) | pass | 11.940 vs 11.792 K (|err| 0.148, tol 1.5) |
| S07/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.910 vs 11.559 K (|err| 0.351, tol 1.5) |
| S07/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.960 vs 11.831 K (|err| 0.129, tol 1.5) |
| S07/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.842 K (|err| 0.108, tol 1.5) |
| S07/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.800 vs 25.928 kW (err 0.5 %, tol 15 %) |
| S07/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 26.468 kW (err 2.9 %, tol 15 %) |
| S07/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.812 kW (err 0.8 %, tol 15 %) |
| S07/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.800 vs 25.659 kW (err 0.5 %, tol 15 %) |
| S07/physics | P-01 shaft power = q H / eta | pass | 0.550 vs 0.573 kW (err 3.9 %, tol 10 %) |
| S07/physics | P-02 shaft power = q H / eta | pass | 0.580 vs 0.570 kW (err 1.7 %, tol 10 %) |
| S07/physics | CH-01 power = load / COP | pass | 7.000 vs 6.879 kW (err 1.8 %, tol 6 %) |
| S07/physics | CH-01 COP plausible (2-12) | pass | COP 8.62 |
| S07/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.966 vs 13.010 kW (err 0.3 %, tol 8 %) |
| S07/physics | facility power = IT + cooling + losses + lighting | pass | 119.212 vs 119.211 kW (err 0.0 %, tol 2 %) |
| S07/physics | PUE = facility / IT | pass | 1.247 vs 1.247  (err 0.0 %, tol 1 %) |
| S07/physics | PUE plausible (1.0-2.5) | pass | PUE 1.247 |
| S07/physics | max inlet = max rack inlet | pass | 25.035 vs 25.000 °C (|err| 0.035, tol 0.4) |
| S07/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.600 vs 101.818 kW (err 0.2 %, tol 15 %) |
| S07/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.900 vs 101.600 kW (err 1.3 %, tol 20 %) |
| S07/physics | PDU A + B load = IT load | pass | 95.590 vs 95.616 kW (err 0.0 %, tol 5 %) |
| S07/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.31 K |
| S07/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.20 K |
| S07/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S08 | batteries discharge | pass | min SoC 99.5 -> 59.6 % |
| S08 | UPS reported in battery mode | pass | UPS state BATTERY seen |
| S08 | IT load maintained | pass | min IT 93.7 kW |
| S08 | baseline branch free of this scenario's faults | pass | isolation |
| S08/physics | IT load = sum of rack power | pass | 94.034 vs 94.010 kW (err 0.0 %, tol 3 %) |
| S08/physics | R-01 heat = electrical power | pass | 12.000 vs 11.940 kW (|err| 0.060, tol 0.3) |
| S08/physics | R-02 heat = electrical power | pass | 12.840 vs 12.870 kW (|err| 0.030, tol 0.3) |
| S08/physics | R-03 heat = electrical power | pass | 12.020 vs 12.090 kW (|err| 0.070, tol 0.3) |
| S08/physics | R-04 heat = electrical power | pass | 11.070 vs 10.900 kW (|err| 0.170, tol 0.3) |
| S08/physics | R-05 heat = electrical power | pass | 11.000 vs 11.030 kW (|err| 0.030, tol 0.3) |
| S08/physics | R-06 heat = electrical power | pass | 12.470 vs 12.540 kW (|err| 0.070, tol 0.3) |
| S08/physics | R-07 heat = electrical power | pass | 10.280 vs 10.320 kW (|err| 0.040, tol 0.3) |
| S08/physics | R-08 heat = electrical power | pass | 12.280 vs 12.320 kW (|err| 0.040, tol 0.3) |
| S08/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.000 vs 12.005 K (|err| 0.005, tol 1.5) |
| S08/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.970 vs 11.612 K (|err| 0.358, tol 1.5) |
| S08/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.170 vs 11.853 K (|err| 0.317, tol 1.5) |
| S08/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.080 vs 11.652 K (|err| 0.428, tol 1.5) |
| S08/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.210 vs 11.818 K (|err| 0.392, tol 1.5) |
| S08/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.160 vs 11.698 K (|err| 0.462, tol 1.5) |
| S08/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.665 K (|err| 0.285, tol 1.5) |
| S08/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.080 vs 11.773 K (|err| 0.307, tol 1.5) |
| S08/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 25.885 kW (err 1.5 %, tol 15 %) |
| S08/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.400 vs 26.265 kW (err 3.3 %, tol 15 %) |
| S08/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 25.964 kW (err 2.6 %, tol 15 %) |
| S08/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 26.012 kW (err 2.0 %, tol 15 %) |
| S08/physics | P-01 shaft power = q H / eta | pass | 0.580 vs 0.572 kW (err 1.4 %, tol 10 %) |
| S08/physics | P-02 shaft power = q H / eta | pass | 0.580 vs 0.565 kW (err 2.7 %, tol 10 %) |
| S08/physics | CH-01 power = load / COP | pass | 7.000 vs 6.911 kW (err 1.3 %, tol 6 %) |
| S08/physics | CH-01 COP plausible (2-12) | pass | COP 8.61 |
| S08/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.881 vs 12.970 kW (err 0.7 %, tol 8 %) |
| S08/physics | facility power = IT + cooling + losses + lighting | pass | 117.513 vs 117.513 kW (err 0.0 %, tol 2 %) |
| S08/physics | PUE = facility / IT | pass | 1.250 vs 1.250  (err 0.0 %, tol 1 %) |
| S08/physics | PUE plausible (1.0-2.5) | pass | PUE 1.250 |
| S08/physics | max inlet = max rack inlet | pass | 25.027 vs 25.010 °C (|err| 0.017, tol 0.4) |
| S08/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.400 vs 101.015 kW (err 0.4 %, tol 15 %) |
| S08/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 101.700 vs 101.400 kW (err 0.3 %, tol 20 %) |
| S08/physics | PDU A + B load = IT load | pass | 94.000 vs 94.034 kW (err 0.0 %, tol 5 %) |
| S08/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.24 K |
| S08/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.12 K |
| S08/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.1 °C |
| S09 | BAT-A state of health reduced | pass | SoH 100.0 -> 68.0 % |
| S09 | BAT-A internal resistance increased | pass | 59.1 -> 137.3 mOhm |
| S09 | discharge test drew the battery down | pass | min SoC 17.8 % |
| S09 | baseline branch free of this scenario's faults | pass | isolation |
| S09/physics | IT load = sum of rack power | pass | 94.191 vs 94.270 kW (err 0.1 %, tol 3 %) |
| S09/physics | R-01 heat = electrical power | pass | 11.950 vs 11.900 kW (|err| 0.050, tol 0.3) |
| S09/physics | R-02 heat = electrical power | pass | 12.870 vs 12.960 kW (|err| 0.090, tol 0.3) |
| S09/physics | R-03 heat = electrical power | pass | 12.050 vs 11.960 kW (|err| 0.090, tol 0.3) |
| S09/physics | R-04 heat = electrical power | pass | 11.090 vs 11.040 kW (|err| 0.050, tol 0.3) |
| S09/physics | R-05 heat = electrical power | pass | 11.120 vs 11.140 kW (|err| 0.020, tol 0.3) |
| S09/physics | R-06 heat = electrical power | pass | 12.510 vs 12.510 kW (|err| 0.000, tol 0.3) |
| S09/physics | R-07 heat = electrical power | pass | 10.400 vs 10.440 kW (|err| 0.040, tol 0.3) |
| S09/physics | R-08 heat = electrical power | pass | 12.310 vs 12.320 kW (|err| 0.010, tol 0.3) |
| S09/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.170 vs 11.970 K (|err| 0.200, tol 1.5) |
| S09/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.950 vs 11.767 K (|err| 0.183, tol 1.5) |
| S09/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.240 vs 11.757 K (|err| 0.483, tol 1.5) |
| S09/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.220 vs 11.526 K (|err| 0.694, tol 1.5) |
| S09/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.080 vs 12.010 K (|err| 0.070, tol 1.5) |
| S09/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.010 vs 11.898 K (|err| 0.112, tol 1.5) |
| S09/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.020 vs 11.626 K (|err| 0.394, tol 1.5) |
| S09/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.090 vs 12.111 K (|err| 0.021, tol 1.5) |
| S09/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 26.338 kW (err 2.8 %, tol 15 %) |
| S09/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.894 kW (err 1.1 %, tol 15 %) |
| S09/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.300 vs 26.001 kW (err 2.7 %, tol 15 %) |
| S09/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.400 vs 25.164 kW (err 0.9 %, tol 15 %) |
| S09/physics | P-01 shaft power = q H / eta | pass | 0.560 vs 0.569 kW (err 1.6 %, tol 10 %) |
| S09/physics | P-02 shaft power = q H / eta | pass | 0.540 vs 0.563 kW (err 4.1 %, tol 10 %) |
| S09/physics | CH-01 power = load / COP | pass | 6.900 vs 6.919 kW (err 0.3 %, tol 6 %) |
| S09/physics | CH-01 COP plausible (2-12) | pass | COP 8.60 |
| S09/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.888 vs 12.800 kW (err 0.7 %, tol 8 %) |
| S09/physics | facility power = IT + cooling + losses + lighting | pass | 117.653 vs 117.652 kW (err 0.0 %, tol 2 %) |
| S09/physics | PUE = facility / IT | pass | 1.249 vs 1.249  (err 0.0 %, tol 1 %) |
| S09/physics | PUE plausible (1.0-2.5) | pass | PUE 1.249 |
| S09/physics | max inlet = max rack inlet | pass | 25.028 vs 25.020 °C (|err| 0.008, tol 0.4) |
| S09/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.100 vs 100.481 kW (err 0.6 %, tol 15 %) |
| S09/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 101.900 vs 101.100 kW (err 0.8 %, tol 20 %) |
| S09/physics | PDU A + B load = IT load | pass | 93.950 vs 94.191 kW (err 0.3 %, tol 5 %) |
| S09/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.29 K |
| S09/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.21 K |
| S09/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.1 °C |
| S10 | total IT load unchanged (placement only) | pass | 94.334 vs 94.334 kW (err 0.0 %, tol 5 %) |
| S10 | load moved onto R-01, R-02, R-03, R-04 | pass | x1.34 |
| S10 | baseline branch free of this scenario's faults | pass | isolation |
| S10/physics | IT load = sum of rack power | pass | 94.334 vs 94.170 kW (err 0.2 %, tol 3 %) |
| S10/physics | R-01 heat = electrical power | pass | 16.110 vs 15.910 kW (|err| 0.200, tol 0.3) |
| S10/physics | R-02 heat = electrical power | pass | 16.000 vs 15.990 kW (|err| 0.010, tol 0.3) |
| S10/physics | R-03 heat = electrical power | pass | 16.060 vs 15.990 kW (|err| 0.070, tol 0.3) |
| S10/physics | R-04 heat = electrical power | pass | 16.080 vs 15.940 kW (|err| 0.140, tol 0.3) |
| S10/physics | R-05 heat = electrical power | pass | 7.590 vs 7.590 kW (|err| 0.000, tol 0.3) |
| S10/physics | R-06 heat = electrical power | pass | 7.570 vs 7.580 kW (|err| 0.010, tol 0.3) |
| S10/physics | R-07 heat = electrical power | pass | 7.580 vs 7.640 kW (|err| 0.060, tol 0.3) |
| S10/physics | R-08 heat = electrical power | pass | 7.560 vs 7.530 kW (|err| 0.030, tol 0.3) |
| S10/physics | R-01 outlet - inlet = Q/(m cp) | pass | 11.930 vs 11.852 K (|err| 0.078, tol 1.5) |
| S10/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.010 vs 11.688 K (|err| 0.322, tol 1.5) |
| S10/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.050 vs 11.660 K (|err| 0.390, tol 1.5) |
| S10/physics | R-04 outlet - inlet = Q/(m cp) | pass | 11.960 vs 11.872 K (|err| 0.088, tol 1.5) |
| S10/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.040 vs 11.774 K (|err| 0.266, tol 1.5) |
| S10/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.070 vs 11.743 K (|err| 0.327, tol 1.5) |
| S10/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.990 vs 11.892 K (|err| 0.098, tol 1.5) |
| S10/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.110 vs 11.997 K (|err| 0.113, tol 1.5) |
| S10/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 26.600 vs 26.702 kW (err 0.4 %, tol 15 %) |
| S10/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 26.400 vs 26.990 kW (err 2.2 %, tol 15 %) |
| S10/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 26.600 vs 27.109 kW (err 1.9 %, tol 15 %) |
| S10/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 26.700 vs 27.169 kW (err 1.7 %, tol 15 %) |
| S10/physics | P-01 shaft power = q H / eta | pass | 0.560 vs 0.561 kW (err 0.2 %, tol 10 %) |
| S10/physics | P-02 shaft power = q H / eta | pass | 0.570 vs 0.565 kW (err 0.9 %, tol 10 %) |
| S10/physics | CH-01 power = load / COP | pass | 7.000 vs 7.121 kW (err 1.7 %, tol 6 %) |
| S10/physics | CH-01 COP plausible (2-12) | pass | COP 8.51 |
| S10/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 13.503 vs 13.460 kW (err 0.3 %, tol 8 %) |
| S10/physics | facility power = IT + cooling + losses + lighting | pass | 118.405 vs 118.405 kW (err 0.0 %, tol 2 %) |
| S10/physics | PUE = facility / IT | pass | 1.255 vs 1.255  (err 0.0 %, tol 1 %) |
| S10/physics | PUE plausible (1.0-2.5) | pass | PUE 1.255 |
| S10/physics | max inlet = max rack inlet | pass | 24.998 vs 25.020 °C (|err| 0.022, tol 0.4) |
| S10/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 106.600 vs 106.697 kW (err 0.1 %, tol 15 %) |
| S10/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 106.300 vs 106.600 kW (err 0.3 %, tol 20 %) |
| S10/physics | PDU A + B load = IT load | pass | 94.270 vs 94.334 kW (err 0.1 %, tol 5 %) |
| S10/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.22 K |
| S10/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.19 K |
| S10/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S11 | P-01 vibration grows (bearing) | pass | 1.62 -> 6.63 mm/s |
| S11 | P-01 health index degrades | pass | HI 96.6 -> 27.4 |
| S11 | baseline branch free of this scenario's faults | pass | isolation |
| S11/physics | IT load = sum of rack power | pass | 94.399 vs 94.180 kW (err 0.2 %, tol 3 %) |
| S11/physics | R-01 heat = electrical power | pass | 11.970 vs 11.830 kW (|err| 0.140, tol 0.3) |
| S11/physics | R-02 heat = electrical power | pass | 12.810 vs 12.860 kW (|err| 0.050, tol 0.3) |
| S11/physics | R-03 heat = electrical power | pass | 12.030 vs 12.030 kW (|err| 0.000, tol 0.3) |
| S11/physics | R-04 heat = electrical power | pass | 11.000 vs 10.960 kW (|err| 0.040, tol 0.3) |
| S11/physics | R-05 heat = electrical power | pass | 11.180 vs 11.160 kW (|err| 0.020, tol 0.3) |
| S11/physics | R-06 heat = electrical power | pass | 12.570 vs 12.670 kW (|err| 0.100, tol 0.3) |
| S11/physics | R-07 heat = electrical power | pass | 10.430 vs 10.370 kW (|err| 0.060, tol 0.3) |
| S11/physics | R-08 heat = electrical power | pass | 12.330 vs 12.300 kW (|err| 0.030, tol 0.3) |
| S11/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.150 vs 11.889 K (|err| 0.261, tol 1.5) |
| S11/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.960 vs 11.686 K (|err| 0.274, tol 1.5) |
| S11/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.030 vs 11.561 K (|err| 0.469, tol 1.5) |
| S11/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.120 vs 11.712 K (|err| 0.408, tol 1.5) |
| S11/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.270 vs 11.828 K (|err| 0.442, tol 1.5) |
| S11/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.060 vs 11.779 K (|err| 0.281, tol 1.5) |
| S11/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.090 vs 11.707 K (|err| 0.383, tol 1.5) |
| S11/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.960 vs 12.059 K (|err| 0.099, tol 1.5) |
| S11/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 26.203 kW (err 2.7 %, tol 15 %) |
| S11/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 26.039 kW (err 2.1 %, tol 15 %) |
| S11/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.776 kW (err 0.7 %, tol 15 %) |
| S11/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 26.221 kW (err 2.0 %, tol 15 %) |
| S11/physics | P-01 shaft power = q H / eta | pass | 0.630 vs 0.593 kW (err 6.2 %, tol 10 %) |
| S11/physics | P-02 shaft power = q H / eta | pass | 0.550 vs 0.573 kW (err 4.0 %, tol 10 %) |
| S11/physics | CH-01 power = load / COP | pass | 6.900 vs 6.972 kW (err 1.0 %, tol 6 %) |
| S11/physics | CH-01 COP plausible (2-12) | pass | COP 8.52 |
| S11/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.985 vs 12.940 kW (err 0.3 %, tol 8 %) |
| S11/physics | facility power = IT + cooling + losses + lighting | pass | 117.952 vs 117.953 kW (err 0.0 %, tol 2 %) |
| S11/physics | PUE = facility / IT | pass | 1.250 vs 1.250  (err 0.0 %, tol 1 %) |
| S11/physics | PUE plausible (1.0-2.5) | pass | PUE 1.250 |
| S11/physics | max inlet = max rack inlet | pass | 25.026 vs 25.010 °C (|err| 0.016, tol 0.4) |
| S11/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.400 vs 100.890 kW (err 0.5 %, tol 15 %) |
| S11/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.300 vs 101.400 kW (err 0.9 %, tol 20 %) |
| S11/physics | PDU A + B load = IT load | pass | 94.300 vs 94.399 kW (err 0.1 %, tol 5 %) |
| S11/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.24 K |
| S11/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.30 K |
| S11/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S12 | HX effectiveness reduced | pass | 71.9 -> 23.0 % |
| S12 | load shifts from economiser to chillers | pass | chiller load 59.4 -> 87.9 kW |
| S12 | baseline branch free of this scenario's faults | pass | isolation |
| S12/physics | IT load = sum of rack power | pass | 94.506 vs 94.600 kW (err 0.1 %, tol 3 %) |
| S12/physics | R-01 heat = electrical power | pass | 11.940 vs 11.900 kW (|err| 0.040, tol 0.3) |
| S12/physics | R-02 heat = electrical power | pass | 12.840 vs 12.760 kW (|err| 0.080, tol 0.3) |
| S12/physics | R-03 heat = electrical power | pass | 12.090 vs 12.050 kW (|err| 0.040, tol 0.3) |
| S12/physics | R-04 heat = electrical power | pass | 11.120 vs 11.170 kW (|err| 0.050, tol 0.3) |
| S12/physics | R-05 heat = electrical power | pass | 11.160 vs 11.210 kW (|err| 0.050, tol 0.3) |
| S12/physics | R-06 heat = electrical power | pass | 12.580 vs 12.600 kW (|err| 0.020, tol 0.3) |
| S12/physics | R-07 heat = electrical power | pass | 10.490 vs 10.550 kW (|err| 0.060, tol 0.3) |
| S12/physics | R-08 heat = electrical power | pass | 12.550 vs 12.360 kW (|err| 0.190, tol 0.3) |
| S12/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.120 vs 12.003 K (|err| 0.117, tol 1.5) |
| S12/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.050 vs 11.714 K (|err| 0.336, tol 1.5) |
| S12/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.040 vs 11.866 K (|err| 0.174, tol 1.5) |
| S12/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.150 vs 12.057 K (|err| 0.093, tol 1.5) |
| S12/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.290 vs 11.822 K (|err| 0.468, tol 1.5) |
| S12/physics | R-06 outlet - inlet = Q/(m cp) | pass | 12.040 vs 11.696 K (|err| 0.344, tol 1.5) |
| S12/physics | R-07 outlet - inlet = Q/(m cp) | pass | 11.990 vs 11.855 K (|err| 0.135, tol 1.5) |
| S12/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.120 vs 11.854 K (|err| 0.266, tol 1.5) |
| S12/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 26.049 kW (err 1.3 %, tol 15 %) |
| S12/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 25.876 kW (err 1.5 %, tol 15 %) |
| S12/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 26.166 kW (err 2.5 %, tol 15 %) |
| S12/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 26.148 kW (err 2.1 %, tol 15 %) |
| S12/physics | P-01 shaft power = q H / eta | pass | 0.560 vs 0.569 kW (err 1.7 %, tol 10 %) |
| S12/physics | P-02 shaft power = q H / eta | pass | 0.550 vs 0.568 kW (err 3.2 %, tol 10 %) |
| S12/physics | CH-01 power = load / COP | pass | 8.900 vs 8.969 kW (err 0.8 %, tol 6 %) |
| S12/physics | CH-01 COP plausible (2-12) | pass | COP 9.80 |
| S12/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 14.899 vs 14.870 kW (err 0.2 %, tol 8 %) |
| S12/physics | facility power = IT + cooling + losses + lighting | pass | 119.988 vs 119.988 kW (err 0.0 %, tol 2 %) |
| S12/physics | PUE = facility / IT | pass | 1.270 vs 1.270  (err 0.0 %, tol 1 %) |
| S12/physics | PUE plausible (1.0-2.5) | pass | PUE 1.270 |
| S12/physics | max inlet = max rack inlet | pass | 25.025 vs 24.960 °C (|err| 0.065, tol 0.4) |
| S12/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.300 vs 102.132 kW (err 0.8 %, tol 15 %) |
| S12/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.300 vs 101.300 kW (err 1.0 %, tol 20 %) |
| S12/physics | PDU A + B load = IT load | pass | 94.600 vs 94.506 kW (err 0.1 %, tol 5 %) |
| S12/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.18 K |
| S12/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.16 K |
| S12/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.1 °C |
| S13 | CT-01 approach increases | pass | 4.15 -> 5.82 K |
| S13 | baseline branch free of this scenario's faults | pass | isolation |
| S13/physics | IT load = sum of rack power | pass | 94.742 vs 94.820 kW (err 0.1 %, tol 3 %) |
| S13/physics | R-01 heat = electrical power | pass | 11.810 vs 12.020 kW (|err| 0.210, tol 0.3) |
| S13/physics | R-02 heat = electrical power | pass | 12.850 vs 12.840 kW (|err| 0.010, tol 0.3) |
| S13/physics | R-03 heat = electrical power | pass | 12.130 vs 12.080 kW (|err| 0.050, tol 0.3) |
| S13/physics | R-04 heat = electrical power | pass | 11.100 vs 11.020 kW (|err| 0.080, tol 0.3) |
| S13/physics | R-05 heat = electrical power | pass | 11.150 vs 11.280 kW (|err| 0.130, tol 0.3) |
| S13/physics | R-06 heat = electrical power | pass | 12.810 vs 12.650 kW (|err| 0.160, tol 0.3) |
| S13/physics | R-07 heat = electrical power | pass | 10.460 vs 10.520 kW (|err| 0.060, tol 0.3) |
| S13/physics | R-08 heat = electrical power | pass | 12.500 vs 12.410 kW (|err| 0.090, tol 0.3) |
| S13/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.010 vs 11.730 K (|err| 0.280, tol 1.5) |
| S13/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.980 vs 11.710 K (|err| 0.270, tol 1.5) |
| S13/physics | R-03 outlet - inlet = Q/(m cp) | pass | 11.980 vs 11.877 K (|err| 0.103, tol 1.5) |
| S13/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.170 vs 11.683 K (|err| 0.487, tol 1.5) |
| S13/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.070 vs 11.811 K (|err| 0.259, tol 1.5) |
| S13/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.910 vs 12.113 K (|err| 0.203, tol 1.5) |
| S13/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.090 vs 11.902 K (|err| 0.188, tol 1.5) |
| S13/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.040 vs 11.915 K (|err| 0.125, tol 1.5) |
| S13/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 26.038 kW (err 1.3 %, tol 15 %) |
| S13/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.713 kW (err 0.4 %, tol 15 %) |
| S13/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.740 kW (err 0.5 %, tol 15 %) |
| S13/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 25.848 kW (err 0.6 %, tol 15 %) |
| S13/physics | P-01 shaft power = q H / eta | pass | 0.560 vs 0.572 kW (err 2.1 %, tol 10 %) |
| S13/physics | P-02 shaft power = q H / eta | pass | 0.570 vs 0.560 kW (err 1.9 %, tol 10 %) |
| S13/physics | CH-01 power = load / COP | pass | 6.900 vs 6.938 kW (err 0.6 %, tol 6 %) |
| S13/physics | CH-01 COP plausible (2-12) | pass | COP 8.59 |
| S13/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 17.705 vs 17.630 kW (err 0.4 %, tol 8 %) |
| S13/physics | facility power = IT + cooling + losses + lighting | pass | 123.055 vs 123.055 kW (err 0.0 %, tol 2 %) |
| S13/physics | PUE = facility / IT | pass | 1.299 vs 1.299  (err 0.0 %, tol 1 %) |
| S13/physics | PUE plausible (1.0-2.5) | pass | PUE 1.299 |
| S13/physics | max inlet = max rack inlet | pass | 25.027 vs 25.030 °C (|err| 0.003, tol 0.4) |
| S13/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.500 vs 101.019 kW (err 0.5 %, tol 15 %) |
| S13/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.600 vs 101.500 kW (err 1.1 %, tol 20 %) |
| S13/physics | PDU A + B load = IT load | pass | 94.620 vs 94.742 kW (err 0.1 %, tol 5 %) |
| S13/physics | CT-01 approach plausible (0.5-10 K) | pass | 5.82 K |
| S13/physics | CT-02 approach plausible (0.5-10 K) | pass | 2.52 K |
| S13/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.1 °C |
| S14 | R-03 measured inlet biased by +4 K | pass | 4.000 vs 4.000 K (|err| 0.000, tol 0.8) |
| S14 | R-03 outlet (physical) unchanged | pass | 36.560 vs 36.560 °C (|err| 0.000, tol 0.6) |
| S14 | facility max inlet (true temperature) unchanged | pass | 25.016 vs 25.016 °C (|err| 0.000, tol 0.4) |
| S14 | other racks unaffected | pass | max |dT| over other racks < 0.5 K |
| S14 | baseline branch free of this scenario's faults | pass | isolation |
| S14/physics | IT load = sum of rack power | pass | 94.865 vs 94.980 kW (err 0.1 %, tol 3 %) |
| S14/physics | R-01 heat = electrical power | pass | 12.090 vs 11.970 kW (|err| 0.120, tol 0.3) |
| S14/physics | R-02 heat = electrical power | pass | 12.850 vs 12.930 kW (|err| 0.080, tol 0.3) |
| S14/physics | R-03 heat = electrical power | pass | 12.200 vs 12.000 kW (|err| 0.200, tol 0.3) |
| S14/physics | R-04 heat = electrical power | pass | 11.070 vs 11.240 kW (|err| 0.170, tol 0.3) |
| S14/physics | R-05 heat = electrical power | pass | 11.100 vs 11.180 kW (|err| 0.080, tol 0.3) |
| S14/physics | R-06 heat = electrical power | pass | 12.630 vs 12.750 kW (|err| 0.120, tol 0.3) |
| S14/physics | R-07 heat = electrical power | pass | 10.480 vs 10.490 kW (|err| 0.010, tol 0.3) |
| S14/physics | R-08 heat = electrical power | pass | 12.300 vs 12.420 kW (|err| 0.120, tol 0.3) |
| S14/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.140 vs 11.782 K (|err| 0.358, tol 1.5) |
| S14/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.180 vs 12.001 K (|err| 0.179, tol 1.5) |
| S14/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.030 vs 11.696 K (|err| 0.334, tol 1.5) |
| S14/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.200 vs 11.972 K (|err| 0.228, tol 1.5) |
| S14/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.970 vs 11.782 K (|err| 0.188, tol 1.5) |
| S14/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.030 vs 11.925 K (|err| 0.105, tol 1.5) |
| S14/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.970 vs 11.793 K (|err| 0.177, tol 1.5) |
| S14/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 26.130 kW (err 1.6 %, tol 15 %) |
| S14/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.500 vs 26.269 kW (err 2.9 %, tol 15 %) |
| S14/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 26.585 kW (err 3.7 %, tol 15 %) |
| S14/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 26.172 kW (err 2.2 %, tol 15 %) |
| S14/physics | P-01 shaft power = q H / eta | pass | 0.550 vs 0.567 kW (err 2.9 %, tol 10 %) |
| S14/physics | P-02 shaft power = q H / eta | pass | 0.560 vs 0.567 kW (err 1.2 %, tol 10 %) |
| S14/physics | CH-01 power = load / COP | pass | 7.000 vs 6.956 kW (err 0.6 %, tol 6 %) |
| S14/physics | CH-01 COP plausible (2-12) | pass | COP 8.54 |
| S14/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.941 vs 13.020 kW (err 0.6 %, tol 8 %) |
| S14/physics | facility power = IT + cooling + losses + lighting | pass | 118.396 vs 118.397 kW (err 0.0 %, tol 2 %) |
| S14/physics | PUE = facility / IT | pass | 1.248 vs 1.248  (err 0.0 %, tol 1 %) |
| S14/physics | PUE plausible (1.0-2.5) | pass | PUE 1.248 |
| S14/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.700 vs 102.008 kW (err 0.3 %, tol 15 %) |
| S14/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.400 vs 101.700 kW (err 0.7 %, tol 20 %) |
| S14/physics | PDU A + B load = IT load | pass | 94.860 vs 94.865 kW (err 0.0 %, tol 5 %) |
| S14/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.23 K |
| S14/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.27 K |
| S14/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S15 | CRAH-01 vibration rise = 6 x severity x speed^2 (1x imbalance, speed 40 %) | pass | 0.790 vs 0.776 mm/s (|err| 0.014, tol 0.3) |
| S15 | CRAH-01 vibration grows | pass | 0.40 -> 1.19 mm/s |
| S15 | airflow / thermal unaffected | pass | 24.999 vs 24.999 °C (|err| 0.000, tol 0.4) |
| S15 | baseline branch free of this scenario's faults | pass | isolation |
| S15/physics | IT load = sum of rack power | pass | 94.940 vs 94.730 kW (err 0.2 %, tol 3 %) |
| S15/physics | R-01 heat = electrical power | pass | 12.050 vs 12.080 kW (|err| 0.030, tol 0.3) |
| S15/physics | R-02 heat = electrical power | pass | 12.800 vs 12.820 kW (|err| 0.020, tol 0.3) |
| S15/physics | R-03 heat = electrical power | pass | 12.120 vs 12.090 kW (|err| 0.030, tol 0.3) |
| S15/physics | R-04 heat = electrical power | pass | 11.280 vs 11.150 kW (|err| 0.130, tol 0.3) |
| S15/physics | R-05 heat = electrical power | pass | 11.090 vs 11.140 kW (|err| 0.050, tol 0.3) |
| S15/physics | R-06 heat = electrical power | pass | 12.670 vs 12.700 kW (|err| 0.030, tol 0.3) |
| S15/physics | R-07 heat = electrical power | pass | 10.500 vs 10.380 kW (|err| 0.120, tol 0.3) |
| S15/physics | R-08 heat = electrical power | pass | 12.460 vs 12.370 kW (|err| 0.090, tol 0.3) |
| S15/physics | R-01 outlet - inlet = Q/(m cp) | pass | 12.090 vs 11.785 K (|err| 0.305, tol 1.5) |
| S15/physics | R-02 outlet - inlet = Q/(m cp) | pass | 12.130 vs 11.742 K (|err| 0.388, tol 1.5) |
| S15/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.150 vs 11.938 K (|err| 0.212, tol 1.5) |
| S15/physics | R-04 outlet - inlet = Q/(m cp) | pass | 12.160 vs 11.783 K (|err| 0.377, tol 1.5) |
| S15/physics | R-05 outlet - inlet = Q/(m cp) | pass | 12.260 vs 11.658 K (|err| 0.602, tol 1.5) |
| S15/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.990 vs 11.508 K (|err| 0.482, tol 1.5) |
| S15/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.040 vs 11.899 K (|err| 0.141, tol 1.5) |
| S15/physics | R-08 outlet - inlet = Q/(m cp) | pass | 12.000 vs 11.702 K (|err| 0.298, tol 1.5) |
| S15/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 25.976 kW (err 1.1 %, tol 15 %) |
| S15/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.867 kW (err 1.0 %, tol 15 %) |
| S15/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 26.357 kW (err 2.5 %, tol 15 %) |
| S15/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.800 vs 25.578 kW (err 0.9 %, tol 15 %) |
| S15/physics | P-01 shaft power = q H / eta | pass | 0.590 vs 0.569 kW (err 3.7 %, tol 10 %) |
| S15/physics | P-02 shaft power = q H / eta | pass | 0.580 vs 0.557 kW (err 4.1 %, tol 10 %) |
| S15/physics | CH-01 power = load / COP | pass | 7.100 vs 6.971 kW (err 1.9 %, tol 6 %) |
| S15/physics | CH-01 COP plausible (2-12) | pass | COP 8.55 |
| S15/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.953 vs 13.130 kW (err 1.3 %, tol 8 %) |
| S15/physics | facility power = IT + cooling + losses + lighting | pass | 118.488 vs 118.487 kW (err 0.0 %, tol 2 %) |
| S15/physics | PUE = facility / IT | pass | 1.248 vs 1.248  (err 0.0 %, tol 1 %) |
| S15/physics | PUE plausible (1.0-2.5) | pass | PUE 1.248 |
| S15/physics | max inlet = max rack inlet | pass | 24.999 vs 25.000 °C (|err| 0.001, tol 0.4) |
| S15/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.600 vs 101.233 kW (err 0.4 %, tol 15 %) |
| S15/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.800 vs 101.600 kW (err 1.2 %, tol 20 %) |
| S15/physics | PDU A + B load = IT load | pass | 94.990 vs 94.940 kW (err 0.1 %, tol 5 %) |
| S15/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.19 K |
| S15/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.12 K |
| S15/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 37.0 °C |
| S16 | P-01 tripped | pass | state TRIPPED, flow 0.00 |
| S16 | standby pump started (redundancy restored) | pass | running pumps 2 -> 2 |
| S16 | loop flow restored | pass | 3.390 vs 3.400 L/s (err 0.3 %, tol 10 %) |
| S16 | no thermal excursion | pass | max inlet 25.03 °C |
| S16 | baseline branch free of this scenario's faults | pass | isolation |
| S16/physics | IT load = sum of rack power | pass | 95.537 vs 95.610 kW (err 0.1 %, tol 3 %) |
| S16/physics | R-01 heat = electrical power | pass | 11.950 vs 11.960 kW (|err| 0.010, tol 0.3) |
| S16/physics | R-02 heat = electrical power | pass | 13.240 vs 13.250 kW (|err| 0.010, tol 0.3) |
| S16/physics | R-03 heat = electrical power | pass | 12.440 vs 12.410 kW (|err| 0.030, tol 0.3) |
| S16/physics | R-04 heat = electrical power | pass | 11.020 vs 11.060 kW (|err| 0.040, tol 0.3) |
| S16/physics | R-05 heat = electrical power | pass | 11.410 vs 11.340 kW (|err| 0.070, tol 0.3) |
| S16/physics | R-06 heat = electrical power | pass | 12.810 vs 12.710 kW (|err| 0.100, tol 0.3) |
| S16/physics | R-07 heat = electrical power | pass | 10.480 vs 10.430 kW (|err| 0.050, tol 0.3) |
| S16/physics | R-08 heat = electrical power | pass | 12.470 vs 12.450 kW (|err| 0.020, tol 0.3) |
| S16/physics | R-01 outlet - inlet = Q/(m cp) | pass | 11.870 vs 11.673 K (|err| 0.197, tol 1.5) |
| S16/physics | R-02 outlet - inlet = Q/(m cp) | pass | 11.940 vs 11.921 K (|err| 0.019, tol 1.5) |
| S16/physics | R-03 outlet - inlet = Q/(m cp) | pass | 12.050 vs 11.941 K (|err| 0.109, tol 1.5) |
| S16/physics | R-04 outlet - inlet = Q/(m cp) | pass | 11.970 vs 11.733 K (|err| 0.237, tol 1.5) |
| S16/physics | R-05 outlet - inlet = Q/(m cp) | pass | 11.910 vs 11.770 K (|err| 0.140, tol 1.5) |
| S16/physics | R-06 outlet - inlet = Q/(m cp) | pass | 11.880 vs 11.725 K (|err| 0.155, tol 1.5) |
| S16/physics | R-07 outlet - inlet = Q/(m cp) | pass | 12.030 vs 11.811 K (|err| 0.219, tol 1.5) |
| S16/physics | R-08 outlet - inlet = Q/(m cp) | pass | 11.850 vs 11.887 K (|err| 0.037, tol 1.5) |
| S16/physics | CRAH-01 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 26.195 kW (err 2.3 %, tol 15 %) |
| S16/physics | CRAH-02 coil duty = m cp (Tret - Tsup) | pass | 25.400 vs 26.191 kW (err 3.0 %, tol 15 %) |
| S16/physics | CRAH-03 coil duty = m cp (Tret - Tsup) | pass | 25.600 vs 25.611 kW (err 0.0 %, tol 15 %) |
| S16/physics | CRAH-04 coil duty = m cp (Tret - Tsup) | pass | 25.700 vs 25.964 kW (err 1.0 %, tol 15 %) |
| S16/physics | P-02 shaft power = q H / eta | pass | 0.540 vs 0.559 kW (err 3.3 %, tol 10 %) |
| S16/physics | P-03 shaft power = q H / eta | pass | 0.570 vs 0.565 kW (err 0.9 %, tol 10 %) |
| S16/physics | CH-01 power = load / COP | pass | 7.000 vs 6.991 kW (err 0.1 %, tol 6 %) |
| S16/physics | CH-01 COP plausible (2-12) | pass | COP 8.54 |
| S16/physics | cooling power = chillers + pumps + towers + CW pump + CRAH fans | pass | 12.964 vs 13.010 kW (err 0.4 %, tol 8 %) |
| S16/physics | facility power = IT + cooling + losses + lighting | pass | 119.124 vs 119.124 kW (err 0.0 %, tol 2 %) |
| S16/physics | PUE = facility / IT | pass | 1.247 vs 1.247  (err 0.0 %, tol 1 %) |
| S16/physics | PUE plausible (1.0-2.5) | pass | PUE 1.247 |
| S16/physics | max inlet = max rack inlet | pass | 25.033 vs 25.090 °C (|err| 0.057, tol 0.4) |
| S16/physics | CHW plant duty = rho cp q (Tr - Ts) | pass | 101.900 vs 101.335 kW (err 0.6 %, tol 15 %) |
| S16/physics | CRAH coil duty = CHW plant duty (quasi-steady) | pass | 102.300 vs 101.900 kW (err 0.4 %, tol 20 %) |
| S16/physics | PDU A + B load = IT load | pass | 95.440 vs 95.537 kW (err 0.1 %, tol 5 %) |
| S16/physics | CT-01 approach plausible (0.5-10 K) | pass | 4.22 K |
| S16/physics | CT-02 approach plausible (0.5-10 K) | pass | 4.23 K |
| S16/physics | all key temperatures finite and in 5-60 °C | pass | min 18.0, max 36.9 °C |
