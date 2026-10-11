from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

from app.config import settings
from app.services.ssh_client import (
    SSHAuthenticationError,
    SSHClient,
    SSHConfigurationMissingError,
    SSHUnreachableError,
)

router = APIRouter(prefix="/deploy", tags=["Deployment"])

class TopologyPayload(BaseModel):
    topology: Any  # The JSON representation of nodes and edges

@router.get("/status", response_model=dict)
async def deployment_status():
    """Classify VM connectivity and Mininet readiness without exposing SSH details."""
    try:
        ssh = SSHClient()
        try:
            ssh.exec_command(settings.mininet_check_command)
        except Exception:
            return {
                "connected": True,
                "vm_status": "Connected",
                "mininet_status": "Mininet Not Ready",
                "simulation_status": "Offline",
                "message": "SSH connected, but Mininet is not available on the VM.",
            }
        finally:
            ssh.close()
        return {
            "connected": True,
            "vm_status": "Connected",
            "mininet_status": "Ready",
            "simulation_status": "Idle",
            "message": "VM connection and Mininet readiness check succeeded.",
        }
    except SSHConfigurationMissingError:
        return {
            "connected": False,
            "vm_status": "Configuration Missing",
            "mininet_status": "Unknown",
            "simulation_status": "Offline",
            "message": "Configure SSH_HOST, SSH_USER, and SSH_KEY_PATH or SSH_PASSWORD.",
        }
    except SSHAuthenticationError:
        return {
            "connected": False,
            "vm_status": "Authentication Failed",
            "mininet_status": "Unknown",
            "simulation_status": "Offline",
            "message": "The VM rejected the configured SSH credentials.",
        }
    except SSHUnreachableError:
        return {
            "connected": False,
            "vm_status": "Unreachable",
            "mininet_status": "Unknown",
            "simulation_status": "Offline",
            "message": "The configured VM could not be reached before the connection timeout.",
        }
    except Exception:
        return {
            "connected": False,
            "vm_status": "Unreachable",
            "mininet_status": "Unknown",
            "simulation_status": "Offline",
            "message": "The VM connectivity check failed.",
        }

