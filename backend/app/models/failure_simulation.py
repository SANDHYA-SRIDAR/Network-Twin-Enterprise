from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import ConfigDict, Field, model_validator
from app.models.network import BaseModel

from app.models.scenario import ScenarioType


class TrafficDemand(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
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


class OptimizerSettings(BaseModel):
    population_size: int = Field(default=16, ge=8, le=64)
    generations: int = Field(default=12, ge=2, le=50)
    seed: int = Field(default=17, ge=0, le=2**31-1)
    timeout_seconds: float = Field(default=10, gt=0, le=30)
    crossover_probability: float = Field(default=0.9, gt=0, le=1)
    mutation_probability: float = Field(default=0.5, gt=0, le=1)
    minimum_delivery_ratio: float = Field(default=0.95, gt=0, le=1)


class ExperimentModernizeRequest(BaseModel):
    optimizer: Optional[OptimizerSettings] = None
    latency_target_ms: float = Field(default=50, gt=0, le=1_000_000, allow_inf_nan=False)
    weights: Dict[Literal["performance", "resilience", "feasibility", "cost"], float] = Field(default_factory=lambda: {"performance": 0.4, "resilience": 0.3, "feasibility": 0.2, "cost": 0.1})
    max_change_units: int = Field(default=100, ge=0, le=10000)
    allow_new_links: bool = True
    allow_repair: bool = True

    @model_validator(mode="after")
    def valid_weights(self):
        import math
        if set(self.weights) != {"performance", "resilience", "feasibility", "cost"} or any(not math.isfinite(v) or v < 0 for v in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("Supply four finite, nonnegative weights with a positive sum.")
        return self


class SimulationExperimentResponse(BaseModel):
    decisions: list[Dict[str, Any]] = Field(default_factory=list)
    analysis: Optional[Dict[str, Any]] = None
    traffic: Dict[str, Any] = Field(default_factory=dict)
    scenario_parameters: Dict[str, Any] = Field(default_factory=dict)
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
    assistant: Optional[Dict[str, Any]] = None


class CandidateDecisionRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    action: Literal["select", "accept", "reject"]
    topology_fingerprint: str = Field(min_length=1, max_length=128)
    proposal_revision: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=1000)


class SavedTopologyResponse(BaseModel):
    topology_fingerprint: str
    topology: Dict[str, Any]


class ScenarioOption(BaseModel):
    id: ScenarioType
    title: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
