"""Owner-scoped decision lifecycle with mocked persistence, real analytical candidates."""
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.api.failure_simulation import fingerprint
from app.engines.analytical_simulator import ENGINE_VERSION, run_experiment, run_modernization
from app.models.network import NetworkDefinition
from app.models.failure_simulation import ExperimentModernizeRequest, OptimizerSettings
from app.services.supabase_repository import repository
from app.services.transformation import proposal_revision
from test_optimization import fixture


class CandidateDecisionTests(unittest.TestCase):
    def setUp(self):
        self.graph, self.demand = fixture()
        failure = run_experiment(self.graph, "link_failure", {"link_id": "ab"}, self.demand)
        failed = NetworkDefinition.model_validate(failure["failed_topology"])
        criteria = ExperimentModernizeRequest(optimizer=OptimizerSettings(population_size=8, generations=3, timeout_seconds=30))
        recovered = run_modernization(self.graph, failed, "link_failure", {"link_id": "ab"}, self.demand, failure["failed_metrics"], failure["assumptions"], criteria)
        self.row = {"id": "saved", "user_id": "owner", "engine_version": ENGINE_VERSION,
                    "scenario_id": "link_failure", "scenario_parameters": {"link_id": "ab"},
                    "topology_fingerprint": fingerprint(self.graph), "traffic_configuration": self.demand.model_dump(),
                    "baseline_snapshot": failure["baseline_topology"], "failure_snapshot": failure["failed_topology"],
                    "modernized_snapshot": recovered["modernized_topology"], "proposal": recovered["modernization"],
                    "metrics": {"baseline": failure["baseline_metrics"], "failure": failure["failed_metrics"], "analysis": failure["analysis"],
                                "modernized": recovered["modernized_metrics"], "assumptions": recovered["assumptions"], "assistant": {"old": True}}}
        async def update(token, identifier, user_id, body):
            self.assertEqual((token, identifier, user_id), ("caller-token", "saved", "owner"))
            self.row.update(deepcopy(body))
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(repository, "user_id", AsyncMock(return_value="owner")))
        self.get = stack.enter_context(patch.object(repository, "get_experiment", AsyncMock(side_effect=lambda *args: deepcopy(self.row))))
        self.load = stack.enter_context(patch.object(repository, "load_topology", AsyncMock(return_value=self.graph)))
        self.updated = stack.enter_context(patch.object(repository, "update_experiment", AsyncMock(side_effect=update)))
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer caller-token"}

    def body(self, action="select", candidate="repair"):
        return {"action": action, "candidate_id": candidate, "note": "Reviewed actual graph",
                "proposal_revision": proposal_revision(self.row["proposal"]), "topology_fingerprint": self.row["topology_fingerprint"]}

    def decide(self, **kwargs):
        return self.client.post("/api/failure-simulation/saved/decision", headers=self.headers, json=self.body(**kwargs))

    def test_select_accept_reject_reload_preserves_evidence_and_canonical_graph(self):
        original = deepcopy(self.graph.model_dump())
        snapshots = deepcopy((self.row["baseline_snapshot"], self.row["failure_snapshot"]))
        selected = self.decide()
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["modernization"]["selected_strategy_id"], "repair")
        candidate = next(c for c in selected.json()["modernization"]["candidates"] if c["id"] == "repair")
        self.assertEqual(selected.json()["modernized_topology"], candidate["topology"])
        self.assertEqual(selected.json()["modernized_metrics"], candidate["metrics"])
        self.assertIsNone(selected.json()["assistant"])
        self.assertEqual(self.decide(action="accept").status_code, 200)
        self.assertEqual(self.decide(action="reject").status_code, 200)
        loaded = self.client.get("/api/failure-simulation/experiments/saved", headers=self.headers).json()
        self.assertEqual([d["action"] for d in loaded["decisions"]], ["select", "accept", "reject"])
        self.assertTrue(all(d["scope"] == "experiment_plan_only" and not d["canonical_topology_changed"] for d in loaded["decisions"]))
        self.assertEqual(loaded["decisions"][1]["candidate_snapshot"], candidate["topology"])
        self.assertEqual(self.graph.model_dump(), original)
        self.assertEqual((self.row["baseline_snapshot"], self.row["failure_snapshot"]), snapshots)
        self.assertTrue(loaded["modernization"]["optimization"]["pareto_candidate_ids"])

    def test_accept_checks_current_topology_fingerprint(self):
        self.graph.links[0].bandwidth_mbps = 200
        response = self.decide(action="accept")
        self.assertEqual(response.status_code, 409)
        self.updated.assert_not_called()

    def test_stale_proposal_missing_candidate_and_missing_auth(self):
        body = {**self.body(), "proposal_revision": "stale"}
        self.assertEqual(self.client.post("/api/failure-simulation/saved/decision", headers=self.headers, json=body).status_code, 409)
        self.assertEqual(self.decide(candidate="someone-elses-candidate").status_code, 404)
        self.assertEqual(self.client.post("/api/failure-simulation/saved/decision", json=self.body()).status_code, 401)
        self.updated.assert_not_called()

    def test_other_owner_denial_propagates_without_write(self):
        self.get.side_effect = HTTPException(404, "Experiment not found")
        self.assertEqual(self.decide().status_code, 404)
        self.updated.assert_not_called()

    def test_infeasible_candidate_can_only_be_rejected(self):
        candidate = next(c for c in self.row["proposal"]["candidates"] if not c["feasible"])
        self.assertEqual(self.decide(candidate=candidate["id"]).status_code, 422)
        self.assertEqual(self.decide(action="reject", candidate=candidate["id"]).status_code, 200)

    def test_disconnected_retain_cannot_be_accepted_as_recovery(self):
        self.assertEqual(self.decide(action="accept", candidate="retain").status_code, 422)
        self.updated.assert_not_called()

    def test_write_failure_propagates_not_fake_success(self):
        self.updated.side_effect = HTTPException(502, "Persistence confirmation missing")
        self.assertEqual(self.decide().status_code, 502)


if __name__ == "__main__":
    unittest.main()
