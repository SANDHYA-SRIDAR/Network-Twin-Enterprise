"""Controlled synthetic regression fixtures, not captured telemetry or ML training data."""
from copy import deepcopy
import unittest

from pydantic import ValidationError
from fastapi import HTTPException

from app.engines.analytical_simulator import evaluate, run_experiment, run_modernization
from app.engines.graph_adapter import graph_changes, network_graph, structural_analysis
from app.models.failure_simulation import ExperimentModernizeRequest, TrafficDemand
from app.models.network import LinkDefinition, NetworkDefinition, NodeDefinition
from app.services.anomaly_analysis import analyze_state


def fixture():
    graph = NetworkDefinition(name="Controlled chain", nodes=[
        NodeDefinition(id=i, name=i, device_type="router") for i in ("a", "b", "c")], links=[
        LinkDefinition(id="ab", source_node_id="a", target_node_id="b", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
        LinkDefinition(id="bc", source_node_id="b", target_node_id="c", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0)])
    return graph, TrafficDemand(source_node_id="a", target_node_id="c", offered_mbps=100)


class GraphAnalysisTests(unittest.TestCase):
    def test_catalogue_scenarios_keep_baseline_immutable(self):
        cases = [("link_failure", {"link_id": "ab"}), ("device_failure", {"node_id": "b"}),
                 ("segment_isolation", {"node_id": "b"}), ("traffic_increase", {"factor": 2}),
                 ("bandwidth_change", {"link_id": "ab", "bandwidth_mbps": 50}),
                 ("capacity_increase", {"link_id": "ab", "increase_mbps": 100}),
                 ("redundancy_add", {"source_node_id": "a", "target_node_id": "c", "bandwidth_mbps": 500}),
                 ("cloud_migration", {"node_id": "c"})]
        graph, demand = fixture()
        before = deepcopy(graph.model_dump())
        for kind, parameters in cases:
            with self.subTest(scenario=kind):
                result = run_experiment(graph, kind, parameters, demand)
                self.assertEqual(graph.model_dump(), before)
                self.assertEqual(result["provenance"], "simulated")
                if kind == "traffic_increase":
                    self.assertEqual(result["baseline_metrics"]["offered_traffic_mbps"], 100)
                    self.assertEqual(result["failed_metrics"]["offered_traffic_mbps"], 200)

    def test_analysis_size_limit_applies_to_stateless_evaluation(self):
        graph, demand = fixture()
        graph.nodes.extend(NodeDefinition(id=str(i), name=str(i), device_type="router") for i in range(498))
        with self.assertRaises(HTTPException) as raised:
            evaluate(graph, demand, set(), "baseline")
        self.assertEqual(raised.exception.status_code, 413)

    def test_direction_is_explicit_and_directed_input_rejected(self):
        graph, _ = fixture()
        self.assertFalse(graph.directed)
        with self.assertRaises(ValidationError):
            NetworkDefinition.model_validate({**graph.model_dump(), "directed": True})

    def test_parallel_ids_survive_and_are_not_bridges(self):
        graph, demand = fixture()
        graph.links.append(LinkDefinition(id="ab-backup", source_node_id="a", target_node_id="b", bandwidth_mbps=1000, delay_ms=5))
        before = graph.model_dump()
        self.assertEqual(set(network_graph(graph)["a"]["b"]), {"ab", "ab-backup"})
        self.assertEqual(structural_analysis(graph)["bridge_link_ids"], ["bc"])
        result = run_experiment(graph, "link_failure", {"link_id": "ab"}, demand)
        self.assertEqual(result["failed_metrics"]["route_link_ids"], ["ab-backup", "bc"])
        self.assertEqual(result["analysis"]["structure"]["bridge_link_ids"], ["ab-backup", "bc"])
        self.assertEqual(graph.model_dump(), before)

    def test_louvain_disconnected_and_edgeless_safe_repeatable(self):
        graph, _ = fixture()
        graph.nodes.append(NodeDefinition(id="isolated", name="isolated", device_type="router"))
        one = structural_analysis(graph)
        graph.nodes.reverse()
        graph.links.reverse()
        self.assertEqual(one, structural_analysis(graph))
        self.assertIn(["isolated"], one["communities"])
        self.assertEqual(set(one["membership"]), {"a", "b", "c", "isolated"})
        self.assertIsNotNone(one["modularity"])
        graph.links = []
        self.assertIsNone(structural_analysis(graph)["modularity"])
        self.assertEqual(len(structural_analysis(graph)["communities"]), 4)
        self.assertEqual(structural_analysis(NetworkDefinition(name="Empty", nodes=[]))["communities"], [])

    def test_dense_clusters_have_structural_communities_not_anomaly_claims(self):
        graph, _ = fixture()
        graph.nodes = [NodeDefinition(id=i, name=i, device_type="router") for i in "abcdef"]
        graph.links = [LinkDefinition(id=u+v, source_node_id=u, target_node_id=v) for u, v in
                       [("a", "b"), ("b", "c"), ("a", "c"), ("d", "e"), ("e", "f"), ("d", "f"), ("c", "d")]]
        result = structural_analysis(graph)
        self.assertEqual(result["communities"], [["a", "b", "c"], ["d", "e", "f"]])
        self.assertEqual(result["bridge_link_ids"], ["cd"])
        self.assertGreater(result["modularity"], 0)

    def test_bridge_failure_impact_and_diff(self):
        graph, demand = fixture()
        result = run_experiment(graph, "link_failure", {"link_id": "ab"}, demand)
        analysis = result["analysis"]
        self.assertTrue(analysis["impact"]["route_changed"])
        self.assertEqual(analysis["impact"]["affected_baseline_route_links"], ["ab"])
        self.assertEqual(analysis["impact"]["newly_unreachable_node_ids"], ["b", "c"])
        self.assertEqual(len(analysis["impact"]["unreachable_demands"]), 1)
        self.assertEqual(analysis["graph_changes"]["links"]["changed"], ["ab"])
        failed = NetworkDefinition.model_validate(result["failed_topology"])
        self.assertEqual(network_graph(failed, operational_only=False).number_of_edges(), 2)
        self.assertEqual(network_graph(failed).number_of_edges(), 1)

    def test_device_failure_unavailable_nodes_and_immutable_input(self):
        graph, demand = fixture()
        before = deepcopy(graph.model_dump())
        result = run_experiment(graph, "device_failure", {"node_id": "b"}, demand)
        self.assertFalse(result["failed_metrics"]["flow_connected"])
        self.assertEqual(result["analysis"]["structure"]["unavailable_node_ids"], ["b"])
        self.assertEqual(graph.model_dump(), before)
        self.assertEqual(graph_changes(graph, graph)["nodes"]["changed"], [])


class RuleBaselineTests(unittest.TestCase):
    def test_declared_synthetic_validation_confusion_counts(self):
        # Labels mean operational/configuration concern, NOT unexpected anomaly/future failure.
        # Three declared negatives: unchanged, sub-threshold delay, added spare link.
        # Three declared positives: bridge failure, saturation, >=50% delay increase.
        graph, demand = fixture()
        before = evaluate(graph, demand, set(), "baseline")["metrics"]
        cases = []
        for label, kind in [(False, "unchanged"), (False, "small_delay"), (False, "spare"),
                            (True, "failure"), (True, "saturation"), (True, "large_delay")]:
            changed = deepcopy(graph)
            if kind == "small_delay":
                changed.links[0].delay_ms = 1.1
            elif kind == "spare":
                changed.links.append(LinkDefinition(id="spare", source_node_id="a", target_node_id="c", bandwidth_mbps=1000, delay_ms=10))
            elif kind == "failure":
                changed.links[0].status = "failed"
            elif kind == "saturation":
                changed.links[0].bandwidth_mbps = demand.offered_mbps
            elif kind == "large_delay":
                changed.links[0].delay_ms = 10
            metrics = evaluate(changed, demand, set(), "scenario")["metrics"]
            analysis = analyze_state(graph, changed, before, metrics)
            cases.append((label, analysis["flagged"]))
            self.assertFalse(analysis["trained_model"])
            self.assertEqual(analysis["training_data"], "none")
            self.assertGreaterEqual(analysis["score"], 0)
            self.assertLessEqual(analysis["score"], 1)
        self.assertEqual({"tp": sum(a and b for a, b in cases), "tn": sum(not a and not b for a, b in cases),
                          "fp": sum(not a and b for a, b in cases), "fn": sum(a and not b for a, b in cases)},
                         {"tp": 3, "tn": 3, "fp": 0, "fn": 0})

    def test_off_route_failure_flags_fault_but_does_not_claim_service_impact(self):
        graph, demand = fixture()
        graph.links.append(LinkDefinition(id="off-route", source_node_id="a", target_node_id="c", delay_ms=10))
        result = run_experiment(graph, "link_failure", {"link_id": "off-route"}, demand)
        self.assertTrue(result["analysis"]["flagged"])
        self.assertFalse(result["analysis"]["impact"]["route_changed"])
        self.assertEqual(result["analysis"]["impact"]["affected_baseline_route_links"], [])
        self.assertEqual(result["baseline_metrics"]["throughput_mbps"], result["failed_metrics"]["throughput_mbps"])

    def test_unconfigured_loss_and_undefined_latency_not_invented(self):
        graph, demand = fixture()
        graph.links[0].packet_loss_pct = None
        before = evaluate(graph, demand, set(), "baseline")["metrics"]
        changed = deepcopy(graph)
        changed.links[0].bandwidth_mbps = 50
        after = evaluate(changed, demand, set(), "failure")["metrics"]
        analysis = analyze_state(graph, changed, before, after)
        self.assertIsNone(analysis["features"]["configured_loss_deviation_pct"])
        self.assertIsNone(analysis["features"]["relative_latency_deviation"])
        self.assertEqual(analysis["features"]["max_offered_capacity_ratio"], 2)

    def test_risk_does_not_filter_only_available_option(self):
        graph, demand = fixture()
        result = run_experiment(graph, "link_failure", {"link_id": "ab"}, demand)
        failed = NetworkDefinition.model_validate(result["failed_topology"])
        proposal = run_modernization(graph, failed, "link_failure", {"link_id": "ab"}, demand,
                                     result["failed_metrics"], [], ExperimentModernizeRequest(max_change_units=0, allow_repair=False, allow_new_links=False))["modernization"]
        retain = next(c for c in proposal["candidates"] if c["id"] == "retain")
        self.assertTrue(retain["risk_analysis"]["flagged"])
        self.assertTrue(retain["feasible"])
        self.assertEqual(proposal["selected_strategy_id"], "retain")
        self.assertFalse(proposal["resolved"])


if __name__ == "__main__":
    unittest.main()
