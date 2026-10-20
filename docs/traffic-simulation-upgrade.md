# Traffic simulation upgrade — 2026-10-20

## Audit and implementation boundaries

The existing repository already had a canonical Pydantic/Supabase topology, an undirected NetworkX adapter, a deterministic single-flow analytical engine, seeded Louvain structural analysis, rule-based anomaly findings, deterministic transformation rules, pymoo NSGA-II, clickable Pareto inspection, authenticated experiment persistence, and an optional evidence-checking AI adapter. It did not execute packet events or share finite queues among concurrent application flows.

This increment preserves that workflow. The optional traffic panel on Failure Simulation runs a bounded discrete-event extension over the same canonical graph, operational-link rules, scenario mutations and candidate action library. It does not replace authentication, theme controls, topology editing, saved experiments, the WAN demonstration or the existing analytical optimizer.

## Run and demonstrate

From the repository root, use separate terminals:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

```powershell
npm run dev -- --host localhost --port 8080
```

Sign in at http://localhost:8080. Choose a scenario in Scenario Studio, then open Failure Simulation. The **Interactive application traffic, risk and recovery** section opens automatically for scenario launches; it can also be expanded manually. It receives the saved topology, selected scenario, target and traffic endpoints. Running this panel is explicitly a stateless preview and does not overwrite the saved analytical experiment.

1. Choose **Try home**: a bridge-link outage disconnects both applications. Run traffic simulation and inspect repair/capacity alternatives.
2. Choose **Try office**: a primary-link failure reroutes traffic onto a lower-capacity backup, causing finite-buffer loss. Shared-traffic capacity candidates can restore delivery. Compare named application routes and the throughput chart.
3. Choose **Try multi branch**: two sources compete for shared links. Change application rates and peak factors and repeat.
4. Select **Prioritize traffic** to use strict non-preemptive priority queues. Critical traffic can wait less, while lower-priority traffic can be delayed or starved. This is not additional capacity.
5. Choose **Explore NSGA-II trade-offs**. Click a chart point or a recovery button to inspect its graph, actual event metrics and target attainment. Switch between latency/cost and flow-availability/cost views.
6. Choose **Try wan** for the existing SD-WAN architecture under the primary WAN outage. For an explicit repair-versus-redesign comparison, use the separate Branch WAN transformation demonstration.
7. Click **Explain the recommended option**. The server recomputes the experiment and sends evidence to the configured provider, with real session validation. Missing/invalid providers produce a labeled deterministic explanation.

Sample requests are reusable through `GET /api/analysis/traffic-samples/home`, `/office`, `/multi_branch` and `/wan`. POST the returned JSON to `/api/analysis/traffic-experiment`. `POST /api/analysis/traffic-experiment/explain` requires a real Supabase access token and validates it with Supabase. Simulation previews use the existing public, stateless analysis namespace; they cannot read or write another user's topology.

## What is simulated

- Each application declares source, destination, total Mbps, associated user count, packet size, TCP/UDP label, priority and peak factor. User count is explanatory metadata, not a multiplier on offered traffic. User counts across applications can overlap.
- Peak traffic starts halfway through the observation interval. Arrivals are evenly spaced within each half; only complete packets are generated. Requests that generate no packets are rejected, rather than reporting invented averages.
- NetworkX Dijkstra minimizes configured propagation plus serialization cost. A deterministic projection chooses the cheapest physical link among parallel links and retains its ID. Failed nodes, links and interfaces are excluded through the shared adapter. Directionality remains explicitly undirected.
- Scenario changes apply to a separate copy at time zero. The before/after routes represent instantaneous recalculation, not simulated OSPF/BGP or measured convergence time.
- Synthetic packets enter store-and-forward queues. Each undirected connection has one shared service capacity for both directions. Service time is packet bits divided by capacity; propagation happens after service. Queues are bounded, with FIFO or non-preemptive strict priority and tail drop. Configured independent link loss uses a local seeded RNG.
- This is not a complete TCP/UDP stack: no SYN/ACK, retransmission, congestion window, encryption, real sockets or physical network traffic. No Mininet, VM or SSH is needed.
- Runs are bounded to 8 flows, 0.1–5 seconds, 20,000 generated packets and 200,000 packet hops. Oversized requests return 422; there is no silent sampling. Default duration is 1 second, queue length 32 and seed 17.

## Metrics and honest comparisons

Throughput is delivered packet bits divided by the observation interval. Loss is explicitly dropped packets divided by generated packets. At the boundary, packets still queued, in service or propagating are **pending**, not silently counted as loss or delivery. The invariant is `sent = delivered + dropped + pending`. Latency is the mean end-to-end delay of delivered packets only; no delivery means null latency. Link utilization is busy serialization time within the interval divided by interval duration, bounded to 100%.

The response includes network, link, node and application results, twenty throughput time bins, rerouted flow IDs, topology changes, unreachable destinations and structural communities. Availability means fraction of flows with an operational route in the snapshot; it is not an uptime SLA. Costs are relative configuration-change units, not procurement prices.

Existing explicit defaults remain 1000 Mbps, 1 ms and 0% configured loss when absent, with assumptions returned. Configured static/firewall/segmentation policies are rejected rather than silently simulated incorrectly.

## Candidate construction and optimization

The existing transformation rules create retain, repair, targeted recovery and dedicated-path graphs. Each applicable graph also gets a capacity variant sized to 125% of the sum of peak demands using each actual route. This extends the existing capacity action to shared traffic; it does not create routes for disconnected demands. Device replacements map application endpoints to candidate replacements. Intentional isolation is not bypassed.

Every graph is reevaluated with the same finite-queue event model and scenario traffic. The recommendation is the least-cost allowed candidate meeting **90% delivered packets and at most 50 ms mean delivered latency for every flow**. No qualifying option produces an explicit no-recovery-targets-met outcome. Candidate generation remains bounded and does not prove every possible architecture has been searched.

Optional pymoo NSGA-II uses a reproducible integer index into this already evaluated finite action catalog. All entries seed its population (at least 8); it runs 8 generations with seed 17 by default, SBX probability .9 and polynomial mutation probability .5, with integer rounding. Objectives are mean latency/50 ms, loss fraction, relative change cost, maximum link utilization, unreachable-flow fraction and critical-flow delivery deficit. Hard constraints require allowed graph/change constraints and all-flow service targets. Returned solutions are independently checked for dominance against the feasible catalog. This is operational NSGA-II over a small catalog, not continuous topology synthesis or global optimality. Missing dependencies/contention/errors return labeled fallback; no feasible candidate returns an empty front.

The original analytical NSGA-II implementation and objectives remain available in Advanced Details. Its steady-state results are not relabeled as event-model results. The event optimizer's reachability objective is not a new N-1 or time-based reliability guarantee.

## Extra what-if actions and limits

| Action | Actual scope |
| --- | --- |
| Link/device failure, rerouting, bandwidth and capacity changes, traffic growth, backup links | Existing isolated graph mutations plus all-flow event evaluation. Rerouting uses valid remaining paths only. |
| Traffic prioritization | Strict non-preemptive queue priority; does not increase capacity. |
| Cloud security | Inserts a gateway and an explicitly assumed 5 ms service-chain hop. No threat detection, security efficacy or firewall-policy implementation is claimed. |
| Load balancer | Converts the selected service endpoint to a load-balancer role and assigns application flows round-robin to two new replicas with explicitly assumed 100 Mbps/1 ms access links. No CPU/service-time/session-affinity model. Shared upstream bottlenecks remain. |
| SD-WAN | Uses the existing declared WAN roles and independent-provider assumption, retaining the primary-domain outage. Incompatible topologies return a clear error; the WAN sample is explicitly chosen. No SD-WAN control protocol or convergence timing. |

Service-chain scenarios compare the requested architecture with the original. Their recovery catalog currently contains only retaining that architecture, not a search over further service-chain designs. Architecture change units are reported separately from additional recovery cost. Original snapshots remain intact.

## Risk and AI provenance

No trained ML model or calibrated future failure prediction is introduced. The transparent severity score is 100 for an unreachable flow; otherwise `min(100, max(3 * loss_percent, 60 if any link has queue drops or >=95% utilization else 0))`. Thresholds are low below 30, medium from 30, high from 60 and critical from 80. Findings report affected applications and user assignments. These are synthetic scenario estimates, not probabilities. Congestion findings describe the entered workload, not an independently validated forecast.

Server-only `ASSISTANT_URL`, `ASSISTANT_MODEL` and optional `ASSISTANT_API_KEY` configure the existing chat-completion provider. Its structured scalar claims must match supplied evidence; prose remains advisory. Effective provider-presence checks in this pass found all three absent. No live AI call is claimed. Existing provider tests use mocks; the new test verifies that the adapter receives recomputed event evidence after authentication.

## Responsibility map

- `backend/app/models/packet_simulation.py`: validated flow and bounded request contract.
- `backend/app/engines/packet_simulator.py`: NetworkX routes, event scheduler, queue/loss accounting and time series.
- `backend/app/services/traffic_experiment.py`: samples, shared-traffic capacity candidates, all-flow evaluation, selection and rule findings.
- `backend/app/services/traffic_actions.py`: explicit service-chain and WAN actions.
- `backend/app/services/optimization.py`: existing analytical optimizer plus bounded event-catalog NSGA-II.
- `backend/app/api/analysis.py`: stateless preview/sample routes and authenticated explanation endpoint.
- `src/components/network/traffic-experiment-panel.tsx`: reusable themed dashboard, flow controls, comparisons, insights and clickable alternatives.
- `src/lib/traffic-experiment.ts`: typed frontend contract and chart transformations.

See `project-status.md` for actual verification results. Browser sign-in/interaction and real-provider generation remain separate verification steps; passing mocks does not establish those integrations.
