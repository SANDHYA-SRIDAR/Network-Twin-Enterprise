"""Transparent, untrained risk baseline. Scores are NOT failure probabilities."""
from app.engines.graph_adapter import structural_analysis, graph_changes


def analyze_state(baseline, state, before: dict, after: dict, *, structure: bool = True) -> dict:
    changes = graph_changes(baseline, state)
    ratios = [link.get("offered_load_ratio", 0) for link in after["links"]]
    old_latency, new_latency = before.get("average_latency_ms"), after.get("average_latency_ms")
    latency_deviation = ((new_latency - old_latency) / old_latency
                         if old_latency is not None and old_latency > 0 and new_latency is not None else None)
    # Loss defaults are not observations: report deviation only on fully configured routes.
    def configured_loss(graph, metrics):
        ids = set(metrics.get("route_link_ids", []))
        return bool(ids) and all(e.packet_loss_pct is not None for e in graph.links if e.id in ids)
    loss_deviation = (after["configured_path_loss_pct"] - before["configured_path_loss_pct"]
                      if configured_loss(baseline, before) and configured_loss(state, after) else None)
    features = {
        "max_offered_capacity_ratio": max(ratios, default=0),
        "failed_links": after["failed_links"], "new_failed_links": max(0, after["failed_links"] - before["failed_links"]),
        "disconnected_demand": not after["flow_connected"],
        "reachable_node_change": after["reachable_nodes"] - before["reachable_nodes"],
        "relative_latency_deviation": latency_deviation, "configured_loss_deviation_pct": loss_deviation,
        "changed_link_count": sum(len(v) for v in changes["links"].values()),
        "queueing_unstable": after.get("queueing_status") == "unstable",
    }
    rules = []
    if features["disconnected_demand"]:
        rules.append({"rule": "unreachable_demand", "severity": 1.0, "explanation": "The analytical graph has no route for the demand."})
    if features["new_failed_links"]:
        rules.append({"rule": "new_disabled_connections", "severity": 1.0, "explanation": "The scenario introduces disabled connections; this may be intentional and need not affect this flow."})
    if features["queueing_unstable"]:
        rules.append({"rule": "unstable_queue", "severity": 1.0, "explanation": "Offered load is at or above capacity; a finite steady-state queue mean is unavailable."})
    if latency_deviation is not None and latency_deviation > 0:
        rules.append({"rule": "latency_increase", "severity": min(1.0, latency_deviation), "explanation": "Mean modeled delay increased relative to the specified baseline."})
    if loss_deviation is not None and loss_deviation > 0:
        rules.append({"rule": "configured_loss_increase", "severity": min(1.0, loss_deviation / 10), "explanation": "End-to-end loss estimate increased on fully configured routes; not measured telemetry."})
    score = max((r["severity"] for r in rules), default=0.0)
    result = {"method": "rule_based_baseline_v1", "trained_model": False, "training_data": "none",
              "provenance": "analytical_features", "score": score, "threshold": 0.5,
              "flagged": score >= 0.5, "features": features, "findings": rules, "graph_changes": changes,
              "limitations": ["Score is a transparent rule severity, not a calibrated anomaly/failure probability or future failure prediction.",
                             "No historical telemetry or trained model is available. Intentional faults may be flagged."]}
    if structure:
        result["structure"] = structural_analysis(state)
    return result
