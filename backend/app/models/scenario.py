from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.network import NetworkDefinition

ScenarioType = Literal[
    "link_failure",
    "traffic_increase",
    "bandwidth_change",
    "redundancy_add",
    "device_failure",
    "segment_isolation",
    "capacity_increase",
    "cloud_migration",
]


class ScenarioMutation(BaseModel):
    type: ScenarioType
    target: Optional[str] = None
    node_id: Optional[str] = None
    link_id: Optional[str] = None
    value: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    name: str = "Scenario analysis"
    description: str = ""
    baseline: NetworkDefinition
    traffic: Dict[str, Any]
    scenario: ScenarioMutation
    assumptions: Dict[str, Any] = Field(default_factory=dict)


class ScenarioResult(BaseModel):
    id: str
    status: str
    baseline_name: str
    scenario_type: ScenarioType
    created_at: str
    summary: Dict[str, Any]
    baseline: Dict[str, Any]
    scenario: Dict[str, Any]
    evidence: List[str]
    provenance: str = "simulated"
