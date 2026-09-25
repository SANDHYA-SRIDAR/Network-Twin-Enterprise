from pydantic import BaseModel
from typing import List

class LinkTelemetry(BaseModel):
    source: str
    target: str
    latency_ms: float
    throughput_mbps: float
    packet_loss_pct: float
    status: str

class NodeTelemetry(BaseModel):
    node_id: str
    cpu_usage_pct: float
    mem_usage_pct: float
    status: str

class MininetTelemetry(BaseModel):
    timestamp: str
    nodes: List[NodeTelemetry]
    links: List[LinkTelemetry]
