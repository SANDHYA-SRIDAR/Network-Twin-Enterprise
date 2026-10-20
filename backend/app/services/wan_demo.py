"""Scoped WAN architecture demonstration using the existing analytical evaluator."""
from copy import deepcopy
from app.models.network import NetworkDefinition, NodeDefinition, LinkDefinition
from app.models.failure_simulation import TrafficDemand, ExperimentModernizeRequest
from app.engines.analytical_simulator import run_experiment, evaluate
from app.services.transformation import evaluate_candidate, describe_selection


def demo_topology():
    return NetworkDefinition(name="Demonstration: single-WAN branch", metadata={"synthetic_demo": True}, nodes=[
        NodeDefinition(id="branch", name="Branch office", device_type="router", role="branch_wan", metadata={"position": {"x": 0, "y": 100}}),
        NodeDefinition(id="carrier-a", name="WAN provider A", device_type="router", role="wan_provider", metadata={"position": {"x": 300, "y": 0}}),
        NodeDefinition(id="service", name="Head office service", device_type="server", role="wan_service", metadata={"position": {"x": 600, "y": 100}}),
    ], links=[
        LinkDefinition(id="wan-primary", source_node_id="branch", target_node_id="carrier-a", bandwidth_mbps=200, delay_ms=10, packet_loss_pct=0, metadata={"wan": True, "failure_domain": "carrier-a"}),
        LinkDefinition(id="carrier-core", source_node_id="carrier-a", target_node_id="service", bandwidth_mbps=1000, delay_ms=5, packet_loss_pct=0),
    ])


def wan_context(graph):
    branches = [n for n in graph.nodes if n.role == "branch_wan"]
    services = [n for n in graph.nodes if n.role == "wan_service"]
    if len(branches) != 1 or len(services) != 1:
        return None
    links = [e for e in graph.links if e.metadata.get("wan") is True and branches[0].id in (e.source_node_id, e.target_node_id)]
    if len(links) != 1 or not links[0].metadata.get("failure_domain"):
        return None
    edge = links[0]
    peer = edge.target_node_id if edge.source_node_id == branches[0].id else edge.source_node_id
    return branches[0].id, services[0].id, edge, peer


def transformed_graph(baseline, failed):
    branch, service, primary, peer = wan_context(baseline)
    graph = deepcopy(failed)
    # Stable candidate IDs must never collide with saved topology IDs.
    prefix = "candidate:sdwan:"
    existing = {n.id for n in graph.nodes} | {e.id for e in graph.links}
    while any(i.startswith(prefix) for i in existing):
        prefix += "new:"
    edge_id, provider = prefix + "edge", prefix + "provider-b"
    graph.nodes.extend([
        NodeDefinition(id=edge_id, name="SD-WAN edge (modeled role)", device_type="router", role="sd_wan_edge", metadata={"position": {"x": 150, "y": 200}}),
        NodeDefinition(id=provider, name="Independent WAN provider B (assumed)", device_type="router", role="wan_provider", metadata={"position": {"x": 400, "y": 300}}),
    ])
    for suffix, source, target, capacity, delay, status, domain in [
        ("lan", branch, edge_id, 1000, 1, "active", "branch-lan"),
        ("uplink-a", edge_id, peer, primary.bandwidth_mbps or 1000, primary.delay_ms if primary.delay_ms is not None else 1, "failed", primary.metadata["failure_domain"]),
        ("uplink-b", edge_id, provider, 200, 15, "active", str(primary.metadata["failure_domain"]) + ":assumed-independent-b"),
        ("provider-b-core", provider, service, 1000, 5, "active", str(primary.metadata["failure_domain"]) + ":assumed-independent-b"),
    ]:
        graph.links.append(LinkDefinition(id=prefix+suffix, source_node_id=source, target_node_id=target, bandwidth_mbps=capacity, delay_ms=delay, packet_loss_pct=0, status=status, metadata={"candidate": True, "failure_domain": domain, "design_assumption": True}))
    return graph


def run_wan_demo(saved=None, require_continuity=True, offered_mbps=100):
    supported = saved is not None and wan_context(saved) is not None
    baseline = deepcopy(saved) if supported else demo_topology()
    branch, service, primary, _ = wan_context(baseline)
    demand = TrafficDemand(source_node_id=branch, target_node_id=service, offered_mbps=offered_mbps)
    result = run_experiment(baseline, "link_failure", {"link_id": primary.id}, demand)
    failed = NetworkDefinition.model_validate(result["failed_topology"])
    assumptions = set(result["assumptions"])
    assumptions.add("SD-WAN is an architectural role only: static shortest-path failover, no control-plane protocol, tunnel overhead or convergence timing. Provider B diversity, 200 Mbps capacity, 20 ms WAN delay and zero configured loss are explicit design assumptions. Shared LAN/edge/service failures are not protected.")
    criteria = ExperimentModernizeRequest()
    repair = deepcopy(failed)
    next(e for e in repair.links if e.id == primary.id).status = next(e for e in baseline.links if e.id == primary.id).status
    options = [("retain", "Retain surviving routes", failed), ("repair", "Repair the original WAN connection", repair), ("sdwan", "Add an SD-WAN edge and two independent WAN uplinks", transformed_graph(baseline, failed))]
    candidates = []
    for ident, title, graph in options:
        candidate = evaluate_candidate(ident, title, graph, failed, demand, result["failed_metrics"], assumptions, criteria)
        stress = deepcopy(graph)
        for link in stress.links:
            if link.id == primary.id or link.metadata.get("failure_domain") == primary.metadata["failure_domain"]:
                link.status = "failed"
        outage = evaluate(stress, demand, assumptions, "wan_outage")["metrics"]
        def meets(metrics):
            return metrics["flow_connected"] and metrics["throughput_mbps"] >= .95 * offered_mbps and metrics["average_latency_ms"] is not None and metrics["average_latency_ms"] <= criteria.latency_target_ms
        candidate["wan_outage_metrics"] = outage
        candidate["meets_service_target"] = meets(candidate["metrics"])
        candidate["survives_primary_wan_outage"] = meets(outage)
        candidates.append(candidate)
    eligible = [c for c in candidates if c["feasible"] and c["meets_service_target"] and (not require_continuity or c["survives_primary_wan_outage"])]
    selected = min(eligible, key=lambda c: (c["change_units"], c["id"])) if eligible else candidates[0]
    reason = ("The primary WAN outage must be tolerated. Repair restores the original connection but does not protect against its outage; the dual-uplink design meets the tested service targets through provider B." if selected["id"] == "sdwan" else "The least-change option meets the declared service requirement. Continuing through a primary WAN outage was not required, so architectural transformation is not justified." if eligible else "No evaluated option meets the declared service targets. No successful recovery is claimed.")
    proposal = describe_selection(selected, candidates, result["failed_metrics"], demand, criteria, assumptions, "link_failure")
    proposal["recommendation"]["rationale"] = reason
    proposal["selection_source"] = "least_change_meeting_explicit_wan_requirement"
    result.update(modernization=proposal, modernized_topology=proposal.pop("selected_topology"), modernized_metrics=selected["metrics"], modernization_steps=selected["steps"], assumptions=sorted(assumptions), persisted=False, topology_source="saved topology snapshot" if supported else "reusable demonstration topology (not your saved network)", require_continuity=require_continuity, requirement_met=bool(eligible))
    return result
