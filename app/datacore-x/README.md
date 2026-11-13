# DATACORE-X — Interactive 3D Digital Twin (Section 8A)

A browser-based, navigable 3D operational twin of the DATACORE-X reference data centre. It renders **only** simulation, virtual-instrumentation and intelligence outputs, and it carries an approval-gated what-if workflow, acknowledged supervisory commands, and communication-health handling.

The design and approval package is in [`docs/8A_3D_digital_twin_design.md`](docs/8A_3D_digital_twin_design.md).

## Quick start

```bash
# 1. backend (Python 3.11+)
pip install -r requirements.txt
cd backend
python -m datacorex.tools.export_artifacts          # registry, tag map, Ignition tag imports
DCX_SPEED=10 uvicorn datacorex.api:app --port 8000  # add DCX_OPCUA=1 for the OPC UA server

# 2. frontend bundle (Node 18+)
cd .. && npm install && python tools/build.py
# open http://localhost:8000
```

To get the standalone demo without a server:

```bash
cd backend && python -m datacorex.tools.record_replay --out ../dist/replay.json
cd .. && python tools/build.py   # -> dist/datacorex_3d_twin_demo.html
```

To run the tests:

```bash
cd backend && python -m pytest -q                         # 24 backend tests
python tests_e2e/live_e2e.py http://localhost:8000/ /tmp  # 3D twin G1–G10 (Playwright + Chrome)
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `DCX_SPEED` | 1 | Simulation seconds per wall second (0.1–120) |
| `DCX_SOURCE` | surrogate | `external` = expect the MATLAB/Simulink bridge to publish snapshots |
| `DCX_OPCUA` | 0 | `1` starts the OPC UA server on `opc.tcp://0.0.0.0:4840/datacorex/` |
| `DCX_HISTORIAN` | in-memory | SQLite file path |
| `DCX_SEED` | 7 | Surrogate random seed (reproducible runs) |

## Repository map

```
backend/datacorex/   registry · plant (surrogate) · instrumentation · intelligence · alarms · core
                     historian · runtime · api (REST/WS) · opcua_server · scenarios · tools/
backend/tests/       pytest suite
frontend/            index.html · src/{data,scene,ui} (Three.js r170, esbuild)
config/              asset_registry.json · tag_map.csv            (generated)
ignition/            tags/*.json (generated) · scripts/dcx_bridge.py · perspective/view.json
simulation/matlab/   dcx_bridge_publish.m · dcx_bridge_run.m      (MATLAB/Simulink bridge)
tests_e2e/           Playwright end-to-end validation
dist/                replay.json · datacorex_3d_twin_demo.html    (generated)
docs/                8A design / approval package and validation record
```

## Ignition 8.3 setup (`ignition/setup_ignition.py`)

1. On the gateway (http://localhost:8088), open **Platform → Security → API Keys** and create a key with read/write access.
2. Save the token in `Documents\DATACORE-X\ignition_api_key.txt`. Do not paste it on the command line or in chat.
3. Start the backend with the OPC UA server enabled (`DCX_OPCUA=1`, port 4840).
4. Run `python ignition/setup_ignition.py` for a dry run. It discovers the routes from the gateway's `/openapi` document and prints the plan.
5. Run `python ignition/setup_ignition.py --apply`. This creates the OPC UA connection `DATACORE-X` to `opc.tcp://localhost:4840/datacorex/`, imports `ignition/tags/datacorex_opc_tags.json` into the `default` provider, and verifies both.

The API key needs a security level that is ticked under Gateway Read and Write Permissions (Platform → Security → General Settings). Over plain HTTP, also untick "Require secure connections for API Keys". Without these the gateway answers 401/403. Tag import over REST needs Ignition 8.3.2 or later. On older gateways, the script tells you to import the JSON in the Designer Tag Browser instead.

## Ignition Perspective dashboard (`ignition/build_perspective.py`)

`python ignition/build_perspective.py --apply` adds the DATACORE-X screens to the `DATACORE_X` project. It needs the backend running, because it reads the scenario catalogue from it. It exports the project first and keeps a backup in `ignition/_build/`. The screens are at http://localhost:8088/data/perspective/client/DATACORE_X.

* **Style:** ISA-101 high-performance HMI. Neutral grey, dark text, colour only for abnormal values: amber near a limit, red past a limit or worse than baseline.
* **Overview (`/`):**
  * the live 3D twin, embedded with `?embed=bare`;
  * a facility summary (IT, facility and cooling power, PUE, max inlet, CHW, wet bulb, energy);
  * rack inlet temperatures with margin to 27 °C;
  * plant status.
* **Equipment (`/equipment`):** tables for CRAHs, pumps, heat rejection, chillers and electrical.
* **Scenarios (`/scenarios`):**
  1. Pick one of the 16 catalogue scenarios and a horizon, then run a what-if on an isolated copy of the twin.
  2. Compare the predicted impact against the baseline.
  3. Replay the scenario or the baseline in the embedded 3D model (`?run=<id>&branch=`).
  4. **Apply to live plant** injects the same faults into the running twin. The 3D model, every OPC UA tag and every screen then change together, because they all read the one twin state.
  5. **Clear live faults** resets them.

  The dashboard acts as the `engineer` role. This is simulation only.

All tags, including `Facility/*` and `System/*`, now come from the twin's OPC UA server (`DCX.Facility.<key>`, `DCX.System.<name>`). The REST bridge script is no longer needed for the OPC route.

## Scenario and physics cross-verification (`tests_e2e/verify_scenarios.py`)

`python tests_e2e/verify_scenarios.py` (with the backend running) checks the twin in two parts:

1. **Live-twin physics consistency:**
   * rack heat = electrical power;
   * rack ΔT = Q/(ṁ·cp);
   * CRAH coil duty = ṁ·cp·ΔT;
   * pump power = q·H/η;
   * chiller power = load/COP;
   * CHW plant duty = ρ·cp·q·ΔT;
   * coil duty = plant duty;
   * cooling and facility power sums;
   * PUE;
   * PDU totals.
2. **All 16 scenarios:** each runs through the same REST path as the dashboard and is checked for the expected cause and effect, plus the physics checks on its last frame.

The run uses `clean_start=True`: the what-if starts from a fault-free copy of the live state, and the live plant is not touched. The results are in `docs/scenario_verification.md` and `.json`. Last run: **670/670 checks pass** (horizon 1800 s).

Related fixes:

* Re-applying a scenario replaces its live fault instead of stacking a duplicate.
* Scenario requests accept `clean_start` to run from a healthy plant.

## Honesty notes

* The default data source is a **reduced-order Python surrogate**, written so the whole chain can be built and validated before the Simulink facility model is connected. The UI always names the active source.
* Health, fault and RUL come from a transparent **physics-residual estimator v0**, not from trained ML. Degradation in the scenarios is time-compressed, so RUL is in simulation hours.
* The heatmap is an IDW interpolation of virtual sensors, **not CFD**.
* The MATLAB/Simulink bridge has been run live against this backend (DCX_SOURCE=external). The Ignition setup script below has been run against an Ignition 8.3.10 Maker gateway (2026-11-10). It created the `DATACORE-X` OPC UA connection, which reported healthy with an established session, and imported the tags (311 entries, 0 failures). `ignition/conn_status.py` re-checks the connection.
* Every parameter belongs to a hypothetical facility and is a design assumption. Nothing in this repository claims real-world performance.
