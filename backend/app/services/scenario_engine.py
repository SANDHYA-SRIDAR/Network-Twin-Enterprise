from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.models.network import LinkDefinition, NetworkDefinition


class ScenarioEngine:
    @staticmethod
    def run_scenario(baseline: NetworkDefinition, scenario_config: Dict[str, Any]) -> Dict[str, Any]:
        scenario_type = scenario_config.get("type", "traffic_increase")
        scenario = deepcopy(baseline)
        evidence: List[str] = []

        if scenario_type == "link_failure":
            target = scenario_config.get("link_id") or scenario_config.get("target") or scenario_config.get("node_id")
            filtered_links = [
                link for link in scenario.links
                if target is None or link.id == target or link.source_node_id == target or link.target_node_id == target
            ]
            for link in filtered_links:
                link.status = "down"
                link.delay_ms = max(link.delay_ms or 0, 200)
                link.packet_loss_pct = min((link.packet_loss_pct or 0) + 12, 100)
            if not filtered_links and target is None and scenario.links:
                filtered_links = [scenario.links[0]]
                filtered_links[0].status = "down"
            evidence.append(f"{scenario_type}: degraded path for {target or 'selected link'}" if filtered_links else f"{scenario_type}: no matching link found for {target}")

        elif scenario_type == "device_failure":
            node_id = scenario_config.get("node_id") or scenario_config.get("target")
            for node in scenario.nodes:
                if node.id == node_id:
                    node.status = "down"
                    evidence.append(f"device {node_id} marked offline")
            scenario.links = [
                link for link in scenario.links
                if link.source_node_id != node_id and link.target_node_id != node_id
            ]

        elif scenario_type == "traffic_increase":
            for link in scenario.links:
                current_load = float(link.metadata.get("current_load_mbps", 100))
                link.metadata["current_load_mbps"] = current_load * 1.5
            evidence.append("traffic profile increased across all active links")

        elif scenario_type == "bandwidth_change":
            scale = float(scenario_config.get("value") or 0.75)
            for link in scenario.links:
                link.bandwidth_mbps = max((link.bandwidth_mbps or 0) * scale, 10)
            evidence.append(f"bandwidth scaled by {scale:.2f}x")

        elif scenario_type == "redundancy_add":
            if scenario.links:
                first_link = scenario.links[0]
                duplicate = LinkDefinition(
                    id=f"rebund-{uuid.uuid4().hex[:8]}",
                    source_node_id=first_link.source_node_id,
                    target_node_id=first_link.target_node_id,
                    cable_type=first_link.cable_type,
                    bandwidth_mbps=max((first_link.bandwidth_mbps or 0) * 1.25, 50),
                    delay_ms=max((first_link.delay_ms or 0) // 2, 1),
                    packet_loss_pct=max((first_link.packet_loss_pct or 0) // 2, 0),
                )
                scenario.links.append(duplicate)
            evidence.append("redundant path introduced for failover resilience")

        elif scenario_type == "segment_isolation":
            node_id = scenario_config.get("node_id") or scenario_config.get("target")
            if node_id:
                scenario.links = [
                    link for link in scenario.links
                    if link.source_node_id != node_id and link.target_node_id != node_id
                ]
            evidence.append(f"segment isolation applied around {node_id or 'selected segment'}")

        elif scenario_type == "capacity_increase":
            for link in scenario.links:
                link.bandwidth_mbps = max((link.bandwidth_mbps or 0) + 250, 50)
            evidence.append("capacity uplift applied across network backbone")

        elif scenario_type == "cloud_migration":
            for node in scenario.nodes:
                if node.device_type == "router":
                    node.status = "optimized"
            evidence.append("cloud migration scenario modeled with centralized routing impact")

        baseline_summary = ScenarioEngine._summarize_network(baseline)
        scenario_summary = ScenarioEngine._summarize_network(scenario)

        risk_score = max(0.0, scenario_summary["risk_score"] - baseline_summary["risk_score"])
        redundancy = min(1.0, scenario_summary["service_redundancy"])

        return {
            "id": str(uuid.uuid4()),
            "status": "completed",
            "baseline_name": baseline.name,
            "scenario_type": scenario_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "loss_probability": round(max(0.0, scenario_summary["loss_probability"]), 3),
                "risk_score": round(risk_score, 3),
                "service_redundancy": round(redundancy, 3),
                "decision": ScenarioEngine._decision_for(risk_score, redundancy),
                "throughput_mbps": round(scenario_summary["throughput_mbps"], 2),
                "latency_ms": round(scenario_summary["latency_ms"], 2),
            },
            "baseline": {
                "name": baseline.name,
                "names": [baseline.name],
                "nodes": len(baseline.nodes),
                "links": len(baseline.links),
                "throughput_mbps": round(baseline_summary["throughput_mbps"], 2),
                "latency_ms": round(baseline_summary["latency_ms"], 2),
                "risk_score": round(baseline_summary["risk_score"], 3),
            },
            "scenario": {
                "name": f"{baseline.name} - {scenario_type}",
                "nodes": len(scenario.nodes),
                "links": len(scenario.links),
                "throughput_mbps": round(scenario_summary["throughput_mbps"], 2),
                "latency_ms": round(scenario_summary["latency_ms"], 2),
                "risk_score": round(scenario_summary["risk_score"], 3),
                "status": "active",
            },
            "evidence": evidence,
            "provenance": "simulated",
        }

    @staticmethod
    def _summarize_network(network: NetworkDefinition) -> Dict[str, Any]:
        link_count = len(network.links)
        node_count = len(network.nodes)
        active_links = [link for link in network.links if getattr(link, "status", "active") not in {"down", "offline", "failed"}]
        link_metrics = []
        for link in active_links:
            capacity = max(float(link.bandwidth_mbps or 0), 0.001)
            load = max(0.0, float(link.metadata.get("current_load_mbps", 100)))
            utilization_pct = load / capacity * 100
            safe_utilization = min(max(utilization_pct, 0), 99.9)
            queue_delay = (safe_utilization / (100 - safe_utilization)) * 10 if safe_utilization > 70 else 0
            overload_loss = min(100.0, (utilization_pct - 100) * 0.5) if utilization_pct > 100 else 0.0
            link_metrics.append({
                "throughput": min(load, capacity),
                "latency": float(link.delay_ms or 0) + queue_delay,
                "loss": max(float(link.packet_loss_pct or 0), overload_loss),
            })
        throughput = sum(metric["throughput"] for metric in link_metrics)
        latency = sum(metric["latency"] for metric in link_metrics) / max(1, len(link_metrics))
        loss_probability = min(1.0, sum(metric["loss"] for metric in link_metrics) / max(1, len(link_metrics)) / 100)
        down_nodes = sum(1 for node in network.nodes if getattr(node, "status", "active") in {"down", "offline", "failed"})
        unhealthy_links = sum(1 for link in network.links if getattr(link, "status", "active") in {"down", "offline", "failed"})
        risk_score = min(1.0, (down_nodes * 0.35) + (unhealthy_links * 0.2) + (loss_probability * 0.55))
        redundancy = 1.0 - (1.0 / max(1.0, link_count + node_count / 2.0))
        return {
            "throughput_mbps": throughput,
            "latency_ms": latency,
            "loss_probability": loss_probability,
            "risk_score": risk_score,
            "service_redundancy": redundancy,
        }

    @staticmethod
    def _decision_for(risk_score: float, redundancy: float) -> str:
        if risk_score > 0.6:
            return "Escalate with circuit failover and inspection"
        if redundancy > 0.55:
            return "Proceed with controlled rollout"
        return "Monitor and validate before production change"
