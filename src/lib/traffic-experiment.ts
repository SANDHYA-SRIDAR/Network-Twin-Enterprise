import type { NetworkDefinition } from "./network-schema";
import type { ScenarioType } from "./scenario";

export type ApplicationFlow = {
  id: string;
  application: string;
  users: number;
  protocol: "TCP" | "UDP";
  priority: number;
  source_node_id: string;
  target_node_id: string;
  offered_mbps: number;
  peak_multiplier: number;
  packet_size_bytes: number;
};
export type TrafficRequest = {
  topology: NetworkDefinition;
  flows: ApplicationFlow[];
  scenario_type:
    | ScenarioType
    | "traffic_prioritization"
    | "rerouting"
    | "cloud_security"
    | "load_balancer"
    | "sd_wan";
  parameters: Record<string, unknown>;
  duration_seconds: number;
  queue_packets: number;
  seed: number;
  optimize: boolean;
};
export type TrafficMetrics = {
  sent: number;
  delivered: number;
  dropped: number;
  pending: number;
  throughput_mbps: number;
  packet_loss_pct: number | null;
  average_latency_ms: number | null;
  connectivity_pct: number;
  mean_link_utilization_pct: number;
  flows: Array<{
    id: string;
    application: string;
    users: number;
    protocol: string;
    priority: number;
    throughput_mbps: number;
    packet_loss_pct: number | null;
    average_latency_ms: number | null;
    sent: number;
    delivered: number;
    dropped: number;
    pending: number;
    flow_connected: boolean;
    route_node_ids: string[];
    route_link_ids: string[];
  }>;
  links: Array<{
    id: string;
    status: string;
    congested: boolean;
    on_route: boolean;
    utilization_pct: number;
    queue_drops: number;
    random_drops: number;
    max_queue: number;
  }>;
  series: Array<{ time_seconds: number; throughput_mbps: number; dropped: number }>;
};
export type TrafficInsights = {
  level: string;
  score: number;
  reasons: string[];
  confidence: string;
  affected_applications: string[];
  affected_users: number;
  trained_model: false;
  method: string;
};
export type TrafficCandidate = {
  id: string;
  title: string;
  topology: NetworkDefinition;
  metrics: TrafficMetrics;
  insights: TrafficInsights;
  cost_units: number;
  changes: string[];
  feasible: boolean;
  targets_met: boolean;
  objectives: number[];
  constraints: string[];
};
export type TrafficResult = {
  baseline_topology: NetworkDefinition;
  failed_topology: NetworkDefinition;
  baseline_metrics: TrafficMetrics;
  failed_metrics: TrafficMetrics;
  insights: TrafficInsights;
  baseline_insights: TrafficInsights;
  candidates: TrafficCandidate[];
  selected_id: string;
  summary: string;
  recovery_targets_met: boolean;
  rerouted_flows: string[];
  request: TrafficRequest;
  structure: { communities: string[][]; modularity: number | null };
  limitations: string[];
  optimization: null | {
    status: string;
    reason?: string;
    scope: string;
    pareto_candidate_ids: string[];
  };
};

export function trafficChartRows(
  before: TrafficMetrics,
  after: TrafficMetrics,
  candidate?: TrafficMetrics,
) {
  return before.series.map((row, index) => ({
    time: row.time_seconds,
    original: row.throughput_mbps,
    scenario: after.series[index]?.throughput_mbps ?? null,
    proposed: candidate?.series[index]?.throughput_mbps ?? null,
  }));
}

export function trafficParetoPoints(
  candidates: TrafficCandidate[],
  ids: string[],
  axis: "latency" | "connectivity",
) {
  return candidates
    .filter(
      (c) =>
        ids.includes(c.id) &&
        c.feasible &&
        (axis !== "latency" || c.metrics.average_latency_ms !== null),
    )
    .map((c) => ({
      id: c.id,
      title: c.title,
      cost: c.cost_units,
      value: axis === "latency" ? c.metrics.average_latency_ms : c.metrics.connectivity_pct,
    }));
}
