"""API endpoints for topology anomaly detection and explanation."""
from __future__ import annotations

from typing import Annotated, Any, Optional
from fastapi import APIRouter, Body, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.auth import require_access_token
from app.models.anomaly import (
    AnomalyAnalysisRequest,
    AnomalyAnalysisResponse,
    AnomalyExplainRequest,
    AnomalyExplainResponse,
    AnomalySavedRequest,
)
from app.services.anomaly_detector import analyze_topology_anomalies
from app.services.assistant import explain_anomalies
from app.services.supabase_repository import repository

router = APIRouter(prefix="/anomalies", tags=["anomaly-detection"])
AccessToken = Annotated[str, Depends(require_access_token)]


@router.post("/analyze", response_model=AnomalyAnalysisResponse)
async def analyze_stateless_topology(request: AnomalyAnalysisRequest) -> AnomalyAnalysisResponse:
    """Stateless topology anomaly detection. Enforces canonical 500 node / 2000 link limits."""
    raw = request.topology if isinstance(request.topology, dict) else request.topology.model_dump()
    nodes = raw.get("nodes", []) if isinstance(raw, dict) else getattr(request.topology, "nodes", [])
    links = raw.get("links", []) if isinstance(raw, dict) else getattr(request.topology, "links", [])
    if len(nodes) > 500 or len(links) > 2000:
        raise HTTPException(
            status_code=413,
            detail="Topology exceeds the analytical limit of 500 devices and 2000 connections.",
        )
    from app.models.network import NetworkDefinition
    network = request.topology if isinstance(request.topology, NetworkDefinition) else NetworkDefinition.model_validate(raw)
    return await run_in_threadpool(analyze_topology_anomalies, network, request.traffic)


@router.post("/saved", response_model=AnomalyAnalysisResponse)
async def analyze_saved_topology(
    token: AccessToken,
    request: Optional[AnomalySavedRequest] = Body(default=None),
) -> AnomalyAnalysisResponse:
    """Analyze the authenticated user's current saved topology directly from Supabase."""
    user_id = await repository.user_id(token)
    network = await repository.load_topology(token, user_id)
    if len(network.nodes) > 500 or len(network.links) > 2000:
        raise HTTPException(
            status_code=413,
            detail="Topology exceeds the analytical limit of 500 devices and 2000 connections.",
        )
    traffic = request.traffic if request is not None else None
    return await run_in_threadpool(analyze_topology_anomalies, network, traffic)


@router.post("/explain", response_model=AnomalyExplainResponse)
async def explain_detected_anomalies(
    request: AnomalyExplainRequest,
    token: AccessToken,
) -> AnomalyExplainResponse:
    """Generate an evidence-grounded explanation for detected topology anomalies using the assistant."""
    # Authenticated endpoint - verify token validity via user_id check
    await repository.user_id(token)
    explanation = await explain_anomalies(request.findings, request.summary, request.question)
    return AnomalyExplainResponse.model_validate(explanation)
