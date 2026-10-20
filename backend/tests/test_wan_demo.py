import unittest
from copy import deepcopy
from fastapi.testclient import TestClient
from app.main import app
from app.services.wan_demo import demo_topology, run_wan_demo, transformed_graph
from app.engines.analytical_simulator import evaluate
from app.models.network import NetworkDefinition
from app.models.failure_simulation import TrafficDemand


class WanDemoTests(unittest.TestCase):
    def test_transformation_and_same_outage_metrics(self):
        baseline = demo_topology()
        original = baseline.model_dump()
        result = run_wan_demo(baseline)
        self.assertEqual(baseline.model_dump(), original)
        self.assertEqual(result["modernization"]["selected_strategy_id"], "sdwan")
        self.assertEqual(result["failed_metrics"]["throughput_mbps"], 0)
        candidate = NetworkDefinition.model_validate(result["modernized_topology"])
        edge = next(n for n in candidate.nodes if n.role == "sd_wan_edge")
        uplinks = [e for e in candidate.links if e.source_node_id == edge.id]
        self.assertEqual(len(uplinks), 2)
        self.assertEqual(len({e.metadata["failure_domain"] for e in uplinks}), 2)
        self.assertIn(next(e for e in candidate.links if e.id == "wan-primary").status, ("down", "failed"))
        metrics = evaluate(candidate, TrafficDemand(source_node_id="branch", target_node_id="service", offered_mbps=100), set(), "modernized")["metrics"]
        self.assertEqual(metrics, result["modernized_metrics"])
        self.assertEqual(metrics["throughput_mbps"], 100)
        self.assertGreater(metrics["average_latency_ms"], result["baseline_metrics"]["average_latency_ms"])
        self.assertTrue(any("uplink-b" in e for e in metrics["route_link_ids"]))
        healthy = deepcopy(candidate)
        next(e for e in healthy.links if e.id.endswith("uplink-a")).status = "active"
        healthy_route = evaluate(healthy, TrafficDemand(source_node_id="branch", target_node_id="service", offered_mbps=100), set(), "modernized")["metrics"]["route_link_ids"]
        self.assertTrue(any("uplink-a" in e for e in healthy_route))
        self.assertNotEqual(healthy_route, metrics["route_link_ids"])
        # Removing the only surviving uplink must disconnect the demand.
        next(e for e in candidate.links if e.id.endswith("uplink-b")).status = "failed"
        self.assertFalse(evaluate(candidate, TrafficDemand(source_node_id="branch", target_node_id="service", offered_mbps=100), set(), "modernized")["metrics"]["flow_connected"])

    def test_repair_sufficient_without_continuity_requirement(self):
        result = run_wan_demo(require_continuity=False)
        self.assertEqual(result["modernization"]["selected_strategy_id"], "repair")
        repair = next(c for c in result["modernization"]["candidates"] if c["id"] == "repair")
        self.assertTrue(repair["meets_service_target"])
        self.assertFalse(repair["survives_primary_wan_outage"])
        self.assertEqual(repair["wan_outage_metrics"]["throughput_mbps"], 0)

    def test_no_feasible_service_target(self):
        result = run_wan_demo(offered_mbps=500)
        self.assertFalse(result["requirement_met"])
        self.assertFalse(result["modernization"]["resolved"])

    def test_missing_wan_metadata_uses_labeled_example(self):
        saved = demo_topology()
        saved.nodes[0].role = "endpoint"
        original = deepcopy(saved.model_dump())
        result = run_wan_demo(saved)
        self.assertIn("demonstration", result["topology_source"])
        self.assertEqual(saved.model_dump(), original)
        self.assertFalse(result["persisted"])

    def test_endpoint(self):
        response = TestClient(app).post("/api/analysis/wan-demo", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provenance"], "simulated")
        self.assertEqual(TestClient(app).post("/api/analysis/wan-demo", json={"offered_mbps": 0}).status_code, 422)
