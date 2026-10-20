"""Candidate generation and explicit decision scoring over the one analytical engine."""
from copy import deepcopy
from math import isclose
from typing import Any
import hashlib
import json

from app.engines.analytical_simulator import DOWN, evaluate, modernize, shortest_path
from app.models.failure_simulation import ExperimentModernizeRequest, TrafficDemand
from app.models.network import LinkDefinition, NetworkDefinition
from app.services.anomaly_analysis import analyze_state


def proposal_revision(proposal):
    return hashlib.sha256(json.dumps({"criteria": proposal.get("criteria"), "candidates": proposal.get("candidates")}, sort_keys=True).encode()).hexdigest()


def service_outcome(before: dict, after: dict) -> dict:
    """Describe predicted service change separately from ranking/target attainment."""
    gains, regressions = [], []
    for key, higher_is_better in (("throughput_mbps", True), ("reachable_nodes", True),
                                 ("packet_loss_pct", False), ("average_latency_ms", False)):
        old, new = before.get(key), after.get(key)
        if old is None or new is None:
            continue  # Undefined/unstable delay is not a numerical improvement.
        if not isclose(old, new, rel_tol=1e-6, abs_tol=1e-6):
            (gains if (new > old) == higher_is_better else regressions).append(key)
    if after.get("flow_connected") and not before.get("flow_connected"):
        gains.append("flow_connected")
    elif before.get("flow_connected") and not after.get("flow_connected"):
        regressions.append("flow_connected")
    if regressions:
        message = "Mixed modeled effects; review trade-offs" if gains else "Modeled service degradation predicted"
    elif gains:
        message = "Modeled service improvement predicted"
    elif after.get("flow_connected"):
        message = "Service maintained; no additional performance gain predicted"
    else:
        message = "No operational route; no recovery predicted"
    return {"service_outcome": message, "performance_improved": bool(gains) and not regressions,
            "performance_gains": gains, "performance_regressions": regressions}


def _changes(before: NetworkDefinition, after: NetworkDefinition) -> tuple[int, list[str]]:
    nodes = {n.id: n for n in before.nodes}
    links = {e.id: e for e in before.links}
    units, changes = 0, []
    for node in after.nodes:
        if node.id not in nodes:
            units += 8
            changes.append(f"Add device {node.id}")
        elif node.status != nodes[node.id].status:
            units += 1
            changes.append(f"Repair device {node.id}")
    for link in after.links:
        if link.id not in links:
            units += 3
            changes.append(f"Add link {link.id}")
        else:
            if link.status != links[link.id].status:
                units += 1
                changes.append(f"Restore link state {link.id} to {link.status}")
            if link.bandwidth_mbps != links[link.id].bandwidth_mbps:
                units += 2
                capacity = f"{link.bandwidth_mbps:g} Mbps" if link.bandwidth_mbps is not None else "unconfigured (explicit model default)"
                changes.append(f"Set capacity {link.id} to {capacity}")
    return units, changes


def evaluate_strategies(baseline: NetworkDefinition, failed: NetworkDefinition, scenario_type: str,
                        parameters: dict, demand: TrafficDemand, failed_metrics: dict,
                        assumptions: set[str], criteria: ExperimentModernizeRequest) -> dict[str, Any]:
    candidates = [("retain", "Retain surviving routes", deepcopy(failed))]
    if criteria.allow_repair and scenario_type in {"link_failure", "device_failure", "bandwidth_change"}:
        repair = deepcopy(failed)
        # Restore only the selected scenario's changes, never unrelated baseline faults.
        old_nodes = {n.id: n for n in baseline.nodes}
        old_links = {e.id: e for e in baseline.links}
        if scenario_type == "device_failure":
            target = parameters["node_id"]
            for node in repair.nodes:
                if node.id == target:
                    node.status = old_nodes[node.id].status
            for link in repair.links:
                if target in (link.source_node_id, link.target_node_id):
                    link.status = old_links[link.id].status
        else:
            target = parameters["link_id"]
            for link in repair.links:
                if link.id == target:
                    link.status = old_links[link.id].status
                    link.bandwidth_mbps = old_links[link.id].bandwidth_mbps
        candidates.append(("repair", "Restore selected failed configuration", repair))
    if scenario_type not in {"segment_isolation", "cloud_migration"}:
        engineered, _, _ = modernize(baseline, failed, scenario_type, parameters, demand, failed_metrics, assumptions)
        if engineered.model_dump() != failed.model_dump():
            candidates.append(("targeted", "Targeted replacement or capacity upgrade", engineered))
        if criteria.allow_new_links:
            bypass = deepcopy(failed)
            nodes = {n.id: n for n in bypass.nodes}
            pair = {demand.source_node_id, demand.target_node_id}
            existing_direct = any({e.source_node_id, e.target_node_id} == pair and e.status not in DOWN for e in bypass.links)
            if not existing_direct and nodes[demand.source_node_id].status not in DOWN and nodes[demand.target_node_id].status not in DOWN:
                bypass.links.append(LinkDefinition(
                    id="candidate:dedicated-service-path", source_node_id=demand.source_node_id,
                    target_node_id=demand.target_node_id, bandwidth_mbps=min(1_000_000, demand.offered_mbps * 1.25),
                    delay_ms=None, packet_loss_pct=None, metadata={"candidate": True, "design_assumption": True}))
                candidates.append(("bypass", "Dedicated service path with capacity headroom", bypass))
    evaluated = []
    total_weight = sum(criteria.weights.values())
    for strategy_id, title, candidate in candidates:
        evaluated.append(evaluate_candidate(strategy_id, title, candidate, failed, demand, failed_metrics, assumptions, criteria))
    evaluated.sort(key=lambda item: (not item["feasible"], -item["score"], item["id"]))
    selected = next(item for item in evaluated if item["feasible"])  # retain always fits a nonnegative budget
    optimization = None
    if criteria.optimizer:
        from app.services.optimization import optimize_candidates
        optimization = optimize_candidates(failed, evaluated, demand, failed_metrics, assumptions, criteria)
        alternatives = optimization.pop("candidates")
        evaluated.extend(alternatives)
        pareto = [c for c in alternatives if c["id"] in optimization["pareto_candidate_ids"]]
        if pareto:
            selected = sorted(pareto, key=lambda c: (-c["score"], c["id"]))[0]
    proposal = describe_selection(selected, evaluated, failed_metrics, demand, criteria, assumptions, scenario_type)
    if optimization:
        proposal["optimization"] = optimization
        if optimization["status"] == "completed":
            proposal["recommendation"]["rationale"] = "Weighted preference among the evaluated feasible Pareto alternatives. " + proposal["recommendation"]["rationale"].split(". ", 1)[1]
    return proposal


def describe_selection(selected, evaluated, failed_metrics, demand, criteria, assumptions, scenario_type, operator=False):
    metrics = selected["metrics"]
    outcome = service_outcome(failed_metrics, metrics)
    disabled_links = sorted(link["id"] for link in metrics["links"] if link["status"] in DOWN)
    previously_disabled = {link["id"] for link in failed_metrics["links"] if link["status"] in DOWN}
    repaired_links = sorted(link["id"] for link in metrics["links"] if link["id"] in previously_disabled and link["status"] not in DOWN)
    failure_explanation = (
        f"Disabled connections remain isolated and red: {', '.join(disabled_links)}. They have not been repaired or removed."
        if disabled_links else "No disabled connections remain in this candidate."
    )
    if repaired_links:
        failure_explanation += f" Repaired connections are operational in this candidate: {', '.join(repaired_links)}."
    route_explanation = (f"Calculated operational route: {' -> '.join(metrics['route_node_ids'])}; links: {', '.join(metrics['route_link_ids'])}."
                         if metrics["flow_connected"] else "No operational alternate route exists for this demand in the candidate graph.")
    trade_offs = list(selected["trade_offs"])
    if selected["id"] == "retain":
        trade_offs.append("Avoids configuration changes and their cost, but retains the outage and depends on surviving paths; service targets being met does not imply a repaired link or extra performance.")
    failed_impact = failed_metrics.get("flow_impact") or {}
    if failed_impact.get("is_on_route") is False and selected["id"] == "bypass":
        trade_offs.append("The scenario failed link was outside the traffic path. The proposed bypass addresses traffic congestion (offered load exceeding baseline path bottleneck) rather than recovering a broken link.")
    if not outcome["performance_improved"]:
        trade_offs.append(outcome["service_outcome"])
    minimum_delivery = criteria.optimizer.minimum_delivery_ratio if criteria.optimizer else 0.95
    resolved = (metrics["flow_connected"] and metrics["throughput_mbps"] >= minimum_delivery * demand.offered_mbps
                and metrics["average_latency_ms"] is not None and metrics["average_latency_ms"] <= criteria.latency_target_ms)
    assumptions.add("Ranking uses user weights. Performance = 80% delivered/offered + 20% latency-target ratio; resilience = surviving selected-route single-link outage fraction; feasibility = 1/(1+0.1*change count); cost = 1/(1+change units).")
    assumptions.add("Change units: device addition 8, link addition 3, capacity upgrade 2, state restoration 1. Physical feasibility and monetary costs are unverified.")
    return {
        **outcome,
        "resolved": bool(resolved), "summary": f"Selected {selected['title']} with weighted score {selected['score']:.3f}. {outcome['service_outcome']}. {failure_explanation}",
        "disabled_link_ids": disabled_links, "repaired_link_ids": repaired_links,
        "selected_strategy_id": selected["id"], "criteria": criteria.model_dump(), "candidates": evaluated,
        "recommendation": {
            "problem": scenario_type, "root_cause": f"Failed state: connected={failed_metrics['flow_connected']}, delivery={failed_metrics['throughput_mbps']} Mbps, bottlenecks={failed_metrics['bottleneck_link_ids']}.",
            "proposed_modification": f"{selected['title']}. {failure_explanation}", "relative_cost": f"{selected['change_units']} change units",
            "rationale": ("Explicit operator choice. " if operator else "Highest weighted score among candidates satisfying the declared change budget and permissions. ") + f" The score measures preference fit, not performance improvement or failure repair. {route_explanation} {outcome['service_outcome']}.",
            "implementation_steps": selected["changes"] or ["Retain surviving route configuration.", failure_explanation, route_explanation],
            "trade_offs": trade_offs,
        },
        "metrics": metrics, "steps": selected["steps"], "selected_topology": selected["topology"],
    }


def evaluate_candidate(strategy_id, title, candidate, failed, demand, failed_metrics, assumptions, criteria):
    total_weight = sum(criteria.weights.values())
    units, changes = _changes(failed, candidate)
    new_link = any(e.id not in {old.id for old in failed.links} for e in candidate.links)
    feasible = units <= criteria.max_change_units and (criteria.allow_new_links or not new_link)
    replacement_map = {n.metadata["replaces_node_id"]: n.id for n in candidate.nodes if n.metadata.get("replaces_node_id")}
    effective = TrafficDemand.model_validate({**demand.model_dump(),
        "source_node_id": replacement_map.get(demand.source_node_id, demand.source_node_id),
        "target_node_id": replacement_map.get(demand.target_node_id, demand.target_node_id)})
    result = evaluate(candidate, effective, assumptions, "modernized")
    metrics = result["metrics"]
    # Available before any future optimizer: flag risk without suppressing recovery options.
    risk = analyze_state(failed, candidate, failed_metrics, metrics, structure=False)
    # Exact single-link stress cases on the selected route; no random sampling.
    survives = 0
    route = metrics["route_link_ids"]
    for link_id in route:
        stress = deepcopy(candidate)
        next(e for e in stress.links if e.id == link_id).status = "failed"
        survives += shortest_path(stress, effective.source_node_id, effective.target_node_id,
                                  effective.offered_mbps, effective.packet_size_bytes, assumptions) is not None
    resilience = survives / len(route) if route else 0.0
    latency = metrics["average_latency_ms"]
    delivery = metrics["throughput_mbps"] / demand.offered_mbps
    components = {
        "performance": 0.8 * delivery + 0.2 * (min(1.0, criteria.latency_target_ms / max(latency, 1e-12)) if latency is not None else 0),
        "resilience": resilience,
        "feasibility": 1 / (1 + 0.1 * len(changes)),
        "cost": 1 / (1 + units),
    }
    score = sum(criteria.weights[k] * components[k] for k in components) / total_weight
    trade_offs = [
        "Change units are relative design assumptions, not monetary quotes.",
        "Ports, physical installation, device compatibility and routing policy need engineering validation.",
    ] if changes else ["Retains current outages and capacity limitations."]
    if strategy_id == "bypass":
        path_cap = metrics.get("path_capacity_mbps", 0.0)
        if path_cap >= demand.offered_mbps:
            trade_offs.append(f"Dedicated service path capacity ({path_cap:g} Mbps) verified sufficient for offered traffic ({demand.offered_mbps:g} Mbps); 0% congestion loss.")
        else:
            loss_fraction = max(0.0, 1.0 - (path_cap / demand.offered_mbps))
            metrics["congestion_loss_pct"] = round(100 * loss_fraction, 6)
            trade_offs.append(f"Dedicated service path capacity ({path_cap:g} Mbps) is less than offered traffic ({demand.offered_mbps:g} Mbps); congestion loss occurs.")
    return {
        "id": strategy_id, "title": title, "topology": candidate.model_dump(mode="json"),
        "metrics": metrics, "steps": result["steps"], "score": round(score, 6),
        "components": components, "change_units": units, "changes": changes,
        "feasible": feasible, "feasibility_status": "conditional on engineering review" if changes else "existing configuration",
        "constraints": [] if feasible else ["Change budget or new-link constraint exceeded"],
        "resilience_test": {"type": "selected-route single-link outages", "survived": survives, "tested": len(route)},
        "endpoint_mapping": replacement_map,
        "risk_analysis": risk,
        "screening": {"eligible": feasible, "risk_flag_only": risk["flagged"],
                      "reason": "Risk never excludes a candidate; only explicit budget/permission constraints do."},
        "trade_offs": trade_offs,
    }
