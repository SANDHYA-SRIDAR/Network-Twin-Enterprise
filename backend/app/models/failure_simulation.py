from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.scenario import ScenarioType


class TrafficDemand(BaseModel):
    source_node_id: str
    target_node_id: str
    offered_mbps: float = Field(gt=0, le=1_000_000)
    duration_seconds: int = Field(default=60, ge=1, le=86_400)
    packet_size_bytes: int = Field(default=1500, ge=64, le=65_535)

    @model_validator(mode="after")
    def distinct_endpoints(self) -> "TrafficDemand":
        if self.source_node_id == self.target_node_id:
            raise ValueError("Traffic source and destination must be different devices.")
        return self


class FailureSimulationRequest(BaseModel):
    scenario_type: ScenarioType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    traffic: TrafficDemand
    topology_fingerprint: Optional[str] = None


class ExperimentModernizeRequest(BaseModel):
    pass


class SimulationExperimentResponse(BaseModel):
    experiment_id: str
    status: Literal["completed"]
    scenario_type: ScenarioType
    engine_version: str
    provenance: Literal["simulated"] = "simulated"
    assumptions: list[str] = Field(default_factory=list)
    topology_fingerprint: str
    baseline_topology: Dict[str, Any]
    failed_topology: Dict[str, Any]
    baseline_metrics: Dict[str, Any]
    failed_metrics: Dict[str, Any]
    failure_steps: list[Dict[str, Any]] = Field(default_factory=list)
    modernization: Optional[Dict[str, Any]] = None
    modernized_topology: Optional[Dict[str, Any]] = None
    modernized_metrics: Optional[Dict[str, Any]] = None
    modernization_steps: list[Dict[str, Any]] = Field(default_factory=list)


class SavedTopologyResponse(BaseModel):
    topology_fingerprint: str
    topology: Dict[str, Any]


class ScenarioOption(BaseModel):
    id: ScenarioType
    title: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
