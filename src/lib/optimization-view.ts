import type { StrategyCandidate } from "./failure-simulation";

export function paretoPoints(candidates: StrategyCandidate[], ids: string[]) {
  return candidates
    .filter(
      (c) =>
        ids.includes(c.id) &&
        c.feasible &&
        c.metrics.average_latency_ms !== null &&
        Number.isFinite(c.metrics.average_latency_ms) &&
        Number.isFinite(c.change_units),
    )
    .map((c) => ({
      id: c.id,
      title: c.title,
      cost: c.change_units,
      latency: c.metrics.average_latency_ms as number,
      throughput: c.metrics.throughput_mbps,
    }));
}

export function comparisonDemandText(baseline: number, scenario: number) {
  return baseline === scenario
    ? `Baseline and scenario use the same offered load (${baseline} Mbps); recovery uses that same demand.`
    : `Baseline offered load is ${baseline} Mbps. Scenario and recovery use ${scenario} Mbps; compare delivery as well as offered load.`;
}
