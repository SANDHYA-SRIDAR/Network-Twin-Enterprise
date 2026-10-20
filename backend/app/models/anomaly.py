"""Schemas for topology anomaly detection and grounded explanations."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from app.models.failure_simulation import TrafficDemand
from app.models.network import NetworkDefinition


class AnomalyFinding(BaseModel):
    id: str
    target_type: Literal["link", "node", "topology"]
    target_id: str
    tier: Literal["structural_weak_point", "metric_outlier", "configuration_issue"]
    kind: str
    title: str
    severity: float = Field(ge=0.0, le=1.0)
    score: float
    methods: list[str]
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str


class AnomalyAnalysisRequest(BaseModel):
    topology: Any
    traffic: Optional[TrafficDemand] = None


class AnomalySavedRequest(BaseModel):
    traffic: Optional[TrafficDemand] = None


class AnomalyAnalysisResponse(BaseModel):
    findings: list[AnomalyFinding]
    summary: dict[str, Any]
    ml_status: Literal["evaluated", "skipped_too_small", "skipped_insufficient_peer_context"]
    reachability_sweep_capped: bool = False
    assumptions: list[str] = Field(default_factory=list)
    provenance: str = "modeled_analysis"
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class AnomalyExplainRequest(BaseModel):
    findings: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(
        default="Explain the detected topology anomalies and prioritize remediation.",
        min_length=1,
        max_length=2000,
    )


class AnomalyExplainResponse(BaseModel):
    mode: Literal["ai_assisted", "deterministic"]
    text: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    provider_status: str
    validation: str
