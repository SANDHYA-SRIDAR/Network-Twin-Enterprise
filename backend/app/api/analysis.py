"""Stateless local workflow: no credentials, external services, or persistence required."""
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.engines.analytical_simulator import evaluate, run_experiment, run_modernization
from app.models.network import NetworkDefinition
from app.models.failure_simulation import TrafficDemand, FailureSimulationRequest, ExperimentModernizeRequest

router = APIRouter(prefix="/analysis", tags=["analytical-workflow"])


class EvaluationRequest(BaseModel):
    topology: NetworkDefinition
    traffic: TrafficDemand


class AnalysisRequest(FailureSimulationRequest):
    topology: NetworkDefinition
    criteria: ExperimentModernizeRequest = Field(default_factory=ExperimentModernizeRequest)


@router.post("/evaluate")
async def evaluate_topology(request: EvaluationRequest):
    assumptions: set[str] = set()
    result = evaluate(request.topology, request.traffic, assumptions, "preview")
    return {**result, "assumptions": sorted(assumptions), "persisted": False}


@router.post("/experiment")
async def analyze_experiment(request: AnalysisRequest):
    result = run_experiment(request.topology, request.scenario_type, request.parameters, request.traffic)
    result["scenario_type"] = request.scenario_type
    result.update(await run_in_threadpool(run_modernization, request.topology, NetworkDefinition.model_validate(result["failed_topology"]),
        request.scenario_type, request.parameters, TrafficDemand.model_validate(result["traffic"]),
        result["failed_metrics"], result["assumptions"], request.criteria))
    # Local mode remains deterministic and does not require an AI provider.
    result["persisted"] = False
    return result


class WanDemoRequest(BaseModel):
    topology: NetworkDefinition | None = None
    require_continuity: bool = True
    offered_mbps: float = Field(default=100, gt=0, le=1_000_000, allow_inf_nan=False)


@router.post("/wan-demo")
async def wan_demo(request: WanDemoRequest):
    from app.services.wan_demo import run_wan_demo
    return await run_in_threadpool(run_wan_demo, request.topology, request.require_continuity, request.offered_mbps)


from app.models.packet_simulation import PacketExperimentRequest
from app.services.traffic_experiment import sample_experiment, run_traffic_experiment


@router.get("/traffic-samples/{name}")
async def traffic_sample(name: str):
    return sample_experiment(name)


@router.post("/traffic-experiment")
async def traffic_experiment(request: PacketExperimentRequest):
    return await run_in_threadpool(run_traffic_experiment, request)


from typing import Annotated
from fastapi import Depends
from app.api.auth import require_access_token


@router.post("/traffic-experiment/explain")
async def explain_traffic_experiment(request: PacketExperimentRequest, token: Annotated[str, Depends(require_access_token)]):
    from app.services.supabase_repository import repository
    from app.services.assistant import explain_experiment
    await repository.user_id(token)
    result = await run_in_threadpool(run_traffic_experiment, request)
    selected = next(c for c in result["candidates"] if c["id"] == result["selected_id"])
    def metric_summary(metrics):
        return {**metrics, "flow_connected": metrics["connectivity_pct"] == 100,
                "reachable_nodes": None, "queueing_status": "finite_queue_event_model", "route_link_ids": []}
    evidence = {"engine_version": result["engine_version"], "scenario_type": request.scenario_type,
                "baseline_metrics": metric_summary(result["baseline_metrics"]),
                "failed_metrics": metric_summary(result["failed_metrics"]),
                "modernized_metrics": metric_summary(selected["metrics"]),
                "analysis": {"risk": result["insights"], "flows": result["failed_metrics"]["flows"], "candidate_risk": selected["insights"]},
                "assumptions": result["limitations"],
                "modernization": {"summary": result["summary"], "selected_strategy_id": selected["id"],
                                  "selection_source": "least_change_meeting_all_flow_targets", "optimization": result["optimization"],
                                  "candidates": [{**c, "change_units": c["cost_units"], "metrics": metric_summary(c["metrics"])} for c in result["candidates"]]}}
    return await explain_experiment(evidence, "Explain the synthetic traffic impact, affected applications, rule-based risk and recovery trade-offs. Do not claim trained prediction or real TCP behavior.")
