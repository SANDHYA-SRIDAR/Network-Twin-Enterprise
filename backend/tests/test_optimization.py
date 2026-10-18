"""Small controlled analytical networks; real pymoo execution, no AI or database."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from app.engines.analytical_simulator import evaluate, run_experiment, run_modernization
from app.models.failure_simulation import ExperimentModernizeRequest, OptimizerSettings
from app.models.network import NetworkDefinition, NodeDefinition, LinkDefinition
from app.services.optimization import decode, dominates, objective_values
from app.services.transformation import _changes


def fixture():
    graph = NetworkDefinition(name="Optimizer control", nodes=[NodeDefinition(id=i, name=i, device_type="router") for i in "abc"],
        links=[LinkDefinition(id=u+v, source_node_id=u, target_node_id=v, bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0)
               for u, v in [("a", "b"), ("b", "c")]])
    from app.models.failure_simulation import TrafficDemand
    return graph, TrafficDemand(source_node_id="a", target_node_id="c", offered_mbps=100)


class OptimizationTests(unittest.TestCase):
    def test_concurrent_seeded_searches_remain_reproducible(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.run_case()[0], range(2)))
        self.assertEqual(results[0], results[1])

    def test_cost_counts_repair_and_capacity_separately_and_handles_unconfigured(self):
        graph, _ = fixture()
        old = deepcopy(graph)
        old.links[0].status = "failed"
        graph.links[0].bandwidth_mbps = None
        units, changes = _changes(old, graph)
        self.assertEqual(units, 3)
        self.assertEqual(len(changes), 2)
        self.assertIn("unconfigured", changes[1])

    def run_case(self, criteria=None, scenario="link_failure", parameters=None):
        graph, traffic = fixture()
        result = run_experiment(graph, scenario, parameters or {"link_id": "ab"}, traffic)
        failed = NetworkDefinition.model_validate(result["failed_topology"])
        before = graph.model_dump(), failed.model_dump()
        criteria = criteria or ExperimentModernizeRequest(optimizer=OptimizerSettings(population_size=12, generations=6, timeout_seconds=30))
        recovery = run_modernization(graph, failed, scenario, parameters or {"link_id": "ab"}, traffic,
                                     result["failed_metrics"], result["assumptions"], criteria)
        self.assertEqual((graph.model_dump(), failed.model_dump()), before)
        return recovery, traffic, criteria

    def test_actual_nsga_repeatability_pareto_and_objective_correctness(self):
        first, traffic, criteria = self.run_case()
        second, _, _ = self.run_case()
        self.assertEqual(first, second)
        proposal = first["modernization"]
        opt = proposal["optimization"]
        self.assertEqual(opt["status"], "completed")
        self.assertEqual(opt["generations_completed"], 6)
        self.assertGreaterEqual(len(opt["pareto_candidate_ids"]), 2)
        front = [c for c in proposal["candidates"] if c["id"] in opt["pareto_candidate_ids"]]
        for item in front:
            self.assertTrue(item["feasible"])
            self.assertEqual(item["constraints"], [])
            graph = NetworkDefinition.model_validate(item["topology"])
            self.assertEqual(evaluate(graph, traffic, set(), "modernized")["metrics"], item["metrics"])
            self.assertEqual(objective_values(item, traffic, criteria), item["objectives"])
            self.assertFalse(any(dominates(c["objectives"], item["objectives"]) for c in front))
        self.assertIn(proposal["selected_strategy_id"], opt["pareto_candidate_ids"])
        self.assertTrue(any(c["id"] == "repair" for c in opt["baseline_comparison"]))
        self.assertNotEqual(min(c["change_units"] for c in front), max(c["change_units"] for c in front))

    def test_no_feasible_recovery_is_explicit(self):
        result, _, _ = self.run_case(ExperimentModernizeRequest(max_change_units=0, allow_repair=False, allow_new_links=False,
                            optimizer=OptimizerSettings(population_size=8, generations=3, timeout_seconds=30)))
        proposal = result["modernization"]
        self.assertEqual(proposal["optimization"]["status"], "no_feasible_candidates")
        self.assertEqual(proposal["optimization"]["pareto_candidate_ids"], [])
        self.assertFalse(proposal["resolved"])
        self.assertTrue(any(c["constraints"] for c in proposal["candidates"] if c.get("origin") == "nsga2"))

    def test_capacity_alternatives_recalculate_actual_graph(self):
        result, _, _ = self.run_case(scenario="bandwidth_change", parameters={"link_id": "ab", "bandwidth_mbps": 50})
        alternatives = [c for c in result["modernization"]["candidates"] if c.get("origin") == "nsga2"]
        self.assertTrue(any(c["metrics"]["throughput_mbps"] == 100 and c["metrics"]["queueing_status"] == "estimated" for c in alternatives))
        self.assertTrue(any(c["metrics"]["average_latency_ms"] is None and not c["feasible"] for c in alternatives))

    def test_device_replacement_and_endpoint_mapping(self):
        result, _, _ = self.run_case(scenario="device_failure", parameters={"node_id": "b"})
        self.assertEqual(result["modernization"]["optimization"]["status"], "completed")
        self.assertTrue(result["modernized_metrics"]["flow_connected"])

    def test_timeout_retains_real_deterministic_result_without_fake_front(self):
        result, _, _ = self.run_case(ExperimentModernizeRequest(optimizer=OptimizerSettings(timeout_seconds=1e-9)))
        opt = result["modernization"]["optimization"]
        self.assertEqual(opt["status"], "fallback")
        self.assertEqual(opt["pareto_candidate_ids"], [])
        self.assertFalse(any(c.get("origin") == "nsga2" for c in result["modernization"]["candidates"]))
        self.assertTrue(result["modernized_metrics"]["flow_connected"])

    def test_missing_dependency_retains_deterministic_result(self):
        import builtins
        original = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name.startswith("pymoo"):
                raise ImportError("controlled unavailable optimizer")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=unavailable):
            result, _, _ = self.run_case()
        self.assertEqual(result["modernization"]["optimization"]["status"], "fallback")

    def test_dominance_equal_tradeoff_and_strict_dominance(self):
        self.assertFalse(dominates([1, 2], [1, 2]))
        self.assertFalse(dominates([1, 3], [2, 2]))
        self.assertTrue(dominates([1, 2], [2, 2]))

    def test_decode_rejects_conflicts_repairs_and_new_duplicates(self):
        graph, traffic = fixture()
        one, two = deepcopy(graph), deepcopy(graph)
        one.links[0].bandwidth_mbps = 500
        two.links[0].bandwidth_mbps = 250
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            decode(graph, [one, two], 3, 0, traffic, set())
        graph.links[0].status = "failed"
        with self.assertRaisesRegex(ValueError, "Repair"):
            decode(graph, [one], 1, 0, traffic, set(), False)
        graph.links[0].status = "active"
        one = deepcopy(graph)
        one.links.append(LinkDefinition(id="duplicate", source_node_id="a", target_node_id="b"))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            decode(graph, [one], 1, 0, traffic, set())


if __name__ == "__main__":
    unittest.main()
