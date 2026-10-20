from fastapi import APIRouter, HTTPException

from app.models.network import NetworkDefinition, ValidationResponse
from app.services.network_validation import validate_network_definition

router = APIRouter(prefix="/network", tags=["Network"])


@router.post("/validate", response_model=ValidationResponse)
async def validate_network(payload: NetworkDefinition) -> ValidationResponse:
    errors = validate_network_definition(payload)
    return ValidationResponse(valid=not errors, errors=errors)


@router.post("/create", response_model=dict)
async def create_network(payload: NetworkDefinition) -> dict:
    errors = validate_network_definition(payload)
    if errors:
        raise HTTPException(status_code=422, detail=[error.model_dump() for error in errors])
    return {"valid": True, "network": payload.model_dump()}


@router.get("/status")
async def network_status() -> dict:
    return {"status": "ready", "schema_version": "1.0"}
