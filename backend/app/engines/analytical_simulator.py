from __future__ import annotations

import heapq
import uuid
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from app.models.failure_simulation import TrafficDemand
from app.models.network import LinkDefinition, NetworkDefinition

ENGINE_VERSION = "analytical-network-sim/1.0"
DEFAULT_CAPACITY_MBPS = 1000.0
DEFAULT_DELAY_MS = 1.0
DEFAULT_PACKET_LOSS_PCT = 0.0
DOWN = {"down", "offline", "failed"}


def _effective_capacity(link: LinkDefinition, assumptions: set[str]) -> float:
    if link.bandwidth_mbps is None:
        assumptions.add(f"Link {link.id}: configured capacity missing; simulation uses an explicit {DEFAULT_CAPACITY_MBPS:g} Mbps assumption.")
        return DEFAULT_CAPACITY_MBPS
    return link.bandwidth_mbps


def _edge_cost(link: LinkDefinition, offered_mbps: float, packet_size_bytes: int, assumptions: set[str]) -> float:
    capacity = _effective_capacity(link, assumptions)
    delay = link.delay_ms
    if delay is None:
        assumptions.add(f"Link {link.id}: configured latency missing; simulation uses an explicit {DEFAULT_DELAY_MS:g} ms assumption.")
        delay = DEFAULT_DELAY_MS
    rho = offered_mbps / capacity
    service_ms = packet_size_bytes * 8 / (capacity * 1000)
    queue_ms = min(1000.0, service_ms * rho / max(0.01, 1.0 - min(rho, 0.99)))
    return delay + service_ms + queue_ms


def shortest_path(network: NetworkDefinition, source: str, target: str, offered_mbps: float, packet_size_bytes: int, assumptions: set[str]) -> list[str] | None:
    nodes = {node.id: node for node in network.nodes}
    if source not in nodes or target not in nodes:
        raise HTTPException(status_code=422, detail="Traffic source or destination is not in the saved topology.")
    if nodes[source].status in DOWN or nodes[target].status in DOWN:
        return None
    adjacency: dict[str, list[tuple[str, LinkDefinition]]] = {node_id: [] for node_id in nodes}
    for link in network.links:
        if link.status in DOWN or link.source_node_id not in nodes or link.target_node_id not in nodes:
            continue
        if nodes[link.source_node_id].status in DOWN or nodes[link.target_node_id].status in DOWN:
            continue
        adjacency[link.source_node_id].append((link.target_node_id, link))
        adjacency[link.target_node_id].append((link.source_node_id, link))
    distances = {source: 0.0}
    prior: dict[str, tuple[str, str]] = {}
    queue: list[tuple[float, str]] = [(0.0, source)]
    while queue:
        distance, current = heapq.heappop(queue)
        if distance > distances.get(current, float("inf")):
            continue
        if current == target:
            break
        for neighbor, link in sorted(adjacency[current], key=lambda entry: (entry[0], entry[1].id)):
            candidate = distance + _edge_cost(link, offered_mbps, packet_size_bytes, assumptions)
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                prior[neighbor] = (current, link.id)
                heapq.heappush(queue, (candidate, neighbor))
    if target not in distances:
        return None
    path: list[str] = []
    cursor = target
    while cursor != source:
        parent, link_id = prior[cursor]
        path.append(link_id)
        cursor = parent
    path.reverse()
    return path


def _reachable(network: NetworkDefinition, source: str) -> set[str]:
    nodes = {node.id: node for node in network.nodes}
    if source not in nodes or nodes[source].status in DOWN:
        return set()
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for link in network.links:
        if link.status not in DOWN and link.source_node_id in nodes and link.target_node_id in nodes and nodes[link.source_node_id].status not in DOWN and nodes[link.target_node_id].status not in DOWN:
            adjacency[link.source_node_id].add(link.target_node_id)
            adjacency[link.target_node_id].add(link.source_node_id)
    seen = {source}
    stack = [source]
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current] - seen:
            seen.add(neighbor)
            stack.append(neighbor)
    return seen


def evaluate(network: NetworkDefinition, demand: TrafficDemand, assumptions: set[str], stage: str) -> dict[str, Any]:
    route = shortest_path(network, demand.source_node_id, demand.target_node_id, demand.offered_mbps, demand.packet_size_bytes, assumptions)
    by_id = {link.id: link for link in network.links}
    path_links = [by_id[link_id] for link_id in route or []]
    capacities = [_effective_capacity(link, assumptions) for link in path_links]
    bottleneck_capacity = min(capacities) if capacities else 0.0
    throughput = min(demand.offered_mbps, bottleneck_capacity) if route is not None else 0.0
    loss_probability = 1.0
    latency_ms = 0.0
    for link in path_links:
        configured_loss = link.packet_loss_pct
        if configured_loss is None:
            assumptions.add(f"Link {link.id}: packet loss is unconfigured; simulation assumes {DEFAULT_PACKET_LOSS_PCT:g}%.")
            configured_loss = DEFAULT_PACKET_LOSS_PCT
        loss_probability *= 1 - min(100.0, max(0.0, configured_loss)) / 100
        capacity = _effective_capacity(link, assumptions)
        delay = link.delay_ms if link.delay_ms is not None else DEFAULT_DELAY_MS
        utilization = demand.offered_mbps / capacity
        service_ms = demand.packet_size_bytes * 8 / (capacity * 1000)
        queue_ms = min(1000.0, service_ms * utilization / max(0.01, 1.0 - min(utilization, 0.99)))
        latency_ms += delay + service_ms + queue_ms
    capacity_delivery = throughput / demand.offered_mbps if demand.offered_mbps else 0.0
    delivery_probability = max(0.0, min(1.0, capacity_delivery * (1 - loss_probability))) if route is not None else 0.0
    sent = int(demand.offered_mbps * 1_000_000 * demand.duration_seconds / (demand.packet_size_bytes * 8))
    received = min(sent, int(sent * delivery_probability))
    dropped = sent - received
    reached = _reachable(network, demand.source_node_id)
    active_links = [link for link in network.links if link.status not in DOWN]
    link_results = []
    bottlenecks = []
    for link in network.links:
        capacity = _effective_capacity(link, assumptions)
        on_route = route is not None and link.id in route
        offered_on_link = demand.offered_mbps if on_route else 0.0
        util = offered_on_link / capacity * 100 if link.status not in DOWN else 0.0
        if on_route and (util >= 80 or capacity == bottleneck_capacity):
            bottlenecks.append(link.id)
        link_results.append({
            "id": link.id, "source_node_id": link.source_node_id, "target_node_id": link.target_node_id,
            "status": "failed" if link.status in DOWN else link.status,
            "configured_capacity_mbps": link.bandwidth_mbps, "effective_capacity_mbps": capacity,
            "offered_traffic_mbps": offered_on_link, "achieved_throughput_mbps": min(offered_on_link, capacity),
            "utilization_pct": round(util, 3), "latency_ms": link.delay_ms,
            "packet_loss_pct": link.packet_loss_pct,
            "congested": util >= 80, "on_route": on_route,
        })
    failed_nodes = sum(1 for node in network.nodes if node.status in DOWN)
    active_node_count = len(network.nodes) - failed_nodes
    reachable_active = len(reached)
    metrics = {
        "packets_sent": sent, "packets_delivered": received, "packets_dropped": dropped,
        "packet_loss_pct": round(dropped / sent * 100, 4) if sent else 0,
        "average_latency_ms": round(latency_ms, 4) if route is not None else None,
        "maximum_latency_ms": round(latency_ms, 4) if route is not None else None,
        "offered_traffic_mbps": demand.offered_mbps,
        "throughput_mbps": round(throughput * max(0.0, 1 - loss_probability), 4),
        "path_capacity_mbps": bottleneck_capacity,
        "mean_link_utilization_pct": round(sum(item["utilization_pct"] for item in link_results) / max(1, len(active_links)), 3),
        "reachable_nodes": reachable_active, "total_nodes": len(network.nodes),
        "unreachable_nodes": len(network.nodes) - reachable_active,
        "active_links": len(active_links), "failed_links": len(network.links) - len(active_links),
        "congested_links": sum(1 for item in link_results if item["congested"]),
        "bottleneck_link_ids": sorted(set(bottlenecks)),
        "connectivity_pct": round(reachable_active / max(1, len(network.nodes)) * 100, 3),
        "flow_connected": route is not None,
        "route_node_ids": [],
        "route_link_ids": route or [], "links": link_results,
        "provenance": "simulated", "stage": stage,
    }
    # Reconstruct the path node sequence from the selected edge sequence, including reverse links.
    if route is not None:
        path_nodes = [demand.source_node_id]
        current = demand.source_node_id
        for link_id in route:
            edge = by_id[link_id]
            current = edge.target_node_id if edge.source_node_id == current else edge.source_node_id
            path_nodes.append(current)
        metrics["route_node_ids"] = path_nodes
    steps: list[dict[str, Any]] = [{"index": 0, "kind": "start", "node_id": demand.source_node_id}]
    if route is None:
        steps.append({"index": 1, "kind": "dropped", "node_id": demand.target_node_id, "reason": "No operational route exists."})
    else:
        for index, link_id in enumerate(route, start=1):
            steps.append({"index": index, "kind": "forward", "link_id": link_id, "node_id": metrics["route_node_ids"][index]})
    return {"metrics": metrics, "steps": steps, "route_link_ids": route or []}


def apply_scenario(baseline: NetworkDefinition, scenario_type: str, parameters: dict[str, Any]) -> tuple[NetworkDefinition, TrafficDemand | None, list[str]]:
    network = deepcopy(baseline)
    assumptions: list[str] = []
    multiplier: TrafficDemand | None = None
    nodes = {node.id: node for node in network.nodes}
    links = {link.id: link for link in network.links}

    if scenario_type == "link_failure":
        link_id = parameters.get("link_id")
        if link_id not in links:
            raise HTTPException(status_code=422, detail="Choose a valid connection for the link failure scenario.")
        links[link_id].status = "down"
    elif scenario_type in {"device_failure", "segment_isolation"}:
        node_id = parameters.get("node_id")
        if node_id not in nodes:
            raise HTTPException(status_code=422, detail="Choose a valid device for this scenario.")
        nodes[node_id].status = "down"
        for link in network.links:
            if link.source_node_id == node_id or link.target_node_id == node_id:
                link.status = "down"
        if scenario_type == "segment_isolation":
            assumptions.append("Segment isolation disables the selected node and its incident traffic paths in this simulation copy.")
    elif scenario_type == "traffic_increase":
        factor = parameters.get("factor", parameters.get("value", 1.5))
        if not isinstance(factor, (int, float)) or isinstance(factor, bool) or factor <= 0:
            raise HTTPException(status_code=422, detail="Traffic increase factor must be greater than zero.")
        multiplier = factor
    elif scenario_type == "bandwidth_change":
        link_id, value = parameters.get("link_id"), parameters.get("bandwidth_mbps", parameters.get("value"))
        if link_id not in links:
            raise HTTPException(status_code=422, detail="Choose a valid connection for the bandwidth change scenario.")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise HTTPException(status_code=422, detail="New link capacity must be greater than zero Mbps.")
        links[link_id].bandwidth_mbps = float(value)
    elif scenario_type == "redundancy_add":
        source, target = parameters.get("source_node_id"), parameters.get("target_node_id")
        if source not in nodes or target not in nodes or source == target:
            raise HTTPException(status_code=422, detail="Choose two different saved devices for the candidate redundant link.")
        if any({edge.source_node_id, edge.target_node_id} == {source, target} and edge.status not in DOWN for edge in network.links):
            raise HTTPException(status_code=422, detail="Those devices already have an operational link.")
        capacity = parameters.get("bandwidth_mbps")
        if capacity is not None and (not isinstance(capacity, (int, float)) or isinstance(capacity, bool) or capacity <= 0):
            raise HTTPException(status_code=422, detail="Candidate link capacity must be positive.")
        candidate_id = f"candidate:{uuid.uuid5(uuid.NAMESPACE_URL, f'{source}:{target}:redundancy')}"
        network.links.append(LinkDefinition(id=candidate_id, source_node_id=source, target_node_id=target,
                                            bandwidth_mbps=float(capacity) if capacity else None,
                                            delay_ms=None, packet_loss_pct=None, metadata={"candidate": True}))
        if capacity is None:
            assumptions.append("Candidate redundant link capacity is unconfigured; evaluation uses the explicit 1000 Mbps simulation default.")
    elif scenario_type == "capacity_increase":
        link_id = parameters.get("link_id")
        if link_id not in links:
            raise HTTPException(status_code=422, detail="Choose a valid connection for the capacity increase scenario.")
        amount = parameters.get("increase_mbps", parameters.get("value", 250))
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            raise HTTPException(status_code=422, detail="Capacity increase must be greater than zero Mbps.")
        old_capacity = links[link_id].bandwidth_mbps or DEFAULT_CAPACITY_MBPS
        if links[link_id].bandwidth_mbps is None:
            assumptions.append(f"Link {link_id}: capacity was unconfigured; a {DEFAULT_CAPACITY_MBPS:g} Mbps assumption was used before the requested increase.")
        links[link_id].bandwidth_mbps = old_capacity + float(amount)
    elif scenario_type == "cloud_migration":
        node_id = parameters.get("node_id")
        if node_id not in nodes:
            raise HTTPException(status_code=422, detail="Choose a valid service device for the placement scenario.")
        assumptions.append("The saved topology schema has no geographic placement or cloud latency fields; cloud migration is marked as placement-only and does not change path metrics.")
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported scenario type: {scenario_type}")
    return network, multiplier, assumptions


def modernize(baseline: NetworkDefinition, failed: NetworkDefinition, scenario_type: str, parameters: dict[str, Any], demand: TrafficDemand, failed_metrics: dict[str, Any], assumptions: set[str]) -> tuple[NetworkDefinition, dict[str, Any], str]:
    candidate = deepcopy(failed)
    ids = {node.id for node in candidate.nodes}
    link_ids = {link.id for link in candidate.links}
    message = "No safe automatic transformation is supported by the available topology data. The failed state remains visible."
    resolved = False

    if scenario_type == "link_failure":
        failed_link = next(link for link in baseline.links if link.id == parameters["link_id"])
        if failed_metrics.get("flow_connected"):
            message = "The selected path was rerouted through existing operational links; no physical topology change is needed."
            resolved = True
        else:
            candidate_id = f"candidate:{uuid.uuid5(uuid.NAMESPACE_URL, f'{failed_link.id}:modernized-backup')}"
            if candidate_id not in link_ids:
                candidate.links.append(LinkDefinition(id=candidate_id, source_node_id=failed_link.source_node_id,
                    target_node_id=failed_link.target_node_id, cable_type=failed_link.cable_type,
                    bandwidth_mbps=failed_link.bandwidth_mbps, delay_ms=failed_link.delay_ms,
                    packet_loss_pct=failed_link.packet_loss_pct, status="active", metadata={"candidate": True, "replaces_failed_link": failed_link.id}))
                message = f"Add candidate backup connection {candidate_id} between the failed link's endpoints; the saved failed link remains down."
                resolved = True
    elif scenario_type == "device_failure":
        failed_node = next(node for node in baseline.nodes if node.id == parameters["node_id"])
        replacement_id = f"candidate:{uuid.uuid5(uuid.NAMESPACE_URL, f'{failed_node.id}:replacement')}"
        if replacement_id not in ids:
            replacement = failed_node.model_copy(deep=True)
            replacement.id = replacement_id
            replacement.name = f"{failed_node.name} (candidate replacement)"
            replacement.status = "active"
            replacement.metadata = {**replacement.metadata, "candidate": True, "replaces_node_id": failed_node.id}
            candidate.nodes.append(replacement)
            for link in baseline.links:
                if link.source_node_id == failed_node.id or link.target_node_id == failed_node.id:
                    new_id = f"candidate:{uuid.uuid5(uuid.NAMESPACE_URL, f'{link.id}:replacement:{replacement_id}')}"
                    candidate.links.append(link.model_copy(update={"id": new_id,
                        "source_node_id": replacement_id if link.source_node_id == failed_node.id else link.source_node_id,
                        "target_node_id": replacement_id if link.target_node_id == failed_node.id else link.target_node_id,
                        "status": "active", "metadata": {**link.metadata, "candidate": True}}))
            message = f"Add candidate replacement {failed_node.name} and reconnect its saved adjacent devices. The original failed device remains marked down."
            resolved = True
    elif scenario_type in {"traffic_increase", "bandwidth_change", "capacity_increase"}:
        bottleneck_ids = failed_metrics.get("bottleneck_link_ids", []) if failed_metrics.get("congested_links", 0) else []
        if scenario_type == "bandwidth_change":
            bottleneck_ids = [parameters["link_id"]]
        if scenario_type == "capacity_increase":
            bottleneck_ids = [parameters["link_id"]]
        for link_id in bottleneck_ids:
            link = next((item for item in candidate.links if item.id == link_id and item.status not in DOWN), None)
            baseline_link = next((item for item in baseline.links if item.id == link_id), None)
            if not link:
                continue
            capacity = link.bandwidth_mbps or _effective_capacity(link, assumptions)
            desired = max(capacity * 2, demand.offered_mbps * 1.25)
            if scenario_type == "bandwidth_change" and baseline_link and baseline_link.bandwidth_mbps:
                desired = baseline_link.bandwidth_mbps
            link.bandwidth_mbps = desired
            link.metadata = {**link.metadata, "candidate": True, "previous_capacity_mbps": capacity}
            resolved = True
        if resolved:
            message = f"Increase capacity on bottleneck link(s) {', '.join(bottleneck_ids)} to reduce modeled congestion under the same offered traffic."
    elif scenario_type == "redundancy_add":
        resolved = bool(failed_metrics.get("flow_connected"))
        message = "The scenario-added candidate connection is the proposed resilience change; no second copy was added."
    elif scenario_type == "segment_isolation":
        message = "The selected isolation is an intentional policy boundary. No alternate path was added because that would undo the requested isolation."
    elif scenario_type == "cloud_migration":
        message = "Cannot evaluate a network modernization for cloud placement: the saved topology has no site, region, or cloud-latency model."

    result = evaluate(candidate, demand, assumptions, "modernized")
    return candidate, {"resolved": resolved, "summary": message, "recommendation": _recommendation(scenario_type, parameters, failed_metrics, result["metrics"], resolved), "metrics": result["metrics"], "steps": result["steps"]}, message


def _recommendation(scenario_type: str, parameters: dict[str, Any], before: dict[str, Any], after: dict[str, Any], resolved: bool) -> dict[str, Any]:
    if scenario_type == "device_failure":
        cause = f"Device {parameters.get('node_id')} is unavailable and its attached traffic paths cannot forward."
        change = "Introduce a candidate replacement device and reconnect the existing adjacent nodes." if resolved else "No replacement could be constructed from saved configuration."
        affected = [parameters.get("node_id")]
        cost = "high"
    elif scenario_type == "link_failure":
        cause = f"Connection {parameters.get('link_id')} is failed; no active route reaches the selected destination." if not before.get("flow_connected") else "The primary connection failed, but an existing alternate route carries the selected flow."
        change = "Add a candidate backup connection between the failed connection endpoints." if not before.get("flow_connected") else "Use the alternate route; no new connection is required."
        affected = [parameters.get("link_id")]
        cost = "medium" if not before.get("flow_connected") else "low"
    elif scenario_type in {"traffic_increase", "bandwidth_change", "capacity_increase"}:
        cause = "Offered traffic approaches or exceeds the capacity of a route bottleneck." if before.get("congested_links") else "No congestion bottleneck was measured for the selected traffic flow."
        change = "Increase candidate capacity on the bottleneck connection(s)." if resolved else "No congested link has a supported capacity change."
        affected = before.get("bottleneck_link_ids", [])
        cost = "medium"
    else:
        cause = "The selected scenario does not establish a measurable network failure with the saved fields."
        change = "No automatic change was proposed."
        affected = [parameters.get("node_id"), parameters.get("link_id")]
        cost = "undetermined"
    return {
        "problem": scenario_type.replace("_", " ").title(), "root_cause": cause,
        "proposed_modification": change, "affected_ids": [item for item in affected if item],
        "expected_benefits": ["improves modeled delivery or reachability" if resolved else "no recovery can be claimed from the current topology"],
        "trade_offs": ["candidate devices or links are simulations only and have not been deployed"],
        "relative_cost": cost, "rationale": f"Calculated from the saved graph using the same traffic demand; simulated throughput {before.get('throughput_mbps')} → {after.get('throughput_mbps')} Mbps and reachability {before.get('reachable_nodes')} → {after.get('reachable_nodes')} nodes.",
    }


def run_experiment(network: NetworkDefinition, scenario_type: str, parameters: dict[str, Any], traffic: TrafficDemand) -> dict[str, Any]:
    failed, traffic_factor, scenario_assumptions = apply_scenario(network, scenario_type, parameters)
    effective_traffic = traffic.model_copy(update={"offered_mbps": traffic.offered_mbps * traffic_factor}) if traffic_factor else traffic
    assumptions = set(scenario_assumptions)
    baseline_result = evaluate(network, effective_traffic, assumptions, "baseline")
    failed_result = evaluate(failed, effective_traffic, assumptions, "failure")
    experiment_id = str(uuid.uuid4())
    assumptions.update({
        "Routing uses deterministic shortest path with link cost = configured propagation delay + packet serialization delay + M/M/1-style queue approximation.",
        "Packet counts use the user-entered offered Mbps, duration, and packet-size assumptions; they are modeled counts, not measurements.",
        "Effective throughput is constrained by the minimum capacity on the selected route and configured loss probabilities.",
        "Missing capacity, delay, and packet loss values are shown as unconfigured; simulation uses explicit defaults of 1000 Mbps, 1 ms, and 0% only for calculation.",
    })
    return {
        "experiment_id": experiment_id, "engine_version": ENGINE_VERSION, "traffic": effective_traffic.model_dump(),
        "baseline_topology": network.model_dump(mode="json"), "failed_topology": failed.model_dump(mode="json"),
        "baseline_metrics": baseline_result["metrics"], "failed_metrics": failed_result["metrics"],
        "failure_steps": _failure_steps(network, failed, failed_result["steps"]),
        "assumptions": sorted(assumptions),
        "status": "completed", "provenance": "simulated",
    }


def run_modernization(network: NetworkDefinition, failed: NetworkDefinition, scenario_type: str, parameters: dict[str, Any], traffic: TrafficDemand, failed_metrics: dict[str, Any], assumption_values: list[str]) -> dict[str, Any]:
    assumptions = set(assumption_values)
    candidate, proposal, _ = modernize(network, failed, scenario_type, parameters, traffic, failed_metrics, assumptions)
    return {
        "modernized_topology": candidate.model_dump(mode="json"),
        "modernization": proposal,
        "modernized_metrics": proposal["metrics"],
        "modernization_steps": proposal["steps"],
        "assumptions": sorted(assumptions),
    }


def _failure_steps(baseline: NetworkDefinition, failed: NetworkDefinition, flow_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_nodes = {node.id: node for node in baseline.nodes}
    old_links = {link.id: link for link in baseline.links}
    steps = []
    index = 0
    for node in failed.nodes:
        if node.id in old_nodes and old_nodes[node.id].status != node.status and node.status in DOWN:
            steps.append({"index": index, "kind": "node_failed", "node_id": node.id}); index += 1
    for link in failed.links:
        if link.id in old_links and old_links[link.id].status != link.status and link.status in DOWN:
            steps.append({"index": index, "kind": "link_failed", "link_id": link.id}); index += 1
    for step in flow_steps:
        steps.append({**step, "index": index}); index += 1
    return steps
