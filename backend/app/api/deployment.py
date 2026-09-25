from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from app.services.ssh_client import SSHClient

router = APIRouter(prefix="/deploy", tags=["Deployment"])

class TopologyPayload(BaseModel):
    topology: Any  # The JSON representation of nodes and edges

@router.get("/status", response_model=dict)
async def deployment_status():
    """Check SSH connectivity to the Ubuntu VM.
    Returns {'connected': True} if SSH succeeds, otherwise False.
    """
    try:
        ssh = SSHClient()
        ssh.close()
        return {"connected": True}
    except Exception:
        return {"connected": False}

