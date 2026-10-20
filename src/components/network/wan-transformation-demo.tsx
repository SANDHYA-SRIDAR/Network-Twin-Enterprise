import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SimulationTopology } from "@/components/network/simulation-topology";
import { authenticatedApi } from "@/lib/api";
import type { NetworkDefinition } from "@/lib/network-schema";
import type { FailureSimulationResult } from "@/lib/failure-simulation";

type DemoResult = FailureSimulationResult & {
  topology_source: string;
  requirement_met: boolean;
  require_continuity: boolean;
};

export function WanTransformationDemo({ saved }: { saved?: NetworkDefinition }) {
  const [continuity, setContinuity] = useState(true);
  const [offered, setOffered] = useState(100);
  const [result, setResult] = useState<DemoResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await authenticatedApi<DemoResult>("analysis/wan-demo", {
          method: "POST",
          body: JSON.stringify({
            topology: saved ?? null,
            require_continuity: continuity,
            offered_mbps: offered,
          }),
        }),
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not evaluate WAN options.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="rounded-lg border p-4">
      <summary className="cursor-pointer font-semibold">
        Branch WAN transformation demonstration
      </summary>
      <div className="mt-4 space-y-4">
        <p className="text-sm text-muted-foreground">
          Compare repairing a single WAN connection with an SD-WAN edge and independent uplinks.
          Uses a compatible saved snapshot with WAN roles; otherwise uses a labeled reusable
          example. Nothing is saved or deployed.
        </p>
        <fieldset disabled={busy} className="flex flex-wrap items-center gap-4">
          <label className="text-sm">
            <input
              type="checkbox"
              checked={continuity}
              onChange={(event) => setContinuity(event.target.checked)}
            />{" "}
            Require service during the primary WAN outage
          </label>
          <label className="text-sm">
            Offered traffic (Mbps)
            <Input
              type="number"
              min="0.01"
              max="1000000"
              value={offered}
              onChange={(event) => setOffered(Number(event.target.value))}
            />
          </label>
          <Button
            disabled={busy || !Number.isFinite(offered) || offered <= 0 || offered > 1000000}
            onClick={run}
          >
            {busy ? "Evaluating WAN options..." : "Run WAN demonstration"}
          </Button>
        </fieldset>
        {busy && <p role="status">Evaluating original, failed, repair and transformed graphs...</p>}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {result && (
          <>
            <p className="rounded bg-muted p-3 text-sm">
              <strong>Analytical simulation:</strong> {result.topology_source}. Requirement:{" "}
              {result.require_continuity
                ? "service must continue during the primary WAN outage"
                : "restoring service by repair is sufficient"}
              .
            </p>
            <div className="grid gap-4 xl:grid-cols-2">
              <SimulationTopology
                compact
                network={result.baseline_topology}
                metrics={result.baseline_metrics}
                title="Original single-WAN network"
              />
              <SimulationTopology
                compact
                network={result.failed_topology}
                metrics={result.failed_metrics}
                title="Primary WAN failure"
              />
            </div>
            <p>
              <strong>Recommended action: </strong>
              {result.requirement_met
                ? result.modernization?.candidates?.find(
                    (c) => c.id === result.modernization?.selected_strategy_id,
                  )?.title
                : "No evaluated option meets the requirement"}
            </p>
            <p className="text-sm">
              <strong>Why: </strong>
              {String(result.modernization?.recommendation["rationale"] ?? "")}
            </p>
            {result.modernized_topology && result.modernized_metrics && (
              <SimulationTopology
                compact
                network={result.modernized_topology}
                comparisonNetwork={result.failed_topology}
                metrics={result.modernized_metrics}
                title={
                  result.modernization?.selected_strategy_id === "sdwan"
                    ? "Transformed architecture during primary WAN outage"
                    : "Selected option (repair assumes WAN restoration)"
                }
              />
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    <th className="p-2">Metric</th>
                    <th>Original network</th>
                    <th>After WAN failure</th>
                    <th>Selected solution</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      "throughput_mbps",
                      "packet_loss_pct",
                      "average_latency_ms",
                      "flow_connected",
                    ] as const
                  ).map((key) => (
                    <tr className="border-t" key={key}>
                      <th className="p-2">
                        {
                          {
                            throughput_mbps: "Throughput (Mbps)",
                            packet_loss_pct: "Packet loss (%)",
                            average_latency_ms: "Average latency (ms)",
                            flow_connected: "Connectivity",
                          }[key]
                        }
                      </th>
                      {[
                        result.baseline_metrics,
                        result.failed_metrics,
                        result.modernized_metrics,
                      ].map((metrics, index) => (
                        <td key={index}>
                          {metrics == null || metrics[key] == null
                            ? "Unavailable"
                            : typeof metrics[key] === "boolean"
                              ? metrics[key]
                                ? "Connected"
                                : "Disconnected"
                              : Number(metrics[key]).toFixed(2)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-sm">
              All options use the same offered traffic. The transformation keeps the primary failure
              active; repair metrics assume the failed WAN is restored. The outage checks below
              reapply the same primary failure to every option.
            </p>
            <details>
              <summary className="cursor-pointer">
                Advanced Details: WAN outage checks and assumptions
              </summary>
              <pre className="max-h-80 overflow-auto text-xs">
                {JSON.stringify(
                  { candidates: result.modernization?.candidates, assumptions: result.assumptions },
                  null,
                  2,
                )}
              </pre>
            </details>
            <p className="text-xs text-muted-foreground">
              Independent provider paths are a design assumption. SD-WAN denotes the edge role and
              dual-path architecture; the simulator calculates routes, not SD-WAN protocols or
              failover time. Shared LAN, edge and destination failures remain possible. No real
              packets are sent.
            </p>
          </>
        )}
      </div>
    </details>
  );
}
