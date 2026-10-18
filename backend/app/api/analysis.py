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
