"""Bounded synthetic traffic; never packet capture or a TCP implementation."""
from typing import Literal
from pydantic import Field, model_validator
from app.models.network import BaseModel, NetworkDefinition
from app.models.scenario import ScenarioType


class ApplicationFlow(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    application: str = Field(default="Application", min_length=1, max_length=100)
    users: int = Field(default=1, ge=1, le=100000)
    protocol: Literal["TCP", "UDP"] = "UDP"
    priority: int = Field(default=1, ge=0, le=3)
    source_node_id: str
    target_node_id: str
    offered_mbps: float = Field(gt=0, le=1000000)
    peak_multiplier: float = Field(default=1, ge=1, le=10)
    packet_size_bytes: int = Field(default=1500, ge=64, le=65535)

    @model_validator(mode="after")
    def endpoints(self):
        if self.source_node_id == self.target_node_id:
            raise ValueError("Choose distinct flow endpoints")
        return self


class PacketExperimentRequest(BaseModel):
    topology: NetworkDefinition
    flows: list[ApplicationFlow] = Field(min_length=1, max_length=8)
    scenario_type: ScenarioType | Literal["traffic_prioritization", "rerouting", "cloud_security", "load_balancer", "sd_wan"] = "link_failure"
    parameters: dict = Field(default_factory=dict)
    duration_seconds: float = Field(default=1, ge=0.1, le=5)
    queue_packets: int = Field(default=32, ge=1, le=512)
    seed: int = Field(default=17, ge=0, le=2147483647)
    optimize: bool = False

    @model_validator(mode="after")
    def unique_flows(self):
        if len({f.id for f in self.flows}) != len(self.flows):
            raise ValueError("Flow IDs must be unique")
        return self
