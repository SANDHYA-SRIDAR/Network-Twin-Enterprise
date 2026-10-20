"""Synthetic traffic experiments using existing mutations and candidate construction."""
from copy import deepcopy
from app.models.packet_simulation import ApplicationFlow, PacketExperimentRequest
from app.models.network import NetworkDefinition, NodeDefinition, LinkDefinition
from app.models.failure_simulation import TrafficDemand, ExperimentModernizeRequest
from app.engines.analytical_simulator import evaluate, run_modernization, apply_scenario
from app.engines.packet_simulator import simulate_packets, flow_route
from app.engines.graph_adapter import structural_analysis, graph_changes
from app.services.transformation import _changes, evaluate_candidate


def sample_experiment(name):
    """Explicit small synthetic fixtures, not enterprise measurements."""
    if name == "wan":
        from app.services.wan_demo import demo_topology
        return PacketExperimentRequest(topology=demo_topology(), flows=[ApplicationFlow(id="branch-app", application="Branch application", users=10, source_node_id="branch", target_node_id="service", offered_mbps=5)], scenario_type="sd_wan")
    if name not in {"home", "office", "multi_branch"}:
        from fastapi import HTTPException
        raise HTTPException(404, "Unknown sample network")
    names = {"a": "Home users" if name == "home" else "Branch users", "b": "Primary router", "c": "Backup router", "d": "Application server"}
    nodes = [NodeDefinition(id=k, name=v, device_type="server" if k == "d" else "pc" if k == "a" else "router",
                            metadata={"position": {"x": x, "y": y}}) for (k, v), (x, y) in zip(names.items(), [(0, 100), (250, 0), (250, 250), (500, 100)])]
    pairs = [("ab", "a", "b", 20, 1), ("bd", "b", "d", 10, 2)]
    if name != "home":
        pairs += [("ac", "a", "c", 20, 2), ("cd", "c", "d", 5, 4)]
    if name == "multi_branch":
        nodes.append(NodeDefinition(id="e", name="Second branch", device_type="pc", metadata={"position": {"x": 0, "y": 350}}))
        pairs += [("ec", "e", "c", 10, 1), ("eb", "e", "b", 10, 3)]
    graph = NetworkDefinition(name=f"Synthetic {name.replace('_', ' ')} example", nodes=nodes,
                              links=[LinkDefinition(id=i, source_node_id=u, target_node_id=v, bandwidth_mbps=cap, delay_ms=delay, packet_loss_pct=0) for i, u, v, cap, delay in pairs], metadata={"synthetic_demo": True})
    flows = [ApplicationFlow(id="voice", application="Voice calls", users=8, protocol="UDP", priority=0, source_node_id="a", target_node_id="d", offered_mbps=2, packet_size_bytes=500),
             ApplicationFlow(id="files", application="File transfers", users=20, protocol="TCP", priority=2, source_node_id="e" if name == "multi_branch" else "a", target_node_id="d", offered_mbps=6, peak_multiplier=2)]
    return PacketExperimentRequest(topology=graph, flows=flows, parameters={"link_id": "bd"})


def traffic_insights(metrics):
    """Severity is a disclosed rule, not a trained or calibrated failure forecast."""
    disconnected = [f for f in metrics["flows"] if not f["flow_connected"]]
    congested = [e for e in metrics["links"] if e["congested"]]
    loss = metrics["packet_loss_pct"] or 0
    score = 100 if disconnected else min(100, max(loss * 3, 60 if congested else 0))
    level = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 30 else "low"
    reasons = []
    if disconnected:
        reasons.append("No route for: " + ", ".join(f["application"] for f in disconnected))
    if congested:
        reasons.append(f"{len(congested)} connections reached 95% utilization or dropped packets from full queues.")
    if loss:
        reasons.append(f"{loss:.2f}% of generated packets were dropped in the observation window.")
    if not reasons:
        reasons.append("No configured risk rule fired for this workload and interval.")
    return {"level": level, "score": round(score, 3), "reasons": reasons, "congested_links": congested,
            "affected_applications": [f["application"] for f in metrics["flows"] if not f["flow_connected"] or f["dropped"]],
            "affected_users": sum(f["users"] for f in metrics["flows"] if not f["flow_connected"] or f["dropped"]),
            "confidence": "Not calibrated; conditional on synthetic workload and model assumptions",
            "method": "rule_based_severity_v1", "trained_model": False,
            "limitations": "Scenario risk, not future failure prediction. User counts can overlap between applications."}


def run_traffic_experiment(request):
    flows = deepcopy(request.flows)
    scenario = request.scenario_type
    params = request.parameters
    # Queue scheduling is the mutation; rerouting is a link outage with route recomputation.
    engine_scenario = "traffic_increase" if scenario == "traffic_prioritization" else "link_failure" if scenario == "rerouting" else scenario
    engine_params = {"factor": 1} if scenario == "traffic_prioritization" else params
    if scenario in {"cloud_security", "load_balancer", "sd_wan"}:
        from app.services.traffic_actions import apply_service_action
        failed, flows = apply_service_action(request.topology, flows, scenario, params)
        multiplier = None
        # These service-chain experiments currently compare the requested architecture
        # with its baseline, without generating unsupported extra bypass/repair actions.
        engine_scenario, engine_params = "cloud_migration", {"node_id": flows[0].source_node_id}
    else:
        failed, multiplier, _ = apply_scenario(request.topology, engine_scenario, engine_params)
    if multiplier:
        flows = [ApplicationFlow.model_validate({**f.model_dump(), "offered_mbps": f.offered_mbps * multiplier}) for f in flows]
    def run(graph, traffic, prioritize=False):
        return simulate_packets(graph, traffic, request.duration_seconds, request.queue_packets, request.seed, prioritize)
    baseline_metrics = run(request.topology, request.flows)
    failed_metrics = run(failed, flows, scenario == "traffic_prioritization")
    # Existing action library is seeded by the highest-priority flow's mean offered rate.
    primary = min(flows, key=lambda f: (f.priority, f.id))
    demand = TrafficDemand(source_node_id=primary.source_node_id, target_node_id=primary.target_node_id,
                           offered_mbps=primary.offered_mbps, packet_size_bytes=primary.packet_size_bytes)
    assumptions = set()
    analytic = evaluate(failed, demand, assumptions, "failed")
    proposal = run_modernization(request.topology, failed, engine_scenario, engine_params, demand,
                                 analytic["metrics"], sorted(assumptions), ExperimentModernizeRequest())
    seeds = list(proposal["modernization"]["candidates"])
    # Reuse each existing action graph, sizing its route capacities for ALL peak
    # demands. Do not invent routes or bypass intentional isolation/service-chain scope.
    if scenario not in {"segment_isolation", "cloud_migration", "cloud_security", "load_balancer", "sd_wan"}:
        for seed in list(seeds):
            graph = NetworkDefinition.model_validate(seed["topology"])
            mapping = seed.get("endpoint_mapping", {})
            loads = {}
            for flow in flows:
                mapped = flow.model_copy(update={"source_node_id": mapping.get(flow.source_node_id, flow.source_node_id),
                                                 "target_node_id": mapping.get(flow.target_node_id, flow.target_node_id)})
                _, path = flow_route(graph, mapped, assumptions)
                for id in path:
                    loads[id] = loads.get(id, 0) + flow.offered_mbps * flow.peak_multiplier
            changed = False
            for link in graph.links:
                needed = min(1000000, loads.get(link.id, 0) * 1.25)
                if needed > (link.bandwidth_mbps or 1000):
                    link.bandwidth_mbps = needed
                    changed = True
            if changed:
                seeds.append(evaluate_candidate(seed["id"] + "-traffic-capacity", seed["title"] + " with shared-traffic capacity", graph,
                                                failed, demand, analytic["metrics"], assumptions, ExperimentModernizeRequest()))
    candidates = []
    for candidate in seeds:
        graph = NetworkDefinition.model_validate(candidate["topology"])
        mapping = candidate.get("endpoint_mapping", {})
        traffic = [f.model_copy(update={"source_node_id": mapping.get(f.source_node_id, f.source_node_id),
                                      "target_node_id": mapping.get(f.target_node_id, f.target_node_id)}) for f in flows]
        metrics = run(graph, traffic, scenario == "traffic_prioritization")
        # Availability means flow reachability in this snapshot, never an uptime SLA.
        targets = all(f["flow_connected"] and f["sent"] > 0 and f["delivered"] / f["sent"] >= .9 and
                      f["average_latency_ms"] is not None and f["average_latency_ms"] <= 50 for f in metrics["flows"])
        critical = [f for f in metrics["flows"] if f["priority"] == min(x.priority for x in flows)]
        critical_delivery = sum(f["delivered"] for f in critical) / max(1, sum(f["sent"] for f in critical))
        objectives = [(metrics["average_latency_ms"] or 0) / 50 if metrics["average_latency_ms"] is not None else 1e6,
                      (metrics["packet_loss_pct"] or 0) / 100, candidate["change_units"],
                      max((e["utilization_pct"] for e in metrics["links"]), default=0) / 100,
                      1 - metrics["connectivity_pct"] / 100, 1 - critical_delivery]
        candidates.append({"id": candidate["id"], "title": candidate["title"], "topology": candidate["topology"],
                           "metrics": metrics, "insights": traffic_insights(metrics), "changes": candidate["changes"],
                           "cost_units": candidate["change_units"], "feasible": candidate["feasible"],
                           "targets_met": targets, "objectives": objectives, "constraints": candidate["constraints"]})
    qualified = [c for c in candidates if c["feasible"] and c["targets_met"]]
    selected = min(qualified, key=lambda c: (c["cost_units"], c["id"])) if qualified else next(c for c in candidates if c["id"] == "retain")
    optimization = None
    if request.optimize:
        from app.services.optimization import optimize_traffic_catalog
        optimization = optimize_traffic_catalog(candidates, request.seed)
    before_insights, after_insights = traffic_insights(baseline_metrics), traffic_insights(failed_metrics)
    explanation = (f"{len(after_insights['affected_applications'])} applications affected in this simulated interval. "
                   f"Delivered traffic changed from {baseline_metrics['throughput_mbps']:.2f} to {failed_metrics['throughput_mbps']:.2f} Mbps. "
                   + (f"Recommended: {selected['title']}; the lowest-change option meeting 90% packet delivery and 50 ms mean delay for every flow. " if qualified else "No evaluated candidate meets all flow targets; inspect alternatives or reduce demand. ")
                   + ("No configuration change is needed for those targets." if qualified and not selected["changes"] else "Proposals require engineering review; nothing is deployed."))
    scenario_cost = _changes(request.topology, failed)[0] if scenario in {"cloud_security", "load_balancer", "sd_wan"} else 0
    if scenario_cost:
        explanation += f" The requested architecture itself adds {scenario_cost} relative change units; recovery costs above describe additional changes only."
    return {"engine_version": "network-traffic-events/1.0", "provenance": "synthetic_discrete_event", "persisted": False,
            "scenario_change_units": scenario_cost,
            "baseline_topology": request.topology.model_dump(mode="json"), "failed_topology": failed.model_dump(mode="json"),
            "baseline_metrics": baseline_metrics, "failed_metrics": failed_metrics,
            "baseline_insights": before_insights, "insights": after_insights, "candidates": candidates,
            "selected_id": selected["id"], "recovery_targets_met": bool(qualified), "summary": explanation,
            "structure": structural_analysis(failed), "graph_changes": graph_changes(request.topology, failed),
            "rerouted_flows": [b["id"] for a, b in zip(baseline_metrics["flows"], failed_metrics["flows"]) if a["route_link_ids"] != b["route_link_ids"] and b["flow_connected"]],
            "optimization": optimization, "request": request.model_dump(mode="json"),
            "limitations": ["Synthetic packet events only; no real traffic, TCP feedback, retransmission, routing protocols or measured predictions.",
                             "Scenario applied at time zero; route recalculation assumes instantaneous convergence. Peak load applies in the second half.",
                             "Finite shared bidirectional queues; strict non-preemptive priority when selected. Low-priority starvation is possible.",
                             "Pending packets at the observation boundary are neither delivered nor dropped. Latency describes delivered packets only.",
                             "Candidate generation uses the highest-priority flow; every resulting candidate is reevaluated with all flows. Cost is a relative proxy.",
                             "Cloud security models an added 5 ms service-chain hop only, not security efficacy. Load balancing assigns flows round-robin to two 100 Mbps replicas, without CPU or session behavior.",
                             "SD-WAN uses declared independent paths with the primary WAN down, not SD-WAN control protocols. The WAN demo separately compares repair against redesign.",
                             "Service-chain scenarios compare a requested architecture; their recovery catalog currently contains only retaining that architecture. Architecture installation cost is separate from additional recovery cost."]}
