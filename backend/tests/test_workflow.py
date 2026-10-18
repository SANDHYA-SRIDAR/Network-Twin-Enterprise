import copy
import math
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.engines.analytical_simulator import ENGINE_VERSION, evaluate, run_experiment, run_modernization
from app.main import app
from app.models.failure_simulation import TrafficDemand, ExperimentModernizeRequest
from app.models.network import NetworkDefinition, NodeDefinition, LinkDefinition, IPConfiguration
from app.services.supabase_repository import repository


def fixture():
    topology = NetworkDefinition(name="LAN", nodes=[NodeDefinition(id=k, name=k, device_type="router") for k in ("a", "b", "c")], links=[
        LinkDefinition(id="ab", source_node_id="a", target_node_id="b", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=10),
        LinkDefinition(id="bc", source_node_id="b", target_node_id="c", bandwidth_mbps=1000, delay_ms=2, packet_loss_pct=20),
    ])
    return topology, TrafficDemand(source_node_id="a", target_node_id="c", offered_mbps=100)


class PhysicsTests(unittest.TestCase):
    def test_delay_components_and_independent_losses(self):
        topology, traffic = fixture()
        metrics = evaluate(topology, traffic, set(), "baseline")["metrics"]
        self.assertAlmostEqual(metrics["throughput_mbps"], 72)
        self.assertAlmostEqual(metrics["configured_path_loss_pct"], 28)
        self.assertAlmostEqual(metrics["propagation_delay_ms"], 3)
        self.assertAlmostEqual(metrics["serialization_delay_ms"], 0.024)
        self.assertAlmostEqual(metrics["queueing_delay_ms"], 2 * 0.012 * 0.1 / 0.9, places=6)
        self.assertIsNone(metrics["maximum_latency_ms"])

    def test_overload_has_no_fabricated_finite_latency(self):
        topology, traffic = fixture()
        topology.links[0].bandwidth_mbps = 50
        metrics = evaluate(topology, traffic, set(), "failure")["metrics"]
        self.assertEqual(metrics["queueing_status"], "unstable")
        self.assertIsNone(metrics["average_latency_ms"])
        self.assertEqual(metrics["congestion_loss_pct"], 50)
        self.assertEqual(metrics["achievable_throughput_mbps"], 50)
        self.assertEqual(metrics["throughput_mbps"], 36)
        self.assertEqual(metrics["links"][0]["utilization_pct"], 100)
        self.assertEqual(metrics["links"][1]["achieved_throughput_mbps"], 50)
        self.assertEqual(metrics["links"][0]["offered_load_ratio"], 2)

    def test_exact_saturation_is_unstable(self):
        topology, traffic = fixture()
        topology.links[0].bandwidth_mbps = 100
        self.assertEqual(evaluate(topology, traffic, set(), "failure")["metrics"]["queueing_status"], "unstable")

    def test_unavailable_and_console_links_are_excluded(self):
        topology, traffic = fixture()
        topology.nodes[1].status = "unavailable"
        self.assertFalse(evaluate(topology, traffic, set(), "failure")["metrics"]["flow_connected"])
        topology.nodes[1].status = "active"
        topology.links[0].cable_type = "console"
        self.assertFalse(evaluate(topology, traffic, set(), "failure")["metrics"]["flow_connected"])

    def test_invalid_references_and_policy_constraints_rejected(self):
        topology, traffic = fixture()
        topology.links[0].source_node_id = "missing"
        with self.assertRaises(HTTPException):
            evaluate(topology, traffic, set(), "failure")
        topology, traffic = fixture()
        topology.routing.static_routes = [{"destination": "10.0.0.0/24"}]
        with self.assertRaises(HTTPException):
            evaluate(topology, traffic, set(), "failure")

    def test_numerical_ranges_and_masks(self):
        for field, value in (("bandwidth_mbps", 0), ("delay_ms", -1), ("packet_loss_pct", 101), ("bandwidth_mbps", math.nan), ("delay_ms", math.inf)):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                LinkDefinition(id="x", source_node_id="a", target_node_id="b", **{field: value})
        with self.assertRaises(ValidationError):
            IPConfiguration(ip_address="10.0.0.1", subnet_mask="255.255.0.0", prefix_length=24)
        self.assertEqual(IPConfiguration(ip_address="10.0.0.1", subnet_mask="255.255.0.0").prefix_length, 16)
        with self.assertRaises(ValidationError):
            IPConfiguration(ip_address="10.0.0.1", gateway="invalid")

    def test_repeatability_and_baseline_is_immutable(self):
        topology, traffic = fixture()
        before = topology.model_dump()
        first = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        second = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        for key in ("baseline_metrics", "failed_metrics", "failed_topology", "assumptions"):
            self.assertEqual(first[key], second[key])
        failed = NetworkDefinition.model_validate(first["failed_topology"])
        one = run_modernization(topology, failed, "link_failure", {"link_id": "ab"}, traffic, first["failed_metrics"], first["assumptions"])
        two = run_modernization(topology, failed, "link_failure", {"link_id": "ab"}, traffic, first["failed_metrics"], first["assumptions"])
        self.assertEqual(one, two)
        self.assertEqual(topology.model_dump(), before)

    def test_ranking_respects_budget_and_repair_permission(self):
        topology, traffic = fixture()
        failure = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        failed = NetworkDefinition.model_validate(failure["failed_topology"])
        result = run_modernization(topology, failed, "link_failure", {"link_id": "ab"}, traffic, failure["failed_metrics"], [], ExperimentModernizeRequest(max_change_units=0, allow_repair=False, allow_new_links=False))
        self.assertEqual(result["modernization"]["selected_strategy_id"], "retain")
        self.assertFalse(result["modernization"]["resolved"])
        self.assertTrue(any(not c["feasible"] for c in result["modernization"]["candidates"]))
        with self.assertRaises(ValidationError):
            ExperimentModernizeRequest(weights={"cost": 0})

    def test_weights_change_selection_and_resilience_has_stress_evidence(self):
        topology, traffic = fixture()
        for link in topology.links:
            link.packet_loss_pct = 0
        # Failed state still has a surviving route; a new dedicated path provides redundancy.
        failure = run_experiment(topology, "traffic_increase", {"factor": 1}, traffic)
        outputs = []
        for priority in ("cost", "resilience"):
            weights = {k: float(k == priority) for k in ("performance", "resilience", "feasibility", "cost")}
            outputs.append(run_modernization(topology, topology, "traffic_increase", {"factor": 1}, traffic, failure["failed_metrics"], [], ExperimentModernizeRequest(weights=weights)))
        self.assertEqual(outputs[0]["modernization"]["selected_strategy_id"], "retain")
        self.assertEqual(outputs[1]["modernization"]["selected_strategy_id"], "bypass")
        bypass = next(c for c in outputs[1]["modernization"]["candidates"] if c["id"] == "bypass")
        self.assertEqual(bypass["resilience_test"]["survived"], 1)


class WorkflowApiTests(unittest.TestCase):
    def test_stateless_complete_workflow_without_supabase_or_ai(self):
        topology, traffic = fixture()
        with patch.object(repository, "_request", side_effect=AssertionError("No external persistence in stateless mode")):
            response = TestClient(app).post("/api/analysis/experiment", json={"topology": topology.model_dump(mode="json"), "traffic": traffic.model_dump(), "scenario_type": "link_failure", "parameters": {"link_id": "ab"}})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertFalse(result["persisted"])
        self.assertFalse(result["failed_metrics"]["flow_connected"])
        self.assertGreaterEqual(len(result["modernization"]["candidates"]), 3)
        self.assertTrue(result["modernized_metrics"]["flow_connected"])

    def test_saved_run_rank_explain_history_reload_contract(self):
        topology, traffic = fixture()
        storage = {}

        async def save(token, row):
            storage.update(copy.deepcopy(row))
            return row

        async def update(token, experiment_id, user_id, body):
            storage.update(copy.deepcopy(body))

        async def get(token, experiment_id, user_id):
            return copy.deepcopy(storage)

        with patch.object(repository, "user_id", AsyncMock(return_value="owner")), \
             patch.object(repository, "load_topology", AsyncMock(return_value=topology)), \
             patch.object(repository, "save_experiment", AsyncMock(side_effect=save)) as saved, \
             patch.object(repository, "update_experiment", AsyncMock(side_effect=update)), \
             patch.object(repository, "get_experiment", AsyncMock(side_effect=get)), \
             patch.object(repository, "list_experiments", AsyncMock(return_value=[{"id": "saved"}])), \
             patch("app.services.assistant.settings.assistant_url", None):
            client = TestClient(app)
            headers = {"Authorization": "Bearer caller-token"}
            loaded = client.get("/api/failure-simulation/topology", headers=headers)
            self.assertEqual(loaded.status_code, 200, loaded.text)
            baseline = client.post("/api/analysis/evaluate", json={"topology": loaded.json()["topology"], "traffic": traffic.model_dump()})
            self.assertEqual(baseline.status_code, 200, baseline.text)
            self.assertTrue(baseline.json()["metrics"]["flow_connected"])
            run = client.post("/api/failure-simulation/run", headers=headers, json={"traffic": traffic.model_dump(), "scenario_type": "link_failure", "parameters": {"link_id": "ab"}})
            self.assertEqual(run.status_code, 200, run.text)
            self.assertFalse(run.json()["failed_metrics"]["flow_connected"])
            self.assertEqual(storage["metrics"]["analysis"], run.json()["analysis"])
            experiment_id = run.json()["experiment_id"]
            base = f"/api/failure-simulation/{experiment_id}"
            ranked = client.post(base + "/modernize", headers=headers, json={"optimizer": {
                "population_size": 8, "generations": 3, "timeout_seconds": 30,
                "minimum_delivery_ratio": 0.5}})  # This fixture explicitly configures 28% path loss.
            self.assertEqual(ranked.status_code, 200, ranked.text)
            self.assertTrue(ranked.json()["modernized_metrics"]["flow_connected"])
            self.assertGreater(len(storage["proposal"]["candidates"]), 1)
            self.assertEqual(ranked.json()["modernization"]["optimization"]["status"], "completed")
            decision = client.post(base + "/decision", headers=headers, json={
                "action": "accept", "candidate_id": ranked.json()["modernization"]["selected_strategy_id"],
                "topology_fingerprint": ranked.json()["topology_fingerprint"],
                "proposal_revision": ranked.json()["modernization"]["revision"], "note": "Controlled review"})
            self.assertEqual(decision.status_code, 200, decision.text)
            self.assertEqual(decision.json()["decisions"][0]["scope"], "experiment_plan_only")
            ranked = decision
            explanation = client.post(base + "/assistant", headers=headers, json={"question": "Why this strategy?"})
            self.assertEqual(explanation.status_code, 200, explanation.text)
            self.assertEqual(explanation.json()["mode"], "deterministic")
            fetched = client.get(f"/api/failure-simulation/experiments/{experiment_id}", headers=headers)
            self.assertEqual(fetched.json()["assistant"]["question"], "Why this strategy?")
            self.assertEqual(fetched.json()["modernization"], ranked.json()["modernization"])
            self.assertEqual(fetched.json()["analysis"], run.json()["analysis"])
            self.assertEqual(fetched.json()["baseline_metrics"], run.json()["baseline_metrics"])
            self.assertEqual(fetched.json()["modernized_metrics"], ranked.json()["modernized_metrics"])
            self.assertEqual(client.get("/api/failure-simulation/experiments", headers=headers).status_code, 200)
            self.assertEqual(saved.call_args.args[0], "caller-token")
            storage["engine_version"] = "old-engine"
            self.assertEqual(client.post(base + "/modernize", headers=headers).status_code, 409)

    def test_fingerprint_conflict_does_not_save(self):
        topology, traffic = fixture()
        with patch.object(repository, "user_id", AsyncMock(return_value="owner")), patch.object(repository, "load_topology", AsyncMock(return_value=topology)), patch.object(repository, "save_experiment", AsyncMock()) as saved:
            response = TestClient(app).post("/api/failure-simulation/run", headers={"Authorization": "Bearer caller"}, json={"traffic": traffic.model_dump(), "scenario_type": "link_failure", "parameters": {"link_id": "ab"}, "topology_fingerprint": "stale"})
            self.assertEqual(response.status_code, 409)
            saved.assert_not_called()

    def test_nonfinite_json_metadata_returns_safe_validation_error(self):
        topology, traffic = fixture()
        import json
        payload = {"topology": topology.model_dump(), "traffic": traffic.model_dump()}
        payload["topology"]["metadata"] = {"unsupported_number": math.nan}
        response = TestClient(app).post("/api/analysis/evaluate", content=json.dumps(payload), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("NaN", response.text)


if __name__ == "__main__":
    unittest.main()
