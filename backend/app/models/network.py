from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

DeviceType = Literal["router", "switch", "hub", "access_point", "pc", "server", "load_balancer"]
CableType = Literal["straight-through", "crossover", "fiber", "serial", "console"]
InterfaceType = Literal["ethernet", "serial", "console"]


class IPConfiguration(BaseModel):
    ip_address: str
    subnet_mask: str = "255.255.255.0"
    prefix_length: int = Field(default=24, ge=0, le=32)
    gateway: Optional[str] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        from ipaddress import IPv4Address

        try:
            IPv4Address(value)
        except ValueError as exc:
            raise ValueError(f"Invalid IPv4 address: {value}") from exc
        return value

    @field_validator("subnet_mask")
    @classmethod
    def validate_subnet_mask(cls, value: str) -> str:
        from ipaddress import IPv4Network

        try:
            IPv4Network(f"0.0.0.0/{value}", strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid subnet mask: {value}") from exc
        return value


class InterfaceDefinition(BaseModel):
    id: str
    name: str
    type: InterfaceType = "ethernet"
    status: str = "up"
    bandwidth_mbps: Optional[float] = None
    ip_configuration: Optional[IPConfiguration] = None
    mac_address: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeDefinition(BaseModel):
    id: str
    name: str
    device_type: DeviceType
    role: str = "endpoint"
    status: str = "active"
    interfaces: List[InterfaceDefinition] = Field(default_factory=list)
    resources: Dict[str, float] = Field(default_factory=dict)
    security_zone: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("interfaces")
    @classmethod
    def unique_interface_ids(cls, value: List[InterfaceDefinition]) -> List[InterfaceDefinition]:
        seen: set[str] = set()
        for item in value:
            if item.id in seen:
                raise ValueError(f"Duplicate interface id: {item.id}")
            seen.add(item.id)
        return value


class LinkDefinition(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    source_interface_id: Optional[str] = None
    target_interface_id: Optional[str] = None
    cable_type: CableType = "straight-through"
    bandwidth_mbps: float = 1000.0
    delay_ms: float = 1.0
    packet_loss_pct: float = 0.0
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RoutingConfiguration(BaseModel):
    static_routes: List[Dict[str, str]] = Field(default_factory=list)
    default_gateway: Optional[str] = None


class SecurityConfiguration(BaseModel):
    zone: str = "default"
    segmentation: List[str] = Field(default_factory=list)
    firewall_rules: List[str] = Field(default_factory=list)


class SimulationConfiguration(BaseModel):
    traffic_profile: str = "baseline"
    scenario_id: Optional[str] = None
    experiment_id: Optional[str] = None
    duration_seconds: int = 300


class NetworkDefinition(BaseModel):
    version: str = "1.0"
    name: str
    description: str = ""
    nodes: List[NodeDefinition]
    links: List[LinkDefinition] = Field(default_factory=list)
    routing: RoutingConfiguration = Field(default_factory=RoutingConfiguration)
    security: SecurityConfiguration = Field(default_factory=SecurityConfiguration)
    simulation: SimulationConfiguration = Field(default_factory=SimulationConfiguration)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    path: str
    code: str
    message: str


class ValidationResponse(BaseModel):
    valid: bool
    errors: List[ValidationIssue] = Field(default_factory=list)
