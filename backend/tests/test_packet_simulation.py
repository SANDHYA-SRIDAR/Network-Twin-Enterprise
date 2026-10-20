import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.models.network import NetworkDefinition, NodeDefinition, LinkDefinition
from app.models.packet_simulation import ApplicationFlow
from app.engines.packet_simulator import simulate_packets, flow_route
from app.services.traffic_experiment import sample_experiment, run_traffic_experiment, traffic_insights


def chain(capacity=10, loss=0):
    return NetworkDefinition(name="Synthetic two-node link", nodes=[NodeDefinition(id=n, name=n, device_type="router") for n in ("a", "b")],
                             links=[LinkDefinition(id="ab", source_node_id="a", target_node_id="b", bandwidth_mbps=capacity, delay_ms=1, packet_loss_pct=loss)])


def flow(id="f", rate=1, priority=1):
    return ApplicationFlow(id=id, source_node_id="a", target_node_id="b", offered_mbps=rate, priority=priority)


class PacketSimulationTests(unittest.TestCase):
    def test_samples_and_networkx_route(self):
        for name in ("home", "office", "multi_branch"):
            request = sample_experiment(name)
            nodes, links = flow_route(request.topology, request.flows[0], set())
            self.assertTrue(nodes)
            self.assertEqual(links, ["ab", "bd"])

    def test_no_loss_delay_and_conservation(self):
        result = simulate_packets(chain(), [flow()])
        self.assertEqual(result["dropped"], 0)
        self.assertAlmostEqual(result["average_latency_ms"], 2.2, places=7)
        self.assertEqual(result["sent"], result["delivered"] + result["dropped"] + result["pending"])
        self.assertLessEqual(result["throughput_mbps"], 1)

    def test_shared_capacity_queue_loss_and_priority(self):
        graph = chain(2)
        flows = [flow("voice", 1, 0), flow("files", 6, 3)]
        fifo = simulate_packets(graph, flows, queue_packets=50)
        priority = simulate_packets(graph, flows, queue_packets=50, prioritize=True)
        self.assertLessEqual(priority["throughput_mbps"], 2)
        self.assertGreater(priority["dropped"], 0)
        self.assertLess(priority["flows"][0]["average_latency_ms"], fifo["flows"][0]["average_latency_ms"])
        self.assertLessEqual(priority["links"][0]["utilization_pct"], 100)

    def test_configured_loss_seed_and_pending(self):
        a = simulate_packets(chain(loss=30), [flow(rate=4)], seed=3)
        b = simulate_packets(chain(loss=30), [flow(rate=4)], seed=3)
        self.assertEqual(a, b)
        self.assertGreater(a["dropped"], 0)
        self.assertEqual(a["sent"], a["delivered"] + a["dropped"] + a["pending"])
        graph = chain()
        graph.links[0].delay_ms = 2000
        delayed = simulate_packets(graph, [flow()])
        self.assertEqual(delayed["dropped"], 0)
        self.assertGreater(delayed["pending"], 0)
        self.assertIsNone(delayed["average_latency_ms"])

    def test_failure_rerouting_recommendation_and_immutable_inputs(self):
        request = sample_experiment("office")
        original = deepcopy(request.model_dump())
        result = run_traffic_experiment(request)
        self.assertEqual(request.model_dump(), original)
        self.assertTrue(result["rerouted_flows"])
        self.assertEqual(result["failed_metrics"]["flows"][0]["route_link_ids"], ["ac", "cd"])
        selected = next(c for c in result["candidates"] if c["id"] == result["selected_id"])
        self.assertEqual(selected["metrics"], simulate_packets(NetworkDefinition.model_validate(selected["topology"]), request.flows))
        self.assertFalse(result["insights"]["trained_model"])
        self.assertTrue(result["recovery_targets_met"])
        self.assertTrue(selected["targets_met"])
        self.assertGreater(selected["metrics"]["throughput_mbps"], result["failed_metrics"]["throughput_mbps"])

    def test_disconnected_and_node_failure(self):
        request = sample_experiment("home")
        result = run_traffic_experiment(request)
        self.assertEqual(result["failed_metrics"]["throughput_mbps"], 0)
        self.assertEqual(result["insights"]["level"], "critical")
        request.scenario_type = "device_failure"
        request.parameters = {"node_id": "b"}
        self.assertEqual(run_traffic_experiment(request)["failed_metrics"]["connectivity_pct"], 0)

    def test_budget_rejects_without_silent_sampling(self):
        with self.assertRaises(HTTPException) as error:
            simulate_packets(chain(), [flow(rate=1000000)])
        self.assertEqual(error.exception.status_code, 422)

    def test_risk_rules_and_peak_traffic(self):
        low = simulate_packets(chain(), [flow()])
        self.assertEqual(traffic_insights(low)["level"], "low")
        peaked = flow(rate=2).model_copy(update={"peak_multiplier": 3})
        metrics = simulate_packets(chain(2), [peaked])
        self.assertGreater(metrics["links"][0]["queue_drops"], 0)
        self.assertGreaterEqual(traffic_insights(metrics)["score"], 60)

    def test_nsga_catalog_repeatability(self):
        request = sample_experiment("office")
        request.optimize = True
        first, second = run_traffic_experiment(request), run_traffic_experiment(request)
        self.assertEqual(first["optimization"], second["optimization"])
        self.assertEqual(first["optimization"]["status"], "completed")
        self.assertTrue(first["optimization"]["pareto_candidate_ids"])

    def test_api_and_auth(self):
        client = TestClient(app)
        response = client.get("/api/analysis/traffic-samples/office")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post("/api/analysis/traffic-experiment", json=response.json()).status_code, 200)
        self.assertEqual(client.post("/api/analysis/traffic-experiment/explain", json=response.json()).status_code, 401)
        self.assertEqual(client.get("/api/analysis/traffic-samples/missing").status_code, 404)

    def test_service_chain_actions_are_explicit_and_recomputed(self):
        for action in ("cloud_security", "load_balancer", "sd_wan"):
            request = sample_experiment("wan" if action == "sd_wan" else "office")
            request.scenario_type = action
            request.parameters = {"node_id": "d"} if action == "load_balancer" else {"link_id": "bd"}
            original = request.topology.model_dump()
            result = run_traffic_experiment(request)
            self.assertEqual(request.topology.model_dump(), original)
            self.assertGreater(len(result["failed_topology"]["nodes"]), len(original["nodes"]))
            self.assertGreater(result["scenario_change_units"], 0)
            self.assertEqual(result["failed_metrics"], result["candidates"][0]["metrics"])
        request = sample_experiment("home")
        request.scenario_type = "sd_wan"
        with self.assertRaises(HTTPException):
            run_traffic_experiment(request)

    def test_assistant_uses_recomputed_event_evidence(self):
        request = sample_experiment("home").model_dump(mode="json")
        with patch("app.services.supabase_repository.repository.user_id", new=AsyncMock(return_value="test-user")), patch("app.services.assistant.explain_experiment", new=AsyncMock(return_value={"mode": "deterministic"})) as explain:
            response = TestClient(app).post("/api/analysis/traffic-experiment/explain", json=request, headers={"Authorization": "Bearer test-only"})
        self.assertEqual(response.status_code, 200)
        evidence = explain.call_args.args[0]
        self.assertEqual(evidence["failed_metrics"]["throughput_mbps"], 0)
        self.assertTrue(evidence["analysis"]["flows"])
