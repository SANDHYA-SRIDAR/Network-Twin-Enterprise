import { authenticatedApi } from "@/lib/api";
import type { NetworkDefinition } from "@/lib/network-schema";
import type { ScenarioType } from "@/lib/scenario";

export type FlowImpact = {
  scenario_type: string;
  target_id: string;
  is_on_route: boolean;
  route_survived: boolean;
  route_changed: boolean;
  baseline_route_links: string[];
  failed_route_links: string[];
  baseline_bottleneck_mbps: number;
  failed_bottleneck_mbps: number;
  baseline_congested: boolean;
  failed_congested: boolean;
  baseline_congestion_loss_pct: number;
  failed_congestion_loss_pct: number;
  status_code: "off_route" | "disconnected" | "rerouted" | "survived" | "non_link_scenario";
  explanation: string;
};

export type SimulationMetrics = {
  queueing_status?: "estimated" | "unstable" | "unreachable";
  congestion_loss_pct?: number;
  link_medium_loss_pct?: number;
  flow_impact?: FlowImpact;
  propagation_delay_ms?: number | null;
  serialization_delay_ms?: number | null;
  queueing_delay_ms?: number | null;
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
  provenance: "simulated";
  stage: string;
};

export type FailureSimulationResult = {
  flow_impact?: FlowImpact | null;
  decisions?: CandidateDecision[];
  analysis?: NetworkAnalysis | null;
  traffic?: Record<string, unknown>;
  scenario_parameters?: Record<string, unknown>;
  assistant?: AssistantExplanation | null;
  experiment_id: string;
  status: "completed";
  scenario_type: ScenarioType;
  engine_version: string;
  provenance: "simulated";
  assumptions: string[];
  topology_fingerprint: string;
  baseline_topology: NetworkDefinition;
  failed_topology: NetworkDefinition;
  baseline_metrics: SimulationMetrics;
  failed_metrics: SimulationMetrics;
  failure_steps: Array<Record<string, unknown>>;
  modernization: null | {
    revision?: string;
    optimization?: OptimizationResult;
    selection_source?: string;
    service_outcome?: string;
    performance_improved?: boolean;
    disabled_link_ids?: string[];
    repaired_link_ids?: string[];
    resolved: boolean;
    summary: string;
    recommendation: Record<string, unknown>;
    metrics: SimulationMetrics;
    steps: Array<Record<string, unknown>>;
    selected_strategy_id?: string;
    criteria?: RankingCriteria;
    candidates?: StrategyCandidate[];
  };
  modernized_topology: NetworkDefinition | null;
  modernized_metrics: SimulationMetrics | null;
  modernization_steps: Array<Record<string, unknown>>;
};

// Keep caller signatures compatible; authentication is resolved fresh by the shared client.
function request<T>(path: string, _accessToken: string, init?: RequestInit): Promise<T> {
  return authenticatedApi<T>(`failure-simulation${path}`, init);
}

export function loadSavedSimulationTopology(
  accessToken: string,
): Promise<{ topology_fingerprint: string; topology: NetworkDefinition }> {
  return request("/topology", accessToken);
}

export function runFailureSimulation(
  accessToken: string,
  body: {
    scenario_type: ScenarioType;
    parameters: Record<string, unknown>;
    traffic: {
      source_node_id: string;
      target_node_id: string;
      offered_mbps: number;
      duration_seconds: number;
      packet_size_bytes: number;
    };
    topology_fingerprint: string;
  },
): Promise<FailureSimulationResult> {
  return request("/run", accessToken, { method: "POST", body: JSON.stringify(body) });
}

export function modernizeSimulation(
  accessToken: string,
  experimentId: string,
  criteria?: RankingCriteria,
): Promise<FailureSimulationResult> {
  return request(`/${encodeURIComponent(experimentId)}/modernize`, accessToken, {
    method: "POST",
    ...(criteria ? { body: JSON.stringify(criteria) } : {}),
  });
}

export type RankingCriteria = {
  optimizer?: OptimizerSettings | null;
  weights: { performance: number; resilience: number; feasibility: number; cost: number };
  max_change_units: number;
  latency_target_ms: number;
  allow_new_links: boolean;
  allow_repair: boolean;
};
export type StrategyCandidate = {
  origin?: "nsga2";
  encoding?: number[];
  objectives?: number[];
  pareto?: boolean;
  risk_analysis?: NetworkAnalysis;
  id: string;
  title: string;
  topology: NetworkDefinition;
  metrics: SimulationMetrics;
  score: number;
  components: Record<string, number>;
  change_units: number;
  changes: string[];
  feasible: boolean;
  feasibility_status: string;
  constraints: string[];
  trade_offs: string[];
  resilience_test: { survived: number; tested: number; type: string };
};
export type OptimizerSettings = {
  population_size: number;
  generations: number;
  seed: number;
  timeout_seconds: number;
  crossover_probability: number;
  mutation_probability: number;
  minimum_delivery_ratio: number;
};
export type OptimizationResult = {
  status: "completed" | "no_feasible_candidates" | "fallback";
  algorithm: string;
  reason?: string;
  objectives: string[];
  parameters: OptimizerSettings;
  pareto_candidate_ids: string[];
  evaluated_configurations?: number;
  generations_completed?: number;
  limitations: string[];
  rejected_encodings?: Array<{ encoding: number[]; constraints: string[] }>;
};
export type CandidateDecision = {
  candidate_id: string;
  action: "select" | "accept" | "reject";
  created_at: string;
  note: string;
  scope: "experiment_plan_only";
  canonical_topology_changed: false;
};
export function decideSimulationCandidate(
  accessToken: string,
  experimentId: string,
  body: {
    candidate_id: string;
    action: CandidateDecision["action"];
    topology_fingerprint: string;
    proposal_revision: string;
    note: string;
  },
): Promise<FailureSimulationResult> {
  return request(`/${encodeURIComponent(experimentId)}/decision`, accessToken, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
export type NetworkAnalysis = {
  method: string;
  trained_model: boolean;
  provenance: string;
  score: number;
  threshold: number;
  flagged: boolean;
  features: Record<string, number | boolean | null>;
  findings: Array<{ rule: string; severity: number; explanation: string }>;
  limitations: string[];
  structure?: {
    communities: string[][];
    modularity: number | null;
    bridge_link_ids: string[];
    connected_components: string[][];
    community_weight_basis: string;
  };
};
export type AssistantExplanation = {
  validation?: string;
  validated_claims?: Array<Record<string, unknown>>;
  mode: "deterministic" | "ai_assisted";
  text: string;
  provider_status: string;
  evidence: Record<string, unknown>;
  question: string;
};
export type ExperimentSummary = {
  id: string;
  scenario_id: string;
  created_at: string;
  engine_version: string;
  status: string;
};
export const listSimulationExperiments = (token: string) =>
  request<{ experiments: ExperimentSummary[] }>("/experiments", token);
export const loadSimulationExperiment = (token: string, id: string) =>
  request<FailureSimulationResult>(`/experiments/${encodeURIComponent(id)}`, token);
export const explainSimulation = (token: string, id: string, question: string) =>
  request<AssistantExplanation>(`/${encodeURIComponent(id)}/assistant`, token, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
