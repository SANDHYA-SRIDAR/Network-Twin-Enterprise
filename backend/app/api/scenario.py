from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from app.engines.analytical_simulator import apply_scenario, validate_inputs
from app.models.failure_simulation import TrafficDemand

from app.models.scenario import ScenarioRequest, ScenarioResult
from app.services.scenario_engine import ScenarioEngine

router = APIRouter(prefix="/scenario", tags=["scenario"])


@router.get("/health")
async def scenario_health() -> Dict[str, Any]:
    return {"status": "ok", "service": "scenario-engine"}


@router.post("/validate")
async def validate_scenario(request: ScenarioRequest) -> Dict[str, Any]:
    validate_inputs(request.baseline)
    demand = TrafficDemand.model_validate(request.traffic)
    ids = {node.id for node in request.baseline.nodes}
    if demand.source_node_id not in ids or demand.target_node_id not in ids:
        raise HTTPException(status_code=422, detail="Scenario traffic endpoints must exist in the topology.")
    apply_scenario(request.baseline, request.scenario.type, ScenarioEngine.parameters(request.scenario.model_dump()))
    return {
        "valid": True,
        "name": request.name,
        "scenario_type": request.scenario.type,
        "baseline_nodes": len(request.baseline.nodes),
        "baseline_links": len(request.baseline.links),
        "message": "Scenario request is structurally valid.",
    }


@router.post("/run", response_model=ScenarioResult)
async def run_scenario(request: ScenarioRequest) -> ScenarioResult:
    result = ScenarioEngine.run_scenario(request.baseline, request.scenario.model_dump(), request.traffic)
    return ScenarioResult(**result)
