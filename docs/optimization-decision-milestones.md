# Optimization and operator decisions — milestones C, D and E

This continues [the graph/rule-analysis milestones](graph-analysis-milestones.md) on the existing `nettransform-integration` branch. It uses the existing analytical engine, topology store, APIs and React Flow views. It does not deploy a virtual or physical network.

## C — actual NSGA-II

`backend/app/services/optimization.py` runs pinned **pymoo 0.6.1.6 NSGA-II**. This is a separate opt-in search, not a new name for the existing weighted strategy ranking. The shared `transformation.evaluate_candidate` calculates every decoded graph using the existing analytical evaluator and selected-route single-link connectivity stress tests.

Two integer genes encode a configuration:

1. A bitmask combines the currently generated non-retain action graphs in sorted strategy-ID order. They are the existing repair, targeted replacement/backup/capacity and permitted dedicated-path actions. Zero means retain. The returned `action_ids` defines the mask for the experiment.
2. Capacity tier 0 preserves configuration; tier 1 or 2 increases selected-route capacity to at least 125% or 200% of the effective demand, capped at the canonical capacity limit. Existing higher capacity is preserved. No valid path means no invented upgrade route. Scenarios with no action library, including intentional isolation/cloud placement, do not receive new capacity actions.

Decoding starts from an independent failed-state copy. Conflicting changes to the same object are rejected explicitly. Saved parallel links remain valid; new connections duplicating operational pairs, including a pair restored by another action in the same candidate, are rejected. Numerical bounds, references, interfaces and unsupported routing/configuration are validated by the canonical schema and actual analytical evaluator. Repair/new-link permissions and change budget remain authoritative.

### Objectives and constraints

All seven objectives are minimized:

| Objective | Formula |
| --- | --- |
| Undelivered fraction | `1 - delivered / offered` |
| Unreachable fraction | `1 - source-reachable nodes / total candidate nodes` |
| Mean delay | `mean latency / latency target` |
| Loss fraction | `packet_loss_pct / 100` |
| Selected-route vulnerability | `1 - single-link connectivity survival fraction` |
| Relative cost | Actual candidate change units |
| Change complexity | Count of recorded changes |

Unsupported latency stays null in graph/metric results; a finite penalty of 1,000,000 is used **only** in the optimizer objective vector. Such a candidate fails the finite-delay constraint. Retained unavailable original devices still count in total candidate nodes; replacement does not silently remove historical failed objects to improve reachability.

Recovery constraints require a valid permitted graph, budget compliance, an operational service route, the requested delivery fraction (default 95%) and finite mean latency within the declared target. Link capacity and configured independent loss constrain delivered traffic through the existing model. Device processing, ports, compatibility and physical feasibility remain unverified. Risk flags are advisory and never independently discard candidates.

Change units remain relative proxies: new device 8, new link 3, capacity configuration change 2, state restoration 1. **Restoration plus capacity modification now counts both charges**, correcting the old mutually exclusive counter. Restoring an unconfigured capacity is described safely rather than causing number-format errors.

### Search and provenance

Defaults: population 16, 12 generations, seed 17, crossover probability 0.9, mutation probability 0.5, cooperative time budget 10 seconds. Limits: population 8–64, generations 2–50, timeout at most 30 seconds. Integer-rounded SBX uses eta 15; polynomial mutation uses eta 20. The initial population includes each deterministic action and retain; remaining configurations are seeded samples. These choices follow pymoo's [NSGA-II interface](https://pymoo.org/algorithms/moo/nsga2.html) and [integer-variable operators](https://pymoo.org/customization/discrete.html).

Duplicate genotypes/graphs reuse evaluated evidence. The non-dominated feasible archive is calculated from **actually evaluated** graphs; equal objective vectors do not dominate each other. This is a bounded action-library search, not arbitrary topology discovery or global optimality. The result includes objective names/vectors, encoding/action IDs, constraints, Pareto IDs, optimizer parameters, generations, rejected encodings and deterministic baseline objective comparisons.

Seeded searches are serialized because the pinned pymoo version seeds global random state. CPU work runs in a threadpool so the FastAPI event loop can serve other requests. Timeout checks occur between evaluations; an in-flight graph evaluation is not forcibly killed. Missing dependencies, contention, timeout or supported runtime failures return a labeled deterministic fallback with **no fabricated Pareto front**. A completed search with zero feasible candidates is a distinct state, not successful recovery.

The selected recommendation is the best existing weighted preference among the evaluated feasible Pareto alternatives. Deterministic strategies remain inspectable and operational without optimization. No weighted score means percentage improvement.

## D — inspect, compare, accept or reject

The existing page now places recovery tools after scenario impact. History, structural diagnostics, detailed assumptions, settings and scores are expandable. Recharts displays relative cost versus finite mean delay; it is a two-dimensional projection of the seven-objective front. The candidate table remains the accessible alternative to plot interaction and can reveal dominated/infeasible candidates. Candidate inspection uses the actual graph and computed route.

- **Use in comparison:** revalidates and reevaluates the stored candidate graph, then saves that selection, graph and metrics to the experiment.
- **Accept plan for review:** requires explicit UI confirmation, checks current saved-topology fingerprint and ownership, enforces service/configuration constraints and records approval of the experiment plan.
- **Reject plan:** records rejection and a note, including for infeasible alternatives.

These actions do **not** publish a candidate into Topology Workspace or deploy configuration. Decision history preserves selected/rejected candidate snapshots, prior selected candidate ID, user, timestamp, note, scope and fingerprints. Original baseline/failure snapshots remain unchanged. There is no transactional canonical topology publish/undo operation; planning acceptance is deliberately labeled as such.

Protected `POST /api/failure-simulation/{id}/decision` requires Bearer auth and a candidate ID, action, topology fingerprint and proposal revision. Candidate lookup is restricted to the owner-scoped experiment. Stale revisions/fingerprints return 409, unknown candidates 404, constraint violations 422, and missing sessions 401. Accept validates the current graph at check time; it does not lock or update canonical rows.

Existing experiment JSON stores optimizer/candidate evidence and decision history. No schema migration was needed. The existing `updated_at` database trigger and a conditional PATCH guard prevent long optimization/AI/decision writes from silently overwriting a concurrently changed experiment; stale writes return 409. Owner filters, caller JWT validation and RLS remain unchanged.

History views now use the recorded baseline graph for device/link tables and fingerprint labels as well as the graph and metrics, even when the workspace has since changed. Comparison wording derives from the actual stored offered rates. Engine 2.1 traffic increases show original baseline rate versus increased scenario/recovery rate. Older equal-rate exports are described accurately. A bandwidth change off the selected route can preserve all service metrics and all active link counts; it is not a link-disable scenario.

## E — evidence explanations and remaining live gates

The assistant receives baseline/failure/recovery metrics, actual candidate changes and objective values, Pareto metadata, criteria, structural/rule findings and plan decisions. No provider credential, arbitrary device configuration or decision-note content is placed in its evidence prompt.

Server-only configuration remains `ASSISTANT_URL`, `ASSISTANT_MODEL` and any required `ASSISTANT_API_KEY`. Do not add a `VITE_` provider credential or paste keys into chat. The endpoint receives the existing chat-completion request shape. The expected `choices[0].message.content` is now a JSON string such as:

```json
{
  "explanation": "The supplied failed-state demand has no operational route. Compare the evaluated recovery costs and delays before choosing a plan.",
  "claims": [
    {"source": "failure", "metric": "flow_connected", "value": false}
  ]
}
```

This example illustrates the contract; it is **not a claimed live provider response**. Claims use baseline/failure/modernized/candidate sources; candidate claims include `candidate_id`. The server rejects missing structure, unsupported fields, unknown candidates, nonfinite values or mismatching scalar claims. Output validation does not prove arbitrary narrative semantics; prose remains advisory and must be reviewed. The UI exposes checked claims and evidence. AI never changes authoritative topology, metrics or scores.

An unavailable/unconfigured provider or invalid output retains the labeled deterministic explanation. Effective provider endpoint/model/key presence flags were all false in this pass. **A genuine provider request could not be verified.** Positive provider tests use explicit mocks. No trained ML model or future failure predictor was introduced.

Live signed-in Supabase/browser and multi-user RLS checks also remain separate gates; no new real user token was available to the agent. Automated save/select/accept/reject/reload tests use mocked persistence and actual graph evaluation, not claimed live database writes.

## Changed files

| Files | Purpose |
| --- | --- |
| `backend/app/services/optimization.py` (new), `backend/requirements.txt` | Real bounded NSGA-II and pinned dependency |
| `backend/app/services/transformation.py` | Shared candidate evaluator, actual cost counting, Pareto recommendation and operator selection description |
| `backend/app/models/failure_simulation.py` | Validated search parameters, decision requests and history response |
| `backend/app/api/failure_simulation.py`, `backend/app/api/analysis.py` | Protected decisions, opt-in search, threadpool execution and experiment persistence |
| `backend/app/services/supabase_repository.py` | Optimistic update guard using existing timestamp column |
| `backend/app/services/assistant.py`, `.env.example` | Evidence/claims contract and honest fallback |
| `backend/tests/test_optimization.py`, `backend/tests/test_candidate_decisions.py` (new), `backend/tests/test_assistant_repository.py`, `backend/tests/test_workflow.py` | Real search, controlled constraints, persistence/auth boundaries and AI claim checks |
| `src/components/network/pareto-analysis.tsx`, `src/lib/optimization-view.ts` (new) | Existing Recharts trade-off plot and safe metric projection |
| `src/components/network/experiment-tools.tsx`, `src/lib/failure-simulation.ts`, `src/routes/_authenticated/failure-simulation.tsx` | Typed controls, inspection/decisions, advanced panels and accurate comparison wording |
| `tests/frontend-api.test.mjs`, `examples/nsga-demo.json` | Projection/wording regressions and reproducible synthetic HTTP input |
| This document, `project-status.md`, roadmap notices and README | Actual implementation/verification and remaining gates |

## Launch and reproduce

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Separate terminals:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

```powershell
npm run dev -- --host localhost --port 8080
```

Open `http://localhost:8080`, sign in, run a saved-topology scenario, then choose **Optimize recovery options (NSGA-II)**. Inspect a table row or Pareto point, use it in comparison and explicitly accept/reject the plan. Save/reload uses the existing experiment store, not canonical graph publication.

The credential-free controlled example runs the same backend search without persistence:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8013/api/analysis/experiment -ContentType application/json -InFile examples/nsga-demo.json
```

The current verification totals and live endpoint results are recorded chronologically in [project-status.md](../project-status.md). Browser/provider gates are not inferred from test doubles.

## Final verification record

- **86 backend tests passed**: 21 additional tests beyond milestone B, including actual pymoo runs, seven decision lifecycle/security cases, a saved API run/optimize/accept/explain/reload lifecycle, concurrent reproducibility, stale-write guarding and structured-provider claim validation. Positive authentication/persistence/provider paths use explicit mocks where stated.
- **10 frontend request/projection tests passed**; TypeScript type-check passed; focused ESLint passed for changed components/helpers/client. The touched route passes non-format lint with one existing hook dependency warning.
- **Final production client/server build passed.** Existing bundle-size/tsconfig-path plugin warnings remain.
- **Full repository lint failed: 2,071 errors, 16 warnings**, predominantly formatting in existing source. This gate is not marked complete and no unrelated bulk rewrite was performed.
- Both live origins (`127.0.0.1:8013`, `localhost:8080`): final controlled full experiment returned 200, optimizer completed, **three Pareto alternatives / five distinct evaluated graphs**, 100/0/100 Mbps baseline/failure/recovery, simulated provenance and no persistence. Health/scenarios returned 200; missing-session decisions returned 401. CORS allowed Authorization/Content-Type: FastAPI 200, Vite 204. An initial smoke-script assumption that every preflight must return 200 was corrected by inspecting the valid 204 response; no unnecessary server change was made.
- No destructive migration, canonical graph write, real packet/telemetry claim or claimed live model call occurred. Genuine AI and signed-in browser/database verification remain external gates. Milestones C and D are implemented and verified within these boundaries; milestone E is partially verified, not falsely marked fully complete.
