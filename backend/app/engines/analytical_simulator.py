from __future__ import annotations

import heapq
import math
import uuid
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from app.models.failure_simulation import TrafficDemand
from app.models.network import LinkDefinition, NetworkDefinition
from app.engines.graph_adapter import DOWN, operational, network_graph
import networkx as nx

ENGINE_VERSION = "analytical-network-sim/2.1"
DEFAULT_CAPACITY_MBPS = 1000.0
DEFAULT_DELAY_MS = 1.0
DEFAULT_PACKET_LOSS_PCT = 0.0


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
    service_ms = packet_size_bytes * 8 / (capacity * 1000)
    # Static propagation + serialization routing avoids circular load-dependent costs.
    return delay + service_ms


def shortest_path(network: NetworkDefinition, source: str, target: str, offered_mbps: float, packet_size_bytes: int, assumptions: set[str]) -> list[str] | None:
    nodes = {node.id: node for node in network.nodes}
    if source not in nodes or target not in nodes:
        raise HTTPException(status_code=422, detail="Traffic source or destination is not in the saved topology.")
    if nodes[source].status in DOWN or nodes[target].status in DOWN:
        return None
    adjacency: dict[str, list[tuple[str, LinkDefinition]]] = {node_id: [] for node_id in nodes}
    for _, _, _, edge in network_graph(network).edges(keys=True, data=True):
        link = edge["definition"]
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
    return set(nx.node_connected_component(network_graph(network), source))


def validate_inputs(network: NetworkDefinition) -> None:
    from app.services.network_validation import validate_network_definition
    if len(network.nodes) > 500 or len(network.links) > 2000:
        raise HTTPException(status_code=413, detail="Topology exceeds the analytical limit of 500 devices and 2000 connections.")
    # Revalidate models too: internal mutation/model_copy must not bypass numerical bounds.
    NetworkDefinition.model_validate(network.model_dump())
    issues = validate_network_definition(network)
    if issues:
        raise HTTPException(status_code=422, detail=[item.model_dump() for item in issues])


def evaluate(network: NetworkDefinition, demand: TrafficDemand, assumptions: set[str], stage: str) -> dict[str, Any]:
    validate_inputs(network)
    demand = TrafficDemand.model_validate(demand.model_dump())
    if network.routing.static_routes or network.security.firewall_rules or network.security.segmentation:
        raise HTTPException(status_code=422, detail="Policy/static routing and firewall constraints are unsupported by this undirected single-flow model. Remove constraints or use a validation adapter.")
    assumptions.update({
        "One steady-state traffic demand; undirected links, static Dijkstra cost = propagation + serialization. No ECMP, QoS scheduling or simultaneous-flow allocation.",
        "M/M/1 queue estimate assumes Poisson arrivals, exponential service, mean configured packet size and rho < 1. It is an approximation; at rho >= 1 queue and total latency are unsupported (unstable).",
        "Congestion loss is fluid excess offered load above the path bottleneck, not a finite-buffer packet-drop prediction. Independent configured link survival probabilities multiply.",
        "Conservative reservation model: capacity and queue loads use ingress traffic without attenuation by random losses. Utilization is reserved pre-loss rate/capacity; delivered traffic applies independent path loss afterward.",
        "No forwarding processing delay, protocol convergence, interface speed negotiation or geographic cloud model is available. Packet counts are modeled expectations, not measurements.",
        "Addressing and gateways are configuration validation inputs; forwarding follows the undirected graph, not IP routing tables or subnet-based reachability.",
    })
    if any(node.resources for node in network.nodes):
        assumptions.add("Device resource parameters are retained but processing-capacity constraints are unsupported; only configured link capacity limits throughput.")
    nodes = {node.id: node for node in network.nodes}
    route = shortest_path(network, demand.source_node_id, demand.target_node_id, demand.offered_mbps, demand.packet_size_bytes, assumptions)
    by_id = {link.id: link for link in network.links}
    path_links = [by_id[link_id] for link_id in route or []]
    capacities = [_effective_capacity(link, assumptions) for link in path_links]
    bottleneck = min(capacities) if capacities else 0.0
    achievable = min(demand.offered_mbps, bottleneck) if route is not None else 0.0
    survival = 1.0
    propagation = serialization = queue = 0.0
    stable = route is not None
    for link in path_links:
        loss = link.packet_loss_pct
        if loss is None:
            assumptions.add(f"Link {link.id}: packet loss is unconfigured; simulation assumes {DEFAULT_PACKET_LOSS_PCT:g}%.")
            loss = DEFAULT_PACKET_LOSS_PCT
        survival *= 1 - loss / 100
        capacity = _effective_capacity(link, assumptions)
        service = demand.packet_size_bytes * 8 / (capacity * 1000)
        rho = demand.offered_mbps / capacity
        propagation += link.delay_ms if link.delay_ms is not None else DEFAULT_DELAY_MS
        serialization += service
        if rho >= 1:
            stable = False
        else:
            queue += service * rho / (1 - rho)
    delivered = achievable * survival
    delivery_fraction = delivered / demand.offered_mbps
    sent = int(demand.offered_mbps * 1_000_000 * demand.duration_seconds / (demand.packet_size_bytes * 8))
    received = min(sent, int(sent * delivery_fraction))
    reached = _reachable(network, demand.source_node_id)
    link_results = []
    for link in network.links:
        capacity = _effective_capacity(link, assumptions)
        eligible = operational(link, nodes)
        on_route = route is not None and link.id in route
        offered = demand.offered_mbps if on_route else 0.0
        link_results.append({
            "id": link.id, "source_node_id": link.source_node_id, "target_node_id": link.target_node_id,
            "status": link.status if eligible else "failed", "configured_capacity_mbps": link.bandwidth_mbps,
            "effective_capacity_mbps": capacity, "offered_traffic_mbps": offered,
            "achieved_throughput_mbps": achievable if on_route else 0.0,
            "utilization_pct": round(100 * achievable / capacity, 3) if on_route else 0.0,
            "offered_load_ratio": offered / capacity,
            "utilization_basis": "reserved pre-loss path rate / link capacity",
            "latency_ms": link.delay_ms, "packet_loss_pct": link.packet_loss_pct,
            "congested": offered >= capacity, "on_route": on_route,
        })
    active_links = sum(operational(link, nodes) for link in network.links)
    latency = round(propagation + serialization + queue, 6) if stable else None
    metrics = {
        "packets_sent": sent, "packets_delivered": received, "packets_dropped": sent - received,
        "packet_loss_pct": round(100 * (1 - delivery_fraction), 6),
        "configured_path_loss_pct": round(100 * (1 - survival), 6) if route is not None else None,
        "link_medium_loss_pct": round(100 * (1 - survival), 6) if route is not None else None,
        "congestion_loss_pct": round(100 * (1 - achievable / demand.offered_mbps), 6),
        "average_latency_ms": latency, "maximum_latency_ms": None,
        "maximum_latency_status": "unsupported: steady-state mean does not determine a maximum",
        "propagation_delay_ms": round(propagation, 6) if route is not None else None,
        "serialization_delay_ms": round(serialization, 6) if route is not None else None,
        "queueing_delay_ms": round(queue, 6) if stable else None,
        "queueing_status": "estimated" if stable else "unstable" if route is not None else "unreachable",
        "offered_traffic_mbps": demand.offered_mbps, "achievable_throughput_mbps": achievable,
        "throughput_mbps": round(delivered, 6), "delivered_traffic_mbps": round(delivered, 6),
        "path_capacity_mbps": bottleneck,
        "mean_link_utilization_pct": round(sum(item["utilization_pct"] for item in link_results) / max(1, active_links), 3),
        "reachable_nodes": len(reached), "total_nodes": len(nodes), "unreachable_nodes": len(nodes) - len(reached),
        "active_links": active_links, "failed_links": len(network.links) - active_links,
        "congested_links": sum(item["congested"] for item in link_results),
        "bottleneck_link_ids": sorted(link.id for link in path_links if _effective_capacity(link, assumptions) == bottleneck),
        "connectivity_pct": round(len(reached) / max(1, len(nodes)) * 100, 3),
        "flow_connected": route is not None, "route_node_ids": [], "route_link_ids": route or [], "links": link_results,
        "unreachable_demands": [demand.model_dump()] if route is None else [],
        "provenance": "simulated", "stage": stage,
    }
    if route is not None:
        current = demand.source_node_id
        metrics["route_node_ids"] = [current]
        for link_id in route:
            edge = by_id[link_id]
            current = edge.target_node_id if edge.source_node_id == current else edge.source_node_id
            metrics["route_node_ids"].append(current)
    steps = [{"index": 0, "kind": "start", "node_id": demand.source_node_id}]
    if route is None:
        steps.append({"index": 1, "kind": "dropped", "node_id": demand.target_node_id, "reason": "No operational route exists."})
    else:
        steps.extend({"index": i, "kind": "forward", "link_id": link_id, "node_id": metrics["route_node_ids"][i]} for i, link_id in enumerate(route, 1))
    return {"metrics": metrics, "steps": steps, "route_link_ids": route or []}


def apply_scenario(baseline: NetworkDefinition, scenario_type: str, parameters: dict[str, Any]) -> tuple[NetworkDefinition, float | None, list[str]]:
    network = deepcopy(baseline)
    assumptions: list[str] = []
    multiplier: float | None = None
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
        if not isinstance(factor, (int, float)) or isinstance(factor, bool) or not math.isfinite(factor) or factor <= 0 or factor > 1000:
            raise HTTPException(status_code=422, detail="Traffic increase factor must be greater than zero.")
        multiplier = factor
    elif scenario_type == "bandwidth_change":
        link_id, value = parameters.get("link_id"), parameters.get("bandwidth_mbps", parameters.get("value"))
        if link_id not in links:
            raise HTTPException(status_code=422, detail="Choose a valid connection for the bandwidth change scenario.")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0 or value > 1_000_000:
            raise HTTPException(status_code=422, detail="New link capacity must be greater than zero Mbps.")
        links[link_id].bandwidth_mbps = float(value)
    elif scenario_type == "redundancy_add":
        source, target = parameters.get("source_node_id"), parameters.get("target_node_id")
        if source not in nodes or target not in nodes or source == target:
            raise HTTPException(status_code=422, detail="Choose two different saved devices for the candidate redundant link.")
        if any({edge.source_node_id, edge.target_node_id} == {source, target} and edge.status not in DOWN for edge in network.links):
            raise HTTPException(status_code=422, detail="Those devices already have an operational link.")
        capacity = parameters.get("bandwidth_mbps")
        if capacity is not None and (not isinstance(capacity, (int, float)) or isinstance(capacity, bool) or not math.isfinite(capacity) or capacity <= 0 or capacity > 1_000_000):
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
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount <= 0 or amount > 1_000_000:
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
        failed_link = next((link for link in baseline.links if link.id == parameters["link_id"]), None)
        if not failed_link:
            raise HTTPException(status_code=422, detail="Selected link is not in baseline topology.")
        baseline_route = shortest_path(baseline, demand.source_node_id, demand.target_node_id, demand.offered_mbps, demand.packet_size_bytes, assumptions) or []
        is_on_route = failed_link.id in baseline_route
        if not is_on_route:
            message = (f"The selected failed link ({failed_link.id}) was outside the active traffic route. "
                       "The path continues using existing operational links; this failure does not directly affect the selected traffic flow.")
            resolved = True
        elif failed_metrics.get("flow_connected"):
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
                        "status": link.status, "metadata": {**link.metadata, "candidate": True}}))
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
            link.bandwidth_mbps = min(1_000_000, desired)
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

    return candidate, {"summary": message}, message


def run_experiment(network: NetworkDefinition, scenario_type: str, parameters: dict[str, Any], traffic: TrafficDemand) -> dict[str, Any]:
    failed, traffic_factor, scenario_assumptions = apply_scenario(network, scenario_type, parameters)
    effective_traffic = TrafficDemand.model_validate({**traffic.model_dump(), "offered_mbps": traffic.offered_mbps * traffic_factor}) if traffic_factor else traffic
    assumptions = set(scenario_assumptions)
    baseline_result = evaluate(network, traffic, assumptions, "baseline")
    if traffic_factor is not None:
        assumptions.add("Traffic-increase baseline uses original offered load; scenario and every recovery candidate use the increased offered load. Rate changes affect the comparison independently of graph changes.")
    failed_result = evaluate(failed, effective_traffic, assumptions, "failure")
    from app.services.anomaly_analysis import analyze_state
    analysis = analyze_state(network, failed, baseline_result["metrics"], failed_result["metrics"])
    failed_link_id = parameters.get("link_id") if scenario_type == "link_failure" else None
    failed_node_id = parameters.get("node_id") if scenario_type in {"device_failure", "segment_isolation"} else None
    baseline_route_links = baseline_result["metrics"].get("route_link_ids", [])
    baseline_route_nodes = baseline_result["metrics"].get("route_node_ids", [])
    failed_route_links = failed_result["metrics"].get("route_link_ids", [])
    failed_route_nodes = failed_result["metrics"].get("route_node_ids", [])

    is_on_route = False
    if scenario_type == "link_failure" and failed_link_id:
        is_on_route = failed_link_id in baseline_route_links
    elif scenario_type in {"device_failure", "segment_isolation"} and failed_node_id:
        is_on_route = failed_node_id in baseline_route_nodes

    baseline_cap = baseline_result["metrics"]["path_capacity_mbps"]
    failed_cap = failed_result["metrics"]["path_capacity_mbps"]
    baseline_congested = traffic.offered_mbps > baseline_cap if baseline_cap > 0 else False
    failed_congested = effective_traffic.offered_mbps > failed_cap if failed_cap > 0 else False

    route_survived = failed_result["metrics"]["flow_connected"]
    route_changed = baseline_route_links != failed_route_links

    if scenario_type == "link_failure":
        if not is_on_route:
            explanation = (
                f"Selected failed link ({failed_link_id}) is OUTSIDE the active source-to-destination route. "
                "This failure does not directly affect the selected traffic flow; the route remains operational."
            )
            if failed_congested:
                explanation += (
                    f" Note: Modeled packet loss of {failed_result['metrics']['packet_loss_pct']:.2f}% is caused by "
                    f"offered traffic ({effective_traffic.offered_mbps:g} Mbps) exceeding the path bottleneck capacity "
                    f"({failed_cap:g} Mbps), NOT by the link failure."
                )
            status_code = "off_route"
        else:
            if not route_survived:
                explanation = (
                    f"Selected failed link ({failed_link_id}) is ON the active route, and NO alternative path exists. "
                    "Traffic is completely disconnected (100% loss due to link failure)."
                )
                status_code = "disconnected"
            elif route_changed:
                explanation = (
                    f"Selected failed link ({failed_link_id}) is ON the active route. Traffic was rerouted "
                    f"to an alternate path ({' → '.join(failed_route_links)})."
                )
                if failed_cap < baseline_cap:
                    explanation += f" The alternate path has lower bottleneck capacity ({failed_cap:g} Mbps vs {baseline_cap:g} Mbps)."
                if failed_congested:
                    explanation += (
                        f" Modeled packet loss of {failed_result['metrics']['packet_loss_pct']:.2f}% is due to "
                        f"offered traffic exceeding the alternate path's capacity."
                    )
                status_code = "rerouted"
            else:
                explanation = f"Selected failed link ({failed_link_id}) is on the route and path survived."
                status_code = "survived"
    else:
        status_code = "non_link_scenario"
        explanation = f"Scenario {scenario_type} evaluated."

    flow_impact = {
        "scenario_type": scenario_type,
        "target_id": failed_link_id or failed_node_id or "",
        "is_on_route": is_on_route,
        "route_survived": route_survived,
        "route_changed": route_changed,
        "baseline_route_links": baseline_route_links,
        "failed_route_links": failed_route_links,
        "baseline_bottleneck_mbps": baseline_cap,
        "failed_bottleneck_mbps": failed_cap,
        "baseline_congested": baseline_congested,
        "failed_congested": failed_congested,
        "baseline_congestion_loss_pct": baseline_result["metrics"]["congestion_loss_pct"],
        "failed_congestion_loss_pct": failed_result["metrics"]["congestion_loss_pct"],
        "status_code": status_code,
        "explanation": explanation,
    }
    analysis["impact"] = {
        "newly_unreachable_node_ids": sorted(_reachable(network, traffic.source_node_id) - _reachable(failed, effective_traffic.source_node_id)),
        "baseline_offered_mbps": traffic.offered_mbps,
        "scenario_offered_mbps": effective_traffic.offered_mbps,
        "route_changed": route_changed,
        "affected_baseline_route_links": sorted(set(baseline_route_links) & set(analysis["graph_changes"]["links"]["changed"])),
        "unreachable_demands": failed_result["metrics"]["unreachable_demands"],
        "flow_impact": flow_impact,
    }
    analysis["flow_impact"] = flow_impact
    failed_result["metrics"]["flow_impact"] = flow_impact
    experiment_id = str(uuid.uuid4())
    assumptions.update({
        "Routing uses deterministic shortest path with link cost = configured propagation delay + packet serialization delay; queue delay is estimated after route selection.",
        "Packet counts use the user-entered offered Mbps, duration, and packet-size assumptions; they are modeled counts, not measurements.",
        "Effective throughput is constrained by the minimum capacity on the selected route and configured loss probabilities.",
        "Missing capacity, delay, and packet loss values are shown as unconfigured; simulation uses explicit defaults of 1000 Mbps, 1 ms, and 0% only for calculation.",
    })
    return {
        "experiment_id": experiment_id, "engine_version": ENGINE_VERSION, "traffic": effective_traffic.model_dump(), "analysis": analysis,
        "baseline_topology": network.model_dump(mode="json"), "failed_topology": failed.model_dump(mode="json"),
        "baseline_metrics": baseline_result["metrics"], "failed_metrics": failed_result["metrics"],
        "flow_impact": flow_impact,
        "failure_steps": _failure_steps(network, failed, failed_result["steps"]),
        "assumptions": sorted(assumptions),
        "status": "completed", "provenance": "simulated",
    }


def run_modernization(network: NetworkDefinition, failed: NetworkDefinition, scenario_type: str, parameters: dict[str, Any], traffic: TrafficDemand, failed_metrics: dict[str, Any], assumption_values: list[str], criteria=None) -> dict[str, Any]:
    from app.models.failure_simulation import ExperimentModernizeRequest
    from app.services.transformation import evaluate_strategies
    assumptions = set(assumption_values)
    proposal = evaluate_strategies(network, failed, scenario_type, parameters, traffic, failed_metrics, assumptions, criteria or ExperimentModernizeRequest())
    topology = proposal.pop("selected_topology")
    return {"modernized_topology": topology, "modernization": proposal,
            "modernized_metrics": proposal["metrics"], "modernization_steps": proposal["steps"],
            "assumptions": sorted(assumptions)}


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
