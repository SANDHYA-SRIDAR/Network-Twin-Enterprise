# Network Failure Simulation and Modernization

## Architecture

The authenticated frontend requests `/api/failure-simulation/topology` with its Supabase access token. FastAPI validates that token with Supabase Auth, then reads `network_nodes` and `network_connections` using that same user token. Supabase RLS remains the access control for both topology reads and experiment writes. The current topology tables remain canonical; experiments store immutable baseline and failure snapshots and an optional candidate snapshot.

Scenario IDs and labels are shared by Scenario Studio and this module in `src/lib/scenario.ts`. The deterministic analytical engine lives in `backend/app/engines/analytical_simulator.py`.

## Supabase setup

Apply [`20261014100000_create_simulation_experiments.sql`](../supabase/migrations/20261014100000_create_simulation_experiments.sql) in the Supabase SQL editor or through the project's normal migration workflow. It creates one RLS protected experiment table. Existing node and connection technical values remain in their current `configuration` JSONB columns; no duplicate capacity or latency columns are added.

Configure the FastAPI process with:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<project-publishable-or-anon-key>
```

The value is the public project key, not a service-role key. Requests use the signed-in user's bearer token, so RLS applies to topology reads and experiment writes. Configure the frontend's `VITE_API_URL` to point to this FastAPI instance.

## Run locally

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8003
```

In another terminal:

```powershell
npm install
npm run dev
```

Sign in, open **Failure Simulation**, choose an existing Scenario Studio scenario, choose traffic endpoints and offered load, then run the failure simulation. After the failure metrics and playback are available, choose **Resolve / Modernize Network** to request a separate candidate snapshot. The original topology is never written by these endpoints.

## API

All experiment and topology endpoints below require `Authorization: Bearer <Supabase access token>`.

- `GET /api/failure-simulation/scenarios` lists the supported scenario IDs.
- `GET /api/failure-simulation/topology` returns the authenticated user's saved topology and a stable fingerprint.
- `POST /api/failure-simulation/run` re-reads the latest saved graph, checks the fingerprint, simulates baseline and failure, and saves an experiment.
- `POST /api/failure-simulation/{experiment_id}/modernize` creates and evaluates a candidate without changing saved nodes or links.
- `GET /api/failure-simulation/experiments/{experiment_id}` returns a user's saved experiment under RLS.

Example run body:

```json
{
  "scenario_type": "link_failure",
  "parameters": { "link_id": "<saved-connection-uuid>" },
  "traffic": {
    "source_node_id": "<saved-source-node-uuid>",
    "target_node_id": "<saved-destination-node-uuid>",
    "offered_mbps": 100,
    "duration_seconds": 60,
    "packet_size_bytes": 1500
  },
  "topology_fingerprint": "<fingerprint-returned-by-topology-endpoint>"
}
```

Scenario parameters use the existing scenario types: `link_failure` (`link_id`), `device_failure` and `segment_isolation` (`node_id`), `traffic_increase` (`factor`), `bandwidth_change` (`link_id`, `bandwidth_mbps`), `redundancy_add` (`source_node_id`, `target_node_id`, optional `bandwidth_mbps`), `capacity_increase` (`link_id`, `increase_mbps`), and `cloud_migration` (`node_id`).

## Model and provenance

Routing uses deterministic shortest path. Per-link cost is propagation delay plus packet serialization delay plus a bounded M/M/1-style queue delay approximation. Offered traffic, interval, and packet size are explicit simulation inputs. Delivery is constrained by the narrowest route capacity and the configured packet-loss probability. Congestion is offered load divided by link capacity; utilization can exceed 100% to show overload.

Missing capacity, delay, and packet-loss values stay absent in saved topology and are shown as unconfigured. For calculations only, the model uses documented defaults of 1000 Mbps, 1 ms, and 0% packet loss and lists each assumption in results. Packet counts are computed estimates, not packets observed on a network. Cloud migration is placement-only because the existing schema has no site or cloud-latency model; its network metrics do not change. Replacement devices and backup links are candidate IDs stored only in an experiment snapshot.

There is no trained AI model or live measurement source in this module. Modernization is a deterministic rule-based candidate engine, and relative cost is qualitative because no monetary cost model exists.

## Verification

Backend simulation unit tests cover alternate and disconnected link failure, device replacement, traffic surge and congestion, bandwidth change, redundancy addition, missing configuration, invalid targets, and distinct flow endpoints. A live Supabase session and database migration are still required to verify RLS reads/writes in an actual project. Browser playback and visual behavior require a running frontend session.
