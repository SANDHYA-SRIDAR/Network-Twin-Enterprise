import unittest

from app.engines.analytical_simulator import run_experiment, run_modernization
from app.models.failure_simulation import TrafficDemand, ExperimentModernizeRequest
from app.models.network import LinkDefinition, NetworkDefinition, NodeDefinition


class LinkFailureRefinementsTests(unittest.TestCase):
    def setUp(self):
        # Topology matching the experiment:
        # PC2 -> 2960-24TT Switch -> Server-PT (1000 Mbps links)
        # Switch also connects to off-route Smart Load Balancer (1000 Mbps)
        self.network = NetworkDefinition(
            name="Incident Topology",
            nodes=[
                NodeDefinition(id="pc2", name="PC2", device_type="pc", metadata={"position": {"x": 0, "y": 0}, "model": "pc-pt"}),
                NodeDefinition(id="switch", name="2960-24TT Switch", device_type="switch", metadata={"position": {"x": 100, "y": 0}, "model": "2960-24tt-switch"}),
                NodeDefinition(id="server", name="Server-PT", device_type="server", metadata={"position": {"x": 200, "y": 0}, "model": "server-pt"}),
                NodeDefinition(id="lb", name="Smart Load Balancer", device_type="load_balancer", metadata={"position": {"x": 100, "y": 100}, "model": "smart-load-balancer"}),
            ],
            links=[
                LinkDefinition(id="pc2-switch", source_node_id="pc2", target_node_id="switch", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
                LinkDefinition(id="switch-server", source_node_id="switch", target_node_id="server", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
                LinkDefinition(id="switch-lb", source_node_id="switch", target_node_id="lb", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0),
            ],
        )

    def test_failed_link_outside_traffic_route(self):
        """1. A failed link outside the traffic route does not disrupt the flow."""
        traffic = TrafficDemand(source_node_id="pc2", target_node_id="server", offered_mbps=500, duration_seconds=60)
        # Fail switch-lb (outside pc2 -> switch -> server route)
        result = run_experiment(self.network, "link_failure", {"link_id": "switch-lb"}, traffic)

        impact = result["flow_impact"]
        self.assertFalse(impact["is_on_route"])
        self.assertEqual(impact["status_code"], "off_route")
        self.assertTrue(impact["route_survived"])
        self.assertFalse(impact["route_changed"])
        self.assertIn("OUTSIDE the active source-to-destination route", impact["explanation"])
        self.assertIn("does not directly affect", impact["explanation"])

        # Baseline and failed metrics should both have active route intact
        self.assertTrue(result["baseline_metrics"]["flow_connected"])
        self.assertTrue(result["failed_metrics"]["flow_connected"])
        self.assertEqual(result["failed_metrics"]["route_link_ids"], ["pc2-switch", "switch-server"])
        self.assertEqual(result["failed_metrics"]["packet_loss_pct"], 0.0)

    def test_failed_link_on_traffic_route_no_alternative(self):
        """2. A failed link on the traffic route with no alternative path results in complete disconnection."""
        traffic = TrafficDemand(source_node_id="pc2", target_node_id="server", offered_mbps=500, duration_seconds=60)
        # Fail pc2-switch (on route, single path exists)
        result = run_experiment(self.network, "link_failure", {"link_id": "pc2-switch"}, traffic)

        impact = result["flow_impact"]
        self.assertTrue(impact["is_on_route"])
        self.assertEqual(impact["status_code"], "disconnected")
        self.assertFalse(impact["route_survived"])
        self.assertFalse(result["failed_metrics"]["flow_connected"])
        self.assertEqual(result["failed_metrics"]["packet_loss_pct"], 100.0)
        self.assertEqual(result["failed_metrics"]["queueing_status"], "unreachable")
        self.assertIn("NO alternative path exists", impact["explanation"])

    def test_failed_link_on_traffic_route_with_alternative(self):
        """3. A failed link on the traffic route with an alternative path recalculates routing."""
        # Add an alternate link bypassing switch
        network_with_alt = NetworkDefinition(
            name="Topology with Alt Link",
            nodes=self.network.nodes,
            links=self.network.links + [
                LinkDefinition(id="pc2-server-backup", source_node_id="pc2", target_node_id="server", bandwidth_mbps=800, delay_ms=5, packet_loss_pct=0)
            ],
        )
        traffic = TrafficDemand(source_node_id="pc2", target_node_id="server", offered_mbps=500, duration_seconds=60)
        # Fail primary link pc2-switch
        result = run_experiment(network_with_alt, "link_failure", {"link_id": "pc2-switch"}, traffic)

        impact = result["flow_impact"]
        self.assertTrue(impact["is_on_route"])
        self.assertEqual(impact["status_code"], "rerouted")
        self.assertTrue(impact["route_survived"])
        self.assertTrue(impact["route_changed"])
        self.assertTrue(result["failed_metrics"]["flow_connected"])
        self.assertEqual(result["failed_metrics"]["route_link_ids"], ["pc2-server-backup"])
        self.assertIn("Traffic was rerouted to an alternate path", impact["explanation"])

    def test_traffic_exceeding_bottleneck_capacity(self):
        """4. Traffic exceeding bottleneck capacity triggers congestion loss and unstable queue, not unreachability."""
        # Offered traffic is 1500 Mbps, exceeding 1000 Mbps capacity
        traffic = TrafficDemand(source_node_id="pc2", target_node_id="server", offered_mbps=1500.01, duration_seconds=60)
        # Fail off-route link switch-lb
        result = run_experiment(self.network, "link_failure", {"link_id": "switch-lb"}, traffic)

        baseline = result["baseline_metrics"]
        failed = result["failed_metrics"]

        # Reachability is intact (not unreachable!)
        self.assertTrue(baseline["flow_connected"])
        self.assertTrue(failed["flow_connected"])

        # Unstable queueing because rho >= 1
        self.assertEqual(baseline["queueing_status"], "unstable")
        self.assertEqual(failed["queueing_status"], "unstable")
        self.assertIsNone(baseline["average_latency_ms"])
        self.assertIsNone(failed["average_latency_ms"])

        # Congestion loss is separated from link failure
        self.assertGreater(failed["congestion_loss_pct"], 30.0)
        self.assertAlmostEqual(failed["packet_loss_pct"], 33.33, delta=0.1)
        self.assertEqual(failed["link_medium_loss_pct"], 0.0)
        self.assertEqual(failed["throughput_mbps"], 1000.0)

        # Impact explanation clearly explains the distinction
        impact = result["flow_impact"]
        self.assertIn("exceeding the path bottleneck capacity", impact["explanation"])
        self.assertIn("NOT by the link failure", impact["explanation"])

    def test_candidate_bypass_restores_sufficient_capacity(self):
        """5. Candidate bypass verifies sufficient capacity before reporting 0% congestion loss."""
        traffic = TrafficDemand(source_node_id="pc2", target_node_id="server", offered_mbps=1500.01, duration_seconds=60)
        result = run_experiment(self.network, "link_failure", {"link_id": "switch-lb"}, traffic)
        failed_topo = NetworkDefinition.model_validate(result["failed_topology"])

        criteria = ExperimentModernizeRequest(allow_new_links=True)
        modernized = run_modernization(
            self.network, failed_topo, "link_failure", {"link_id": "switch-lb"}, traffic,
            result["failed_metrics"], result["assumptions"], criteria
        )

        candidates = modernized["modernization"]["candidates"]
        bypass_cand = next(c for c in candidates if c["id"] == "bypass")

        # Bypass connection was added with 1.25x headroom = ~1875 Mbps
        bypass_links = [l for l in bypass_cand["topology"]["links"] if l["id"] == "candidate:dedicated-service-path"]
        self.assertEqual(len(bypass_links), 1)
        self.assertGreaterEqual(bypass_links[0]["bandwidth_mbps"], 1500.01)

        # Verified sufficient capacity -> 0% congestion loss, full throughput
        self.assertEqual(bypass_cand["metrics"]["congestion_loss_pct"], 0.0)
        self.assertEqual(bypass_cand["metrics"]["packet_loss_pct"], 0.0)
        self.assertAlmostEqual(bypass_cand["metrics"]["throughput_mbps"], 1500.01, places=1)
        self.assertTrue(any("verified sufficient" in trade for trade in bypass_cand["trade_offs"]))

        # Saved topology remains unchanged
        self.assertEqual(len(self.network.links), 3)


if __name__ == "__main__":
    unittest.main()

