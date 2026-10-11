from typing import Any, Dict

from fastapi import APIRouter

from app.models.scenario import ScenarioRequest, ScenarioResult
from app.services.scenario_engine import ScenarioEngine

router = APIRouter(prefix="/scenario", tags=["scenario"])


@router.get("/health")
async def scenario_health() -> Dict[str, Any]:
    return {"status": "ok", "service": "scenario-engine"}


@router.post("/validate")
async def validate_scenario(request: ScenarioRequest) -> Dict[str, Any]:
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
    result = ScenarioEngine.run_scenario(request.baseline, request.scenario.model_dump())
    return ScenarioResult(**result)
