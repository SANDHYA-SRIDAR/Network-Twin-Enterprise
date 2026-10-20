"""Legacy response adapter. All calculation belongs to analytical_simulator."""
from datetime import datetime, timezone

from app.engines.analytical_simulator import run_experiment
from app.models.failure_simulation import TrafficDemand
from app.models.network import NetworkDefinition


class ScenarioEngine:
    @staticmethod
    def parameters(scenario_config: dict) -> dict:
        parameters = {**(scenario_config.get("metadata") or {}), **{k: v for k, v in scenario_config.items() if v is not None and k != "metadata"}}
        if scenario_config["type"] == "traffic_increase":
            parameters["factor"] = parameters.get("value", 1.5)
        return parameters

    @staticmethod
    def run_scenario(baseline: NetworkDefinition, scenario_config: dict, traffic: dict) -> dict:
        kind = scenario_config["type"]
        parameters = ScenarioEngine.parameters(scenario_config)
        result = run_experiment(baseline, kind, parameters, TrafficDemand.model_validate(traffic))
        metrics = result["failed_metrics"]
        return {
            "id": result["experiment_id"], "status": "completed", "baseline_name": baseline.name,
            "scenario_type": kind, "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": {**metrics, "decision": "Compare recovery candidates with explicit criteria.",
                        "service_redundancy": None, "redundancy_status": "unsupported: use modernization link-outage stress tests"},
            "baseline": {**result["baseline_metrics"], "name": baseline.name, "names": [baseline.name]},
            "scenario": metrics, "evidence": result["assumptions"], "provenance": "simulated",
        }
