import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/custom-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { SimulationTopology } from "./simulation-topology";
import { ParetoAnalysis } from "./pareto-analysis";
import {
  explainSimulation,
  listSimulationExperiments,
  loadSimulationExperiment,
  modernizeSimulation,
  decideSimulationCandidate,
  type CandidateDecision,
  type ExperimentSummary,
  type FailureSimulationResult,
  type RankingCriteria,
} from "@/lib/failure-simulation";

const defaults: RankingCriteria = {
  weights: { performance: 0.4, resilience: 0.3, feasibility: 0.2, cost: 0.1 },
  max_change_units: 100,
  latency_target_ms: 50,
  allow_new_links: true,
  allow_repair: true,
};
const optimizerDefaults = {
  population_size: 16,
  generations: 12,
  seed: 17,
  timeout_seconds: 10,
  crossover_probability: 0.9,
  mutation_probability: 0.5,
  minimum_delivery_ratio: 0.95,
};

export function ExperimentTools({
  result,
  onResult,
  disabled = false,
  onBusyChange,
}: {
  result: FailureSimulationResult | null;
  onResult: (result: FailureSimulationResult) => void;
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [history, setHistory] = useState<ExperimentSummary[]>([]);
  const [criteria, setCriteria] = useState(defaults);
  const [selected, setSelected] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [decisionNote, setDecisionNote] = useState("");
  const [question, setQuestion] = useState(
    "Explain the failure and justify the selected recovery strategy and its trade-offs.",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const isBusy = busy || disabled;
  const candidate = result?.modernization?.candidates?.find((item) => item.id === selected);
  const candidates = result?.modernization?.candidates ?? [];
  const visibleCandidates = showAll
    ? candidates
    : candidates.filter((item) => item.origin !== "nsga2" || item.pareto);
  const token = async () => {
    const { data } = await supabase.auth.getSession();
    if (!data.session) throw new Error("Sign in again to access experiments.");
    return data.session.access_token;
  };
  useEffect(() => {
    let active = true;
    setLoadingHistory(true);
    setError("");
    void token()
      .then(listSimulationExperiments)
      .then((data) => {
        if (active) setHistory(data.experiments);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load history.");
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => {
      active = false;
    };
  }, [result?.experiment_id]);
  useEffect(() => {
    setSelected("");
    setCriteria(result?.modernization?.criteria ?? defaults);
  }, [result?.experiment_id, result?.modernization?.criteria]);
  const perform = async (action: () => Promise<void>) => {
    if (isBusy) return;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Experiment operation failed.");
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  };
  const exportResult = () => {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `experiment-${result.experiment_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const decide = (action: CandidateDecision["action"]) => {
    if (!result || !candidate || !result.modernization?.revision) return;
    if (
      action === "accept" &&
      !window.confirm(
        `Accept ${candidate.title} as an experiment plan for engineering review? This does not deploy or update the saved topology.`,
      )
    )
      return;
    void perform(async () =>
      onResult(
        await decideSimulationCandidate(await token(), result.experiment_id, {
          candidate_id: candidate.id,
          action,
          topology_fingerprint: result.topology_fingerprint,
          proposal_revision: result.modernization!.revision!,
          note: decisionNote,
        }),
      ),
    );
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recovery options, Pareto analysis and decision</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <details>
          <summary className="cursor-pointer text-sm">Saved experiment history</summary>
          <label className="mt-2 block text-sm">
            Saved experiments (latest 50)
            <select
              className="mt-2 w-full rounded border bg-background p-2"
              value={result?.experiment_id ?? ""}
              disabled={isBusy || loadingHistory}
              onChange={(event) => {
                const id = event.target.value;
                if (id)
                  void perform(async () =>
                    onResult(await loadSimulationExperiment(await token(), id)),
                  );
              }}
            >
              <option value="">
                {loadingHistory
                  ? "Loading saved experiments..."
                  : history.length
                    ? "Choose a saved experiment"
                    : "No saved experiments yet - run a simulation"}
              </option>
              {history.map((row) => (
                <option key={row.id} value={row.id}>
                  {new Date(row.created_at).toLocaleString()} · {row.scenario_id} ·{" "}
                  {row.engine_version}
                </option>
              ))}
            </select>
          </label>
        </details>
        {busy && (
          <p role="status" className="text-sm text-muted-foreground">
            Processing experiment; explanation requests may take up to 30 seconds...
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {result && (
          <>
            {result.analysis && (
              <details className="rounded border p-3">
                <summary className="cursor-pointer font-medium">
                  Structural analysis and rule-based findings
                </summary>
                <p className="mt-2 text-sm">
                  Analytical features, not live telemetry. No trained ML model. Rule severity{" "}
                  {result.analysis.score.toFixed(2)}; flag threshold {result.analysis.threshold}.
                  This is not a failure probability.
                </p>
                {result.analysis.structure && (
                  <p className="mt-2 text-sm">
                    Operational communities: {result.analysis.structure.communities.length};
                    modularity:{" "}
                    {result.analysis.structure.modularity?.toFixed(3) ?? "Undefined (no edges)"}.
                    Bridge connections:{" "}
                    {result.analysis.structure.bridge_link_ids.join(", ") || "None"}. Community
                    membership is structural, not an anomaly.
                  </p>
                )}
                <ul className="mt-2 list-disc pl-5 text-sm">
                  {result.analysis.findings.map((finding) => (
                    <li key={finding.rule}>{finding.explanation}</li>
                  ))}
                </ul>
                {!result.analysis.findings.length && (
                  <p className="text-sm">
                    No configured rule fired. This does not establish that the network is healthy.
                  </p>
                )}
                <details className="mt-2">
                  <summary>Features, communities and limitations</summary>
                  <pre className="overflow-auto text-xs">
                    {JSON.stringify(result.analysis, null, 2)}
                  </pre>
                </details>
              </details>
            )}
            <details>
              <summary className="cursor-pointer font-medium">
                Advanced criteria and optimizer settings
              </summary>
              <fieldset disabled={isBusy} className="mt-3 space-y-3">
                <p className="text-sm text-muted-foreground">
                  Set relative weights and a maximum change budget. Cost units are design estimates;
                  installation and hardware compatibility require review. Recovery requires at least{" "}
                  {((criteria.optimizer?.minimum_delivery_ratio ?? 0.95) * 100).toFixed(0)}%
                  delivery and the latency target.
                </p>
                <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  {(Object.keys(criteria.weights) as Array<keyof RankingCriteria["weights"]>).map(
                    (key) => (
                      <label key={key} className="text-sm capitalize">
                        {key} weight
                        <Input
                          type="number"
                          min="0"
                          step="0.1"
                          value={criteria.weights[key]}
                          onChange={(event) =>
                            setCriteria((value) => ({
                              ...value,
                              weights: { ...value.weights, [key]: Number(event.target.value) },
                            }))
                          }
                        />
                      </label>
                    ),
                  )}
                  <label className="text-sm">
                    Change budget
                    <Input
                      type="number"
                      min="0"
                      value={criteria.max_change_units}
                      onChange={(event) =>
                        setCriteria((value) => ({
                          ...value,
                          max_change_units: Number(event.target.value),
                        }))
                      }
                    />
                  </label>
                  <label className="text-sm">
                    Latency target (ms)
                    <Input
                      type="number"
                      min="0.01"
                      value={criteria.latency_target_ms}
                      onChange={(event) =>
                        setCriteria((value) => ({
                          ...value,
                          latency_target_ms: Number(event.target.value),
                        }))
                      }
                    />
                  </label>
                </div>
                <div className="flex flex-wrap gap-4 text-sm">
                  <label>
                    <input
                      type="checkbox"
                      checked={criteria.allow_new_links}
                      onChange={(event) =>
                        setCriteria((value) => ({
                          ...value,
                          allow_new_links: event.target.checked,
                        }))
                      }
                    />{" "}
                    Allow new connections
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={criteria.allow_repair}
                      onChange={(event) =>
                        setCriteria((value) => ({ ...value, allow_repair: event.target.checked }))
                      }
                    />{" "}
                    Allow repair
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {(["population_size", "generations", "seed"] as const).map((key) => (
                    <label key={key} className="text-sm">
                      {key.replaceAll("_", " ")}
                      <Input
                        type="number"
                        min={key === "population_size" ? 8 : key === "generations" ? 2 : 0}
                        max={
                          key === "population_size" ? 64 : key === "generations" ? 50 : 2147483647
                        }
                        value={(criteria.optimizer ?? optimizerDefaults)[key]}
                        onChange={(event) =>
                          setCriteria((value) => ({
                            ...value,
                            optimizer: {
                              ...(value.optimizer ?? optimizerDefaults),
                              [key]: Number(event.target.value),
                            },
                          }))
                        }
                      />
                    </label>
                  ))}
                </div>
              </fieldset>
            </details>
            <div className="flex gap-2">
              <Button
                disabled={isBusy}
                onClick={() =>
                  void perform(async () =>
                    onResult(
                      await modernizeSimulation(await token(), result.experiment_id, {
                        ...criteria,
                        optimizer: null,
                      }),
                    ),
                  )
                }
              >
                Evaluate and rank strategies
              </Button>
              <Button
                disabled={isBusy}
                onClick={() =>
                  void perform(async () =>
                    onResult(
                      await modernizeSimulation(await token(), result.experiment_id, {
                        ...criteria,
                        optimizer: criteria.optimizer ?? optimizerDefaults,
                      }),
                    ),
                  )
                }
              >
                Optimize recovery options (NSGA-II)
              </Button>
              <Button variant="outline" onClick={exportResult}>
                Export experiment JSON
              </Button>
            </div>
            {result.modernization?.optimization && (
              <ParetoAnalysis
                optimization={result.modernization.optimization}
                candidates={candidates}
                onInspect={setSelected}
              />
            )}
            {!!result.modernization?.candidates?.length && (
              <div className="overflow-x-auto">
                <label className="mb-2 block text-sm">
                  <input
                    type="checkbox"
                    checked={showAll}
                    onChange={(event) => setShowAll(event.target.checked)}
                  />{" "}
                  Show all evaluated and rejected candidates ({candidates.length})
                </label>
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr>
                      <th className="p-2">Strategy</th>
                      <th>Score</th>
                      <th>Delivered Mbps</th>
                      <th>Mean delay ms</th>
                      <th>Link outages survived</th>
                      <th>Change units</th>
                      <th>Constraints</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleCandidates.map((item) => (
                      <tr key={item.id} className="border-t">
                        <td className="p-2">
                          <button
                            className="text-left text-primary underline"
                            onClick={() => setSelected(item.id)}
                          >
                            {item.title}
                          </button>
                          {item.id === result.modernization?.selected_strategy_id && (
                            <span className="ml-2">(selected)</span>
                          )}
                          {item.pareto && <span className="ml-2 text-green-700">Pareto</span>}
                        </td>
                        <td>{item.score.toFixed(3)}</td>
                        <td>{item.metrics.throughput_mbps}</td>
                        <td>
                          {item.metrics.average_latency_ms ??
                            item.metrics.queueing_status ??
                            "Unsupported"}
                        </td>
                        <td>
                          {item.resilience_test.survived}/{item.resilience_test.tested}
                        </td>
                        <td>{item.change_units}</td>
                        <td>
                          {item.feasible
                            ? "Eligible; engineering review required"
                            : item.constraints.join(", ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {candidate && (
              <section className="space-y-3">
                <h3 className="font-medium">Inspect: {candidate.title}</h3>
                <SimulationTopology
                  network={candidate.topology}
                  metrics={candidate.metrics}
                  title={candidate.title}
                />
                <p className="text-sm">
                  {candidate.feasibility_status}. {candidate.trade_offs.join(" ")}
                </p>
                <p className="text-sm">Changes: {candidate.changes.join("; ") || "None"}</p>
                {candidate.objectives && (
                  <p className="text-xs">
                    Objectives (minimize, in optimizer order):{" "}
                    {candidate.objectives.map((value) => value.toFixed(4)).join(" / ")}
                  </p>
                )}
                {candidate.risk_analysis && (
                  <p className="text-sm">
                    Rule severity: {candidate.risk_analysis.score.toFixed(2)} (threshold{" "}
                    {candidate.risk_analysis.threshold}).
                    {candidate.risk_analysis.flagged
                      ? " Flagged for inspection; risk does not exclude this candidate."
                      : " No risk rule reached the threshold."}
                    {candidate.risk_analysis.findings
                      .map((finding) => ` ${finding.explanation}`)
                      .join("")}
                  </p>
                )}
                <details>
                  <summary>Detailed component scores</summary>
                  <pre className="overflow-auto text-xs">
                    {JSON.stringify(candidate.components, null, 2)}
                  </pre>
                </details>
                <section className="space-y-3 rounded border p-3" aria-label="Candidate decision">
                  <h4 className="font-medium">Decision — experiment plan only</h4>
                  <p className="text-sm">
                    Select updates the comparison to this candidate. Accept records approval for
                    engineering review; it does not deploy or change the canonical saved topology.
                    Original snapshots remain available.
                  </p>
                  <label className="block text-sm">
                    Decision note
                    <Input
                      value={decisionNote}
                      maxLength={1000}
                      onChange={(event) => setDecisionNote(event.target.value)}
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={isBusy || !candidate.feasible}
                      onClick={() => decide("select")}
                    >
                      Use in comparison
                    </Button>
                    <Button
                      disabled={isBusy || !candidate.feasible || !candidate.metrics.flow_connected}
                      onClick={() => decide("accept")}
                    >
                      Accept plan for review
                    </Button>
                    <Button variant="outline" disabled={isBusy} onClick={() => decide("reject")}>
                      Reject plan
                    </Button>
                  </div>
                </section>
              </section>
            )}
            {!!result.decisions?.length && (
              <details>
                <summary>Recorded decision history ({result.decisions.length})</summary>
                <ul className="mt-2 space-y-2 text-sm">
                  {result.decisions.map((decision, index) => (
                    <li key={`${decision.created_at}:${index}`}>
                      {new Date(decision.created_at).toLocaleString()} · {decision.action} ·{" "}
                      {decision.candidate_id} · {decision.note || "No note"} · plan only; saved
                      topology unchanged
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <label className="block text-sm">
              Ask about the computed experiment
              <Input
                value={question}
                maxLength={2000}
                onChange={(event) => setQuestion(event.target.value)}
              />
            </label>
            <Button
              variant="outline"
              disabled={isBusy || !question.trim()}
              onClick={() =>
                void perform(async () =>
                  onResult({
                    ...result,
                    assistant: await explainSimulation(
                      await token(),
                      result.experiment_id,
                      question,
                    ),
                  }),
                )
              }
            >
              Explain evidence and trade-offs
            </Button>
            {result.assistant && (
              <section className="rounded border p-4">
                <p className="mb-2 text-xs uppercase text-muted-foreground">
                  {result.assistant.mode === "ai_assisted"
                    ? "AI-assisted explanation — verify against computed evidence"
                    : "Deterministic evidence explanation"}{" "}
                  · {result.assistant.provider_status}
                </p>
                <p className="whitespace-pre-wrap text-sm">{result.assistant.text}</p>
                <p className="mt-2 text-xs text-muted-foreground">{result.assistant.validation}</p>
                <details className="mt-2">
                  <summary>Explanation evidence and checked claims</summary>
                  <pre className="overflow-auto text-xs">
                    {JSON.stringify(
                      {
                        evidence: result.assistant.evidence,
                        claims: result.assistant.validated_claims,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </section>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
