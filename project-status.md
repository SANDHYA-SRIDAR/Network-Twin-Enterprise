# Project Status

Last reviewed: 2026-10-14

## Current architecture

- React, TypeScript, React Flow topology editor with a FastAPI validation/scenario backend.
- Supabase Auth and Postgres are the canonical store for each user's topology. `network_nodes` stores devices and `network_connections` stores links.
- The topology editor computes network metrics locally from the active graph. This is a mathematical simulation; it does not contact Mininet, a VM, Docker, or live network devices.

## Topology persistence

- **IMPLEMENTED, NOT VERIFIED AGAINST A LIVE SUPABASE PROJECT:** Save Topology reads the current node and link ids, upserts the current graph, then removes rows absent from the canvas. RLS scopes these queries to the authenticated user.
- Node type, label, canvas position, status and device settings are stored on `network_nodes`.
- Link endpoints, handles and cable type are stored on `network_connections`. Simulation parameters (`base_latency_ms`, `max_capacity_mbps`, `current_load_mbps`, `priority_load_mbps`, and `qos`) are stored inside its existing `configuration` JSONB column; no schema change is needed for the SQL supplied by the user.
- Simulation failures are stored as `offline`, which is accepted by the supplied status CHECK constraints. The app maps this to a failed element for routing calculations.
- Editing, adding and deleting elements currently also writes through to Supabase. Save Topology is an explicit full-graph reconciliation.

## Mathematical simulation

- **IMPLEMENTED, NOT VERIFIED:** Dijkstra routing excludes offline nodes and links, with congestion-adjusted latency as its edge weight.
- Utilization, latency, throughput and packet loss are computed in `src/lib/network-simulation.ts`.
- The topology workspace provides controls for device/link failure, traffic spikes, and a load balancing/QoS model. The link inspector edits latency, capacity, total load and critical traffic load. Link colors reflect utilization.
- A Restore Working Topology action can rebuild the 8-device, 7-link layout from the user's screenshot and save it through the canonical Supabase topology tables. Device positions and crossover link choices are reconstructed approximately from the image; this restore action has not been verified in a live Supabase session.
- Live Network Monitor reports a computed endpoint path, latency, throughput, packet loss and mean link utilization.
- These metrics are synthetic by design, not measured telemetry. QoS reserves a modeled critical traffic load for the priority latency metric; it is not a packet-level QoS scheduler.
- Scenario Studio loads and converts the authenticated user's Supabase graph for its modeled scenario request; it no longer submits a hard-coded sample graph.

## Legacy live-network integration

- Mininet telemetry polling, the frontend deploy action, and the backend Mininet/deployment/SSH API path have been removed from the active application. The FastAPI app exposes health, network validation, and modeled scenario endpoints.
- Historical VM/Mininet verification notes from earlier project work are not evidence for the current simulator and are intentionally not carried forward here.

## Validation evidence

- `node_modules/.bin/tsc --noEmit --pretty false` completed without reported TypeScript errors.
- `python -m unittest discover -s tests -p test_scenario_engine.py` (from `backend/`) passed, and `python -m compileall -q backend/app` completed.
- A Node smoke check selected a primary path, rerouted after node failure, returned 25% loss at 150% utilization, and kept modeled critical traffic latency low with QoS enabled.
- `npm run build` is **NOT VERIFIED**: the local Windows environment failed while loading the Tailwind native module (`spawn EPERM`, `UNLOADABLE_DEPENDENCY`). This prevented Vite from compiling the app, so UI integration remains unverified.
- No live Supabase credentials/session were exercised in this review. Persistence behavior is confirmed from source only; a successful toast in a real session is still needed to prove the user's Supabase project accepts the writes.

## Not implemented

- Packet-level traffic simulation, real queue models, real measured telemetry, machine-learning prediction, and persistence transactions across node/link changes.
