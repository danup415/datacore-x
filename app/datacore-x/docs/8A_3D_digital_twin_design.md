# DATACORE-X — Section 8A: Interactive 3D Digital Twin

**Design, implementation record and validation (approval package)**
Registry v1.0.0 · Snapshot schema `dcx.snapshot/1` · Replay format `dcx.replay/1`

> Status: the approval package required by 8A ("present the proposed technology stack, scene hierarchy, asset model, data architecture and development effort for approval") is Sections 1–6. Because the brief asked for the project to be built in full, the proposed design has also been implemented as a working prototype. Section 7 records what was built and how it was validated, and Section 8 lists what still needs your environment (MATLAB, Ignition, a GPU workstation) to close.
>
> Everything below describes **target capabilities and measured prototype behaviour**. None of it claims real-world plant performance.

---

## 1. Technology evaluation and selected stack

### 1.1 Candidates

| Criterion (weight) | Three.js (vanilla) | React Three Fiber | Babylon.js | Simulink 3D Animation | Ignition-native (Perspective SVG/drawing) |
|---|---|---|---|---|---|
| Engineering-grade 3D with instancing, picking, CSS labels (25) | 5 | 5 | 5 | 3 | 1 |
| Decoupled from the physics engine (20) | 5 | 5 | 5 | 1 (runs inside MATLAB) | 3 |
| Embeddable in Ignition Perspective (15) | 5 (iframe / WebDev) | 5 | 5 | 1 | 5 |
| Bundle size / single-file offline build (10) | 5 (≈615 kB min) | 3 (+React) | 3 (≈2–3 MB) | n/a | 5 |
| Licence & deployment (10) | MIT | MIT | Apache-2.0 | Needs a MATLAB licence on the viewer side | Ignition licence |
| Team skills / ecosystem (10) | 5 | 4 | 4 | 3 | 4 |
| Long-term UI complexity (10) | 3 | 5 | 4 | 2 | 2 |
| **Weighted score (/5)** | **4.8** | 4.6 | 4.6 | 1.9 | 2.8 |

### 1.2 Decision

* **Rendering:** Three.js r170 (vanilla ES modules, bundled with esbuild). R3F would be the natural migration path if the operator UI grows into a large React application. The scene modules (`frontend/src/scene/*`) are already framework-agnostic, so moving would only mean re-wrapping them.
* **Physics:** the 3D frontend contains no physics. It renders `dcx.snapshot/1` documents only. The authoritative source is either:
  * the **MATLAB/Simulink facility model**, through the MATLAB bridge (`/api/external/snapshot`), or
  * the **reduced-order Python surrogate** (`backend/datacorex/plant.py`), which is explicitly labelled in the UI as *"DATACORE-X reduced-order Python surrogate (stand-in for MATLAB/Simulink)"*.
* **Simulink 3D Animation:** not used, and not a dependency. It could be evaluated later for in-MATLAB engineering review, but it cannot serve an Ignition operator browser.
* **Ignition Perspective:** the twin embeds through an **Inline Frame** component (`ignition/perspective/view.json`, with URL parameters `embed`, `asset`, `view`), or can be hosted as static files through the WebDev module. Data reaches Ignition by **OPC UA** (`opcua_server.py`, nodes `ns=2;s=DCX.<asset>.<key>`) or by **REST polling** (`ignition/scripts/dcx_bridge.py`). Both routes are generated from the same registry, so tag paths and node ids cannot drift.

---

## 2. Scene hierarchy

```
DCX (facility)
├─ BLD-01 Main building
│  ├─ DH-01 Data hall (raised floor 0.6 m, contained cold aisle)
│  │  ├─ ZONE-CA Cold aisle (contained)      ├─ ZONE-HA Hot aisle / room return
│  │  ├─ ROW-A: R-01…R-04                    ├─ ROW-B: R-05…R-08   (fronts face the cold aisle)
│  │  ├─ CRAH-01…CRAH-04                     └─ PDU-A, PDU-B (every rack dual-corded A+B)
│  ├─ PR-01 Chiller plant room: CH-01, CH-02, P-01/P-02 (duty), P-03 (standby), HX-01, PIPE-CW
│  ├─ ER-01 Electrical/UPS room: SWG-01, UPS-A, UPS-B, BAT-A, BAT-B
│  ├─ PIPE-CHWS, PIPE-CHWR (polyline networks, flow direction = point order)
├─ YARD-01: TX-01, GEN-01 (added — needed for a credible utility-failure scenario)
└─ ROOF-01: CT-01, CT-02
```

The 3D layer groups are building, it, cooling, electrical, piping, cables (power flow), airflow, heatmap, zone, indicators and labels. Each group has an independent visibility toggle, which covers the 8A requirement to toggle the electrical, cooling and IT layers.

All 15 asset classes listed in 8A-A are represented. 43 registry assets are rendered as 319 pickable meshes, plus 26 pipe segments and 29 power links.

---

## 3. Asset model (single source of truth)

`backend/datacorex/registry.py` → `config/asset_registry.json`. Each asset carries:

| Field | Example | Use |
|---|---|---|
| `id` | `P-01` | Asset identifier, the same in every layer |
| `type`, `layer`, `parent` | `pump`, `cooling`, `PR-01` | Hierarchy, the 3D layer and the panel templates |
| `pos`, `size`, `rot_y_deg` | metres, base-centre | 3D placement (SI units; x east, z south, y up) |
| `tags[]` | `{key, label, unit, decimals, path, opc_node}` | Data-point mapping, engineering units and display resolution |
| `paths` (pipes) | polylines | Flow geometry and direction |

The 217 data points are exported to:

* `config/tag_map.csv`, which maps each point to its Ignition path, OPC UA node and Simulink signal name
* `ignition/tags/datacorex_opc_tags.json` (OPC-bound tags)
* `ignition/tags/datacorex_memory_tags.json` (tags for the REST route)

Health-bearing assets (pump, CRAH, chiller, HX, tower, UPS, battery) also carry the common `AssetHealth` interface: HI 0–100, fault, fault code, probability, RUL with lower and upper bounds, confidence, basis and recommendation. RUL is never shown without its bounds, confidence and basis.

---

## 4. Data architecture

```mermaid
flowchart LR
  subgraph SRC[Authoritative state source]
    SL[MATLAB/Simulink facility model] -- MATLAB bridge POST /api/external/snapshot --> TC
    SG[Python reduced-order surrogate] --> TC
  end
  TC[TwinCore: virtual instrumentation → intelligence → alarms<br/>ONE snapshot per cycle: seq + sim_time_s] --> WS[WebSocket /ws/stream]
  TC --> HI[(Historian: measured + ground truth by seq)]
  TC --> TG[REST /api/tags flat Ignition paths]
  TC --> OPC[OPC UA server ns=2;s=DCX.*]
  WS --> UI[3D twin (Three.js)]
  TG --> IGN[Ignition Perspective / tags]
  OPC --> IGN
  UI -- role-checked commands --> CMD[Command service: role → PLC interlocks → ACCEPTED/REJECTED → EXECUTED by process feedback]
  IGN -- commands --> CMD
  CMD --> SG
  CMD -- queue → MATLAB polls & acks --> SL
  UI -- scenario request → approval --> WI[What-if executor: deep copy of live twin → baseline + scenario branches]
  WI --> UI
```

### 4.1 Synchronisation definitions (8A-F)

| Item | Definition |
|---|---|
| Asset identifiers | Registry `id` used verbatim in the snapshot, OPC node (`DCX.<id>.<key>`), Ignition folder (`<id with _>`) and Simulink signal (`DCX_<id>_<key>`) |
| Equipment hierarchy | Registry `parent` links; the UI tree and isolate/inspect use the same links |
| Data-point mapping | `tags[].key` ↔ `path` ↔ `opc_node` ↔ `simulink_signal` (`tag_map.csv`) |
| Engineering units | SI with °C. Each point has exactly one unit, defined in the registry; the frontend never converts units |
| Timestamps | `wall_ts` (epoch s, publisher clock), `sim_time_s`, `sim_clock` (ISO local) on every snapshot; tag API repeats `ts` per tag |
| Simulation time | `sim_time_s`. The runtime paces it with a speed factor of 0.1–120× and a 1 Hz publish rate |
| Operating states | Per-asset `state` enumeration (RUNNING, STANDBY, STOPPED, STARTING, TRIPPED, NO_POWER, DOUBLE_CONVERSION, BATTERY, OUTPUT_OFF, ON_UTILITY, ON_GENERATOR, DEAD_BUS, …) |
| Fault states | **Detected:** `health.fault_code` with `prob`, from the intelligence layer, which drives 3D fault highlighting. **Injected ground truth:** `faults_injected[]` with stage incipient/developing/severe, shown only behind an explicit "ground truth" toggle |
| Data quality | Per-point `q` (GOOD implied, BAD, NOT_PROVIDED). BAD values are rendered as `BAD`, never as a number |
| Communication health | `comm{plant, ai, historian, opcua}` from the server. The client tracks link state OK/STALE/LOST from message age (more than 3 publish periods), sequence gaps, reconnects and ping latency |
| Consistency guarantee | One snapshot object per `seq` is fanned out unchanged to the WebSocket, historian, tag API and OPC UA (including `System.Seq`). The Diagnostics tab's *Consistency check* compares them value by value |

### 4.2 Command path (approved operator commands)

The command path is: role check (viewer < operator < engineer), then PLC interlocks in the plant layer (for example "minimum two CRAH in service" or "cannot stop the last CHW pump"). The command is then ACCEPTED or REJECTED with a reason, and becomes EXECUTED only after a confirming process feedback (state or setpoint observed) within 15 s, otherwise it times out. Every record is stored in the historian. There is no unrestricted autonomous control, and OPC UA writes are intentionally not accepted.

### 4.3 What-if path

The workflow is: REQUEST (operator), then PENDING_APPROVAL, then APPROVE (operator/engineer). Execution runs in a deep copy of the live TwinCore taken at approval time, with the **baseline** and **scenario** branches starting from the identical state. Results contain KPI before/after rows, end-state changes and frames that the 3D scene plays back with a branch switch.

The live twin is untouched (this is unit-tested). An engineer can optionally choose *Apply to live*. There are 16 scenarios: the 10 required by 8A-D plus F01, F03, F05, F07, F09 and F10 from the fault framework.

---

## 5. Development effort

The 20-week blueprint plan assumed 8A would mostly fall in Stage 4 (weeks 11–14). The estimate below assumes one student developer and counts what remains after this prototype.

| Work package | Prototype status | Remaining effort |
|---|---|---|
| Registry, schema, tag/OPC/Ignition generation | Done | 0.5 wk (align with the final Simulink signal list) |
| 3D scene (15 asset classes, flows, heatmap, indicators) | Done (engineering-grade simplified) | 1 wk visual polish where justified (GLB models for chillers/CRAH) |
| Interaction (orbit, walkthrough, pick, hierarchy, isolate/inspect) | Done | — |
| Live engineering visualisation | Done | 0.5 wk once real Simulink signals exist |
| What-if workflow + before/after | Done (surrogate) | 1.5 wk to run scenarios in Simulink (`parsim`, fast restart) |
| MATLAB bridge | Template written, **not executed** | 1–2 wk integration against the actual facility model |
| Ignition integration (OPC UA / REST, Perspective embed) | OPC UA server tested with an asyncua client; Ignition artefacts **not executed** | 1 wk in Designer |
| Validation G1–G10 | Automated; G10 needs a GPU | 0.5 wk |
| **Total remaining** | | **≈ 6–7 weeks** (fits weeks 11–17 alongside Stage 4/5) |

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Simulink chunked co-simulation is too slow for 1 Hz at 1× | Publish rate and chunk size are configurable. Fast Restart is available, and the surrogate can serve as a fallback while still clearly labelled |
| Surrogate behaviour mistaken for the Simulink model | The source label is always shown, `source.type` sits in every snapshot, and the replay is labelled as recorded |
| AI service outage | `comm.ai`; health is held from the last assessment; conventional PLC/PID control is unaffected (`/api/diag/ai_service` hook) |
| Inconsistent values across consumers | Single snapshot fan-out per `seq`, historian keyed by `seq`, automated consistency check |
| Ignition iframe restrictions | Same-origin hosting via WebDev, or a reverse proxy |

---

## 7. What was built and how it was validated

### 7.1 Components

* `backend/datacorex/`: registry; surrogate plant (thermal RC racks/zones, effectiveness-NTU coils/HX, pump/system-curve hydraulics with DP control, Carnot-fraction chillers with lead/lag and anti-recycle, approach-model towers, transformer/generator/ATS, 2N UPS with equivalent-circuit batteries, A/B PDUs); virtual instrumentation (noise, quantisation, drift, failure); physics-residual health estimator v0 with HI/fault/RUL±bounds; ISA-18.2-style alarms; historian; runtime; FastAPI REST + WebSocket; OPC UA server; scenario executor.
* `frontend/`: the Three.js twin (scene, flows, heatmap, UI) with live and replay data sources.
* `dist/datacorex_3d_twin_demo.html`: a standalone build that embeds a recorded run of the twin (30 min live storyline plus 16 recorded what-if runs). It needs no server.

### 7.2 Results

**Backend (`pytest`, 24 tests, all pass):**

* Registry integrity and full point coverage.
* Steady-state plausibility: PUE about 1.25, max inlet about 25 °C, CHWS on setpoint, air-side energy balance.
* No false positives in the healthy baseline.
* Correct fault class *and* isolation (no other asset flagged) for F01, F02, F03, F05, F06, F07, F08 and F10.
* Sensor drift (F09) flagged by the twin residual.
* Standby pump auto-start.
* Utility failure: generator/ATS transfer, a 30 °C inlet excursion during the chiller anti-recycle, and no IT outage.
* What-if isolation from the live twin, plus reproducibility.
* RUL bounds ordered.
* API checks: tag API ≡ historian for the same `seq`, role and interlock rejections, EXECUTED by feedback, approval required (and double approval refused), external-snapshot validation, WebSocket hello/snapshot/pong.

**3D twin (Playwright, headless Chrome against the live service, `tests_e2e/live_e2e.py`):**

| Test (8A-G) | Result |
|---|---|
| G1 Equipment-to-data mapping | PASS: 43 assets, 0 missing points, 0 orphan meshes, 0 unit-less tags |
| G2 Live update | PASS |
| G3 Selection and drill-down | PASS: every asset selected programmatically, panel value = snapshot value |
| G4 Fault highlighting | PASS: highlight set = detected-fault set |
| G5 Thermal heatmap | PASS: 31 sensor points |
| G6 Airflow / fluid animation | PASS: 26/26 pipe segments animate from measured velocity; 256 air particles |
| G7 What-if synchronisation | PASS: scene frame = scenario branch frame |
| G8 Command acknowledgement | PASS: EXECUTED by feedback; interlock REJECTED with reason |
| G9 Communication loss / recovery | PASS: STALE banner and greyed values during an 8 s suppression, "Link recovered" after |
| G10 Performance | **Not established here.** The headless runner uses software rendering (≈3–4 FPS). The scene budget is 120 draw calls and 27k triangles, which is light for any discrete or integrated GPU, but this must be re-run on the target workstation with *Diagnostics → Run checks* |

The consistency check reported 0 mismatches over 217 points between the tag API and the historian, and between the 3D/WebSocket snapshot and the historian.

---

## 8. Open items (needs your environment)

1. Connect the actual MathWorks data-centre cooling / facility model through `simulation/matlab/dcx_bridge_run.m`. Map its logged signals to `tag_map.csv` names and replace the example `CMDMAP` block paths. *Not executed here: no MATLAB in the build environment.*
2. Import the Ignition tags (OPC route: add an OPC UA connection named `DATACORE-X` to `opc.tcp://<host>:4840/datacorex/`), add the project library script, and place `view.json`. *Not executed here.*
3. Run G10 on the target GPU workstation.
4. Replace the physics-residual estimator v0 with the trained models from `predictive_maintenance/`, keeping the `AssetHealth` interface.
5. Production authentication: swap the prototype role headers for the Ignition IdP or OIDC.
