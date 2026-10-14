export type SimulationNode = { id: string; status: string };
export type SimulationLink = {
  id: string;
  source: string;
  target: string;
  status: string;
  baseLatencyMs: number;
  maxCapacityMbps: number;
  currentLoadMbps: number;
  priorityLoadMbps?: number;
  qos?: boolean;
};

export type PathMetrics = {
  connected: boolean;
  path: string[];
  latencyMs: number | null;
  priorityLatencyMs: number | null;
  throughputMbps: number;
  packetLossPct: number;
};

export function calculateLinkMetrics(link: SimulationLink) {
  const capacity = Math.max(link.maxCapacityMbps, 0.001);
  const utilizationPct = (link.currentLoadMbps / capacity) * 100;
  const safeUtilization = Math.min(Math.max(utilizationPct, 0), 99.9);
  const congestionLatencyMs = safeUtilization > 70
    ? (safeUtilization / (100 - safeUtilization)) * 10
    : 0;
  const priorityUtilization = ((link.qos ? link.priorityLoadMbps ?? link.currentLoadMbps : link.currentLoadMbps) / capacity) * 100;
  const safePriorityUtilization = Math.min(Math.max(priorityUtilization, 0), 99.9);
  const priorityLatencyMs = link.baseLatencyMs + (safePriorityUtilization > 70 ? (safePriorityUtilization / (100 - safePriorityUtilization)) * 10 : 0);
  return {
    utilizationPct,
    latencyMs: link.baseLatencyMs + congestionLatencyMs,
    priorityLatencyMs,
    packetLossPct: utilizationPct > 100 ? Math.min(100, (utilizationPct - 100) * 0.5) : 0,
    throughputMbps: Math.max(0, Math.min(link.currentLoadMbps, capacity)),
  };
}

export function findPathMetrics(nodes: SimulationNode[], links: SimulationLink[], source: string, target: string): PathMetrics {
  const availableNodes = new Set(nodes.filter(node => !isFailed(node.status)).map(node => node.id));
  if (!availableNodes.has(source) || !availableNodes.has(target)) return disconnected();
  const distances = new Map<string, number>([[source, 0]]);
  const previous = new Map<string, string>();
  const previousLink = new Map<string, string>();
  const remaining = new Set(availableNodes);
  while (remaining.size) {
    let current: string | undefined;
    for (const id of remaining) if (current === undefined || (distances.get(id) ?? Infinity) < (distances.get(current) ?? Infinity)) current = id;
    if (!current || !Number.isFinite(distances.get(current))) break;
    remaining.delete(current);
    if (current === target) break;
    for (const link of links) {
      if (isFailed(link.status)) continue;
      const neighbor = link.source === current ? link.target : link.target === current ? link.source : undefined;
      if (!neighbor || !remaining.has(neighbor)) continue;
      const weight = calculateLinkMetrics(link).latencyMs;
      const next = (distances.get(current) ?? Infinity) + weight;
      if (next < (distances.get(neighbor) ?? Infinity)) {
        distances.set(neighbor, next);
        previous.set(neighbor, current);
        previousLink.set(neighbor, link.id);
      }
    }
  }
  if (source !== target && !previous.has(target)) return disconnected();
  const path = [target];
  const pathLinkIds: string[] = [];
  while (path[0] !== source) {
    const current = path[0];
    if (!current) return disconnected();
    const parent = previous.get(current);
    if (!parent) return disconnected();
    const linkId = previousLink.get(current);
    if (!linkId) return disconnected();
    pathLinkIds.unshift(linkId);
    path.unshift(parent);
  }
  const pathLinkSet = new Set(pathLinkIds);
  const pathLinks = links.filter(link => pathLinkSet.has(link.id));
  const metrics = pathLinks.map(calculateLinkMetrics);
  return {
    connected: true,
    path,
    latencyMs: metrics.reduce((sum, metric) => sum + metric.latencyMs, 0),
    priorityLatencyMs: metrics.reduce((sum, metric) => sum + metric.priorityLatencyMs, 0),
    throughputMbps: metrics.length ? Math.min(...metrics.map(metric => metric.throughputMbps)) : 0,
    packetLossPct: metrics.length ? 100 * (1 - metrics.reduce((success, metric) => success * (1 - metric.packetLossPct / 100), 1)) : 0,
  };
}

export function isFailed(status: string) {
  return ["failed", "down", "offline"].includes(status.toLowerCase());
}

function disconnected(): PathMetrics {
  return { connected: false, path: [], latencyMs: null, priorityLatencyMs: null, throughputMbps: 0, packetLossPct: 100 };
}
