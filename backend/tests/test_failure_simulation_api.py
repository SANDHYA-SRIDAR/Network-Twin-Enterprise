import unittest

from fastapi.testclient import TestClient

from app.main import app


class FailureSimulationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_topology_endpoint_requires_supabase_bearer_token(self):
        response = self.client.get("/api/failure-simulation/topology")
        self.assertEqual(response.status_code, 401)

    def test_experiment_endpoints_require_supabase_bearer_token(self):
        response = self.client.post("/api/failure-simulation/00000000-0000-0000-0000-000000000001/modernize")
        self.assertEqual(response.status_code, 401)

    def test_scenario_catalog_matches_scenario_studio_types(self):
        response = self.client.get("/api/failure-simulation/scenarios")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["scenarios"]}
        self.assertEqual(ids, {"link_failure", "traffic_increase", "bandwidth_change", "redundancy_add", "device_failure", "segment_isolation", "capacity_increase", "cloud_migration"})


if __name__ == "__main__":
    unittest.main()
