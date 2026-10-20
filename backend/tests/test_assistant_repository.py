import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.engines.analytical_simulator import run_experiment, run_modernization
from app.models.network import NetworkDefinition
from app.services.assistant import explain_experiment, validate_explanation
from app.services.supabase_repository import repository
from test_workflow import fixture


class AssistantTests(unittest.IsolatedAsyncioTestCase):
    def test_claim_validation_rejects_invented_values_and_missing_structure(self):
        evidence = {"failure": {"throughput_mbps": 0, "flow_connected": False}, "candidates": []}
        invalid = ["unstructured prose", json.dumps({"explanation": "Invented rate", "claims": [{"source": "failure", "metric": "throughput_mbps", "value": 999}]}),
                   json.dumps({"explanation": "Unknown field", "claims": [{"source": "failure", "metric": "future_failure_probability", "value": 0.8}]}),
                   json.dumps({"explanation": "Unknown candidate", "claims": [{"source": "candidate", "candidate_id": "not-present", "metric": "score", "value": 1}]})]
        for content in invalid:
            with self.subTest(content=content), self.assertRaises(ValueError):
                validate_explanation(content, evidence)

    async def test_provider_invented_metric_uses_honest_deterministic_fallback(self):
        topology, traffic = fixture()
        result = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        client = AsyncMock()
        content = json.dumps({"explanation": "Wrong throughput", "claims": [{"source": "failure", "metric": "throughput_mbps", "value": 999}]})
        client.post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://provider.invalid/chat"), json={"choices": [{"message": {"content": content}}]})
        with patch("app.services.assistant.settings.assistant_url", "https://provider.invalid/chat"), patch("app.services.assistant.settings.assistant_model", "test"), patch("app.services.assistant.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            answer = await explain_experiment(result, "Explain")
        self.assertEqual(answer["mode"], "deterministic")
        self.assertNotIn("Wrong throughput", answer["text"])

    async def test_optimizer_evidence_is_supplied_without_authoritative_mutation(self):
        from test_optimization import fixture as control_fixture
        from app.models.failure_simulation import ExperimentModernizeRequest, OptimizerSettings
        topology, traffic = control_fixture()
        result = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        result.update(run_modernization(topology, NetworkDefinition.model_validate(result["failed_topology"]), "link_failure", {"link_id": "ab"}, traffic,
                                       result["failed_metrics"], result["assumptions"], ExperimentModernizeRequest(optimizer=OptimizerSettings(population_size=8, generations=3, timeout_seconds=30))))
        before = copy.deepcopy(result)
        client = AsyncMock()
        content = json.dumps({"explanation": "The supplied failed demand is unreachable; alternatives have cost and delay trade-offs.",
                              "claims": [{"source": "failure", "metric": "flow_connected", "value": False}]})
        client.post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://provider.invalid/chat"), json={"choices": [{"message": {"content": content}}]})
        with patch("app.services.assistant.settings.assistant_url", "https://provider.invalid/chat"), patch("app.services.assistant.settings.assistant_model", "test"), patch("app.services.assistant.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            answer = await explain_experiment(result, "Compare")
        self.assertEqual(answer["mode"], "ai_assisted")
        self.assertEqual(answer["evidence"]["optimization"]["pareto_candidate_ids"], result["modernization"]["optimization"]["pareto_candidate_ids"])
        self.assertTrue(any(c.get("objectives") for c in answer["evidence"]["candidates"]))
        self.assertEqual(result, before)

    async def test_provider_explains_evidence_without_changing_results(self):
        topology, traffic = fixture()
        result = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        result["scenario_type"] = "link_failure"
        result.update(run_modernization(topology, NetworkDefinition.model_validate(result["failed_topology"]), "link_failure", {"link_id": "ab"}, traffic, result["failed_metrics"], result["assumptions"]))
        before = copy.deepcopy(result)
        client = AsyncMock()
        client.post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://provider.invalid/chat"), json={"choices": [{"message": {"content": json.dumps({"explanation": "Supplied evidence shows an unreachable service.", "claims": [{"source": "failure", "metric": "flow_connected", "value": False}]})}}]})
        with patch("app.services.assistant.settings.assistant_url", "https://provider.invalid/chat"), \
             patch("app.services.assistant.settings.assistant_model", "test-model"), \
             patch("app.services.assistant.settings.assistant_api_key", "server-only-test-key"), \
             patch("app.services.assistant.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            answer = await explain_experiment(result, "Explain the failure")
        self.assertEqual(answer["mode"], "ai_assisted")
        self.assertEqual(result, before)
        supplied = json.loads(client.post.call_args.kwargs["json"]["messages"][1]["content"])["evidence"]
        self.assertEqual(supplied["modernized"]["throughput_mbps"], result["modernized_metrics"]["throughput_mbps"])
        self.assertEqual(supplied["candidates"][0]["metrics"]["throughput_mbps"], result["modernization"]["candidates"][0]["metrics"]["throughput_mbps"])
        self.assertNotIn("server-only-test-key", str(answer))
        self.assertNotIn("server-only-test-key", str(client.post.call_args.kwargs["json"]))

    async def test_provider_failure_retains_deterministic_evidence(self):
        topology, traffic = fixture()
        result = run_experiment(topology, "link_failure", {"link_id": "ab"}, traffic)
        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("private provider connection details")
        with patch("app.services.assistant.settings.assistant_url", "https://provider.invalid/chat"), \
             patch("app.services.assistant.settings.assistant_model", "test-model"), \
             patch("app.services.assistant.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            answer = await explain_experiment(result, "Explain")
        self.assertEqual(answer["mode"], "deterministic")
        self.assertNotIn("private provider", str(answer))


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_update_guard_returns_conflict_without_false_success(self):
        from fastapi import HTTPException
        with patch.object(repository, "_request", AsyncMock(return_value=httpx.Response(200, json=[]))) as request:
            with self.assertRaises(HTTPException) as raised:
                await repository.update_experiment("caller", "experiment", "owner", {"metrics": {}}, expected_updated_at="2026-10-17T00:00:00Z")
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(request.call_args.kwargs["params"]["updated_at"], "eq.2026-10-17T00:00:00Z")
            self.assertEqual(request.call_args.kwargs["params"]["user_id"], "eq.owner")

    async def test_experiment_access_remains_scoped_to_caller_and_owner(self):
        response = httpx.Response(200, json=[{"id": "experiment"}])
        with patch.object(repository, "_request", AsyncMock(return_value=response)) as request:
            await repository.get_experiment("caller-jwt", "experiment", "owner-id")
            self.assertEqual(request.call_args.args[0], "caller-jwt")
            self.assertEqual(request.call_args.kwargs["params"]["user_id"], "eq.owner-id")
            await repository.list_experiments("caller-jwt", "owner-id")
            self.assertEqual(request.call_args.kwargs["params"]["user_id"], "eq.owner-id")
            self.assertEqual(request.call_args.kwargs["params"]["limit"], "50")

    async def test_canonical_topology_metadata_and_model_mapping(self):
        node = {"id": "access", "node_type": "cloud-server", "label": "AP", "status": "healthy", "configuration": {"model": "accesspoint-pt"}, "created_at": "2026-10-16T00:00:00Z", "updated_at": "2026-10-16T01:00:00Z"}
        with patch.object(repository, "_request", AsyncMock(side_effect=[httpx.Response(200, json=[node]), httpx.Response(200, json=[]), httpx.Response(200, json=[node]), httpx.Response(200, json=[])])):
            first = await repository.load_topology("caller", "owner")
            second = await repository.load_topology("caller", "owner")
        self.assertEqual(first, second)
        self.assertEqual(first.owner_id, "owner")
        self.assertEqual(first.nodes[0].device_type, "access_point")
        self.assertEqual(first.nodes[0].model, "accesspoint-pt")
        self.assertEqual(len(first.version), 64)
