import { authenticatedApi } from "@/lib/api";
import { requestApi } from "@/lib/api-request";
import { API_URL } from "@/lib/constants";
import type { NetworkDefinition } from "@/lib/network-schema";

export type AnomalyFinding = {
  id: string;
  target_type: "link" | "node" | "topology";
  target_id: string;
  tier: "structural_weak_point" | "metric_outlier" | "configuration_issue";
  kind: string;
  title: string;
  severity: number;
  score: number;
  methods: string[];
  evidence: Record<string, unknown>;
  explanation: string;
};

export type AnomalyAnalysisResponse = {
  findings: AnomalyFinding[];
  summary: {
    total_findings: number;
    structural_weak_points: number;
    metric_outliers: number;
    configuration_issues: number;
    ml_outliers?: number;
    rule_findings?: number;
  } & Record<string, unknown>;
  ml_status: "evaluated" | "skipped_too_small" | "skipped_insufficient_peer_context";
  reachability_sweep_capped: boolean;
  assumptions: string[];
  provenance: string;
  model_metadata: Record<string, unknown>;
};

export type AnomalyClaim = {
  metric: string;
  value: string | number;
  id?: string;
};

export type AnomalyExplainResponse = {
  mode: "ai_assisted" | "deterministic";
  text: string;
  claims: AnomalyClaim[];
  provider_status: string;
  validation: string;
};

export type TrafficDemandPayload = {
  source_node_id: string;
  target_node_id: string;
  offered_mbps: number;
  duration_seconds?: number;
  packet_size_bytes?: number;
};

/**
 * Perform stateless anomaly analysis on a supplied network definition.
 */
export function analyzeStatelessTopology(
  topology: NetworkDefinition,
  traffic?: TrafficDemandPayload | null,
): Promise<AnomalyAnalysisResponse> {
  return requestApi<AnomalyAnalysisResponse>(
    "anomalies/analyze",
    {
      method: "POST",
      body: JSON.stringify({ topology, traffic: traffic ?? null }),
    },
    { baseUrl: API_URL },
  );
}

/**
 * Perform authenticated anomaly analysis on the user's saved topology in Supabase.
 */
export function analyzeSavedTopology(
  traffic?: TrafficDemandPayload | null,
): Promise<AnomalyAnalysisResponse> {
  return authenticatedApi<AnomalyAnalysisResponse>(
    "anomalies/saved",
    {
      method: "POST",
      body: JSON.stringify({ traffic: traffic ?? null }),
    },
  );
}

/**
 * Request an evidence-grounded explanation for detected topology anomalies.
 */
export function explainAnomalies(
  findings: AnomalyFinding[],
  summary: Record<string, unknown>,
  question = "Explain the detected topology anomalies and prioritize remediation.",
): Promise<AnomalyExplainResponse> {
  return authenticatedApi<AnomalyExplainResponse>(
    "anomalies/explain",
    {
      method: "POST",
      body: JSON.stringify({ findings, summary, question }),
    },
  );
}
