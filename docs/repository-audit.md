# Repository audit — 2026-10-16 (before implementation)

## Existing architecture

Inspected branch `nettransform-integration` at `9eb570b`, tracking the same origin commit. The only initial working-tree modification was the user's status-date/build-evidence update in `project-status.md`; preserve it. Local main is `4b513fb`, origin/main is `1a0a30e` (README title only). Main contains the authenticated TanStack application and Supabase topology/chat migrations, but no Python backend. The integration branch adds FastAPI, scenarios, analytical simulation, experiment storage, and the Vite API proxy. No branch switching or history rewriting is needed.

React 19/TypeScript/TanStack Start file routes live in `src/routes`, with authenticated topology, scenarios, recommendations and failure-simulation views. React Flow editing, local component state, undo/redo, realtime Supabase synchronization and stored chat live in `network-workspace.tsx`. Shared UI/Tailwind and Recharts dependencies already exist. Supabase Auth protects routes; the custom client is used by application views, while generated client/server helpers support framework integrations. Keep those framework files.

One FastAPI app includes network validation, legacy scenario and failure-simulation routers. Pydantic network models and the TypeScript network schema adapt canonical `network_nodes`/`network_connections` JSON configurations. Experiments use owner-scoped JWT requests through httpx, not service-role access. Existing migrations define profile, topology, chat and experiment RLS. Connection UPDATE policy lacks the endpoint ownership checks present on INSERT.

## Implemented and tested

Initial command: `python -m unittest discover -s tests -p 'test_*.py'` in backend: **16 passed**. Tests cover basic schema validation, failure rerouting/disconnection, replacement, congestion, bandwidth, candidate links, defaults, auth guard and CORS. These are local tests, not live Supabase or device evidence.

## Implemented but unverified

Browser editing/auth/realtime/undo, saved experiment round trips, playback, recommendation writes and deployed migrations. Existing roadmap checkboxes overstate browser verification. Previous build evidence in project-status belongs to the user; rerun build after edits.

## Missing or incorrect

- Three metric implementations disagree: Python scenario summary invents load and redundancy; frontend network-simulation estimates separately; main engine caps unstable queue delays.
- Main engine does not validate every direct call, treats unavailable nodes as up, reports overload as utilization above 100%, and does not expose delay components or unsupported metrics.
- Single modernization proposal, no explicit ranking weights, resilience stress test, feasibility constraints, history listing, or provider-backed assistant. Current chat is templated diagnostics.
- Topology identity/ownership/timestamps are absent in the canonical API shape. Device model mapping loses hub/access-point identity. Mask/prefix, finite values and status validation need strengthening.
- No deployment container or concise self-contained startup guide.

## Retain

Existing app/routes/auth, React Flow editor, UI primitives, Supabase integrations, canonical topology tables, network schema/adapters, failure engine and experiment repository. Preserve valuable configuration and undo/realtime behavior. Historical Lovable plans remain historical requirements, not evidence of completed work.

## Consolidate

Route legacy scenario computation through the main engine; replace frontend metric calculations with API-derived metrics while preserving visualization. Keep adapters for legacy stored row names instead of creating a second topology store. Extend existing experiment JSON proposal/metrics fields for multiple candidates and ranking.

## Safe removal

Nine accidentally tracked Python bytecode files, including three stale Mininet modules. Source inventory shows no current Mininet/Paramiko/SSH/OVS router, runtime requirement, deployment script or dependency; do not fabricate a cleanup of nonexistent source. Retain general telemetry panels, relabel modeled data accurately.

## Migrations

Apply existing experiment migration. Add connection UPDATE endpoint ownership checks. Keep one saved topology per user, deriving stable identity and revision from canonical rows; do not duplicate nodes/links. Candidate graphs, criteria, scores and explanations can use existing experiment JSON columns without new tables.

## Potential breaking changes

Engine version must change for corrected formulas. Unstable latency becomes null with explicit status. Validate invalid/nonfinite configuration rather than silently accepting it. Legacy scenario API response changes require a documented compatibility adapter. Existing saved experiments keep their engine version; recomputation must not mislabel old metrics. No physical deployment or packet simulation is provided. Cloud placement, policy routing, multi-flow allocation and hardware compatibility require explicit unsupported states where data is insufficient.
