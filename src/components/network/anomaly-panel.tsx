import { useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  HelpCircle,
  Info,
  Loader2,
  Network,
  RotateCcw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  analyzeSavedTopology,
  analyzeStatelessTopology,
  explainAnomalies,
  type AnomalyAnalysisResponse,
  type AnomalyFinding,
  type AnomalyExplainResponse,
  type TrafficDemandPayload,
} from "@/lib/anomaly";
import type { NetworkDefinition } from "@/lib/network-schema";

export interface AnomalyPanelProps {
  topology?: NetworkDefinition | null | undefined;
  traffic?: TrafficDemandPayload | null | undefined;
}

function formatTarget(
  targetType: string,
  targetId: string,
  topology?: NetworkDefinition | null,
): string {
  if (!topology) return targetId;
  if (targetType === "node") {
    const node = topology.nodes?.find((n) => n.id === targetId);
    return node ? `${node.name} (${node.id})` : targetId;
  }
  if (targetType === "link") {
    const link = topology.links?.find((l) => l.id === targetId);
    if (!link) return targetId;
    const src =
      topology.nodes?.find((n) => n.id === link.source_node_id)?.name ??
      link.source_node_id;
    const dst =
      topology.nodes?.find((n) => n.id === link.target_node_id)?.name ??
      link.target_node_id;
    return `${src} ↔ ${dst} (${link.id})`;
  }
  return targetId;
}

function tierLabel(tier: string): string {
  switch (tier) {
    case "structural_weak_point":
      return "Structural Weak Point";
    case "metric_outlier":
      return "Metric Outlier";
    case "configuration_issue":
      return "Configuration Issue";
    default:
      return tier;
  }
}

export function AnomalyPanel({ topology, traffic }: AnomalyPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnomalyAnalysisResponse | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<AnomalyExplainResponse | null>(
    null,
  );

  const runAnalysis = async () => {
    if (!topology) return;
    setLoading(true);
    setError(null);
    setExplanation(null);
    setExplainError(null);
    try {
      // First attempt saved topology analysis via authenticated endpoint
      let response: AnomalyAnalysisResponse;
      try {
        response = await analyzeSavedTopology(traffic);
      } catch {
        // Fall back to stateless analysis
        response = await analyzeStatelessTopology(topology, traffic);
      }
      setResult(response);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Anomaly analysis failed.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleExplain = async () => {
    if (!result || !result.findings.length) return;
    setExplaining(true);
    setExplainError(null);
    try {
      const response = await explainAnomalies(result.findings, result.summary);
      setExplanation(response);
    } catch (err) {
      setExplainError(
        err instanceof Error
          ? err.message
          : "Failed to generate anomaly explanation.",
      );
    } finally {
      setExplaining(false);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <Card className="border-border">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Network className="size-5 text-primary" />
              <CardTitle className="text-xl">
                Topology Anomaly Detection
              </CardTitle>
            </div>
            <CardDescription className="mt-1">
              Static topology inspection for single points of failure,
              metric outliers, and configuration flaws.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={runAnalysis}
              disabled={loading || !topology}
              size="sm"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  Analyzing…
                </>
              ) : (
                <>
                  <ShieldAlert className="mr-2 size-4" />
                  {result ? "Re-analyze Topology" : "Analyze Topology Anomalies"}
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Honest labeling banner */}
        <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-900 dark:text-amber-200">
          <Info className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <span className="font-semibold uppercase tracking-wider">
              Modeled data / synthetic baseline — not live telemetry:
            </span>{" "}
            Findings are calculated via structural graph algorithms (Tier 1) and
            multidimensional deviations from a synthetic enterprise baseline (Tier
            2). Deterministic rule findings are primary; ML findings are
            experimental.
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Click <strong>Analyze Topology Anomalies</strong> to inspect the
            current network for structural vulnerabilities and metric anomalies.
          </div>
        )}

        {result && (
          <>
            {/* Status & Summary Stats */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border bg-background p-3">
                <p className="text-xs text-muted-foreground">Total Findings</p>
                <p className="mt-1 text-2xl font-semibold">
                  {result.summary.total_findings ?? result.findings.length}
                </p>
              </div>
              <div className="rounded-lg border bg-background p-3">
                <p className="text-xs text-muted-foreground">
                  Structural Weak Points
                </p>
                <p className="mt-1 text-2xl font-semibold text-destructive">
                  {result.summary.structural_weak_points ?? 0}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Bridges &amp; articulation points
                </p>
              </div>
              <div className="rounded-lg border bg-background p-3">
                <p className="text-xs text-muted-foreground">Metric Outliers</p>
                <p className="mt-1 text-2xl font-semibold text-amber-600">
                  {result.summary.metric_outliers ?? 0}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Latency, loss &amp; load divergence
                </p>
              </div>
              <div className="rounded-lg border bg-background p-3">
                <p className="text-xs text-muted-foreground">ML Engine Status</p>
                <div className="mt-1 flex items-center gap-1.5">
                  {result.ml_status === "evaluated" && (
                    <Badge variant="secondary" className="border border-purple-500/30 text-purple-700 bg-purple-50">
                      Evaluated
                    </Badge>
                  )}
                  {result.ml_status === "skipped_insufficient_peer_context" && (
                    <Badge variant="outline" className="border-amber-500 text-amber-600">
                      Skipped (Small Peer Group)
                    </Badge>
                  )}
                  {result.ml_status === "skipped_too_small" && (
                    <Badge variant="outline" className="border-amber-500 text-amber-600">
                      Skipped (&lt; 3 nodes)
                    </Badge>
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {result.ml_status === "evaluated"
                    ? "Trained on synthetic enterprise baseline"
                    : "Rules active; ML bypassed to prevent false positives"}
                </p>
              </div>
            </div>

            {/* Findings Table */}
            {result.findings.length === 0 ? (
              <div className="flex items-center gap-2 rounded-md border border-green-500/20 bg-green-500/5 p-4 text-sm text-green-700 dark:text-green-300">
                <CheckCircle2 className="size-4 shrink-0" />
                <span>
                  No topology anomalies detected. The network exhibits no single
                  points of failure or baseline metric outliers.
                </span>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full min-w-[700px] text-left text-xs">
                  <thead className="bg-muted/40">
                    <tr>
                      <th className="p-2.5">Target</th>
                      <th className="p-2.5">Category</th>
                      <th className="p-2.5">Issue</th>
                      <th className="p-2.5">Detection Method</th>
                      <th className="p-2.5">Severity</th>
                      <th className="p-2.5 text-right">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.findings.map((f) => {
                      const isExpanded = expandedId === f.id;
                      const hasRule = f.methods.includes("rule");
                      const hasML = f.methods.includes("isolation_forest");
                      return (
                        <tr
                          key={f.id}
                          className="border-t hover:bg-muted/10 transition-colors"
                        >
                          <td className="p-2.5">
                            <div className="font-medium text-foreground">
                              {formatTarget(f.target_type, f.target_id, topology)}
                            </div>
                            <div className="font-mono text-[10px] text-muted-foreground">
                              {f.target_type}:{f.target_id}
                            </div>
                          </td>
                          <td className="p-2.5">
                            <span className="font-medium">
                              {tierLabel(f.tier)}
                            </span>
                          </td>
                          <td className="p-2.5">
                            <div>{f.title}</div>
                            <div className="text-[11px] text-muted-foreground">
                              {f.explanation}
                            </div>
                          </td>
                          <td className="p-2.5">
                            <div className="flex flex-wrap items-center gap-1">
                              {hasRule && (
                                <Badge
                                  variant="outline"
                                  className="text-[10px]"
                                >
                                  Rule
                                </Badge>
                              )}
                              {hasML && (
                                <Badge
                                  variant="secondary"
                                  className="border border-purple-500/30 text-purple-700 bg-purple-50 text-[10px]"
                                  title="Evaluated on synthetic injected anomalies only (F1 = 0.36 vs baseline 0.67)"
                                >
                                  ML (experimental)
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="p-2.5">
                            {f.severity >= 0.8 ? (
                              <Badge variant="destructive" className="text-[10px]">
                                High ({f.severity.toFixed(2)})
                              </Badge>
                            ) : f.severity >= 0.5 ? (
                              <Badge
                                variant="outline"
                                className="border-amber-500 text-amber-600 text-[10px]"
                              >
                                Medium ({f.severity.toFixed(2)})
                              </Badge>
                            ) : (
                              <Badge variant="secondary" className="text-[10px]">
                                Low ({f.severity.toFixed(2)})
                              </Badge>
                            )}
                          </td>
                          <td className="p-2.5 text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              onClick={() => toggleExpand(f.id)}
                            >
                              {isExpanded ? (
                                <ChevronUp className="size-3.5" />
                              ) : (
                                <ChevronDown className="size-3.5" />
                              )}
                              <span className="sr-only">Toggle details</span>
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Expanded Evidence Row */}
            {expandedId && (
              <div className="rounded-md border bg-muted/20 p-3 text-xs">
                {(() => {
                  const finding = result.findings.find((f) => f.id === expandedId);
                  if (!finding) return null;
                  return (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between font-medium">
                        <span>Evidence for {finding.title}</span>
                        <span className="font-mono text-muted-foreground text-[10px]">
                          Anomaly Score: {finding.score.toFixed(4)}
                        </span>
                      </div>
                      <pre className="overflow-x-auto rounded bg-muted/60 p-2 font-mono text-[11px] text-muted-foreground">
                        {JSON.stringify(finding.evidence, null, 2)}
                      </pre>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Methodology Note */}
            <p className="text-[11px] text-muted-foreground italic">
              * ML findings are labeled &quot;ML (experimental)&quot; and evaluated
              on synthetic injected anomalies only (F1 = 0.36 vs deterministic
              baseline F1 = 0.67). Rule findings (bridges, articulation points,
              traffic overloads, and configuration invariants) provide exact
              deterministic guarantees.
            </p>

            {/* Explain Section */}
            <div className="border-t pt-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Button
                  onClick={handleExplain}
                  disabled={explaining || result.findings.length === 0}
                  variant="outline"
                  size="sm"
                >
                  {explaining ? (
                    <>
                      <Loader2 className="mr-2 size-3.5 animate-spin" />
                      Generating Explanation…
                    </>
                  ) : (
                    <>
                      <Sparkles className="mr-2 size-3.5" />
                      Explain Detected Anomalies
                    </>
                  )}
                </Button>
                {explanation && (
                  <Badge variant="outline" className="text-xs">
                    Mode: {explanation.mode === "ai_assisted" ? "AI-Assisted" : "Deterministic Fallback"}
                  </Badge>
                )}
              </div>

              {explainError && (
                <div className="mt-2 text-xs text-destructive">
                  {explainError}
                </div>
              )}

              {explanation && (
                <div className="mt-3 space-y-3 rounded-lg border bg-background p-4 text-xs">
                  <div className="flex items-center justify-between gap-2 border-b pb-2">
                    <span className="font-semibold text-foreground">
                      Analysis Explanation
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      Provider status: {explanation.provider_status}
                    </span>
                  </div>
                  <p className="leading-relaxed text-muted-foreground">
                    {explanation.text}
                  </p>
                  {explanation.claims.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <p className="font-medium text-foreground">
                        Verified Evidence Claims:
                      </p>
                      <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                        {explanation.claims.map((claim, idx) => (
                          <li key={idx}>
                            <span className="font-mono">{String(claim.metric)}</span> ={" "}
                            <span className="font-medium text-foreground">
                              {String(claim.value)}
                            </span>
                            {claim.id && (
                              <span className="ml-1 text-muted-foreground">
                                ({String(claim.id)})
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-[10px] text-muted-foreground border-t pt-1.5">
                    Validation: {explanation.validation}
                  </p>
                </div>
              )}
            </div>

            {/* Assumptions */}
            {result.assumptions.length > 0 && (
              <div className="space-y-1 text-xs text-muted-foreground">
                <span className="font-medium">Model Assumptions:</span>
                {result.assumptions.map((assumption, idx) => (
                  <p
                    key={idx}
                    className="rounded bg-muted/30 px-2 py-1 text-[11px]"
                  >
                    {assumption}
                  </p>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
