# Project Status

Last reviewed: 2026-10-14

## Current architecture

- React, TypeScript, Vite, React Flow and Supabase Auth/Postgres power the existing topology workspace and Scenario Studio.
- `network_nodes` and `network_connections` remain the canonical saved topology tables. The failure simulation reads them through the authenticated user's Supabase JWT, so existing RLS policies continue to apply.
- FastAPI now provides a deterministic analytical failure simulation and modernization API. Results are labelled `simulated`; this feature does not contact Mininet, VMs, or live network devices.

## Network failure simulation and modernization

- **IMPLEMENTED; backend VERIFIED; live Supabase/browser integration NOT VERIFIED:** Authenticated topology retrieval, scenario catalogue, failure simulation, modernization proposal, and experiment retrieval are implemented under `/api/failure-simulation`.
- The authenticated `/failure-simulation` page loads the user's current topology and retains its node/link identifiers and positions. It shares the Scenario Studio scenario definitions, displays a baseline, failure view with playback, modernization candidate, assumptions, metrics and three-stage comparison.
- The engine supports configured link and device faults, traffic increases, capacity changes, redundancy, segment isolation, capacity increase and cloud migration scenarios. Its route choice and metrics are deterministic for the same input.
- Modernization produces a candidate snapshot and persists the experiment only; it does not alter the saved topology. The original changes only through the existing explicit topology save workflow.
- Simulation experiment storage migration: `supabase/migrations/20261014100000_create_simulation_experiments.sql`. It defines owner-scoped RLS. Apply this migration before using experiment persistence.
- The backend needs `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (or the supported publishable-key alias) to validate the user's session and query their RLS-scoped topology.
- The former screenshot-based “Restore Working Topology” action has been removed. The screenshot is not used as application data; restore the actual saved Supabase topology through the authenticated workflow.
- Scenario Studio's **Run scenario** hands the selected scenario and saved entity IDs to Failure Simulation and auto-runs the failed-state analysis. The solution action creates a candidate simulation and displays a scenario-specific implementation outline.
- If the API cannot be reached, the frontend now identifies the configured API URL and backend startup requirement. Local FastAPI settings load the root `.env` as fallback behind backend-local `.env`.
- Local development CORS accepts localhost and 127.0.0.1 on Vite-selected ports, including `http://localhost:8080`; the Scenario Studio redirect no longer sets React state during page navigation.
- Local frontend API requests use same-origin `/api` and Vite proxies them to FastAPI on port 8003, avoiding browser cross-origin requests in local development. Deployed frontends must set `VITE_API_URL` if the API is hosted separately.

## Simulation formulas and assumptions

- Shortest paths use Dijkstra with configured link latency plus serialization and an M/M/1-style queue-delay estimate.
- Missing link capacity, latency and packet-loss configuration are surfaced as assumptions and explicitly defaulted in the analytical model (1000 Mbps, 1 ms and 0% respectively).
- Offered traffic determines utilization; achieved throughput is capped by route capacity. Packet delivery incorporates configured loss and failed/unreachable routes.
- This is a deterministic mathematical model, not packet-level emulation or measured network telemetry. Recommendation selection is rule-based, not an LLM claim.

## Validation evidence

- `python -m unittest discover -s tests -p "test_*.py"` from `backend/`: **16 tests passed**, including alternate/no route, device failure, traffic congestion, bandwidth changes, redundancy, missing values, API auth/catalog and CORS preflight checks.
- `python -m compileall -q app` from `backend/`: passed.
- `git diff --check`: passed.
- Local FastAPI `/api/health` smoke check: **passed** after starting the backend on `127.0.0.1:8003`; its `/api/failure-simulation/scenarios` endpoint is available without authentication. Authenticated topology fetch and experiment persistence still require a signed-in browser session and the experiment migration.
- CORS smoke checks with origin `http://localhost:8080`: health response and authenticated topology preflight both returned the matching `Access-Control-Allow-Origin`; preflight permits `authorization,content-type`.
- Vite proxy smoke check on the user's exact frontend origin `http://localhost:8080`: `/api/health` reached FastAPI and returned 200; `/api/failure-simulation/topology` reached FastAPI and returned the expected unauthenticated 401 JSON instead of a CORS/network error.
- TypeScript type-check was run; it returned no diagnostics, though the local process did not provide an exit status on its first invocation. Frontend build and browser runtime are **NOT VERIFIED**.
- Live Supabase migration, authenticated API calls and persistence are **NOT VERIFIED** in this environment because no live project/session was exercised.

## Known limitations / not implemented

- The analytical playback animates calculated route/link steps; it is not real-time packet transmission.
- Queueing uses a documented approximation, not a packet-level queue simulator. Detailed time-series telemetry is not persisted separately.
- Modernization candidates are limited to transformations supported by the current graph model. They are proposals, not deployed changes.
- No claim of measured performance improvement or machine-learning prediction is made.
