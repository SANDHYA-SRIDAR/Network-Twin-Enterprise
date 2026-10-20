import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import ENV_FILES, Settings, key_category
from app.main import app
from app.services.supabase_repository import repository

URL = "https://test-project.supabase.co"
KEY = "sb_publishable_unit-test-key"
OWNER = "00000000-0000-4000-8000-000000000001"


class ConfigurationTests(unittest.TestCase):
    def settings(self, **values):
        return Settings(_env_file=None, SUPABASE_URL=URL, SUPABASE_PUBLISHABLE_KEY=KEY, **values)

    def test_paths_are_absolute_and_loading_is_independent_of_cwd(self):
        self.assertTrue(all(path.is_absolute() for path in ENV_FILES))
        self.assertEqual(ENV_FILES[0].parent, ENV_FILES[1].parent.parent)
        test_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=test_dir) as directory, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Path(directory).resolve().parent, test_dir)
            root, backend = Path(directory) / "root.env", Path(directory) / "backend.env"
            root.write_text(f"SUPABASE_URL={URL}\nVITE_SUPABASE_PUBLISHABLE_KEY={KEY}\n", encoding="utf-8")
            backend.write_text("PROJECT_NAME=Backend override\n", encoding="utf-8")
            settings = Settings(_env_file=(root, backend))
            self.assertEqual(settings.project_name, "Backend override")
            self.assertEqual(settings.supabase_publishable_key, KEY)
            with patch.dict(os.environ, {"PROJECT_NAME": "Process override"}):
                self.assertEqual(Settings(_env_file=(root, backend)).project_name, "Process override")

    def test_mismatched_aliases_are_rejected_without_disclosing_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = self.settings(VITE_SUPABASE_URL=URL, VITE_SUPABASE_PUBLISHABLE_KEY="sb_publishable_different")
            self.assertIn("disagree", settings.supabase_configuration_error())
            self.assertNotIn(KEY, repr(settings))
            self.assertNotIn(KEY, json.dumps(settings.supabase_diagnostic()))
            self.assertEqual(settings.supabase_diagnostic()["project_reference"], "test-project")
            self.assertFalse(settings.supabase_diagnostic()["configuration_valid"])

    def test_mismatched_projects_are_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn("URLs disagree", self.settings(VITE_SUPABASE_URL="https://another.supabase.co").supabase_configuration_error())
            self.assertIn("project ID", self.settings(SUPABASE_PROJECT_ID="another").supabase_configuration_error())

    def test_publishable_and_legacy_anon_keys_are_supported(self):
        legacy = "eyJhbGciOiJIUzI1NiJ9." + base64.urlsafe_b64encode(json.dumps({"role": "anon"}).encode()).decode().rstrip("=") + ".test-signature"
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(self.settings().supabase_configuration_error())
            settings = Settings(_env_file=None, SUPABASE_URL=URL, SUPABASE_ANON_KEY=legacy)
            self.assertEqual(key_category(settings.supabase_publishable_key), "legacy-anon-jwt")
            self.assertIsNone(settings.supabase_configuration_error())
            settings.supabase_publishable_key = "sb_secret_not-a-browser-key"
            self.assertIsNotNone(settings.supabase_configuration_error())


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_catalog_and_openapi_security(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/failure-simulation/scenarios").status_code, 200)
        spec = self.client.get("/api/openapi.json").json()
        self.assertEqual(spec["components"]["securitySchemes"]["SupabaseBearer"]["scheme"], "bearer")
        for path, methods in spec["paths"].items():
            if path.startswith("/api/failure-simulation/") and not path.endswith("/scenarios"):
                for operation in methods.values():
                    self.assertEqual(operation["security"], [{"SupabaseBearer": []}])
        self.assertNotIn("security", spec["paths"]["/api/analysis/evaluate"]["post"])

    def test_missing_malformed_or_project_key_bearer_returns_401(self):
        for header in (None, "Basic credentials", "Bearer ", "Bearer one two", "Bearer sb_publishable_not-a-session", "Bearer sb_secret_not-a-session"):
            with self.subTest(header_kind=header.split(" ")[0] if header else "missing"):
                response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": header} if header else {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def transport(self, handler):
        original = httpx.AsyncClient
        return patch("app.services.supabase_repository.httpx.AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    def test_invalid_token_is_validated_upstream_and_returns_401(self):
        def handler(request):
            self.assertEqual(request.headers["apikey"], KEY)
            self.assertEqual(request.headers["authorization"], "Bearer invalid-user-token")
            self.assertEqual(request.url.path, "/auth/v1/user")
            return httpx.Response(401, json={"message": "JWT expired"})
        with patch.object(repository, "_configuration", return_value=(URL, KEY)), self.transport(handler):
            response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": "bEaReR invalid-user-token"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("expired", response.json()["detail"])

    def test_auth_user_403_is_invalid_session_but_database_403_is_forbidden(self):
        with patch.object(repository, "_configuration", return_value=(URL, KEY)), self.transport(lambda request: httpx.Response(403, json={"code": "bad_jwt", "message": "Invalid token"})):
            response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": "Bearer invalid-test-token"})
        self.assertEqual(response.status_code, 401)
        def denied_database(request):
            if request.url.path == "/auth/v1/user":
                return httpx.Response(200, json={"id": OWNER})
            return httpx.Response(403, json={"message": "permission denied"})
        with patch.object(repository, "_configuration", return_value=(URL, KEY)), self.transport(denied_database):
            response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": "Bearer valid-test-token"})
        self.assertEqual(response.status_code, 403)

    def test_scenario_run_and_validate_use_same_parameters_and_endpoint_checks(self):
        from test_workflow import fixture
        topology, traffic = fixture()
        payload = {"baseline": topology.model_dump(mode="json"), "traffic": traffic.model_dump(), "scenario": {"type": "traffic_increase", "value": 2}}
        validated = self.client.post("/api/scenario/validate", json=payload)
        executed = self.client.post("/api/scenario/run", json=payload)
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertEqual(executed.status_code, 200, executed.text)
        self.assertEqual(executed.json()["scenario"]["offered_traffic_mbps"], 200)
        payload["traffic"]["target_node_id"] = "missing"
        self.assertEqual(self.client.post("/api/scenario/validate", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/api/scenario/run", json=payload).status_code, 422)

    def test_valid_user_headers_forwarded_through_auth_and_owner_scoped_read(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.headers["apikey"], KEY)
            self.assertEqual(request.headers["authorization"], "Bearer valid-test-user-token")
            if request.url.path == "/auth/v1/user":
                return httpx.Response(200, json={"id": OWNER})
            self.assertEqual(request.url.params["user_id"], f"eq.{OWNER}")
            return httpx.Response(200, json=[])
        with patch.object(repository, "_configuration", return_value=(URL, KEY)), self.transport(handler):
            response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": "Bearer valid-test-user-token"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["topology"]["owner_id"], OWNER)
        self.assertEqual(len(requests), 3)

    def test_bad_project_key_is_configuration_error_not_session_error(self):
        with patch.object(repository, "_configuration", return_value=(URL, KEY)), self.transport(lambda request: httpx.Response(401, json={"message": "Invalid API key", "hint": "secret upstream details"})):
            response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": "Bearer test-user-token"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("project API key", response.json()["detail"])
        self.assertNotIn("secret upstream details", response.text)

    def test_real_upstream_failure_and_invalid_payload_are_not_success(self):
        for upstream_status, expected in ((429, 429), (500, 502)):
            with patch.object(repository, "_configuration", return_value=(URL, KEY)), self.transport(lambda request: httpx.Response(upstream_status, text="private upstream detail")):
                response = self.client.get("/api/failure-simulation/topology", headers={"Authorization": "Bearer test-user-token"})
            self.assertEqual(response.status_code, expected)
        self.assertNotIn("private upstream detail", response.text)

    def test_route_methods_and_prefix(self):
        self.assertEqual(self.client.get("/api/analysis/evaluate").status_code, 405)
        self.assertEqual(self.client.post("/api/analysis/evaluate", json={}).status_code, 422)
        self.assertEqual(self.client.get("/api/api/health").status_code, 404)
        response = self.client.options("/api/analysis/evaluate", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:8080")


class PersistenceConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_insert_and_update_do_not_claim_success(self):
        from unittest.mock import AsyncMock
        with patch.object(repository, "_request", AsyncMock(return_value=httpx.Response(200, json=[]))):
            with self.assertRaises(HTTPException) as insert:
                await repository.save_experiment("test-token", {"id": "experiment"})
            self.assertEqual(insert.exception.status_code, 502)
            with self.assertRaises(HTTPException) as update:
                await repository.update_experiment("test-token", "experiment", OWNER, {})
            self.assertEqual(update.exception.status_code, 404)

    async def test_confirmed_persistence_keeps_owner_filter(self):
        from unittest.mock import AsyncMock
        with patch.object(repository, "_request", AsyncMock(return_value=httpx.Response(200, json=[{"id": "experiment"}]))) as request:
            saved = await repository.save_experiment("test-token", {"id": "experiment"})
            self.assertEqual(saved["id"], "experiment")
            await repository.update_experiment("test-token", "experiment", OWNER, {"status": "modernized"})
            self.assertEqual(request.call_args.kwargs["params"]["user_id"], f"eq.{OWNER}")
            self.assertEqual(request.call_args.kwargs["headers"]["Prefer"], "return=representation")
