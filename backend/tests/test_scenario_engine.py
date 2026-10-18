import unittest

from app.models.network import IPConfiguration, InterfaceDefinition, LinkDefinition, NetworkDefinition, NodeDefinition
from app.services.scenario_engine import ScenarioEngine


class ScenarioEngineTests(unittest.TestCase):
    def setUp(self):
        self.network = NetworkDefinition(
            name="Baseline",
            nodes=[
                NodeDefinition(
                    id="r1",
                    name="Router",
                    device_type="router",
                    interfaces=[InterfaceDefinition(id="eth0", name="eth0", ip_configuration=IPConfiguration(ip_address="10.0.0.1", subnet_mask="255.255.255.0", gateway="10.0.0.254"))],
                ),
                NodeDefinition(
                    id="pc1",
                    name="PC",
                    device_type="pc",
                    interfaces=[InterfaceDefinition(id="eth0", name="eth0", ip_configuration=IPConfiguration(ip_address="10.0.0.2", subnet_mask="255.255.255.0", gateway="10.0.0.254"))],
                ),
            ],
            links=[
                LinkDefinition(id="l1", source_node_id="r1", target_node_id="pc1", cable_type="straight-through", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
            ],
        )

    def test_link_failure_scenario_keeps_baseline_and_reports_risk(self):
        result = ScenarioEngine.run_scenario(self.network, {"type": "link_failure", "link_id": "l1"}, {"source_node_id": "r1", "target_node_id": "pc1", "offered_mbps": 10})
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["summary"]["flow_connected"])
        self.assertIsNone(result["summary"]["service_redundancy"])
        self.assertEqual(result["baseline"]["names"][0], "Baseline")


if __name__ == "__main__":
    unittest.main()
