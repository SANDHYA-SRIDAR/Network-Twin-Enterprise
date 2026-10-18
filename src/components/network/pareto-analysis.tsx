import {
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import type { OptimizationResult, StrategyCandidate } from "@/lib/failure-simulation";
import { paretoPoints } from "@/lib/optimization-view";

export function ParetoAnalysis({
  optimization,
  candidates,
  onInspect,
}: {
  optimization: OptimizationResult;
  candidates: StrategyCandidate[];
  onInspect: (id: string) => void;
}) {
  const points = paretoPoints(candidates, optimization.pareto_candidate_ids);
  return (
    <section className="space-y-3 rounded border p-4" aria-label="Pareto analysis">
      <h3 className="font-medium">Pareto analysis — NSGA-II</h3>
      <p className="text-sm">
        {optimization.status === "completed"
          ? `${points.length} non-dominated alternatives among ${optimization.evaluated_configurations} evaluated configurations. Select a point or table row to inspect.`
          : optimization.status === "fallback"
            ? optimization.reason
            : "No evaluated candidate meets all recovery constraints. Inspect rejected alternatives and revise permitted actions or targets."}
      </p>
      <p className="text-xs text-muted-foreground">
        Cost versus finite mean latency is a two-dimensional projection of seven objectives, not the
        full Pareto ordering. These are modeled alternatives, not globally optimal or deployed
        configurations.
      </p>
      {points.length > 0 && (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 20, bottom: 25, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="cost"
                name="Change units"
                label={{ value: "Relative change units", position: "bottom" }}
              />
              <YAxis type="number" dataKey="latency" name="Mean latency" unit=" ms" />
              <Tooltip
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as (typeof points)[number] | undefined;
                  return active && point ? (
                    <div className="rounded border bg-background p-3 text-sm">
                      {point.title}
                      <br />
                      {point.cost} units · {point.latency} ms · {point.throughput} Mbps
                    </div>
                  ) : null;
                }}
              />
              <Scatter data={points} fill="#2563eb">
                {points.map((point) => (
                  <Cell
                    key={point.id}
                    onClick={() => onInspect(point.id)}
                    className="cursor-pointer"
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
      <details>
        <summary className="cursor-pointer text-sm">
          Optimizer settings, objectives and limitations
        </summary>
        <pre className="overflow-auto text-xs">{JSON.stringify(optimization, null, 2)}</pre>
      </details>
    </section>
  );
}
