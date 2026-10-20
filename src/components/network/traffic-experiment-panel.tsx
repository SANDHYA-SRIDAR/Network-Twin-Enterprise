import { useState } from "react";
import { Activity, Sparkles } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SimulationTopology } from "@/components/network/simulation-topology";
import { authenticatedApi } from "@/lib/api";
import type { AssistantExplanation } from "@/lib/failure-simulation";
import {
  trafficChartRows,
  trafficParetoPoints,
  type TrafficRequest,
  type TrafficResult,
  type TrafficMetrics,
} from "@/lib/traffic-experiment";

const number = (value: number | null | undefined, suffix = "") =>
  value == null ? "Unavailable" : `${value.toFixed(2)}${suffix}`;
const selectClass = "h-10 rounded-md border bg-background px-2 text-sm";

export function TrafficExperimentPanel({ initial }: { initial: TrafficRequest | null }) {
  const [draft, setDraft] = useState<TrafficRequest | null>(null);
  const request = draft ?? initial;
  const [sourceLabel, setSourceLabel] = useState("Saved topology snapshot");
  const [result, setResult] = useState<TrafficResult | null>(null);
  const [selected, setSelected] = useState("");
  const [flowId, setFlowId] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [assistant, setAssistant] = useState<AssistantExplanation | null>(null);
  const [axis, setAxis] = useState<"latency" | "connectivity">("latency");
  const candidate = result?.candidates.find((c) => c.id === selected);
  const run = async (optimize: boolean) => {
    if (!request) return;
    setBusy(
      optimize
        ? "Simulating traffic and comparing Pareto alternatives..."
        : "Generating traffic, evaluating queues and comparing recovery options...",
    );
    setError("");
    setAssistant(null);
    try {
      const next = await authenticatedApi<TrafficResult>("analysis/traffic-experiment", {
        method: "POST",
        body: JSON.stringify({ ...request, optimize }),
      });
      setResult(next);
      setSelected(next.selected_id);
      setFlowId(next.failed_metrics.flows[0]?.id ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Traffic evaluation failed.");
    } finally {
      setBusy("");
    }
  };
  const loadSample = async (name: string) => {
    setBusy("Loading a synthetic example...");
    setError("");
    try {
      setDraft(await authenticatedApi<TrafficRequest>(`analysis/traffic-samples/${name}`));
      setSourceLabel(`Synthetic ${name.replaceAll("_", " ")} example`);
      setResult(null);
      setAssistant(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load example.");
    } finally {
      setBusy("");
    }
  };
  const updateFlow = (index: number, patch: Partial<TrafficRequest["flows"][number]>) => {
    if (request)
      setDraft({
        ...request,
        flows: request.flows.map((f, i) => (i === index ? { ...f, ...patch } : f)),
      });
  };
  const routeMetrics = (metrics: TrafficMetrics) => {
    const flow = metrics.flows.find((f) => f.id === flowId);
    return {
      ...metrics,
      ...flow,
      links: metrics.links.map((link) => ({
        ...link,
        on_route: flow?.route_link_ids.includes(link.id) ?? false,
      })),
    };
  };
  const points = result?.optimization
    ? trafficParetoPoints(result.candidates, result.optimization.pareto_candidate_ids, axis)
    : [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="size-5" />
          Traffic simulation &amp; recovery insights
        </CardTitle>
        <CardDescription>
          Run synthetic packet events through finite queues. Compare applications, congestion and
          recovery options without sending real packets.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <fieldset disabled={!!busy} className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {(["home", "office", "multi_branch", "wan"] as const).map((name) => (
              <Button key={name} variant="outline" onClick={() => loadSample(name)}>
                Try {name.replaceAll("_", " ")}
              </Button>
            ))}
            {initial && (
              <Button
                variant="outline"
                onClick={() => {
                  setDraft(null);
                  setSourceLabel("Saved topology snapshot");
                  setResult(null);
                  setAssistant(null);
                }}
              >
                Use saved network and selected scenario
              </Button>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {request
              ? `${sourceLabel}: ${request.topology.name}. Scenario: ${request.scenario_type.replaceAll("_", " ")}.`
              : "Choose an example, or load a saved topology with two traffic endpoints."}{" "}
            Runs are previews; your saved network and saved analytical experiments stay unchanged.
          </p>
          {request && (
            <>
              <div className="flex flex-wrap gap-3">
                <label className="text-sm">
                  What-if action
                  <select
                    className={selectClass}
                    value={request.scenario_type}
                    onChange={(e) => {
                      const type = e.target.value as TrafficRequest["scenario_type"];
                      const edge = request.topology.links?.[0];
                      setDraft({
                        ...request,
                        scenario_type: type,
                        parameters:
                          type === "traffic_increase"
                            ? { factor: 1.5 }
                            : type === "device_failure" ||
                                type === "segment_isolation" ||
                                type === "load_balancer"
                              ? {
                                  node_id:
                                    type === "load_balancer"
                                      ? request.flows[0]?.target_node_id
                                      : request.topology.nodes[0]?.id,
                                }
                              : type === "redundancy_add"
                                ? {
                                    source_node_id: request.flows[0]?.source_node_id,
                                    target_node_id: request.flows[0]?.target_node_id,
                                    bandwidth_mbps: 20,
                                  }
                                : {
                                    link_id: edge?.id,
                                    ...(type === "bandwidth_change"
                                      ? { bandwidth_mbps: 5 }
                                      : type === "capacity_increase"
                                        ? { increase_mbps: 20 }
                                        : {}),
                                  },
                      });
                    }}
                  >
                    {[
                      ["link_failure", "Link failure"],
                      ["device_failure", "Device failure"],
                      ["rerouting", "Reroute around failed link"],
                      ["traffic_increase", "Traffic growth"],
                      ["bandwidth_change", "Change bandwidth"],
                      ["capacity_increase", "Upgrade capacity"],
                      ["redundancy_add", "Add backup link"],
                      ["traffic_prioritization", "Prioritize traffic"],
                      ["cloud_security", "Cloud security hop (delay only)"],
                      ["load_balancer", "Load balancer (per-flow replicas)"],
                      ["sd_wan", "SD-WAN under WAN failure"],
                    ].map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <Button
                  variant="outline"
                  onClick={() =>
                    setDraft({
                      ...request,
                      scenario_type: "traffic_prioritization",
                      parameters: {},
                    })
                  }
                >
                  What if we prioritize applications?
                </Button>
                <label className="text-sm">
                  Duration (seconds)
                  <Input
                    className="w-28"
                    type="number"
                    min="0.1"
                    max="5"
                    step="0.1"
                    value={request.duration_seconds}
                    onChange={(e) =>
                      setDraft({ ...request, duration_seconds: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
              <div className="flex flex-wrap gap-3">
                {Object.entries(request.parameters).map(([key, value]) => {
                  const update = (value: unknown) =>
                    setDraft({ ...request, parameters: { ...request.parameters, [key]: value } });
                  if (key === "link_id")
                    return (
                      <label className="text-sm" key={key}>
                        Affected connection
                        <select
                          className={selectClass}
                          value={String(value ?? "")}
                          onChange={(e) => update(e.target.value)}
                        >
                          {request.topology.links?.map((edge) => (
                            <option key={edge.id} value={edge.id}>
                              {
                                request.topology.nodes.find((n) => n.id === edge.source_node_id)
                                  ?.name
                              }{" "}
                              to{" "}
                              {
                                request.topology.nodes.find((n) => n.id === edge.target_node_id)
                                  ?.name
                              }
                            </option>
                          ))}
                        </select>
                      </label>
                    );
                  if (key.endsWith("node_id"))
                    return (
                      <label className="text-sm" key={key}>
                        {key.replaceAll("_", " ")}
                        <select
                          className={selectClass}
                          value={String(value ?? "")}
                          onChange={(e) => update(e.target.value)}
                        >
                          {request.topology.nodes.map((n) => (
                            <option key={n.id} value={n.id}>
                              {n.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    );
                  if (typeof value === "number")
                    return (
                      <label className="text-sm" key={key}>
                        {key.replaceAll("_", " ")}
                        <Input
                          type="number"
                          min="0.01"
                          value={value}
                          onChange={(e) => update(Number(e.target.value))}
                        />
                      </label>
                    );
                  return null;
                })}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[850px] text-left text-sm">
                  <thead>
                    <tr>
                      {[
                        "Application",
                        "Users",
                        "Protocol label",
                        "Source",
                        "Destination",
                        "Mbps (total)",
                        "Peak factor",
                        "Priority",
                      ].map((label) => (
                        <th className="p-2" key={label}>
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {request.flows.map((flow, i) => (
                      <tr key={flow.id} className="border-t">
                        <td className="p-2">
                          <Input
                            aria-label={`Application ${i + 1}`}
                            value={flow.application}
                            maxLength={100}
                            onChange={(e) => updateFlow(i, { application: e.target.value })}
                          />
                        </td>
                        <td>
                          <Input
                            aria-label={`Users for ${flow.application}`}
                            type="number"
                            min="1"
                            value={flow.users}
                            onChange={(e) => updateFlow(i, { users: Number(e.target.value) })}
                          />
                        </td>
                        <td>
                          <select
                            aria-label={`Protocol for ${flow.application}`}
                            className={selectClass}
                            value={flow.protocol}
                            onChange={(e) =>
                              updateFlow(i, { protocol: e.target.value as "TCP" | "UDP" })
                            }
                          >
                            <option>TCP</option>
                            <option>UDP</option>
                          </select>
                        </td>
                        <td>
                          <select
                            aria-label={`Source for ${flow.application}`}
                            className={selectClass}
                            value={flow.source_node_id}
                            onChange={(e) => updateFlow(i, { source_node_id: e.target.value })}
                          >
                            {request.topology.nodes.map((n) => (
                              <option key={n.id} value={n.id}>
                                {n.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            aria-label={`Destination for ${flow.application}`}
                            className={selectClass}
                            value={flow.target_node_id}
                            onChange={(e) => updateFlow(i, { target_node_id: e.target.value })}
                          >
                            {request.topology.nodes.map((n) => (
                              <option key={n.id} value={n.id}>
                                {n.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <Input
                            aria-label={`Rate for ${flow.application}`}
                            type="number"
                            min="0.01"
                            step="0.5"
                            value={flow.offered_mbps}
                            onChange={(e) =>
                              updateFlow(i, { offered_mbps: Number(e.target.value) })
                            }
                          />
                        </td>
                        <td>
                          <Input
                            aria-label={`Peak factor for ${flow.application}`}
                            type="number"
                            min="1"
                            max="10"
                            value={flow.peak_multiplier}
                            onChange={(e) =>
                              updateFlow(i, { peak_multiplier: Number(e.target.value) })
                            }
                          />
                        </td>
                        <td>
                          <select
                            aria-label={`Priority for ${flow.application}`}
                            className={selectClass}
                            value={flow.priority}
                            onChange={(e) => updateFlow(i, { priority: Number(e.target.value) })}
                          >
                            <option value={0}>Critical</option>
                            <option value={1}>High</option>
                            <option value={2}>Normal</option>
                            <option value={3}>Low</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={request.flows.length >= 8}
                  onClick={() => {
                    const first = request.flows[0]!;
                    setDraft({
                      ...request,
                      flows: [
                        ...request.flows,
                        {
                          ...first,
                          id: `application-${request.flows.length + 1}`,
                          application: `Application ${request.flows.length + 1}`,
                        },
                      ],
                    });
                  }}
                >
                  Add application
                </Button>
                {request.flows.length > 1 && (
                  <Button
                    variant="outline"
                    onClick={() => setDraft({ ...request, flows: request.flows.slice(0, -1) })}
                  >
                    Remove last application
                  </Button>
                )}
                <Button onClick={() => run(false)}>Run traffic simulation</Button>
                <Button variant="outline" onClick={() => run(true)}>
                  Explore NSGA-II trade-offs
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Rates are total per application, not per user. Peak load starts halfway through the
                run. TCP/UDP are labels; transport feedback and retransmissions are not modeled.
                Maximum 20,000 packets per run; reduce load or duration if exceeded.
              </p>
            </>
          )}
        </fieldset>
        {busy && (
          <div role="status" className="rounded bg-primary/10 p-3 text-sm">
            <Activity className="mr-2 inline size-4 animate-pulse" />
            {busy}
          </div>
        )}
        {error && (
          <p
            role="alert"
            className="rounded border border-destructive/40 p-3 text-sm text-destructive"
          >
            {error}
          </p>
        )}
        {result && (
          <>
            <p className="rounded-lg bg-muted p-4 text-sm leading-relaxed">{result.summary}</p>
            <p className="text-xs text-muted-foreground">
              Displayed results use the recorded run: {result.request.topology.name},{" "}
              {result.request.duration_seconds} seconds,{" "}
              {result.request.scenario_type.replaceAll("_", " ")}. Edited controls take effect on
              the next run.
            </p>
            <section
              aria-label="Risk and congestion insights"
              className="space-y-2 rounded-lg border p-4"
            >
              <h3 className="font-semibold">What needs attention?</h3>
              <p>
                <strong
                  className={result.insights.score >= 60 ? "text-destructive" : "text-primary"}
                >
                  {result.insights.level.toUpperCase()} scenario risk ({result.insights.score}/100)
                </strong>
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {result.insights.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              <p className="text-sm">
                Affected application-user assignments: {result.insights.affected_users}. Counts may
                overlap between applications.
              </p>
              <p className="text-xs text-muted-foreground">
                Transparent rule-based severity, not a trained prediction or failure probability.{" "}
                {result.insights.confidence}.
              </p>
            </section>
            <label className="block text-sm">
              Highlight application route{" "}
              <select
                className={selectClass}
                value={flowId}
                onChange={(e) => setFlowId(e.target.value)}
              >
                {result.failed_metrics.flows.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.application}
                    {result.rerouted_flows.includes(f.id)
                      ? " (rerouted)"
                      : !f.flow_connected
                        ? " (unreachable)"
                        : ""}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-4 xl:grid-cols-2">
              <SimulationTopology
                compact
                network={result.baseline_topology}
                metrics={routeMetrics(result.baseline_metrics)}
                title="Original traffic routes"
              />
              <SimulationTopology
                compact
                network={result.failed_topology}
                comparisonNetwork={result.baseline_topology}
                metrics={routeMetrics(result.failed_metrics)}
                title="After scenario"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Throughput", number(result.failed_metrics.throughput_mbps, " Mbps")],
                ["Average latency", number(result.failed_metrics.average_latency_ms, " ms")],
                ["Packet loss", number(result.failed_metrics.packet_loss_pct, "%")],
                [
                  "Mean link utilization",
                  number(result.failed_metrics.mean_link_utilization_pct, "%"),
                ],
                [
                  "Flow availability",
                  number(result.failed_metrics.connectivity_pct, "% reachable"),
                ],
                ["Scenario risk", `${result.insights.score}/100`],
                ["Inspected option cost", `${candidate?.cost_units ?? 0} relative units`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border p-3">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="mt-1 text-lg font-semibold">{value}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Availability is route reachability, not measured uptime. Latency covers delivered
              packets only. {result.failed_metrics.pending} packets remain in flight or queued at
              the observation boundary.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead>
                  <tr>
                    <th className="p-2">Metric</th>
                    <th>Original</th>
                    <th>After scenario</th>
                    <th>Inspected solution</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["Throughput (Mbps)", "throughput_mbps"],
                      ["Latency (ms)", "average_latency_ms"],
                      ["Packet loss (%)", "packet_loss_pct"],
                      ["Flow availability (%)", "connectivity_pct"],
                      ["Mean link utilization (%)", "mean_link_utilization_pct"],
                    ] as const
                  ).map(([label, key]) => (
                    <tr key={key} className="border-t">
                      <th className="p-2 font-medium">{label}</th>
                      {[result.baseline_metrics, result.failed_metrics, candidate?.metrics].map(
                        (metrics, i) => (
                          <td key={i}>{number(metrics?.[key])}</td>
                        ),
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details className="rounded border p-3">
              <summary className="cursor-pointer font-medium">
                Which applications and connections were affected?
              </summary>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[600px] text-left text-sm">
                  <thead>
                    <tr>
                      <th>Application</th>
                      <th>Original Mbps</th>
                      <th>Scenario Mbps</th>
                      <th>Inspected Mbps</th>
                      <th>Scenario state</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.failed_metrics.flows.map((flow) => (
                      <tr className="border-t" key={flow.id}>
                        <th className="py-2 font-medium">{flow.application}</th>
                        <td>
                          {number(
                            result.baseline_metrics.flows.find((f) => f.id === flow.id)
                              ?.throughput_mbps,
                          )}
                        </td>
                        <td>{number(flow.throughput_mbps)}</td>
                        <td>
                          {number(
                            candidate?.metrics.flows.find((f) => f.id === flow.id)?.throughput_mbps,
                          )}
                        </td>
                        <td>
                          {!flow.flow_connected
                            ? "Unreachable"
                            : result.rerouted_flows.includes(flow.id)
                              ? "Rerouted"
                              : "Route retained"}
                          ; {flow.dropped} dropped, {flow.pending} pending
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="mt-3 space-y-1 text-sm">
                {result.failed_metrics.links
                  .filter(
                    (link) =>
                      link.congested ||
                      ["failed", "down", "offline", "unavailable"].includes(link.status),
                  )
                  .map((link) => {
                    const edge = result.failed_topology.links?.find((e) => e.id === link.id);
                    const name = (id: string | undefined) =>
                      result.failed_topology.nodes.find((n) => n.id === id)?.name ?? "Connection";
                    return (
                      <li key={link.id}>
                        {name(edge?.source_node_id)} to {name(edge?.target_node_id)}: {link.status},{" "}
                        {number(link.utilization_pct, "% utilization")}, {link.queue_drops} queue
                        drops. Original utilization:{" "}
                        {number(
                          result.baseline_metrics.links.find((e) => e.id === link.id)
                            ?.utilization_pct,
                          "%",
                        )}
                        .
                      </li>
                    );
                  })}
              </ul>
            </details>
            <div className="h-64" aria-label="Delivered throughput over simulated time">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={trafficChartRows(
                    result.baseline_metrics,
                    result.failed_metrics,
                    candidate?.metrics,
                  )}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" unit=" s" />
                  <YAxis unit=" Mbps" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--background)",
                      color: "var(--foreground)",
                    }}
                  />
                  <Legend />
                  <Area type="stepAfter" dataKey="original" stroke="#64748b" fillOpacity={0} />
                  <Area type="stepAfter" dataKey="scenario" stroke="#d97706" fillOpacity={0} />
                  <Area type="stepAfter" dataKey="proposed" stroke="#16a34a" fillOpacity={0} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <section className="space-y-3">
              <h3 className="font-semibold">Recovery options</h3>
              <div className="flex flex-wrap gap-2">
                {result.candidates.map((c) => (
                  <Button
                    key={c.id}
                    variant={c.id === selected ? "default" : "outline"}
                    onClick={() => setSelected(c.id)}
                  >
                    {c.title}
                    {c.id === result.selected_id ? " (recommended)" : ""}
                  </Button>
                ))}
              </div>
              {candidate && (
                <>
                  <p className="text-sm">
                    {candidate.targets_met
                      ? "Meets the modeled service targets for every application."
                      : "Does not meet all modeled service targets."}{" "}
                    {candidate.changes.length
                      ? `${candidate.changes.length} configuration changes, ${candidate.cost_units} relative cost units.`
                      : "No configuration change; keeps the surviving network."}{" "}
                    Scenario risk changes from {result.insights.score} to {candidate.insights.score}
                    /100. This is an inspection, not acceptance or deployment.
                  </p>
                  <SimulationTopology
                    compact
                    network={candidate.topology}
                    comparisonNetwork={result.failed_topology}
                    metrics={routeMetrics(candidate.metrics)}
                    title={`Inspect: ${candidate.title}`}
                  />
                </>
              )}
            </section>
            {result.optimization && (
              <section className="space-y-3 rounded border p-4">
                <h3 className="font-semibold">Pareto trade-offs</h3>
                <p className="text-sm">
                  {result.optimization.status === "completed"
                    ? "NSGA-II compares the generated action catalog using six event-based objectives. Click a point to inspect its complete result."
                    : result.optimization.reason}
                </p>
                <select
                  aria-label="Pareto vertical axis"
                  className={selectClass}
                  value={axis}
                  onChange={(e) => setAxis(e.target.value as typeof axis)}
                >
                  <option value="latency">Latency versus cost</option>
                  <option value="connectivity">Flow availability versus cost</option>
                </select>
                <p className="text-xs text-muted-foreground">
                  {result.optimization.scope} Availability is snapshot reachability, not uptime
                  reliability.
                </p>
                {points.length > 0 ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="cost" type="number" name="Relative cost" />
                        <YAxis
                          dataKey="value"
                          type="number"
                          name={axis}
                          unit={axis === "latency" ? " ms" : "%"}
                        />
                        <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                        <Scatter data={points} fill="#2563eb">
                          {points.map((p) => (
                            <Cell
                              key={p.id}
                              className="cursor-pointer"
                              onClick={() => setSelected(p.id)}
                            />
                          ))}
                        </Scatter>
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="text-sm">No finite eligible points for this view.</p>
                )}
              </section>
            )}
            <section className="space-y-3 rounded-lg border p-4">
              <h3 className="font-semibold">Help me understand these results</h3>
              <p className="text-sm">
                Ask the configured AI service to explain the computed evidence. If unavailable, the
                response is explicitly deterministic.
              </p>
              <Button
                variant="outline"
                disabled={!!busy}
                onClick={async () => {
                  setBusy("Preparing an evidence-based explanation (up to 30 seconds)...");
                  setError("");
                  try {
                    setAssistant(
                      await authenticatedApi<AssistantExplanation>(
                        "analysis/traffic-experiment/explain",
                        { method: "POST", body: JSON.stringify(result.request) },
                      ),
                    );
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Explanation unavailable.");
                  } finally {
                    setBusy("");
                  }
                }}
              >
                <Sparkles className="mr-2 size-4" />
                Explain the recommended option
              </Button>
              {assistant && (
                <>
                  <p className="text-xs text-muted-foreground">
                    {assistant.mode === "ai_assisted"
                      ? "AI-assisted"
                      : "Deterministic explanation; live AI unavailable"}{" "}
                    / {assistant.provider_status}
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{assistant.text}</p>
                </>
              )}
            </section>
            <details>
              <summary className="cursor-pointer font-medium">
                Advanced Details: applications, links, communities and assumptions
              </summary>
              <div className="mt-3 space-y-3">
                <p className="text-sm">
                  Louvain structural zones (not security boundaries):{" "}
                  {result.structure.communities
                    .map((group) =>
                      group
                        .map(
                          (id) => result.failed_topology.nodes.find((n) => n.id === id)?.name ?? id,
                        )
                        .join(", "),
                    )
                    .join(" / ")}
                </p>
                {result.limitations.map((line) => (
                  <p key={line} className="text-sm text-muted-foreground">
                    {line}
                  </p>
                ))}
                <pre className="max-h-96 overflow-auto text-xs">
                  {JSON.stringify(
                    {
                      baseline: result.baseline_metrics,
                      scenario: result.failed_metrics,
                      inspected: candidate?.metrics,
                      optimization: result.optimization,
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            </details>
          </>
        )}
      </CardContent>
    </Card>
  );
}
