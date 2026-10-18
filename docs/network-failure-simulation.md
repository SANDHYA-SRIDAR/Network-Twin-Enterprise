# Analytical simulation and decision workflow

## Canonical architecture

One FastAPI application (`backend/app/main.py`) mounts the analytical API. `engines/analytical_simulator.py` owns routing, scenario mutation and metrics. `services/transformation.py` generates proposals, evaluates them through that engine, stress-tests resilience and ranks them. The old scenario endpoint is a compatibility response adapter to the same engine, with explicit traffic required. Browser metric code calls FastAPI; it only calculates configured load ratios locally for cable annotations. The original diagnostics chat remains a labeled topology diagnostics feature; experiment explanations use the optional AI adapter.

`models/network.py` is authoritative. `export_contract.py` generates `docs/network-definition.schema.json` and `src/lib/network-contract.ts`. `network-schema.ts` contains React Flow adapters and editor validation. IDs, node/link status, numerical bounds, finite numbers, IPs, masks/prefix agreement, gateways, unique IDs and graph/interface references are validated before evaluation. Unknown schema fields and unsupported traffic constraints are rejected. A workstation uses the established device type `pc`; `hub`, `access_point`, and `load_balancer` are supported too. Device resource parameters are retained; processing-delay/capacity effects are explicitly unsupported.

Supabase `network_nodes` and `network_connections` remain the sole editable topology. The canonical saved graph has a stable UUID derived from its owner, a content revision hash, and timestamps derived from the earliest/latest surviving rows; these are not a separate topology creation/version-history table. Unsaved inline graphs default to id `unsaved`, schema version `1.0`, no owner/timestamps. No timestamp or ownership measurement is invented. An experiment stores immutable baseline/failure snapshots, effective traffic, scenario parameters, engine version, candidate graphs, scores, selection, criteria and the latest explanation in the existing JSON columns. Re-ranking replaces that experiment's current proposal; export first to retain a separate decision revision. Saved topology is never written by simulation endpoints.

## API contract

`GET /api/openapi.json` is the full machine-readable contract; `/docs` exposes Swagger UI.

| Endpoint | Behavior | Auth/persistence |
| --- | --- | --- |
| `GET /api/health` | Application readiness | Public |
| `POST /api/analysis/evaluate` | `{topology, traffic}` returns route, metrics and assumptions | Public, stateless |
| `POST /api/analysis/experiment` | Inline topology plus scenario, traffic, optional criteria; baseline/failure/all candidates and ranking | Public, stateless; `persisted:false` |
| `GET /api/failure-simulation/scenarios` | Supported scenarios and parameters | Public |
| `GET /api/failure-simulation/topology` | Owner's saved canonical graph and fingerprint | Supabase bearer JWT |
| `POST /api/failure-simulation/run` | `{scenario_type, parameters, traffic, topology_fingerprint?}`; checks latest saved graph and stores experiment | Supabase bearer JWT |
| `POST /api/failure-simulation/{id}/modernize` | Optional ranking criteria; stores all candidates, selection and metrics | Supabase bearer JWT |
| `POST /api/failure-simulation/{id}/assistant` | `{question}`; evidence explanation, persisted with provenance | Supabase bearer JWT |
| `GET /api/failure-simulation/experiments` | Latest 50 owner-scoped summaries | Supabase bearer JWT |
| `GET /api/failure-simulation/experiments/{id}` | Full snapshots, input parameters, metrics, proposal and explanation | Supabase bearer JWT |
| `POST /api/network/validate` | Schema and graph consistency issues | Public, stateless |
| `POST /api/network/create` | Legacy validation/normalization; does not save or deploy | Public, stateless |
| `POST /api/scenario/run` | Legacy response adapter; explicit `traffic` now required | Public, stateless |
| `POST /api/scenario/validate` | Validates graph, demand and mutation | Public, stateless |

Limits: 500 nodes, 2000 links, one demand of 0 < offered Mbps <= 1,000,000, 64?65,535-byte mean packet size (default 1500), 1?86,400-second reporting interval (default 60). Analytical runs return 422 for invalid values/references; the validation-only endpoint returns its issue list. A changed topology fingerprint or re-ranking an older engine experiment returns 409. Repository errors use safe messages; every database request uses the caller JWT and explicit owner filter, retaining RLS authority. Configure Supabase for saved routes only.

Scenarios: `link_failure(link_id)`, `device_failure(node_id)`, `traffic_increase(factor)`, `bandwidth_change(link_id, bandwidth_mbps)`, `redundancy_add(source_node_id,target_node_id,bandwidth_mbps?)`, `capacity_increase(link_id,increase_mbps)`, `segment_isolation(node_id)`, and `cloud_migration(node_id)`. Cloud migration is placement-only, with no claimed metric effect. Isolation is not automatically bypassed. Traffic factors are positive and at most 1000; scaled demand must still fit demand bounds. Link capacity is positive and at most 1,000,000 Mbps.

## Mathematical model

This is a deterministic, undirected, single-flow, steady-state reservation model. Dijkstra minimizes propagation plus serialization delay, with stable node/link ordering for ties. Failed, offline, unavailable devices/links, down referenced interfaces and console cables cannot forward. Static/policy routing, segmentation rules and firewall constraints produce explicit unsupported errors rather than being silently ignored. IP addresses/gateways are validated configuration; packet forwarding follows the graph, not subnet/IP routing rules. QoS and multiple simultaneous flows are unsupported. No packet transmission or convergence is simulated.

For offered load L Mbps, capacity C Mbps, mean packet size B bytes:

- Serialization S = 8B / (1000C) milliseconds.
- Queue utilization ratio rho = L/C. Under a Poisson arrival / exponential-service M/M/1 approximation, mean queue wait Wq = S*rho/(1-rho), only for rho < 1. Configured mean packet size sets mean service time; real fixed-size packets are not exponential, so this remains an approximation.
- At rho >= 1, there is no finite steady-state queue mean: queue and total latency are null, `queueing_status=unstable`. Unreachable demands use null delay with status `unreachable`. Maximum latency is always unsupported; a mean does not determine a maximum.
- Propagation and serialization sum along the selected path. Stable total mean adds queue waits. Queue delay is not part of routing cost, avoiding circular load-dependent route selection.
- Path capacity is the minimum link capacity. Achievable pre-loss rate A = min(L, path capacity). Link utilization is the reserved pre-loss rate A/C, between 0 and 100%; `offered_load_ratio=L/C` separately exposes overload. It is not observed wire utilization.
- Conservative reservations and queue loads do not attenuate ingress traffic by intermediate random losses. This deliberate approximation overestimates downstream reservation/queue load when configured losses are large. Per-link achieved rate fields represent pre-loss reservations, not observed forwarded traffic.
- Independent link-loss survival P = product(1 - loss_pct/100). Delivered rate = A*P. Fluid congestion loss fraction = 1-A/L. Combined end-to-end loss fraction = 1-(A/L)*P. This is excess-demand admission/drop accounting, not a finite-buffer stochastic loss model.
- Estimated sent packet count = floor(L*1,000,000*duration/(8B)). Delivered counts are floored expectations; aggregate loss percentages derive from rates and can differ slightly from rounded counts.

The result includes reachability, selected node/link routes, component delays, achievable/delivered/offered rates, link reservations and offered ratios, bottleneck IDs, congestion and unreachable demands. It never labels these as measured values. Connectivity percentage means nodes reachable from the demand source, not all-pairs enterprise reachability.

Missing capacity, delay and loss remain null in configured fields. Calculations explicitly assume 1000 Mbps, 1 ms and 0% and list each use in assumptions. These defaults are neither measurements nor written back to the saved topology. Stored resource, IP, cable and traffic metadata are preserved without pretending to model unsupported effects. Duplicate addresses on active devices are invalid; an offline original and its active candidate replacement may retain the same address for takeover.

Baseline and failure use the same effective demand, including a selected traffic multiplier, isolating graph changes. For a traffic-only surge the two graph metrics are consequently equal; compare a separate experiment at the original rate to study load change itself. Every candidate uses that same effective demand. Replacement endpoint identity is explicitly mapped to the candidate replacement; unrelated baseline outages remain in place.

## Decision criteria

Candidates include retain surviving routes, restore the selected failed configuration if repair is allowed, targeted backup/replacement or capacity upgrade where supported, and a dedicated service path when new links are allowed and endpoints remain operational. Duplicate no-change proposals are omitted. No bypass is proposed for segment isolation or unsupported cloud placement. Proposed link delay/loss use explicit defaults where installation data is missing; this is conditional design feasibility, not proof a cable can be installed.

Weights default to performance .4, resilience .3, feasibility .2, cost .1. Supply all four nonnegative finite weights with a positive sum. Additional controls: `max_change_units` (default 100), `latency_target_ms` (default 50), `allow_new_links`, `allow_repair`. Hard budget/link permissions filter eligible candidates; all evaluated candidates remain visible with constraints. A no-change candidate always fits the budget, including when no recovery is possible.

Component scores (0?1): performance = .8*(delivered/offered) + .2*min(1,latency_target/mean_latency), with absent mean scoring zero for latency; resilience = fraction of individually failed selected-route links whose outage still leaves the demand connected; feasibility = 1/(1+.1*change count), a complexity proxy; cost = 1/(1+change units). New device=8 units, link=3, capacity upgrade=2, restored status=1. No monetary pricing or verified interface compatibility is implied. Resilience tests are deterministic connectivity stress cases; they do not assert full N-1 node or load resilience. Weighted scores are normalized by weight sum, then tied by stable strategy ID. Selection is preference-dependent. A selected strategy is labeled recovered only if connected, at least 95% offered traffic is delivered and finite mean latency meets the target.

## Persistence, AI, and deployment

Apply existing migrations plus `20261016120000_harden_connection_updates.sql`, which adds endpoint ownership checks to connection UPDATE. Experiment JSON already supports proposals, scores and explanations; no duplicate topology tables are introduced. Live migration/RLS verification requires a real Supabase project and separate test sessions.

An explicit explanation request can call the server-only chat-completion adapter. It receives selected computed metrics, scores, criteria, assumptions and the question, not arbitrary topology configuration or provider credentials. Text is stored with `mode`, provider status and evidence. Generated text is advisory; it cannot mutate graph, scores or selection. Missing/failed providers return a deterministic explanation. The supplied tests mock the provider contract; no live model performance claim is made.

Docker Compose runs only the API. There is no deployment adapter in the core. A future Containerlab or hardware validation adapter could consume an approved exported candidate and record separate measured evidence with its own provenance, credentials, lifecycle and optional dependencies. It must remain outside the analytical primary pipeline and must never relabel analytical metrics as measurements.

See project-status.md for executed checks and remaining verification limits.
