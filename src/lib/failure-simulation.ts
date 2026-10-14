import { API_URL } from '@/lib/constants';
import type { NetworkDefinition } from '@/lib/network-schema';
import type { ScenarioType } from '@/lib/scenario';

export type SimulationMetrics = {
  packets_sent: number;
  packets_delivered: number;
  packets_dropped: number;
  packet_loss_pct: number;
  average_latency_ms: number | null;
  maximum_latency_ms: number | null;
  offered_traffic_mbps: number;
  throughput_mbps: number;
  path_capacity_mbps: number;
  mean_link_utilization_pct: number;
  reachable_nodes: number;
  total_nodes: number;
  unreachable_nodes: number;
  active_links: number;
  failed_links: number;
  congested_links: number;
  bottleneck_link_ids: string[];
  connectivity_pct: number;
  flow_connected: boolean;
  route_node_ids: string[];
  route_link_ids: string[];
  links: Array<{
    id: string;
    source_node_id: string;
    target_node_id: string;
    status: string;
    configured_capacity_mbps: number | null;
    effective_capacity_mbps: number;
    offered_traffic_mbps: number;
    achieved_throughput_mbps: number;
    utilization_pct: number;
    latency_ms: number | null;
    packet_loss_pct: number | null;
    congested: boolean;
    on_route: boolean;
  }>;
  provenance: 'simulated';
  stage: string;
};

export type FailureSimulationResult = {
  experiment_id: string;
  status: 'completed';
  scenario_type: ScenarioType;
  engine_version: string;
  provenance: 'simulated';
  assumptions: string[];
  topology_fingerprint: string;
  baseline_topology: NetworkDefinition;
  failed_topology: NetworkDefinition;
  baseline_metrics: SimulationMetrics;
  failed_metrics: SimulationMetrics;
  failure_steps: Array<Record<string, unknown>>;
  modernization: null | {
    resolved: boolean;
    summary: string;
    recommendation: Record<string, unknown>;
    metrics: SimulationMetrics;
    steps: Array<Record<string, unknown>>;
  };
  modernized_topology: NetworkDefinition | null;
  modernized_metrics: SimulationMetrics | null;
  modernization_steps: Array<Record<string, unknown>>;
};

async function request<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/api/failure-simulation${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    let message = `Simulation API returned ${response.status}`;
    try {
      const body = await response.json() as { detail?: unknown };
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch { /* Keep the status fallback for non-JSON errors. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function loadSavedSimulationTopology(accessToken: string): Promise<{ topology_fingerprint: string; topology: NetworkDefinition }> {
  return request('/topology', accessToken);
}

export function runFailureSimulation(accessToken: string, body: {
  scenario_type: ScenarioType;
  parameters: Record<string, unknown>;
  traffic: { source_node_id: string; target_node_id: string; offered_mbps: number; duration_seconds: number; packet_size_bytes: number };
  topology_fingerprint: string;
}): Promise<FailureSimulationResult> {
  return request('/run', accessToken, { method: 'POST', body: JSON.stringify(body) });
}

export function modernizeSimulation(accessToken: string, experimentId: string): Promise<FailureSimulationResult> {
  return request(`/${encodeURIComponent(experimentId)}/modernize`, accessToken, { method: 'POST' });
}
