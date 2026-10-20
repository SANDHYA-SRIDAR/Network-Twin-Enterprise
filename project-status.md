# Project Status

Last reviewed: 2026-10-19

## Link Failure Analytical Simulation Refinements - 2026-10-19

- **DONE AND VERIFIED (Incident Root Cause Fixed):** Fixed Link Failure simulation behavior where off-route link failures (e.g. Switch ↔ Load Balancer when traffic is PC2 → Server-PT) were not distinguished from on-route failures, and where traffic exceeding bottleneck capacity (1500 Mbps offered vs 1000 Mbps capacity) produced unstable queueing (`ρ ≥ 1`) that previously displayed as "Unreachable".
- **DONE AND VERIFIED (Engine & Analysis Separation):**
  - Baseline metrics are strictly calculated from the recorded original topology with no injected failure.
  - Active traffic route is identified (`is_on_route`); if the failed link is outside the tested route, the engine and UI explicitly state that the failure does not directly affect the selected traffic flow.
  - Congestion loss (`congestion_loss_pct`) is decoupled from physical link/medium loss (`link_medium_loss_pct`). The engine explicitly explains that modeled packet loss when `offered > bottleneck` is caused by traffic overload, NOT by an off-route link failure.
  - When traffic exceeds bottleneck capacity, queue status is labeled `unstable (ρ ≥ 1)` and latency is marked undefined due to queue instability rather than falsely claiming the destination is topologically unreachable.
  - Baseline, failure, and recovery calculations use identical offered traffic, packet size, and duration.
- **DONE AND VERIFIED (Candidate Bypass Verification & Visualization):**
  - Dedicated service path capacity is verified against offered traffic before claiming 0% modeled congestion loss.
  - The proposed bypass (`candidate:dedicated-service-path`) is rendered as a distinct purple highlighted connection in the candidate topology with legend indicator, leaving the original saved topology unchanged.
- **DONE AND VERIFIED (Frontend UI & Three-Way Comparison):**
  - Added on-route indicators (`★ [ON ROUTE]`) in connection selector dropdown with quick switch button to test failures on the active route.
  - Added flow impact alert banners explaining whether failure is on-route or off-route, and separating topological reachability from congestion delivery.
  - Fixed latency display in metric cards and three-way comparison table (`Queue unstable (ρ ≥ 1)` vs `Unreachable (no route)`).
  - Three-way comparison displays flow path reachability, total loss, congestion loss, link medium loss, average latency, throughput, bottleneck capacity, and queueing status.
- **DONE AND VERIFIED (Automated Tests & Build):**
  - Created `backend/tests/test_link_failure_refinements.py` covering all 5 required scenarios:
    1. Failed link outside traffic route (off_route, flow preserved).
    2. Failed link on traffic route with no alternative path (disconnected, 100% loss).
    3. Failed link on traffic route with alternative path (rerouted, alternate links used).
    4. Traffic exceeding bottleneck capacity (unstable queue, congestion loss separated from link failure, flow connected).
    5. Candidate bypass restoring sufficient capacity (headroom verified, 0% congestion loss, original saved topology unchanged).
  - All 91 backend unit tests pass in `backend/.venv/Scripts/python.exe`.
  - Frontend production build (`npm run build`) compiles cleanly (client + SSR) with zero errors.

## Quick runtime verification - 2026-10-18

- Existing backend 8013 and frontend 8080 were already running; direct and proxied health and the frontend root returned 200. No startup/simulation blocker was reproduced, so no application code was rewritten or unrelated working changes discarded.
- Live Vite-proxied scenarios/configuration endpoints returned 200. Missing-session topology returned the expected 401; positive signed-in ownership/persistence was not inferred from that result.
- Actual controlled analytical experiment returned 200, optimizer completed, three Pareto candidates and throughput 100 -> 0 -> 100 Mbps. Results reported simulated provenance. No database writes or real-network claims were made.
- Re-ran 86 backend tests and 10 frontend request/projection tests: all passed. TypeScript type-check also passed. Existing live-AI configuration and full-repository lint limitations remain as documented below.

## NSGA-II and operator decision workflow - 2026-10-17

- **DONE AND VERIFIED (backend/local contracts):** real pymoo 0.6.1.6 NSGA-II searches combinations of the existing action library plus bounded route-capacity tiers. Shared analytical candidate evaluation, seven actual objectives, explicit graph/service/budget/permission constraints, seeded search, feasible non-dominated archive, deterministic baseline comparisons and honest timeout/dependency fallback. Concurrent seeded searches are serialized for reproducibility. No global optimum, packet-level emulation, trained ML or measured-network claim.
- **DONE AND VERIFIED:** restoration and capacity changes now both incur their relative change charges; unconfigured capacity restoration no longer risks numeric-format errors. Proposed duplicate operational pairs and conflicting combined actions are rejected; pre-existing saved parallel connections remain intact.
- **DONE AND VERIFIED (mocked persistence and actual analytical graphs):** protected candidate selection and explicit accept/reject planning decisions, fingerprint/revision checks, re-evaluated candidate graph/metrics, history snapshots and no canonical topology writes. Existing timestamp trigger supports owner-scoped conditional updates; conflicts return 409 rather than overwriting concurrent experiment evidence. No SQL migration was run.
- **DONE AND VERIFIED (types/build/request tests; browser interaction not verified):** Recharts Pareto projection, candidate inspection and decision controls, advanced settings/history/evidence panels, recorded-baseline graph/table consistency, corrected comparison text based on actual offered rates and configured delivery targets. Acceptance records a plan for engineering review and explicitly does not deploy or publish to Topology Workspace.
- **DONE AND VERIFIED:** assistant transports Pareto/objective/rule/decision evidence and validates structured factual claims against supplied values. Invalid/missing provider output keeps deterministic provenance. Positive provider paths are MOCKED. Effective endpoint/model/key flags remain absent; genuine AI remains BLOCKED by configuration, not claimed verified.
- **DONE AND VERIFIED:** 86 backend tests, including 21 additions for real optimization, constraints, Pareto dominance, repeatability/concurrency, graph-specific objectives, cost, owner/stale-decision protections and evidence validation. Ten frontend tests passed; TypeScript and focused lint passed. Final production client/server build PASSED. Final repository-wide lint FAILED: 2,071 errors and 16 warnings, predominantly existing formatting; no unrelated formatting sweep. The touched route also passed non-format lint with one existing exhaustive-deps warning. Diff whitespace check passed.
- **DONE AND VERIFIED (live native HTTP):** FastAPI 8013 and Vite 8080 public experiment each return 200, real optimizer status completed, three Pareto alternatives from five distinct evaluated graphs, modeled throughput 100 -> 0 -> 100 Mbps, provenance simulated and persisted=false. Health/scenarios 200 and protected decision without session 401 at both origins. CORS preflight returns 200 at FastAPI and 204 at Vite, both allowing localhost:8080 and Authorization/Content-Type. The first smoke script incorrectly expected Vite preflight 200; inspecting the actual 204 and headers verified valid behavior, and final optimizer checks passed independently.
- **REMAINING VERIFICATION GATES:** genuine provider request, signed-in browser/Supabase round trip and multi-user live RLS checks. No authenticated user token was available to the agent, and no credential or fake session was introduced. Canonical candidate publication/physical deployment remains out of scope; review decisions are operational in experiments.
- See [the complete implementation/file map/launch report](docs/optimization-decision-milestones.md) and `examples/nsga-demo.json` for reproducible inputs. Earlier milestone entries below are historical and do not describe the current optimizer availability.

## Graph and structural/rule analysis upgrade - 2026-10-17

- **Scope:** completed milestones A and B in this implementation pass under the user's staged-scope allowance. [Pre-code audit](docs/intelligent-upgrade-audit.md) and [implementation, file map, validation and remaining milestones](docs/graph-analysis-milestones.md). Existing integration branch and unrelated local work retained; no database schema/data changes or canonical topology writes.
- **DONE AND VERIFIED:** pinned NetworkX 3.5 adapter preserves IDs/parallel links and operational eligibility; shared connectivity and existing Dijkstra use its graph view. Canonical `directed?: false` rejects directed inputs. Seeded Louvain, modularity, components, bridges, graph diffs and impact evidence handle empty/disconnected/parallel networks. Existing undirected, single-demand routing and capacity/loss/queue equations remain.
- **DONE AND VERIFIED:** engine 2.1 fixes traffic-increase comparison: original-load baseline, multiplied-load scenario and recovery. Experiments from older versions remain readable but must be rerun for modernization; topology clients should reload after the new direction marker changes fingerprints.
- **DONE AND VERIFIED (controlled synthetic evidence):** untrained rule baseline reports features, severity, threshold, findings and limitations; no trained ML/failure probability/prediction claim. Six labelled regression cases yield TP=3/TN=3/FP=0/FN=0, without establishing real-world accuracy. Candidate risk flags never silently reject the only available option or change weighted ranking. Community features provide inspection context, not a new candidate generator.
- **DONE AND VERIFIED:** analysis stored in existing experiment metrics JSON and retained on mocked save/rank/explain/reload; frontend expandable inspection panel and candidate risk descriptions; assistant supplied actual structural/rule evidence. Provider remains unconfigured, so genuine AI is unavailable/unverified; provider success tests are mocked.
- **DONE AND VERIFIED:** 65 backend tests; 8 frontend API tests; TypeScript type-check; production client/server build; generated-contract consistency; focused ESLint for changed frontend/config/generated files. Full `npm run lint` FAILED with 2,157 errors and 16 warnings, predominantly repository-wide formatting. Python venv/cache directories now excluded from ESLint traversal after an initial cache EPERM. No unrelated formatting sweep.
- **DONE AND VERIFIED (10 live HTTP checks):** both backend 8013 and Vite 8080: health/scenarios 200; missing-token topology 401; synthetic stateless experiment 200 with engine 2.1, structural analysis, disconnected failure and connected recovery; directed input 422. No authenticated live persistence, browser flow or real-user RLS verification claimed.
- **NOT IMPLEMENTED:** milestone C NSGA-II/Pareto objectives/search, milestone D Pareto visualization/durable operator selection/acceptance. Deterministic strategies and inspection remain operational. Pymoo was installed only for local dependency assessment; no application optimizer or fabricated Pareto data was added. Milestone E live provider/session verification remains outstanding. The full requested upgrade definition of done is not claimed.

## Detailed workflow and roadmap review - 2026-10-17

- **DONE AND VERIFIED (document/source inspection):** Added `docs/failure-simulation-modernization-roadmap.md` and indexed it from `roadmap.md`. Describes page controls, schemas, every supported scenario, exact routing/metric formulas, candidate rules, ranking/benefit semantics, persistence, AI boundaries, source functions and phased acceptance criteria. No application code or database changes in this pass.
- Inspected the user-selected export `experiment-abaae93e-09b9-402f-bff1-eddc78a0459e.json`: eight nodes, fourteen original links, one failed switch-to-load-balancer connection, and unchanged PC2-to-server route. Baseline/failure both report 100 Mbps, 2.026667 ms, 0% modeled loss and 8/8 reachable nodes. The failed connection is outside the selected route, so this export does not demonstrate rerouting. Packet loss is unconfigured on all fourteen connections; the explicit zero-loss assumption is not a measurement.
- That export has no modernization proposal/candidate metrics or explanation. A completed initial calculation is not evidence that the subsequent modernization/AI stages ran. The export was read only and was not changed.
- Effective provider flags remain unset for endpoint, model and credential; genuine AI is still unavailable. The roadmap does not label deterministic explanations or mocked transport tests as live AI.
- Latest application test/build evidence remains the recorded 2026-10-16 results below: 53 backend tests, eight frontend tests, type-check and build passed. No application tests/builds were rerun for this documentation-only request. Local documentation links and diff whitespace were checked in this pass.

## Retained-route versus repair clarification - 2026-10-16

- **DONE AND VERIFIED:** Actual trace: `backend/app/engines/analytical_simulator.py::apply_scenario` deep-copies baseline and disables the selected link; `run_experiment` evaluates baseline and failed copies; `modernize` generates a targeted graph; `run_modernization` delegates to `backend/app/services/transformation.py::evaluate_strategies`. That function deep-copies failed state for retain; restores only selected baseline state/capacity for repair; evaluates every candidate through `analytical_simulator.py::evaluate`; stress-tests routes and ranks normalized weighted scores. `backend/app/api/failure_simulation.py::modernize_failure_simulation` persists only the experiment proposal/snapshot/metrics; `_experiment_result` returns it. Supabase canonical topology is not updated.
- **Rules retained:** Retain never repairs/removes the failed connection. Link-failure targeted logic adds a backup only if the demand is disconnected; an already-surviving route produces no duplicate no-change proposal. Other existing targeted rules replace failed devices or upgrade supported capacities. An optional dedicated service path is an explicit new candidate link. Repair restores selected pre-scenario configuration; unrelated outages remain untouched. Ranking score is criterion fit, not percentage gain or proof of repair. No ranking algorithm was changed.
- **Targeted fixes:** New `service_outcome` describes actual failed-versus-candidate connectivity, throughput, latency, loss and reachable-node changes separately from `resolved` (service-target attainment). No-gain retained service displays exactly "Service maintained; no additional performance gain predicted". Proposal summary/rationale/trade-offs identify remaining disabled links, actual repairs and computed routes. Older saved proposals receive descriptive outcome metadata at read time without rewriting stored graphs or scores. Renderer keeps failed links red, renders repaired links operational, emphasizes calculated route edges and lists path nodes/connections. UI no longer equates `resolved` with improvement.
- **Exact files changed this pass:** `backend/app/services/transformation.py`, `backend/app/api/failure_simulation.py`, `backend/tests/test_analytical_simulator.py`, `src/lib/failure-simulation.ts`, `src/components/network/simulation-topology.tsx`, `src/routes/_authenticated/failure-simulation.tsx`, and this status file. Analytical engine, ranking weights, authentication, RLS, persistence schemas and saved topology were preserved.
- **DONE AND VERIFIED:** 53 backend tests pass (five new focused cases: score-one retention/immutability, selected repair, per-candidate graph recomputation, no possible recovery, older saved-proposal wording). Eight frontend request tests and TypeScript type-check pass. A live HTTP check through Vite reproduced a configured 14-link example: retain score **1.000**, **13 active / 1 failed**, real route **l02 -> l12**, explicit no-gain message; repair under latency-focused criteria: **14 active / 0 failed**, real route **l01**, predicted modeled improvement. These were analytical sample experiments with no database writes or live-network claims.
- **DONE AND VERIFIED:** Production client/server build and diff whitespace check pass. Browser visual interaction and a live signed-in persistence round trip are not claimed by these checks.

## Final demo-readiness pass - 2026-10-16

- **DONE AND VERIFIED:** Preserved the existing integration branch and all configuration/auth/proxy fixes. Only targeted demo changes: shared busy state between simulation and experiment operations prevents stale responses replacing a newer run; history has loading/empty states; topology session/load failures are caught and retryable; a failed new run retains the previous result.
- **DONE AND VERIFIED:** Explanation requests now include actual modernized metrics/routes and candidate metrics alongside baseline/failure evidence. The existing mocked provider test asserts those values match engine output and cannot alter results. No generated AI text is fabricated when no provider exists.
- **DONE AND VERIFIED:** Re-ran **48 backend tests**, **8 frontend tests**, `npm run typecheck`, `npm run build`, and `git diff --check`. Extended the existing saved-experiment test to cover load topology, evaluate baseline, fail a link, transform, explain, save and reload matching baseline/recovery metrics. Authentication and persistence in that test use explicit mocks.
- **DONE AND VERIFIED (live native HTTP):** Existing backend 8013 and frontend 8080 health, baseline evaluation and full stateless analytical comparison return 200. Both origins report the configured synthetic example as **100 -> 0 -> 100 Mbps**, with simulated provenance and no persistence claim. Missing-session topology requests return 401. Frontend sign-in page returns 200. Results remain labeled analytical/simulated; candidate changes apply to experiment snapshots, not production deployment.
- **BLOCKER - genuine AI unavailable:** Effective backend configuration has no ASSISTANT_URL, ASSISTANT_MODEL or ASSISTANT_API_KEY. Exercising the actual explanation function returns `mode=deterministic`, `provider_status=not_configured`. A real AI-service request/output cannot be claimed. Configure a real chat-completion endpoint/model and any required server-only credential before an AI demo, then restart the backend.
- **IMPLEMENTED BUT NOT VERIFIED with a live signed-in session:** Successful sign-in, authenticated saved-topology retrieval and real Supabase save/reload. Browser session access is unavailable to the agent; passing mocked contracts are not live RLS/persistence evidence. No credentials, authentication policy, RLS or migrations were changed.
- Native servers are the actual demo setup; Docker Compose was not inspected or changed during this pass.

Launch from repository root in separate PowerShell terminals (existing servers are already running):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

```powershell
npm run dev -- --host localhost --port 8080
```

Open http://localhost:8080. Experiments save automatically on successful simulation/transformation/explanation calls; reload through Saved experiments. Do not rerun database migrations for this pass.

## Authentication and API repair verification - 2026-10-16

- **DONE AND VERIFIED (root cause):** Root `.env` had different backend/frontend public project keys. Live Supabase Auth settings rejected the backend-selected key with 401/Invalid API key and accepted the frontend key with 200. Synchronized the ignored backend key to the verified frontend key without printing either value. The running safe diagnostic now reports the intended project, publishable category and consistent configuration.
- **DONE AND VERIFIED:** Absolute root/backend environment paths, explicit separate alias fields with cross-project/key conflict checks, legacy anon fallback, key-category checks and redacted diagnostics. Settings remain process-scoped; restart after environment-only edits. No credentials are included in diagnostics or committed files.
- **DONE AND VERIFIED:** Standard HTTP Bearer security on all saved-topology/experiment routes and OpenAPI Authorize integration. Project API key goes in `apikey`; user token goes in `Authorization`. Missing/invalid/expired sessions return 401; upstream Auth 403/bad JWT is also mapped to 401. Database permission/RLS denials remain 403. Invalid project key is 503, not a misleading sign-in error. Transport/malformed upstream failures are 502.
- **DONE AND VERIFIED:** Vite's stale 8003 target was reproduced as proxy 502 while FastAPI 8013 was healthy, then corrected to shared target 8013. API URL normalization prevents a duplicate `/api` prefix. Protected frontend requests resolve current Supabase session and refresh once after 401. Publishable and legacy anon headers are tested separately. Public analytical evaluation remains stateless.
- **DONE AND VERIFIED:** Experiment insert/update requires confirmed returned rows; empty writes no longer report success. Scenario validation and execution share parameter normalization and reject nonexistent traffic endpoints. Caller JWT, explicit owner filtering and database RLS are retained.
- **DONE AND VERIFIED:** **48 backend tests pass** using `backend/.venv`; **8 frontend tests pass** with `npm run test:api`; `npm run typecheck`, focused ESLint, `npm run build`, schema export check, Python compilation and `git diff --check` pass. Windows temporary-file tests and Vite build needed execution outside sandbox process/ACL restrictions.
- **DONE AND VERIFIED (live HTTP):** **24 checks pass** across `127.0.0.1:8013` and `localhost:8080`, including health, scenario catalogue, safe configuration, analytical evaluation, full stateless experiment, legacy scenario execution, unauthenticated and invalid-token topology rejection, 404/405/422 negative cases, OpenAPI security and CORS. Backend preflight returns 200; Vite's valid preflight returns 204. Detailed statuses: `docs/api-verification.json`; repair report: `docs/auth-api-fix-report.md`.
- **IMPLEMENTED BUT NOT VERIFIED with a live valid user session:** Successful authenticated topology retrieval and persisted experiment round trip. These paths pass mocked Supabase transport/repository tests; the agent cannot access the browser's authenticated session. Live project-key acceptance and live invalid-token rejection were verified separately and are not presented as successful user authentication.
- No migrations were rerun, no tables reset, no database data deleted, and no RLS policy weakened. Existing development servers were reused and reloaded the changes.

## Previous analytical implementation verification - 2026-10-16

- **DONE AND VERIFIED:** Pre-change audit in `docs/repository-audit.md`. Work stays on `nettransform-integration`, preserving the user's initial status-date/build-evidence edits. No branch switching, resets or history rewriting.
- **DONE AND VERIFIED:** One analytical engine v2.0: deterministic Dijkstra, failure/interface exclusion, explicit defaults, delay components, stable-only M/M/1 queue estimates, bounded reserved utilization and separate overload ratios, independent path loss and unreachable demands. Browser previews and the legacy scenario API use that engine. Nine tracked bytecode artifacts, including stale deployment modules, were removed; no active Mininet/SSH source dependency existed.
- **DONE AND VERIFIED:** Multiple strategy generation, same-engine evaluation, selected-route link-outage stress cases, weighted ranking, change-budget/link/repair controls and recovery criteria. Candidate snapshots, changes, scores and assumptions remain inspectable. Physical feasibility and cost are conditional design proxies.
- **DONE AND VERIFIED (local contracts):** Saved run/rank/explain/history/reload APIs with repository test doubles; owner filters and caller JWT forwarding; optional AI-provider response/failure handling with mock transport and secret-exclusion assertions. These are not live database/provider checks.
- **DONE AND VERIFIED (native HTTP):** Uvicorn on localhost:8013 served health/OpenAPI and the complete stateless workflow without database or provider calls. Configured synthetic example: baseline **100 Mbps**, failure **0 Mbps**, recovery **100 Mbps**, **4 candidates**, repair selected, recovery criteria met. This is analytical example output, never physical telemetry. Temporary server stopped afterward.
- **DONE AND VERIFIED:** Backend suite **33 tests pass**; schema export drift check, Python compilation, frontend type-check, focused ESLint for new experiment tools/API client, production client/server build and diff whitespace check pass. Vite required execution outside the Windows sandbox process restriction. Pydantic generates the frontend topology types and JSON Schema.
- **IMPLEMENTED BUT NOT VERIFIED in a signed-in browser:** History, weighted strategy inspection, persisted explanation UI and JSON export. Compilation/type-check pass; visual interactions and realtime were not exercised with a live user session.
- **IMPLEMENTED BUT NOT VERIFIED against live services:** Supabase migration/RLS and a live AI provider. Apply all migrations, including `20261016120000_harden_connection_updates.sql`. Experiment proposals/criteria/explanations reuse existing JSON columns; topology remains in the original canonical tables.
- **IMPLEMENTED BUT NOT VERIFIED as a running container:** API Dockerfile/Compose. `docker compose config --quiet` passes; image build/start was not run. Native API startup and HTTP workflow were verified.
- **MOCKED:** Repository and AI-provider test doubles only. With no provider, actual application explanations are explicitly labeled deterministic.
- **NOT IMPLEMENTED:** Packet-level simulation, measured telemetry, ECMP/multiple simultaneous flows, QoS scheduling, policy/static routing, monetary pricing, physical installation validation, cloud/site latency and automatic deployment. Optional future Containerlab validation remains outside the core.

## Current architecture

- React, TypeScript, Vite, React Flow and Supabase Auth/Postgres power the existing topology workspace and Scenario Studio.
- `network_nodes` and `network_connections` remain the canonical saved topology tables. The failure simulation reads them through the authenticated user's Supabase JWT, so existing RLS policies continue to apply.
- FastAPI now provides a deterministic analytical failure simulation and modernization API. Results are labelled `simulated`; this feature does not contact Mininet, VMs, or live network devices.

## Network failure simulation and modernization

- **IMPLEMENTED; backend VERIFIED; live Supabase/browser integration NOT VERIFIED:** Authenticated topology retrieval, scenario catalogue, failure simulation, modernization proposal, and experiment retrieval are implemented under `/api/failure-simulation`.
- The authenticated `/failure-simulation` page loads the user's current topology and retains its node/link identifiers and positions. It shares the Scenario Studio scenario definitions, displays a baseline, failure view with playback, modernization candidate, assumptions, metrics and three-stage comparison.
- The engine supports configured link and device faults, traffic increases, capacity changes, redundancy, segment isolation, capacity increase and cloud migration scenarios. Its route choice and metrics are deterministic for the same input.
- Modernization evaluates and ranks multiple candidate snapshots and persists the experiment only; it does not alter the saved topology. The original changes only through the existing explicit topology save workflow.
- Simulation experiment storage migration: `supabase/migrations/20261014100000_create_simulation_experiments.sql`. It defines owner-scoped RLS. Apply this migration before using experiment persistence.
- The backend needs `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (or the supported publishable-key alias) to validate the user's session and query their RLS-scoped topology.
- The former screenshot-based “Restore Working Topology” action has been removed. The screenshot is not used as application data; restore the actual saved Supabase topology through the authenticated workflow.
- Scenario Studio's **Run scenario** hands the selected scenario and saved entity IDs to Failure Simulation and auto-runs the failed-state analysis. The solution action creates a candidate simulation and displays a scenario-specific implementation outline.
- If the API cannot be reached, the frontend now identifies the configured API URL and backend startup requirement. Local FastAPI settings load the root `.env` as fallback behind backend-local `.env`.
- Local development CORS accepts localhost and 127.0.0.1 on Vite-selected ports, including `http://localhost:8080`; the Scenario Studio redirect no longer sets React state during page navigation.
- Local frontend API requests use same-origin `/api` and Vite proxies them to FastAPI on port 8013, avoiding browser cross-origin requests in local development. Deployed frontends must set `VITE_API_URL` if the API is hosted separately.

## Simulation formulas and assumptions

- Shortest paths use Dijkstra with propagation plus serialization cost. Queue delay is estimated after routing only for stable loads; unstable delay is explicitly null.
- Missing link capacity, latency and packet-loss configuration are surfaced as assumptions and explicitly defaulted in the analytical model (1000 Mbps, 1 ms and 0% respectively).
- Offered traffic determines overload ratios; bottleneck-capped pre-loss reservations determine utilization. Delivered throughput applies independent configured path losses. Packet delivery incorporates configured loss and failed/unreachable routes.
- This is a deterministic mathematical model, not packet-level emulation or measured network telemetry. Recommendation selection is rule-based, not an LLM claim.

## Earlier validation evidence (retained history; current checks above)

- `python -m unittest discover -s tests -p "test_*.py"` from `backend/`: **16 tests passed**, including alternate/no route, device failure, traffic congestion, bandwidth changes, redundancy, missing values, API auth/catalog and CORS preflight checks.
- `python -m compileall -q app` from `backend/`: passed.
- `git diff --check`: passed.
- Local FastAPI `/api/health` smoke check: **passed** after starting the backend on `127.0.0.1:8003`; its `/api/failure-simulation/scenarios` endpoint is available without authentication. Authenticated topology fetch and experiment persistence still require a signed-in browser session and the experiment migration.
- CORS smoke checks with origin `http://localhost:8080`: health response and authenticated topology preflight both returned the matching `Access-Control-Allow-Origin`; preflight permits `authorization,content-type`.
- Vite proxy smoke check on the user's exact frontend origin `http://localhost:8080`: `/api/health` reached FastAPI and returned 200; `/api/failure-simulation/topology` reached FastAPI and returned the expected unauthenticated 401 JSON instead of a CORS/network error.
- `npm run build`: **passed** (Vite + TanStack Nitro production client and server bundles built cleanly). Browser runtime with a live session remains **NOT VERIFIED**.
- Live Supabase migration, authenticated API calls and persistence are **NOT VERIFIED** in this environment because no live project/session was exercised.

## Known limitations / not implemented

- The analytical playback animates calculated route/link steps; it is not real-time packet transmission.
- Queueing uses a documented approximation, not a packet-level queue simulator. Detailed time-series telemetry is not persisted separately.
- Modernization candidates are limited to transformations supported by the current graph model. They are proposals, not deployed changes.
- No claim of measured performance improvement or machine-learning prediction is made.


## 2026-10-19 - Simplified failure simulation presentation

- IMPLEMENTED: Existing page reorganized into five steps: select failure, run, generate solution, inspect proposal, compare. Four primary metrics show throughput, packet loss, average latency and tested-flow connectivity. Failure metrics remain bound to the failure snapshot after generating a candidate.
- IMPLEMENTED: Collapsed Advanced Details retains existing optimizer controls, Pareto analysis, alternative selection/decision tools, AI explanations, history/export, inventory, assumptions, detailed metrics and route playback. Backend impact, recommendation and outcome text remain authoritative; no-change candidates are explicitly labeled.
- IMPLEMENTED: Existing React Flow component supports compact route labels and highlights candidate node/link changes against the failed graph, including repairs/capacity changes. Failed links stay red. Canonical topology and all existing backend changes were preserved.
- DONE AND VERIFIED: 10 existing frontend tests passed; TypeScript check passed; focused ESLint completed with zero errors and one pre-existing auto-run effect dependency warning. Production build passed outside the Windows sandbox (initial sandbox attempt failed with spawn EPERM). Diff whitespace check passed.
- IMPLEMENTED BUT NOT VERIFIED: Signed-in browser interaction and visual review were not exercised in this pass. No backend calculation changes or database operations were made for this presentation task.
- Files changed for this task: src/routes/_authenticated/failure-simulation.tsx, src/components/network/simulation-topology.tsx, project-status.md. Other pre-existing working-tree changes remain untouched.


## 2026-10-19 - Branch WAN transformation demonstration

- IMPLEMENTED: Expandable Branch WAN transformation demonstration on the existing failure page; POST /api/analysis/wan-demo reuses run_experiment, evaluate_candidate, describe_selection and the same analytical simulator. No second simulator or canonical topology store.
- Selection: least change units among candidates meeting 95% delivery and 50 ms mean latency, plus primary-WAN-outage survival when explicitly required. Retain, repair and dual-WAN SD-WAN architecture are independently evaluated. No qualifying candidate is reported honestly.
- Architecture: adds a router with sd_wan_edge role, a second provider and two distinct uplinks. Primary-domain links remain disabled during the transformation evaluation. Provider independence, secondary 200 Mbps uplink and delay/loss values are design assumptions. Static shortest paths model failover; no SD-WAN protocol, convergence time, real packets or physical diversity validation.
- Saved topology eligibility: exactly one branch_wan node, one wan_service node, and one incident connection with metadata.wan=true and a declared failure_domain. Otherwise a clearly labeled reusable synthetic branch example is used. All operations are isolated copies and stateless; no saved topology or experiment is overwritten.
- DONE AND VERIFIED: 5 new focused tests; full backend suite 96 tests passed outside sandbox (initial run had a Windows temporary-directory permission error). 10 frontend tests, type-check, new component lint and production build passed. Fresh Uvicorn on 8014 returned HTTP 200 for continuity-required SD-WAN (100/0/100 Mbps), repair-sufficient (100/0/100 Mbps), and no-feasible-option at 500 Mbps. Tests verify architectural difference, original immutability, exact metric recalculation, primary-to-secondary route change and disconnection with both uplinks down.
- IMPLEMENTED BUT NOT VERIFIED: Signed-in browser interaction. Existing 8013 process returned 404 for the newly added route, as did its 8080 proxy; restart backend to load current code. Temporary verification server is stopped after checks.
- Launch from backend: .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload. Frontend from root: npm run dev -- --host localhost --port 8080. Open Failure Simulation and expand Branch WAN transformation demonstration.
- Task files: backend/app/services/wan_demo.py, backend/app/api/analysis.py, backend/tests/test_wan_demo.py, src/components/network/wan-transformation-demo.tsx, src/routes/_authenticated/failure-simulation.tsx, project-status.md. Existing unrelated working changes preserved.

## 2026-10-20 - Integration snapshot and traffic simulation verification

- Current integration snapshot includes the simplified failure workflow, WAN architecture demonstration, bounded synthetic packet-event simulation, shared-traffic capacity candidates, service-chain what-if actions, rule-based insights, and the event-catalog NSGA-II UI. See docs/traffic-simulation-upgrade.md for model boundaries and demonstration steps.
- Backend regression suite: 108 tests passed in the pre-push verification. Provider configuration was absent in the implementation pass; no trained predictive ML model or live AI success is claimed. Signed-in browser interaction remains unverified.
- User requested pushing current nettransform-integration and switching to backend. Remote and local inspection found no backend branch; a local backend branch will be created from the saved integration commit. No published history is rewritten.
- Credential scan of 192 tracked/nonignored files found no configured credential values or private-key/token patterns. Root and backend .env files remain ignored and excluded.
- DONE AND VERIFIED before push: TypeScript check, all 12 frontend tests, production build, and diff whitespace check passed.
