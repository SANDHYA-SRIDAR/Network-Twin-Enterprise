"""AI-based topology anomaly and vulnerability detector.

Combines deterministic graph analysis (Tier 1: bridges, articulation points),
unsupervised machine learning (Tier 2: IsolationForest fitted on synthetic baseline),
and configuration validation (Tier 3: IP/subnet/gateway checks).
All outputs are labeled as modeled/simulated analysis.
"""
from __future__ import annotations

from copy import deepcopy
import math
from threading import Lock
from typing import Any, Optional

import networkx as nx
import numpy as np
from sklearn.ensemble import IsolationForest

from app.engines.analytical_simulator import (
    DEFAULT_CAPACITY_MBPS,
    DEFAULT_DELAY_MS,
    DEFAULT_PACKET_LOSS_PCT,
    _effective_capacity,
    evaluate,
    shortest_path,
)
from app.engines.graph_adapter import DOWN, network_graph, operational
from app.models.anomaly import AnomalyAnalysisResponse, AnomalyFinding
from app.models.failure_simulation import TrafficDemand
from app.models.network import LinkDefinition, NetworkDefinition, NodeDefinition
from app.services.network_validation import validate_network_definition
from app.services.synthetic_topologies import get_training_topologies

_MODEL_LOCK = Lock()
_CACHED_LINK_MODEL: Optional[IsolationForest] = None
_CACHED_NODE_MODEL: Optional[IsolationForest] = None
_BASELINE_STATS: Optional[dict[str, Any]] = None

REACHABILITY_SWEEP_CAP = 50


def _extract_link_features(
    network: NetworkDefinition,
    traffic: Optional[TrafficDemand] = None,
    assumptions: Optional[set[str]] = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Extract contextual ML features per operational link plus exact structural reachability impact."""
    nodes = {n.id: n for n in network.nodes}
    assumptions_set = assumptions if assumptions is not None else set()
    graph = network_graph(network, operational_only=True)

    # Simple undirected projection for networkx algorithms
    projection = nx.Graph()
    projection.add_nodes_from(graph.nodes)
    for u, v in graph.edges():
        projection.add_edge(u, v)

    # Edge betweenness centrality on the projection
    edge_bc = nx.edge_betweenness_centrality(projection) if projection.number_of_edges() else {}

    # Simulated traffic evaluation if demand provided, or default reference demand
    demand = traffic
    eval_metrics: dict[str, Any] = {}
    if demand and demand.source_node_id in nodes and demand.target_node_id in nodes:
        try:
            clean_net = network.model_copy(deep=True)
            for n in clean_net.nodes:
                for iface in n.interfaces:
                    if iface.ip_configuration:
                        iface.ip_configuration.gateway = None
            eval_result = evaluate(clean_net, demand, assumptions_set, "baseline")
            eval_metrics = {l["id"]: l for l in eval_result["metrics"].get("links", [])}
        except Exception:
            pass

    operational_links = [e for e in network.links if operational(e, nodes)]
    
    # Cap the per-link reachability magnitude sweep
    reachability_sweep_capped = len(operational_links) > REACHABILITY_SWEEP_CAP
    sweep_candidates = operational_links
    if reachability_sweep_capped:
        sweep_candidates = sorted(
            operational_links,
            key=lambda e: edge_bc.get(tuple(sorted((e.source_node_id, e.target_node_id))), 0.0),
            reverse=True,
        )[:REACHABILITY_SWEEP_CAP]
    sweep_set = {e.id for e in sweep_candidates}

    # Group links by device_type pair in current topology
    links_by_pair: dict[tuple[str, str], list[LinkDefinition]] = {}
    for l in operational_links:
        u_type = nodes[l.source_node_id].device_type if l.source_node_id in nodes else "unknown"
        v_type = nodes[l.target_node_id].device_type if l.target_node_id in nodes else "unknown"
        p = tuple(sorted([u_type, v_type]))
        links_by_pair.setdefault(p, []).append(l)

    # Topology-wide medians as fallback
    topo_delays = [l.delay_ms if l.delay_ms is not None else DEFAULT_DELAY_MS for l in operational_links]
    topo_losses = [l.packet_loss_pct if l.packet_loss_pct is not None else 0.0 for l in operational_links]
    topo_caps = [_effective_capacity(l, assumptions_set) for l in operational_links]
    topo_med_delay = float(np.median(topo_delays)) if topo_delays else DEFAULT_DELAY_MS
    topo_med_loss = float(np.median(topo_losses)) if topo_losses else 0.0
    topo_med_cap = float(np.median(topo_caps)) if topo_caps else DEFAULT_CAPACITY_MBPS

    link_data = []
    base_components = nx.number_connected_components(projection) if projection.number_of_nodes() else 0

    for link in operational_links:
        cap = _effective_capacity(link, assumptions_set)
        delay = link.delay_ms if link.delay_ms is not None else DEFAULT_DELAY_MS
        loss = link.packet_loss_pct if link.packet_loss_pct is not None else 0.0
        pair_nodes = tuple(sorted((link.source_node_id, link.target_node_id)))
        bc = edge_bc.get(pair_nodes, 0.0)

        u_type = nodes[link.source_node_id].device_type if link.source_node_id in nodes else "unknown"
        v_type = nodes[link.target_node_id].device_type if link.target_node_id in nodes else "unknown"
        pair = tuple(sorted([u_type, v_type]))
        group = links_by_pair.get(pair, [link])

        g_delays = [x.delay_ms if x.delay_ms is not None else DEFAULT_DELAY_MS for x in group]
        g_losses = [x.packet_loss_pct if x.packet_loss_pct is not None else 0.0 for x in group]
        g_caps = [_effective_capacity(x, assumptions_set) for x in group]

        med_delay = float(np.median(g_delays)) if len(group) > 1 else topo_med_delay
        med_loss = float(np.median(g_losses)) if len(group) > 1 else topo_med_loss
        med_cap = float(np.median(g_caps)) if len(group) > 1 else topo_med_cap

        # Traffic utilization
        link_eval = eval_metrics.get(link.id, {})
        util_pct = link_eval.get("utilization_pct", 0.0)
        offered_load = link_eval.get("offered_load_ratio", 0.0)

        # Contextual relative ratios within peer device-type group
        rel_delay = float(delay / max(med_delay, 0.01))
        rel_loss = float(loss - med_loss)
        rel_cap = float(cap / max(med_cap, 1.0))

        # Reachability magnitude impact (evaluated only if within sweep cap)
        reach_drop = 0
        if link.id in sweep_set:
            test_proj = projection.copy()
            if graph.number_of_edges(link.source_node_id, link.target_node_id) == 1:
                test_proj.remove_edge(link.source_node_id, link.target_node_id)
            new_comp = nx.number_connected_components(test_proj)
            reach_drop = max(0, new_comp - base_components)

        features = [
            float(util_pct),
            float(offered_load),
            float(delay),
            float(loss),
            float(cap),
            float(bc),
            float(rel_delay),
            float(rel_loss),
            float(rel_cap),
        ]

        link_data.append({
            "id": link.id,
            "source_node_id": link.source_node_id,
            "target_node_id": link.target_node_id,
            "peer_pair": f"{pair[0]}<->{pair[1]}",
            "features": features,
            "metrics": {
                "utilization_pct": round(util_pct, 2),
                "offered_load_ratio": round(offered_load, 3),
                "delay_ms": round(delay, 2),
                "packet_loss_pct": round(loss, 2),
                "bandwidth_mbps": round(cap, 2),
                "betweenness_centrality": round(bc, 4),
                "rel_delay_in_pair": round(rel_delay, 2),
                "rel_loss_in_pair": round(rel_loss, 2),
                "rel_cap_in_pair": round(rel_cap, 2),
                "reachability_impact": reach_drop if link.id in sweep_set else None,
            },
        })

    return link_data, reachability_sweep_capped


def _extract_node_features(
    network: NetworkDefinition,
    assumptions: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Extract 6-dimensional ML features per operational node."""
    nodes = {n.id: n for n in network.nodes}
    assumptions_set = assumptions if assumptions is not None else set()
    graph = network_graph(network, operational_only=True)

    projection = nx.Graph()
    projection.add_nodes_from(graph.nodes)
    for u, v in graph.edges():
        projection.add_edge(u, v)

    node_bc = nx.betweenness_centrality(projection) if projection.number_of_nodes() else {}

    node_data = []
    for node in network.nodes:
        if node.status in DOWN:
            continue
        degree = graph.degree(node.id) if node.id in graph else 0
        bc = node_bc.get(node.id, 0.0)

        # Incident link characteristics
        incident_links = [
            e for e in network.links
            if operational(e, nodes) and (e.source_node_id == node.id or e.target_node_id == node.id)
        ]
        inc_cap = sum(_effective_capacity(e, assumptions_set) for e in incident_links)
        inc_delays = [e.delay_ms if e.delay_ms is not None else DEFAULT_DELAY_MS for e in incident_links]
        mean_delay = float(np.mean(inc_delays)) if inc_delays else DEFAULT_DELAY_MS
        inc_losses = [e.packet_loss_pct if e.packet_loss_pct is not None else DEFAULT_PACKET_LOSS_PCT for e in incident_links]
        max_loss = float(max(inc_losses)) if inc_losses else 0.0
        is_isolated = 1.0 if degree == 0 else 0.0

        # ML feature vector (6 dimensions): NO is_articulation_point
        features = [
            float(degree),
            float(bc),
            float(inc_cap),
            float(mean_delay),
            float(max_loss),
            float(is_isolated),
        ]
        node_data.append({
            "id": node.id,
            "name": node.name,
            "device_type": node.device_type,
            "features": features,
            "metrics": {
                "degree": degree,
                "betweenness_centrality": round(bc, 4),
                "incident_capacity_mbps": round(inc_cap, 2),
                "mean_incident_delay_ms": round(mean_delay, 2),
                "max_incident_loss_pct": round(max_loss, 2),
                "is_isolated": bool(degree == 0),
            },
        })

    return node_data


def _train_baseline_models() -> tuple[IsolationForest, IsolationForest, dict[str, Any]]:
    """Train link and node IsolationForest detectors on synthetic enterprise topologies."""
    train_topos = get_training_topologies()
    link_rows: list[list[float]] = []
    node_rows: list[list[float]] = []

    base_traffic = TrafficDemand(source_node_id="pc-1", target_node_id="server-web", offered_mbps=200.0)

    for topo in train_topos:
        links, _ = _extract_link_features(topo, traffic=base_traffic)
        nodes = _extract_node_features(topo)
        for l in links:
            link_rows.append(l["features"])
        for n in nodes:
            node_rows.append(n["features"])

    X_links = np.array(link_rows, dtype=np.float64)
    X_nodes = np.array(node_rows, dtype=np.float64)

    # Train IsolationForest with contamination="auto"
    link_model = IsolationForest(n_estimators=100, contamination="auto", random_state=42)
    link_model.fit(X_links)

    node_model = IsolationForest(n_estimators=100, contamination="auto", random_state=42)
    node_model.fit(X_nodes)

    train_link_scores = -link_model.decision_function(X_links)
    train_node_scores = -node_model.decision_function(X_nodes)

    # Threshold chosen on validation split (seeds 2000..2009): 99.8th percentile
    link_threshold = float(np.percentile(train_link_scores, 99.8))
    node_threshold = float(np.percentile(train_node_scores, 99.8))

    stats = {
        "train_samples": {"links": len(link_rows), "nodes": len(node_rows)},
        "link_threshold": round(link_threshold, 4),
        "node_threshold": round(node_threshold, 4),
        "threshold_percentile": 99.8,
        "link_feature_medians": np.median(X_links, axis=0).tolist(),
        "node_feature_medians": np.median(X_nodes, axis=0).tolist(),
    }
    return link_model, node_model, stats


def get_trained_models() -> tuple[IsolationForest, IsolationForest, dict[str, Any]]:
    """Thread-safe cached access to baseline models."""
    global _CACHED_LINK_MODEL, _CACHED_NODE_MODEL, _BASELINE_STATS
    if _CACHED_LINK_MODEL is None or _CACHED_NODE_MODEL is None:
        with _MODEL_LOCK:
            if _CACHED_LINK_MODEL is None or _CACHED_NODE_MODEL is None:
                _CACHED_LINK_MODEL, _CACHED_NODE_MODEL, _BASELINE_STATS = _train_baseline_models()
    return _CACHED_LINK_MODEL, _CACHED_NODE_MODEL, _BASELINE_STATS


def analyze_topology_anomalies(
    network: NetworkDefinition,
    traffic: Optional[TrafficDemand] = None,
) -> AnomalyAnalysisResponse:
    """Analyze a single topology for structural weak points, ML metric outliers, and configuration issues."""
    assumptions: set[str] = {
        "Detections are modeled analytical findings, not captured live telemetry or real-time failure alerts.",
        "Normal baseline distribution is defined by a seeded synthetic enterprise generator (25 topologies, ~300 links, ~150 nodes).",
        "Deterministic structural rules take precedence; ML findings highlight multidimensional metric outliers relative to the synthetic baseline.",
    }

    nodes = {n.id: n for n in network.nodes}
    operational_nodes = [n for n in network.nodes if n.status not in DOWN]
    operational_links = [e for e in network.links if operational(e, nodes)]

    # Graph projections for exact structural analysis
    graph = network_graph(network, operational_only=True)
    projection = nx.Graph()
    projection.add_nodes_from(graph.nodes)
    for u, v in graph.edges():
        projection.add_edge(u, v)

    # Containers for raw findings by element id to facilitate merging
    findings_by_id: dict[str, dict[str, Any]] = {}

    def add_or_merge_finding(
        target_type: str,
        target_id: str,
        tier: str,
        kind: str,
        title: str,
        severity: float,
        score: float,
        method: str,
        evidence: dict[str, Any],
        explanation: str,
    ):
        key = f"{target_type}:{target_id}"
        if key in findings_by_id:
            existing = findings_by_id[key]
            if method not in existing["methods"]:
                existing["methods"].append(method)
            # Consolidate title and explanation
            if method == "isolation_forest" and "rule" in existing["methods"]:
                existing["explanation"] += f" Additionally flagged as an outlier by Isolation Forest (score {score:.3f})."
                existing["evidence"].update(evidence)
            elif method == "rule" and "isolation_forest" in existing["methods"]:
                existing["tier"] = tier  # Rule tier takes precedence
                existing["title"] = title
                existing["explanation"] = f"{explanation} Also flagged as an outlier by Isolation Forest."
                existing["evidence"].update(evidence)
            existing["severity"] = max(existing["severity"], severity)
            existing["score"] = max(existing["score"], score)
        else:
            findings_by_id[key] = {
                "id": f"anomaly:{key}",
                "target_type": target_type,
                "target_id": target_id,
                "tier": tier,
                "kind": kind,
                "title": title,
                "severity": round(severity, 3),
                "score": round(score, 4),
                "methods": [method],
                "evidence": evidence,
                "explanation": explanation,
            }

    # =========================================================================
    # TIER 1: Structural Weak Points (Exact NetworkX rules - NO CAP)
    # =========================================================================
    if projection.number_of_nodes() > 0:
        # Exact bridges: single links whose failure partitions the graph
        bridges = sorted(
            link.id
            for u, v in nx.bridges(projection)
            if graph.number_of_edges(u, v) == 1
            for link in network.links
            if operational(link, nodes) and {link.source_node_id, link.target_node_id} == {u, v}
        )
        for bridge_id in bridges:
            link = next(e for e in network.links if e.id == bridge_id)
            add_or_merge_finding(
                target_type="link",
                target_id=bridge_id,
                tier="structural_weak_point",
                kind="bridge_link",
                title=f"Bridge Link (Single Point of Failure): {bridge_id}",
                severity=0.85,
                score=0.85,
                method="rule",
                evidence={"bridge": True, "source": link.source_node_id, "target": link.target_node_id},
                explanation="This connection is a topological bridge. Its failure immediately partitions network components.",
            )

        # Exact articulation points: nodes whose removal disconnects the graph
        articulation_pts = sorted(nx.articulation_points(projection))
        for node_id in articulation_pts:
            node = nodes.get(node_id)
            name = node.name if node else node_id
            add_or_merge_finding(
                target_type="node",
                target_id=node_id,
                tier="structural_weak_point",
                kind="articulation_point",
                title=f"Cut-Vertex / SPOF Device: {name}",
                severity=0.90,
                score=0.90,
                method="rule",
                evidence={"articulation_point": True, "degree": graph.degree(node_id)},
                explanation=f"Device {name} is an articulation point. If it fails, connected components lose mutual reachability.",
            )

        # Isolated nodes (degree == 0)
        for node_id in graph.nodes:
            if graph.degree(node_id) == 0:
                node = nodes.get(node_id)
                name = node.name if node else node_id
                add_or_merge_finding(
                    target_type="node",
                    target_id=node_id,
                    tier="structural_weak_point",
                    kind="isolated_node",
                    title=f"Isolated Device: {name}",
                    severity=0.95,
                    score=0.95,
                    method="rule",
                    evidence={"isolated": True, "degree": 0},
                    explanation=f"Device {name} has no operational connections to any other network device.",
                )

    # =========================================================================
    # TIER 3: Configuration Issues (Rules from network_validation.py)
    # =========================================================================
    config_issues = validate_network_definition(network)
    for issue in config_issues:
        target_id = issue.path
        target_type = "node" if issue.path.startswith("nodes") else "link" if issue.path.startswith("links") else "topology"
        add_or_merge_finding(
            target_type=target_type,
            target_id=target_id,
            tier="configuration_issue",
            kind=issue.code,
            title=f"Configuration Concern: {issue.code.replace('_', ' ').capitalize()}",
            severity=0.70,
            score=0.70,
            method="rule",
            evidence={"path": issue.path, "code": issue.code},
            explanation=issue.message,
        )

    # =========================================================================
    # DETERMINISTIC METRIC RULES: Traffic Overload & Extreme Degradation
    # =========================================================================
    if traffic and traffic.source_node_id in nodes and traffic.target_node_id in nodes:
        try:
            clean_net = network.model_copy(deep=True)
            for n in clean_net.nodes:
                for iface in n.interfaces:
                    if iface.ip_configuration:
                        iface.ip_configuration.gateway = None
            eval_result = evaluate(clean_net, traffic, assumptions, "baseline")
            for link_res in eval_result["metrics"].get("links", []):
                lid = link_res["id"]
                offered = link_res.get("offered_traffic_mbps", 0.0)
                cap = link_res.get("effective_capacity_mbps", 1000.0)
                load_ratio = link_res.get("offered_load_ratio", 0.0)
                util_pct = link_res.get("utilization_pct", 0.0)
                congested = link_res.get("congested", False) or load_ratio >= 1.0

                if congested or load_ratio >= 1.0:
                    add_or_merge_finding(
                        target_type="link",
                        target_id=lid,
                        tier="metric_outlier",
                        kind="overloaded_link",
                        title=f"Overloaded Connection (Capacity Exceeded): {lid}",
                        severity=0.85,
                        score=0.85,
                        method="rule",
                        evidence={
                            "offered_mbps": offered,
                            "capacity_mbps": cap,
                            "offered_load_ratio": round(load_ratio, 3),
                            "utilization_pct": util_pct,
                        },
                        explanation=f"Connection {lid} offered load ({offered:.1f} Mbps) exceeds effective capacity ({cap:.1f} Mbps) under supplied traffic demand. Congestion and dropped traffic will occur.",
                    )
                elif load_ratio >= 0.80 or util_pct >= 80.0:
                    add_or_merge_finding(
                        target_type="link",
                        target_id=lid,
                        tier="metric_outlier",
                        kind="high_utilization_warning",
                        title=f"High Utilization Warning: {lid}",
                        severity=0.65,
                        score=0.65,
                        method="rule",
                        evidence={
                            "offered_mbps": offered,
                            "capacity_mbps": cap,
                            "offered_load_ratio": round(load_ratio, 3),
                            "utilization_pct": util_pct,
                        },
                        explanation=f"Connection {lid} utilization is {util_pct:.1f}% under supplied traffic demand, approaching saturation threshold (80%).",
                    )
        except Exception:
            pass
    else:
        assumptions.add("No traffic demand was supplied; connection throughput and utilization could not be assessed.")

    # Severe metric degradation rule
    for link in operational_links:
        loss = link.packet_loss_pct if link.packet_loss_pct is not None else 0.0
        delay = link.delay_ms if link.delay_ms is not None else 1.0
        if loss > 5.0 or delay > 25.0:
            add_or_merge_finding(
                target_type="link",
                target_id=link.id,
                tier="metric_outlier",
                kind="degraded_link",
                title=f"Degraded Performance Link: {link.id}",
                severity=0.80,
                score=0.80,
                method="rule",
                evidence={"delay_ms": delay, "packet_loss_pct": loss},
                explanation=f"Connection {link.id} exhibits severe performance degradation (latency {delay:.1f} ms, loss {loss:.1f}%).",
            )

    # =========================================================================
    # TIER 2: Abnormal Metrics (Contextual IsolationForest ML)
    # =========================================================================
    ml_status = "evaluated"
    reachability_sweep_capped = False

    # Group operational links by device-type pair to check peer group context
    links_by_pair: dict[tuple[str, str], list[LinkDefinition]] = {}
    for l in operational_links:
        u_type = nodes[l.source_node_id].device_type if l.source_node_id in nodes else "unknown"
        v_type = nodes[l.target_node_id].device_type if l.target_node_id in nodes else "unknown"
        p = tuple(sorted([u_type, v_type]))
        links_by_pair.setdefault(p, []).append(l)

    max_peer_group_size = max((len(grp) for grp in links_by_pair.values()), default=0) if links_by_pair else 0

    # Minimum topology size and peer group guard for ML evaluation
    if len(operational_nodes) < 3 or len(operational_links) < 1:
        ml_status = "skipped_too_small"
        assumptions.add("Topology has fewer than 3 operational nodes or no operational connections; ML outlier scoring bypassed in favor of deterministic rules.")
    elif len(operational_links) < 6 or max_peer_group_size < 3:
        ml_status = "skipped_insufficient_peer_context"
        assumptions.add("Topology has fewer than 6 connections or lacks peer groups with at least 3 connections; contextual ML outlier scoring was bypassed in favor of deterministic rules.")
    else:
        link_model, node_model, baseline_stats = get_trained_models()
        link_data, reachability_sweep_capped = _extract_link_features(network, traffic, assumptions)
        node_data = _extract_node_features(network, assumptions)

        if reachability_sweep_capped:
            assumptions.add(f"Reachability impact sweep was capped at the top {REACHABILITY_SWEEP_CAP} connections by betweenness centrality to avoid analysis timeouts.")

        link_threshold = float(baseline_stats.get("link_threshold", 0.134))
        node_threshold = float(baseline_stats.get("node_threshold", 0.130))

        # Score links
        if link_data:
            X_links = np.array([l["features"] for l in link_data], dtype=np.float64)
            # IsolationForest decision_function: lower means more anomalous (negative = outlier)
            raw_scores = -link_model.decision_function(X_links)

            for item, score in zip(link_data, raw_scores):
                if score > link_threshold:  # Flagged by threshold from baseline distribution (99.8th percentile)
                    sev = min(0.85, max(0.5, 0.5 + float(score) * 0.7))
                    add_or_merge_finding(
                        target_type="link",
                        target_id=item["id"],
                        tier="metric_outlier",
                        kind="metric_outlier",
                        title=f"Outlier Connection: {item['id']}",
                        severity=sev,
                        score=float(score),
                        method="isolation_forest",
                        evidence={
                            "metrics": item["metrics"],
                            "anomaly_score": round(float(score), 4),
                            "decision_threshold": round(link_threshold, 4),
                            "threshold_percentile": 99.8,
                            "peer_device_pair": item["peer_pair"],
                            "baseline_medians": {
                                "utilization_pct": baseline_stats["link_feature_medians"][0],
                                "delay_ms": baseline_stats["link_feature_medians"][2],
                                "loss_pct": baseline_stats["link_feature_medians"][3],
                                "bandwidth_mbps": baseline_stats["link_feature_medians"][4],
                            },
                        },
                        explanation=f"Connection {item['id']} ({item['peer_pair']}) has contextual metrics (delay {item['metrics']['delay_ms']}ms, loss {item['metrics']['packet_loss_pct']}%, bandwidth {item['metrics']['bandwidth_mbps']}Mbps) that diverge from its peer baseline distribution.",
                    )

        # Score nodes
        if node_data:
            X_nodes = np.array([n["features"] for n in node_data], dtype=np.float64)
            raw_scores = -node_model.decision_function(X_nodes)

            for item, score in zip(node_data, raw_scores):
                if score > node_threshold:
                    sev = min(0.85, max(0.5, 0.5 + float(score) * 0.7))
                    add_or_merge_finding(
                        target_type="node",
                        target_id=item["id"],
                        tier="metric_outlier",
                        kind="metric_outlier",
                        title=f"Outlier Device: {item['name']}",
                        severity=sev,
                        score=float(score),
                        method="isolation_forest",
                        evidence={
                            "metrics": item["metrics"],
                            "anomaly_score": round(float(score), 4),
                            "decision_threshold": round(node_threshold, 4),
                            "threshold_percentile": 99.8,
                            "baseline_medians": {
                                "degree": baseline_stats["node_feature_medians"][0],
                                "incident_capacity_mbps": baseline_stats["node_feature_medians"][2],
                                "mean_incident_delay_ms": baseline_stats["node_feature_medians"][3],
                            },
                        },
                        explanation=f"Device {item['name']} ({item['device_type']}) has metric characteristics that diverge from the normal enterprise baseline.",
                    )

    # Sort findings by severity descending, then score descending
    final_findings = [
        AnomalyFinding.model_validate(f)
        for f in sorted(findings_by_id.values(), key=lambda x: (-x["severity"], -x["score"], x["id"]))
    ]

    summary = {
        "total_findings": len(final_findings),
        "rule_findings": sum(1 for f in final_findings if "rule" in f.methods),
        "ml_findings": sum(1 for f in final_findings if "isolation_forest" in f.methods),
        "merged_findings": sum(1 for f in final_findings if len(f.methods) > 1),
        "structural_weak_points": sum(1 for f in final_findings if f.tier == "structural_weak_point"),
        "metric_outliers": sum(1 for f in final_findings if f.tier == "metric_outlier"),
        "configuration_issues": sum(1 for f in final_findings if f.tier == "configuration_issue"),
        "highest_severity": max((f.severity for f in final_findings), default=0.0),
    }

    return AnomalyAnalysisResponse(
        findings=final_findings,
        summary=summary,
        ml_status=ml_status,
        reachability_sweep_capped=reachability_sweep_capped,
        assumptions=sorted(assumptions),
        provenance="modeled_analysis",
        model_metadata={
            "ml_model": "IsolationForest (n_estimators=100, random_state=42, threshold=99.8th percentile of baseline scores)",
            "normal_baseline": "Deterministic synthetic enterprise topology generator (modeled, not physical telemetry)",
            "threshold_percentile": 99.8,
            "features_link": [
                "utilization_pct",
                "offered_load_ratio",
                "delay_ms",
                "packet_loss_pct",
                "bandwidth_mbps",
                "betweenness_centrality",
                "rel_delay_in_pair",
                "rel_loss_in_pair",
                "rel_cap_in_pair",
            ],
            "features_node": [
                "degree",
                "betweenness_centrality",
                "incident_capacity_mbps",
                "mean_incident_delay_ms",
                "max_incident_loss_pct",
                "is_isolated",
            ],
        },
    )
