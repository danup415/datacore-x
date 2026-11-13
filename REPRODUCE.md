# Reproducing the PI-HA-EMPC paper

All results in the paper come from simulation. They are produced by the code in this repository with the configuration in `config/study_config.json` (frozen for release v1.0.0).

## Requirements

* MATLAB R2024a with the following toolboxes:
  * Simulink, Stateflow, Simscape and Simscape Fluids
  * Model Predictive Control Toolbox and System Identification Toolbox
  * Statistics and Machine Learning Toolbox and Predictive Maintenance Toolbox
  * Parallel Computing Toolbox (optional, for parallel runs)
* Internet access, the first time only, to download the 2025 hourly weather from the Open-Meteo archive.
* Optional: Python 3.11+ for the cross-verification reference traces (`app/datacore-x/backend`).
* Optional: a LaTeX distribution with `elsarticle` to build the manuscript.

## One command

```matlab
cd matlab
run_all                 % about 5 h serial; run_all('Workers',4) with >=16 GB RAM
```

## Stages

| Stage | Command | Output |
|---|---|---|
| Calibration and weather | `run_all('Stage',"calibrate")` | `params/dcx_calibration.mat`, `params/weather_*.mat`, `simscape/results/` |
| Verification | `run_all('Stage',"verify")` | 42/42 checks for the stepper and Simulink; Stateflow ATS test |
| Predictive maintenance (E5) | `run_all('Stage',"pdm")` | `pdm/models/*.mat` |
| MPC identification | `run_all('Stage',"ident")` | `control/dcx_mpc_model_calibrated_<climate>.mat` |
| Study (E1-E4, E6) | `run_all('Stage',"study")` | `control/results/study/runs_paper.csv` (500 runs; resumable) |
| Credibility | `run_all('Stage',"credibility")` | `control/results/credibility/` |
| Statistics and paper numbers | `run_all('Stage',"stats")` | `control/results/study/tables/`, `paper/macros_results.tex` |

Most numbers in the manuscript are macros written by `dcx_paper_macros.m`. The E3/E4 discussion quotes a few values (exposure in seconds and per-seed trips) by hand; check them against `tab_E3`/`tab_E4` if you rerun.

Figure `fig_E3E4_risk.pdf` is redrawn from the study CSV with Python (needs pandas, scipy, statsmodels and matplotlib):

```
python paper/fig_e34.py matlab/control/results/study/runs_paper.csv paper/figures/fig_E3E4_risk.pdf
```

Then build the manuscript with `latexmk -pdf main.tex` in `paper/`.

## Notes on the released results

* The chiller pre-start/lead-transfer sequence in `DcxSupervisor.m` is latched. The 40 PI-HA-EMPC fault runs of E1/E2 were rerun after this fix. The pre-fix rows are kept in `control/results/study/runs_paper_prelatch_backup.csv`.
* The room-air energy balance in `dcx_credibility.m` includes the rack-inlet recirculation term relative to the cold-aisle temperature. With that term the balance closes to about 0.01 % of IT heat.

## Seeds and determinism

* Seed `k` (1-10) sets the plant random stream (`40 + k`) and the start day `15 + 36(k-1)`.
* Identification uses seed 11.
* Runs are deterministic for a given MATLAB release. Wall-clock solve times (E6) depend on the hardware.

## Data availability statement (for the paper)

> All code (MATLAB/Simulink models, controllers, experiment scripts), configuration files, random seeds and the generated result tables are openly available at https://doi.org/10.5281/zenodo.XXXXXXX (release v1.0.0). Weather data are from the Open-Meteo historical archive (ERA5 reanalysis) and are downloaded by the provided scripts. No proprietary or personal data were used.

## Minting the Zenodo DOI (author steps)

1. Push the repository to GitHub as a public repository.
2. In Zenodo, open **GitHub** settings and enable the repository.
3. Create GitHub release `v1.0.0`. Zenodo archives it and mints the DOI, using `.zenodo.json` for the metadata.
4. Replace `10.5281/zenodo.XXXXXXX` in `CITATION.cff`, `REPRODUCE.md` and `paper/main.tex`.
