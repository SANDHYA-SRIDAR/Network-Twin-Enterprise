import { API_URL } from "@/lib/constants";
import { requestApi } from "@/lib/api-request";
import type { NetworkDefinition } from "@/lib/network-schema";
import type { SimulationMetrics } from "@/lib/failure-simulation";

// Display-only configured load ratio. No routing or predictive metric engine in the browser.
export function calculateLinkMetrics(link: {
  maxCapacityMbps: number;
  currentLoadMbps: number;
  [key: string]: unknown;
}) {
  return {
    utilizationPct:
      link.maxCapacityMbps > 0 ? (100 * link.currentLoadMbps) / link.maxCapacityMbps : 0,
  };
}

export async function evaluateTopology(
  topology: NetworkDefinition,
  source: string,
  target: string,
  offeredMbps: number,
  signal: AbortSignal,
): Promise<{ metrics: SimulationMetrics; assumptions: string[] }> {
  return requestApi<{ metrics: SimulationMetrics; assumptions: string[] }>(
    "analysis/evaluate",
    {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topology,
        traffic: { source_node_id: source, target_node_id: target, offered_mbps: offeredMbps },
      }),
    },
    { baseUrl: API_URL },
  );
}
