# Graph and analysis upgrade — milestones A and B

> **Subsequent implementation:** [NSGA-II, operator decisions and AI evidence validation](optimization-decision-milestones.md) now extends this historical milestone report. Genuine AI and signed-in browser verification remain explicit external gates.

Implemented and verified on 2026-10-17, on `nettransform-integration`. This pass ends at milestone B under the requested staged-scope rule. It does **not** complete milestones C–E or the full upgrade definition of done.

## Actual implementation

- `backend/app/engines/graph_adapter.py`: ephemeral NetworkX 3.5 `MultiGraph` preserves canonical node IDs and each parallel connection ID. Operational views exclude failed/down/offline/unavailable devices, links, down referenced interfaces and console cables. A full view retains disabled objects. Pydantic/Supabase remain the only canonical model/store.
- `analytical_simulator.py`: the existing heapq Dijkstra still determines routes using propagation plus serialization cost and stable tie ordering. Adjacency now comes from the adapter; NetworkX connectivity replaces duplicate traversal. Capacity, loss and queue equations are retained. One undirected, steady-state demand is supported. `directed: true` is rejected, not silently converted. There is no ECMP, simultaneous-flow allocation, policy routing or device processing-capacity simulation. Both public and saved-topology analytical paths enforce 500 nodes/2,000 links.
- Eight existing scenarios remain isolated from the original graph: link/device failure, traffic increase, bandwidth change, capacity increase, segment isolation, redundancy addition and placement-only cloud migration. Repairs, backups and device replacement remain existing modernization actions, not new catalogue failures. All eight scenarios now have an explicit shared immutability regression test, alongside existing repair/replacement tests.
- **Behavior correction:** traffic-increase baseline uses the original offered rate; the changed state uses the multiplied rate. Recovery candidates use that same multiplied rate. Other scenarios retain identical baseline/scenario demands. Impact evidence identifies both rates, changed route links, newly unreachable nodes and unreachable demands. Engine version is `analytical-network-sim/2.1` to distinguish this baseline semantic change.
- `structural_analysis`: connected components, degree, bridges and seeded Louvain communities with modularity. Louvain receives a documented undirected projection, with adjacency weight equal to the number of operational parallel links, not traffic/capacity. Parallel links are individually preserved in routing and are not incorrectly identified as single-edge bridges. Empty/edgeless graphs return singleton or empty communities and null modularity. Seed 17 and sorted inputs make repeats reproducible in the pinned library version. See the [NetworkX Louvain API](https://networkx.org/documentation/networkx-3.5/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html).
- Communities and bridges provide inspection context for segmentation and single-link vulnerability. **Community membership does not change candidate generation or prove an anomaly.** Existing targeted recovery rules still generate candidates; a future optimizer can consume these structural features without replacing the canonical topology.

## Honest anomaly baseline

`backend/app/services/anomaly_analysis.py::analyze_state` is a transparent, **untrained rule baseline**. There is no historical telemetry corpus, trained ML model, failure probability or predictive claim. Its inputs are actual graph changes and metrics from the analytical engine.

Features: maximum offered/capacity ratio, disabled/newly disabled link counts, disconnected demand, reachable-node change, relative finite mean-delay deviation, configured path-loss deviation, changed-link count and unstable queue status. A delay deviation is null if either delay is unavailable or the baseline denominator is zero. Configured loss deviation is null unless both selected paths have explicit loss values; congestion-related loss is not misrepresented as a configured-loss change.

Rules and severities:

| Rule | Severity |
| --- | --- |
| Demand has no operational route | 1 |
| Newly disabled connection(s) | 1 |
| Queue is unstable | 1 |
| Positive relative mean-delay increase | `min(1, relative increase)` |
| Positive configured path-loss increase | `min(1, percentage-point increase / 10)` |

Score is the maximum fired-rule severity, or zero; flag threshold is 0.5. Thus a 50% mean-delay increase or five percentage-point configured path-loss increase reaches the threshold. Intentional faults can be flagged while this demand's service remains unchanged. No fired rule does not certify network health.

Each modernization candidate receives separate risk evidence calculated from its own graph and metrics relative to the failed state. A flagged candidate remains inspectable and eligible under existing budget/permission constraints; risk does not silently remove the only recovery option. This is evidence ready for **future pre-optimization screening**, not a claim that an optimizer or a new expensive pre-simulation filter exists. Existing weighted ranking is unchanged.

### Evaluation evidence

`backend/tests/test_graph_analysis.py` declares six small synthetic validation cases, not captured observations or training samples. Labels mean an operational/configuration concern: unchanged graph, small delay increase and spare-link addition are negative; bridge failure, saturation and a large delay increase are positive. Observed confusion counts: **TP 3, TN 3, FP 0, FN 0**. These deliberately controlled regression cases establish rule behavior only; they do not estimate real-world detection accuracy. A separate off-route-failure test verifies that a structural fault flag does not falsely claim route/service degradation.

## API, UI, persistence and AI

`SimulationExperimentResponse.analysis` is optional for old experiments. The new result is saved in the existing experiment `metrics` JSON, retained through modernization/assistant writes, returned on reload and included by the existing JSON export. No database schema migration or canonical topology write was added. The saved lifecycle test uses explicit repository mocks; live authenticated persistence was not reverified.

The existing experiment-tools component has an expandable structural/rule-analysis panel and candidate risk explanations. It labels analytical provenance, no trained ML, severity/threshold and limitations. Existing React Flow failure/route rendering, ranking, authentication and RLS remain intact. Generated TypeScript includes `directed?: false`; the contract exporter now handles JSON Schema constants.

Assistant requests include analysis, candidate findings, graph-change descriptions and existing engine metrics. The effective endpoint/model/key configuration is absent. No real AI request succeeded or is claimed. Deterministic explanations remain explicitly labeled; existing provider tests are mocked.

## Verification executed

- Backend: **65 tests passed**, including 12 new graph/rule tests; existing on/off-route failure, repair, replacement, capacity, candidate-specific metric and no-recovery tests pass.
- Frontend: **8 request tests passed**, `npm run typecheck` passed, `npm run build` passed (client/server). Existing build warnings include bundle sizes and Vite's tsconfig-path plugin notice.
- Generated contract check passed. Focused ESLint passed for changed frontend files, generated contract and ESLint config.
- Repository-wide `npm run lint` **failed: 2,157 errors, 16 warnings**, mostly formatting outside the scoped frontend changes. ESLint now excludes Python venv/cache directories after its first run encountered a cache-directory EPERM. No blanket formatting/refactor was performed.
- Ten live HTTP checks across FastAPI `127.0.0.1:8013` and Vite `localhost:8080`: health 200, scenarios 200, protected topology without token 401, public full analytical experiment 200, directed experiment 422 at each origin. The full experiment returned engine 2.1, analysis, disconnected failure state and connected recovery state. These public tests used controlled synthetic topology and made no persistence writes.
- No browser interaction, positive real-user Supabase round trip, multi-user RLS test or live provider verification is claimed. No database data or secret values were exposed or changed.

## Remaining milestones

### Exact files changed in this pass

| Files | Reason |
| --- | --- |
| `backend/app/engines/graph_adapter.py` (new) | ID-preserving MultiGraph, connectivity/bridge/community features and graph comparison |
| `backend/app/services/anomaly_analysis.py` (new) | Separate untrained rule baseline with explicit provenance |
| `backend/app/engines/analytical_simulator.py` | Adapter integration, size bound, impact evidence, paired traffic baseline and engine 2.1 |
| `backend/app/models/network.py`, `backend/app/models/failure_simulation.py` | Explicit undirected schema and optional experiment analysis |
| `backend/app/api/failure_simulation.py` | Persist/return analysis through existing metrics JSON |
| `backend/app/services/transformation.py` | Per-candidate risk annotations without changing weighted ranking |
| `backend/app/services/assistant.py` | Supply structural/rule findings and candidate changes/constraints as evidence |
| `backend/export_contract.py`, `docs/network-definition.schema.json`, `src/lib/network-contract.ts` | Export literal false correctly; regenerate canonical contracts; mark generated formatting |
| `backend/requirements.txt` | Pin NetworkX 3.5 |
| `backend/tests/test_graph_analysis.py` (new), `backend/tests/test_analytical_simulator.py`, `backend/tests/test_workflow.py` | Graph/rule/scenario tests and traffic/persistence regressions |
| `src/lib/failure-simulation.ts`, `src/components/network/experiment-tools.tsx` | Typed analysis and reusable expandable inspection UI |
| `eslint.config.js` | Exclude Python environment/cache directories from JavaScript lint traversal |
| `docs/intelligent-upgrade-audit.md` (new), this document (new), `docs/failure-simulation-modernization-roadmap.md`, `project-status.md` | Audit, actual verification, corrected traffic semantics and explicit remaining scope |

| Milestone | Actual status |
| --- | --- |
| A: canonical graph/scenario reliability | DONE AND VERIFIED within undirected single-demand semantics |
| B: Louvain/features/rule baseline | DONE AND VERIFIED on controlled fixtures; no trained ML |
| C: NSGA-II/objectives/constraints/Pareto | NOT IMPLEMENTED; deterministic weighted strategies remain operational |
| D: Pareto visualization, durable candidate selection, acceptance/rejection | NOT IMPLEMENTED; existing alternatives can be inspected, but no canonical candidate acceptance exists |
| E: genuine AI and signed-in end-to-end verification | BLOCKED for genuine AI by absent provider configuration; positive live session verification remains outstanding |

NetworkX is pinned in requirements. Pymoo was installed in the local venv to assess dependency availability but is **not imported or declared as an application dependency**: installation is not an implemented NSGA-II search. Next work should implement bounded reproducible encoding/objective evaluation, explicit feasibility and real Pareto tests before adding optimizer controls. Do not call current weighted ranking NSGA-II.

## Launch

From the repository root, install the updated backend dependency if using another environment:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Then use separate terminals:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

```powershell
npm run dev -- --host localhost --port 8080
```

Open `http://localhost:8080`. Existing sessions must reload topology after this schema change because its fingerprint now includes the explicit undirected marker. Older engine experiments remain readable; rerun before modernization under engine 2.1. No migration/reset is required.
