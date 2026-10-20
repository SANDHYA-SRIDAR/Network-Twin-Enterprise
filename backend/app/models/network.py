from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from datetime import datetime
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, field_validator, model_validator


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def finite_json_values(cls, value):
        import math
        def check(item):
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("Nonfinite numbers are not supported, including in metadata.")
            if isinstance(item, dict):
                for child in item.values():
                    check(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    check(child)
        check(value)
        return value

DeviceType = Literal["router", "switch", "hub", "access_point", "pc", "server", "load_balancer"]
CableType = Literal["straight-through", "crossover", "fiber", "serial", "console"]
InterfaceType = Literal["ethernet", "serial", "console"]


class IPConfiguration(BaseModel):
    ip_address: str
    subnet_mask: str = "255.255.255.0"
    prefix_length: int = Field(default=24, ge=0, le=32)
    gateway: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def consistent_mask(cls, values):
        from ipaddress import IPv4Network
        values = dict(values)
        mask = values.get("subnet_mask")
        prefix = values.get("prefix_length")
        if mask is not None:
            actual = IPv4Network(f"0.0.0.0/{mask}").prefixlen
            if prefix is not None and actual != prefix:
                raise ValueError("Subnet mask and prefix length disagree.")
            values["prefix_length"] = actual
        elif prefix is not None:
            values["subnet_mask"] = str(IPv4Network(f"0.0.0.0/{prefix}").netmask)
        return values

    @field_validator("gateway")
    @classmethod
    def valid_gateway(cls, value):
        from ipaddress import IPv4Address
        if value is not None:
            IPv4Address(value)
        return value

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
    status: Literal["up", "active", "down", "offline", "failed", "unavailable", "degraded"] = "up"
    bandwidth_mbps: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    ip_configuration: Optional[IPConfiguration] = None
    mac_address: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    hostname: Optional[str] = None
    model: Optional[str] = None
    device_type: DeviceType
    role: str = "endpoint"
    status: Literal["active", "failed", "unavailable", "down", "offline", "degraded"] = "active"
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
    id: str = Field(min_length=1, max_length=200)
    source_node_id: str
    target_node_id: str
    source_interface_id: Optional[str] = None
    target_interface_id: Optional[str] = None
    cable_type: CableType = "straight-through"
    bandwidth_mbps: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    delay_ms: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    packet_loss_pct: Optional[float] = Field(default=None, ge=0, le=100)
    status: Literal["active", "failed", "unavailable", "down", "offline", "degraded"] = "active"
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
    duration_seconds: int = Field(default=300, ge=1, le=86400)


class NetworkDefinition(BaseModel):
    directed: Literal[False] = False
    id: str = "unsaved"
    version: str = "1.0"
    owner_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    name: str
    description: str = ""
    nodes: List[NodeDefinition] = Field(max_length=500)
    links: List[LinkDefinition] = Field(default_factory=list, max_length=2000)
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
