import unittest

from fastapi import HTTPException

from app.engines.analytical_simulator import apply_scenario, evaluate, run_experiment, run_modernization
from app.models.failure_simulation import TrafficDemand
from app.models.network import LinkDefinition, NetworkDefinition, NodeDefinition


class AnalyticalSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.network = NetworkDefinition(
            name="Test topology",
            nodes=[
                NodeDefinition(id="pc", name="Client", device_type="pc", metadata={"position": {"x": 0, "y": 0}, "model": "pc-pt"}),
                NodeDefinition(id="r1", name="Router A", device_type="router", metadata={"position": {"x": 100, "y": 0}, "model": "1941-router"}),
                NodeDefinition(id="r2", name="Router B", device_type="router", metadata={"position": {"x": 200, "y": 0}, "model": "1941-router"}),
                NodeDefinition(id="server", name="Server", device_type="server", metadata={"position": {"x": 300, "y": 0}, "model": "server-pt"}),
            ],
            links=[
                LinkDefinition(id="pc-r1", source_node_id="pc", target_node_id="r1", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
                LinkDefinition(id="primary", source_node_id="r1", target_node_id="r2", bandwidth_mbps=50, delay_ms=2, packet_loss_pct=0),
                LinkDefinition(id="r2-server", source_node_id="r2", target_node_id="server", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
                LinkDefinition(id="alternate", source_node_id="r1", target_node_id="server", bandwidth_mbps=20, delay_ms=8, packet_loss_pct=0),
            ],
        )
        self.traffic = TrafficDemand(source_node_id="pc", target_node_id="server", offered_mbps=10, duration_seconds=10)

    def test_link_failure_reroutes_and_does_not_change_baseline(self):
        result = run_experiment(self.network, "link_failure", {"link_id": "primary"}, self.traffic)
        self.assertEqual(result["failed_metrics"]["route_link_ids"], ["pc-r1", "alternate"])
        self.assertEqual(self.network.links[1].status, "active")
        self.assertTrue(result["baseline_metrics"]["flow_connected"])

    def test_link_failure_without_alternate_drops_flow_then_adds_candidate(self):
        simple = self.network.model_copy(deep=True)
        simple.links = simple.links[:3]
        result = run_experiment(simple, "link_failure", {"link_id": "primary"}, self.traffic)
        self.assertFalse(result["failed_metrics"]["flow_connected"])
        failed = NetworkDefinition.model_validate(result["failed_topology"])
        modernized = run_modernization(simple, failed, "link_failure", {"link_id": "primary"}, self.traffic, result["failed_metrics"], result["assumptions"])
        candidate = NetworkDefinition.model_validate(modernized["modernized_topology"])
        self.assertTrue(modernized["modernization"]["resolved"])
        self.assertTrue(any(link.metadata.get("candidate") for link in candidate.links))
        self.assertTrue(modernized["modernized_metrics"]["flow_connected"])

    def test_device_failure_uses_candidate_replacement_not_failed_node(self):
        result = run_experiment(self.network, "device_failure", {"node_id": "r1"}, self.traffic)
        failed = NetworkDefinition.model_validate(result["failed_topology"])
        modernized = run_modernization(self.network, failed, "device_failure", {"node_id": "r1"}, self.traffic, result["failed_metrics"], result["assumptions"])
        candidate = NetworkDefinition.model_validate(modernized["modernized_topology"])
        self.assertEqual(next(node for node in candidate.nodes if node.id == "r1").status, "down")
        replacement = next(node for node in candidate.nodes if node.id.startswith("candidate:"))
        self.assertEqual(replacement.status, "active")
        self.assertTrue(modernized["modernized_metrics"]["flow_connected"])

    def test_traffic_surge_calculates_congestion_and_capacity_candidate(self):
        result = run_experiment(self.network, "traffic_increase", {"factor": 10}, self.traffic)
        self.assertEqual(result["failed_metrics"]["offered_traffic_mbps"], 100)
        self.assertGreater(result["failed_metrics"]["congested_links"], 0)
        failed = NetworkDefinition.model_validate(result["failed_topology"])
        modernized = run_modernization(self.network, failed, "traffic_increase", {"factor": 10}, TrafficDemand.model_validate(result["traffic"]), result["failed_metrics"], result["assumptions"])
        self.assertGreaterEqual(modernized["modernized_metrics"]["throughput_mbps"], result["failed_metrics"]["throughput_mbps"])

    def test_bandwidth_change_uses_selected_link_and_modernization(self):
        result = run_experiment(self.network, "bandwidth_change", {"link_id": "primary", "bandwidth_mbps": 5}, self.traffic)
        changed_link = next(link for link in result["failed_metrics"]["links"] if link["id"] == "primary")
        self.assertEqual(changed_link["configured_capacity_mbps"], 5)
        self.assertEqual(next(link for link in self.network.links if link.id == "primary").bandwidth_mbps, 50)

    def test_redundancy_is_candidate_and_capacity_is_used(self):
        changed, _, assumptions = apply_scenario(self.network, "redundancy_add", {"source_node_id": "pc", "target_node_id": "server", "bandwidth_mbps": 40})
        candidate = next(link for link in changed.links if link.metadata.get("candidate"))
        self.assertEqual(candidate.bandwidth_mbps, 40)
        self.assertTrue(any(link.id.startswith("candidate:") for link in changed.links))
        self.assertEqual(assumptions, [])

    def test_unconfigured_link_values_are_flagged_and_use_documented_defaults(self):
        network = self.network.model_copy(deep=True)
        network.links[0].bandwidth_mbps = None
        network.links[0].delay_ms = None
        network.links[0].packet_loss_pct = None
        assumptions: set[str] = set()
        metrics = evaluate(network, self.traffic, assumptions, "baseline")["metrics"]
        self.assertTrue(any("capacity missing" in item for item in assumptions))
        self.assertTrue(any("latency missing" in item for item in assumptions))
        self.assertTrue(any("packet loss is unconfigured" in item for item in assumptions))
        self.assertTrue(metrics["flow_connected"])

    def test_invalid_target_is_rejected(self):
        with self.assertRaises(HTTPException):
            apply_scenario(self.network, "link_failure", {"link_id": "not-a-link"})

    def test_scenario_source_and_destination_must_be_distinct(self):
        with self.assertRaises(ValueError):
            TrafficDemand(source_node_id="pc", target_node_id="pc", offered_mbps=10)


if __name__ == "__main__":
    unittest.main()
