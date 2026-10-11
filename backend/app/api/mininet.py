import os

from fastapi import APIRouter
from app.models.mininet import MininetTelemetry
from app.services.mininet_service import MininetService

router = APIRouter(prefix="/mininet", tags=["Mininet"])

@router.get("/telemetry", response_model=MininetTelemetry)
async def get_telemetry():
    """
    Fetches the current real-time state of the Mininet simulation network.
    (Currently mocked to simulate the Ubuntu VM response)
    """
    use_real = os.getenv("USE_REAL_TELEMETRY", "false").lower() == "true"
    if use_real:
        return MininetService.get_real_telemetry()
    else:
        return MininetService.get_mock_telemetry()
