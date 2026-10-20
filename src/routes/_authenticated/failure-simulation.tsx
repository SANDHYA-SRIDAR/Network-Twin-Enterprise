import { WanTransformationDemo } from "@/components/network/wan-transformation-demo";
import { TrafficExperimentPanel } from "@/components/network/traffic-experiment-panel";
import { createFileRoute } from "@tanstack/react-router";
import { Activity, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/network/app-shell";
import { ExperimentTools } from "@/components/network/experiment-tools";
import { SimulationTopology } from "@/components/network/simulation-topology";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/custom-client";
import { AnomalyPanel } from "@/components/network/anomaly-panel";
import {
  loadSavedSimulationTopology,
  modernizeSimulation,
  runFailureSimulation,
  type FailureSimulationResult,
  type SimulationMetrics,
} from "@/lib/failure-simulation";
import { convertNetworkToReactFlow, type NetworkDefinition } from "@/lib/network-schema";
import { comparisonDemandText } from "@/lib/optimization-view";
import { SCENARIO_OPTIONS, type ScenarioType } from "@/lib/scenario";

export const Route = createFileRoute("/_authenticated/failure-simulation")({
  component: FailureSimulationPage,
});

type TopologyState = { topology: NetworkDefinition; topology_fingerprint: string };
const deviceTitle = (topology: NetworkDefinition, id: string) =>
  topology.nodes.find((node) => node.id === id)?.name ?? id;
const linkTitle = (topology: NetworkDefinition, id: string) => {
  const link = topology.links?.find((edge) => edge.id === id);
  return link
    ? `${deviceTitle(topology, link.source_node_id)} ↔ ${deviceTitle(topology, link.target_node_id)}`
    : id;
};
const format = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);

const formatLatency = (metric: SimulationMetrics | null | undefined, digits = 2) => {
  if (!metric) return "—";
  if (metric.average_latency_ms != null && Number.isFinite(metric.average_latency_ms)) {
    return `${metric.average_latency_ms.toFixed(digits)} ms`;
  }
  if (!metric.flow_connected || metric.queueing_status === "unreachable") {
    return "Unreachable (no route)";
  }
  if (metric.queueing_status === "unstable") {
    return "Unavailable (traffic exceeds capacity)";
  }
  return "—";
};

function MetricCard({
  label,
  value,
  unit,
  detail,
}: {
  label: string;
  value: string | number;
  unit?: string;
  detail?: string;
}) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
      </p>
      {detail && <p className="mt-1 text-[11px] text-muted-foreground">{detail}</p>}
    </div>
  );
}

function PrimaryMetrics({ metrics }: { metrics: SimulationMetrics }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="Throughput" value={format(metrics.throughput_mbps)} unit="Mbps" />
      <MetricCard label="Packet loss" value={format(metrics.packet_loss_pct)} unit="%" />
      <MetricCard label="Average latency" value={formatLatency(metrics)} />
      <MetricCard
        label="Connectivity"
        value={metrics.flow_connected ? "Connected" : "Disconnected"}
        detail="Tested traffic flow"
      />
    </div>
  );
}

function metricRows(
  result: FailureSimulationResult | null,
): Array<{ label: string; baseline: string; failed: string; modernized: string }> {
  if (!result) return [];
  const values: [SimulationMetrics, SimulationMetrics, SimulationMetrics | null] = [
    result.baseline_metrics,
    result.failed_metrics,
    result.modernized_metrics ?? null,
  ];
  const show = (metric: SimulationMetrics | null, key: keyof SimulationMetrics, suffix = "") => {
    const value = metric?.[key];
    return typeof value === "number" ? `${format(value)}${suffix}` : "—";
  };
  return [
    {
      label: "Flow path reachability",
      baseline: values[0].flow_connected ? "Connected" : "Disconnected",
      failed: values[1].flow_connected ? "Connected" : "Disconnected",
      modernized: values[2] ? (values[2].flow_connected ? "Connected" : "Disconnected") : "—",
    },
    {
      label: "Total packet loss",
      baseline: show(values[0], "packet_loss_pct", "%"),
      failed: show(values[1], "packet_loss_pct", "%"),
      modernized: show(values[2], "packet_loss_pct", "%"),
    },
    {
      label: "Modeled congestion loss",
      baseline: show(values[0], "congestion_loss_pct", "%"),
      failed: show(values[1], "congestion_loss_pct", "%"),
      modernized: show(values[2], "congestion_loss_pct", "%"),
    },
    {
      label: "Physical link / medium loss",
      baseline: show(values[0], "link_medium_loss_pct", "%"),
      failed: show(values[1], "link_medium_loss_pct", "%"),
      modernized: show(values[2], "link_medium_loss_pct", "%"),
    },
    {
      label: "Average latency",
      baseline: formatLatency(values[0]),
      failed: formatLatency(values[1]),
      modernized: formatLatency(values[2]),
    },
    {
      label: "Achieved throughput",
      baseline: show(values[0], "throughput_mbps", " Mbps"),
      failed: show(values[1], "throughput_mbps", " Mbps"),
      modernized: show(values[2], "throughput_mbps", " Mbps"),
    },
    {
      label: "Bottleneck path capacity",
      baseline: show(values[0], "path_capacity_mbps", " Mbps"),
      failed: show(values[1], "path_capacity_mbps", " Mbps"),
      modernized: show(values[2], "path_capacity_mbps", " Mbps"),
    },
    {
      label: "Queueing status",
      baseline:
        values[0].queueing_status === "unstable"
          ? "Unstable (ρ ≥ 1)"
          : values[0].queueing_status === "estimated"
            ? "Stable (estimated)"
            : "Unreachable",
      failed:
        values[1].queueing_status === "unstable"
          ? "Unstable (ρ ≥ 1)"
          : values[1].queueing_status === "estimated"
            ? "Stable (estimated)"
            : "Unreachable",
      modernized: values[2]
        ? values[2].queueing_status === "unstable"
          ? "Unstable (ρ ≥ 1)"
          : values[2].queueing_status === "estimated"
            ? "Stable (estimated)"
            : "Unreachable"
        : "—",
    },
    {
      label: "Mean link utilization",
      baseline: show(values[0], "mean_link_utilization_pct", "%"),
      failed: show(values[1], "mean_link_utilization_pct", "%"),
      modernized: show(values[2], "mean_link_utilization_pct", "%"),
    },
    {
      label: "Reachable devices",
      baseline: values[0] ? `${values[0].reachable_nodes}/${values[0].total_nodes}` : "—",
      failed: values[1] ? `${values[1].reachable_nodes}/${values[1].total_nodes}` : "—",
      modernized: values[2] ? `${values[2].reachable_nodes}/${values[2].total_nodes}` : "—",
    },
    {
      label: "Active / failed links",
      baseline: values[0] ? `${values[0].active_links} / ${values[0].failed_links}` : "—",
      failed: values[1] ? `${values[1].active_links} / ${values[1].failed_links}` : "—",
      modernized: values[2] ? `${values[2].active_links} / ${values[2].failed_links}` : "—",
    },
    {
      label: "Congested links",
      baseline: values[0] ? String(values[0].congested_links) : "—",
      failed: values[1] ? String(values[1].congested_links) : "—",
      modernized: values[2] ? String(values[2].congested_links) : "—",
    },
    {
      label: "Bottleneck links count",
      baseline: values[0] ? String(values[0].bottleneck_link_ids.length) : "—",
      failed: values[1] ? String(values[1].bottleneck_link_ids.length) : "—",
      modernized: values[2] ? String(values[2].bottleneck_link_ids.length) : "—",
    },
  ];
}

function FailureSimulationPage() {
  const launchParams = useMemo(
    () =>
      typeof window === "undefined"
        ? new URLSearchParams()
        : new URLSearchParams(window.location.search),
    [],
  );
  const requestedScenario = launchParams.get("scenario") as ScenarioType | null;
  const initialScenario = SCENARIO_OPTIONS.some((option) => option.type === requestedScenario)
    ? requestedScenario!
    : "link_failure";
  const autoRunRef = useRef(false);
  const [saved, setSaved] = useState<TopologyState | null>(null);
  const [result, setResult] = useState<FailureSimulationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [topologyReload, setTopologyReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenarioType, setScenarioType] = useState<ScenarioType>(initialScenario);
  const [nodeTarget, setNodeTarget] = useState(launchParams.get("node_id") ?? "");
  const [linkTarget, setLinkTarget] = useState(launchParams.get("link_id") ?? "");
  const [source, setSource] = useState(launchParams.get("flow_source_id") ?? "");
  const [destination, setDestination] = useState(launchParams.get("flow_target_id") ?? "");
  const [trafficMbps, setTrafficMbps] = useState(Number(launchParams.get("offered_mbps") ?? 100));
  const [durationSeconds, setDurationSeconds] = useState(
    Number(launchParams.get("duration_seconds") ?? 60),
  );
  const [parameterValue, setParameterValue] = useState(
    Number(
      launchParams.get("factor") ??
        launchParams.get("bandwidth_mbps") ??
        launchParams.get("increase_mbps") ??
        250,
    ),
  );
  const [redundancySource, setRedundancySource] = useState(
    launchParams.get("redundancy_source_id") ?? "",
  );
  const [redundancyTarget, setRedundancyTarget] = useState(
    launchParams.get("redundancy_target_id") ?? "",
  );
  const [playing, setPlaying] = useState(false);
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [playbackStage, setPlaybackStage] = useState<"failure" | "modernization">("failure");

  useEffect(() => {
    let active = true;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const { data: sessionResult, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !sessionResult.session)
          throw new Error("Sign in to load your saved topology.");
        const topology = await loadSavedSimulationTopology(sessionResult.session.access_token);
        if (!active) return;
        setSaved(topology);
        const endpoints = topology.topology.nodes.filter(
          (node) => !["router", "switch", "hub", "access_point"].includes(node.device_type),
        );
        setSource((current) => current || endpoints[0]?.id || topology.topology.nodes[0]?.id || "");
        setDestination(
          (current) => current || endpoints.at(-1)?.id || topology.topology.nodes.at(-1)?.id || "",
        );
        setNodeTarget((current) => current || topology.topology.nodes[0]?.id || "");
        setLinkTarget((current) => current || topology.topology.links?.[0]?.id || "");
        setRedundancySource((current) => current || topology.topology.nodes[0]?.id || "");
        setRedundancyTarget((current) => current || topology.topology.nodes[1]?.id || "");
      } catch (loadError) {
        if (active)
          setError(
            loadError instanceof Error ? loadError.message : "Could not load the saved topology.",
          );
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [topologyReload]);

  const scenario = useMemo(
    () => SCENARIO_OPTIONS.find((option) => option.type === scenarioType) ?? SCENARIO_OPTIONS[0]!,
    [scenarioType],
  );
  const baselineRouteLinkIds = useMemo(() => {
    return new Set(result?.baseline_metrics?.route_link_ids ?? []);
  }, [result?.baseline_metrics?.route_link_ids]);
  const params = useMemo(() => {
    switch (scenario.parameter) {
      case "link":
        return { link_id: linkTarget };
      case "node":
        return { node_id: nodeTarget };
      case "traffic-factor":
        return { factor: parameterValue };
      case "bandwidth":
        return scenarioType === "capacity_increase"
          ? { link_id: linkTarget, increase_mbps: parameterValue }
          : { link_id: linkTarget, bandwidth_mbps: parameterValue };
      case "redundancy":
        return {
          source_node_id: redundancySource,
          target_node_id: redundancyTarget,
          bandwidth_mbps: parameterValue,
        };
      case "placement":
        return { node_id: nodeTarget };
    }
  }, [
    linkTarget,
    nodeTarget,
    parameterValue,
    redundancySource,
    redundancyTarget,
    scenario.parameter,
    scenarioType,
  ]);
  const parameterValid = useMemo(() => {
    if (!saved) return false;
    if (scenario.parameter === "link")
      return saved.topology.links?.some((link) => link.id === linkTarget) ?? false;
    if (scenario.parameter === "node" || scenario.parameter === "placement")
      return saved.topology.nodes.some((node) => node.id === nodeTarget);
    if (scenario.parameter === "traffic-factor" || scenario.parameter === "bandwidth")
      return (
        Number.isFinite(parameterValue) &&
        parameterValue > 0 &&
        (scenario.parameter !== "bandwidth" || Boolean(linkTarget))
      );
    return Boolean(redundancySource && redundancyTarget && redundancySource !== redundancyTarget);
  }, [
    linkTarget,
    nodeTarget,
    parameterValue,
    redundancySource,
    redundancyTarget,
    saved,
    scenario.parameter,
  ]);
  const playbackEvents =
    playbackStage === "failure"
      ? (result?.failure_steps ?? [])
      : (result?.modernization_steps ?? []);
  const activeLinkId =
    playing && playbackEvents[playbackIndex]?.["kind"] === "forward"
      ? String(playbackEvents[playbackIndex]?.["link_id"] ?? "")
      : undefined;
  const baselineTopology = result?.baseline_topology ?? saved?.topology;
  const failedTopology = result?.failed_topology;
  const modernizedTopology = result?.modernized_topology;

  useEffect(() => {
    if (!playing) return;
    if (playbackIndex >= playbackEvents.length) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setPlaybackIndex((index) => index + 1), 850);
    return () => window.clearTimeout(timer);
  }, [playing, playbackEvents.length, playbackIndex]);

  const run = async () => {
    if (!saved || !parameterValid || !source || !destination || source === destination) return;
    setBusy(true);
    setError(null);
    setPlaying(false);
    setPlaybackIndex(0);
    setPlaybackStage("failure");
    try {
      const { data: session } = await supabase.auth.getSession();
      if (!session.session) throw new Error("Sign in again to run a simulation.");
      const next = await runFailureSimulation(session.session.access_token, {
        scenario_type: scenarioType,
        parameters: params,
        traffic: {
          source_node_id: source,
          target_node_id: destination,
          offered_mbps: trafficMbps,
          duration_seconds: durationSeconds,
          packet_size_bytes: 1500,
        },
        topology_fingerprint: saved.topology_fingerprint,
      });
      setResult(next);
      setSaved({
        topology: next.baseline_topology,
        topology_fingerprint: next.topology_fingerprint,
      });
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Simulation failed.");
    } finally {
      setBusy(false);
    }
  };

  const modernize = async () => {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      const { data: session } = await supabase.auth.getSession();
      if (!session.session) throw new Error("Sign in again to request modernization.");
      const next = await modernizeSimulation(session.session.access_token, result.experiment_id);
      setResult(next);
      setPlaybackStage("modernization");
      setPlaybackIndex(0);
      setPlaying(false);
    } catch (modernizeError) {
      setError(modernizeError instanceof Error ? modernizeError.message : "Modernization failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (
      launchParams.get("autoRun") !== "1" ||
      loading ||
      !saved ||
      !parameterValid ||
      !source ||
      !destination ||
      source === destination ||
      autoRunRef.current
    )
      return;
    autoRunRef.current = true;
    void run();
  }, [launchParams, loading, saved, parameterValid, source, destination]);

  const comparison = metricRows(result);
  const selectedCandidate = result?.modernization?.candidates?.find(
    (candidate) => candidate.id === result.modernization?.selected_strategy_id,
  );
  const noChanges = selectedCandidate?.changes.length === 0;
  const busyLabel = loading ? "Loading saved topology…" : busy ? "Calculating…" : "Run Simulation";

  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-y-auto bg-background">
        <div className="mx-auto max-w-[1500px] space-y-6 px-5 py-7 sm:px-8">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-mono text-xs uppercase text-primary">
                Analytical simulation · provenance: simulated
              </p>
              <h1 className="mt-2 text-3xl font-semibold">
                Network Failure Simulation &amp; Modernization
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                Test a failure, explore recovery options, and compare the predicted results. Your
                saved network stays unchanged.
              </p>
            </div>
          </header>
          <WanTransformationDemo {...(saved ? { saved: saved.topology } : {})} />

          <Card>
            <CardHeader>
              <CardTitle>Step 1: Select a failure</CardTitle>
              <CardDescription>
                Choose what to test and which traffic should travel through the network.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-5 xl:grid-cols-[1fr_1.2fr_1fr]">
              <div className="space-y-2">
                <Label htmlFor="failure-scenario">Scenario</Label>
                <select
                  id="failure-scenario"
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                  value={scenarioType}
                  onChange={(event) => setScenarioType(event.target.value as ScenarioType)}
                >
                  {SCENARIO_OPTIONS.map((item) => (
                    <option key={item.type} value={item.type}>
                      {item.title}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-muted-foreground">{scenario.description}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {(scenario.parameter === "link" || scenario.parameter === "bandwidth") && (
                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor="failure-link">Affected connection</Label>
                    <select
                      id="failure-link"
                      className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                      value={linkTarget}
                      onChange={(event) => setLinkTarget(event.target.value)}
                    >
                      <option value="">Choose saved connection</option>
                      {saved?.topology.links?.map((link) => {
                        const onRoute =
                          result?.baseline_metrics.route_node_ids[0] === source &&
                          result?.baseline_metrics.route_node_ids.at(-1) === destination &&
                          baselineRouteLinkIds.has(link.id);
                        return (
                          <option key={link.id} value={link.id}>
                            {onRoute ? "★ [ON ROUTE] " : ""}
                            {linkTitle(saved.topology, link.id)} (connection{" "}
                            {saved.topology.links!.indexOf(link) + 1})
                          </option>
                        );
                      })}
                    </select>
                  </div>
                )}
                {(scenario.parameter === "node" || scenario.parameter === "placement") && (
                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor="failure-node">Affected device</Label>
                    <select
                      id="failure-node"
                      className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                      value={nodeTarget}
                      onChange={(event) => setNodeTarget(event.target.value)}
                    >
                      <option value="">Choose saved device</option>
                      {saved?.topology.nodes.map((node) => (
                        <option key={node.id} value={node.id}>
                          {node.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {scenario.parameter === "traffic-factor" && (
                  <div className="space-y-2">
                    <Label htmlFor="traffic-factor">Traffic increase factor</Label>
                    <Input
                      id="traffic-factor"
                      type="number"
                      min="0.01"
                      step="0.1"
                      value={parameterValue}
                      onChange={(event) => setParameterValue(Number(event.target.value))}
                    />
                  </div>
                )}
                {scenario.parameter === "bandwidth" && (
                  <div className="space-y-2">
                    <Label htmlFor="capacity-value">
                      {scenarioType === "capacity_increase"
                        ? "Capacity increase (Mbps)"
                        : "New capacity (Mbps)"}
                    </Label>
                    <Input
                      id="capacity-value"
                      type="number"
                      min="1"
                      step="10"
                      value={parameterValue}
                      onChange={(event) => setParameterValue(Number(event.target.value))}
                    />
                  </div>
                )}
                {scenario.parameter === "redundancy" && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="redundancy-source">Candidate link source</Label>
                      <select
                        id="redundancy-source"
                        className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                        value={redundancySource}
                        onChange={(event) => setRedundancySource(event.target.value)}
                      >
                        {saved?.topology.nodes.map((node) => (
                          <option key={node.id} value={node.id}>
                            {node.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="redundancy-target">Candidate link destination</Label>
                      <select
                        id="redundancy-target"
                        className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                        value={redundancyTarget}
                        onChange={(event) => setRedundancyTarget(event.target.value)}
                      >
                        {saved?.topology.nodes.map((node) => (
                          <option key={node.id} value={node.id}>
                            {node.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="redundancy-capacity">Candidate capacity (Mbps)</Label>
                      <Input
                        id="redundancy-capacity"
                        type="number"
                        min="1"
                        step="10"
                        value={parameterValue}
                        onChange={(event) => setParameterValue(Number(event.target.value))}
                      />
                    </div>
                  </>
                )}
                {scenario.parameter === "placement" && (
                  <p className="text-xs text-amber-700 sm:col-span-2">
                    This is an existing Scenario Studio option. The saved schema has no site or
                    cloud-latency model, so the engine reports unchanged network metrics and
                    explains the limitation.
                  </p>
                )}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="traffic-source">Traffic source</Label>
                  <select
                    id="traffic-source"
                    className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                    value={source}
                    onChange={(event) => setSource(event.target.value)}
                  >
                    {saved?.topology.nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="traffic-destination">Traffic destination</Label>
                  <select
                    id="traffic-destination"
                    className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                    value={destination}
                    onChange={(event) => setDestination(event.target.value)}
                  >
                    {saved?.topology.nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="offered-load">Offered traffic (Mbps)</Label>
                  <Input
                    id="offered-load"
                    type="number"
                    min="0.01"
                    step="10"
                    value={trafficMbps}
                    onChange={(event) => setTrafficMbps(Number(event.target.value))}
                  />
                </div>
              </div>
            </CardContent>
            {error && (
              <div
                role="alert"
                className="mx-6 mb-5 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
              >
                {error}
                <Button
                  className="ml-3"
                  variant="outline"
                  size="sm"
                  disabled={busy || loading}
                  onClick={() => setTopologyReload((value) => value + 1)}
                >
                  Reload saved topology
                </Button>
              </div>
            )}
          </Card>

          <details className="rounded-lg border p-4" open={launchParams.get("autoRun") === "1"}>
            <summary className="cursor-pointer font-semibold">
              Interactive application traffic, risk and recovery
            </summary>
            <div className="mt-4">
              <TrafficExperimentPanel
                key={`${scenarioType}:${source}:${destination}:${JSON.stringify(params)}`}
                initial={
                  saved && source && destination && source !== destination
                    ? {
                        topology: saved.topology,
                        scenario_type: scenarioType,
                        parameters: params,
                        duration_seconds: 1,
                        queue_packets: 32,
                        seed: 17,
                        optimize: false,
                        flows: [
                          {
                            id: "primary",
                            application: "Primary application",
                            users: 1,
                            protocol: "UDP",
                            priority: 1,
                            source_node_id: source,
                            target_node_id: destination,
                            offered_mbps: trafficMbps,
                            peak_multiplier: 1,
                            packet_size_bytes: 1500,
                          },
                        ],
                      }
                    : null
                }
              />
            </div>
          </details>

          <Card>
            <CardHeader>
              <CardTitle>Step 2: Run the simulation</CardTitle>
              <CardDescription>
                Red connections are unavailable. The highlighted route shows where the tested
                traffic can travel. Results are analytical estimates.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button
                className="sm:col-span-2"
                onClick={run}
                disabled={
                  busy ||
                  loading ||
                  !saved ||
                  !saved.topology.nodes.length ||
                  !parameterValid ||
                  !source ||
                  !destination ||
                  source === destination
                }
              >
                <Activity className="mr-2 size-4" />
                {busyLabel}
              </Button>
              {loading && <p role="status">Loading your saved network...</p>}
              {!loading && !saved && (
                <p>Could not load your network. Use Reload saved topology above to try again.</p>
              )}
              {saved && !saved.topology.nodes.length && (
                <p>Add and save devices in Topology Workspace before running a simulation.</p>
              )}
              {source && source === destination && (
                <p role="status">Choose different traffic source and destination devices.</p>
              )}
              {baselineTopology && baselineTopology.nodes.length > 0 && (
                <div className="grid gap-4 xl:grid-cols-2">
                  <div className="space-y-3">
                    <SimulationTopology
                      compact
                      network={baselineTopology}
                      metrics={result?.baseline_metrics ?? { links: [] }}
                      title="Original network"
                    />
                    {result && <PrimaryMetrics metrics={result.baseline_metrics} />}
                  </div>
                  <div className="space-y-3">
                    {result && failedTopology ? (
                      <>
                        <SimulationTopology
                          compact
                          network={failedTopology}
                          metrics={result.failed_metrics}
                          {...(playbackStage === "failure" && activeLinkId ? { activeLinkId } : {})}
                          title="After failure"
                        />
                        <PrimaryMetrics metrics={result.failed_metrics} />
                      </>
                    ) : (
                      <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                        Run the simulation to see the failure's effect on your network.
                      </p>
                    )}
                  </div>
                </div>
              )}
              {result && (
                <p className="rounded-lg bg-muted p-3 text-sm">
                  {result.flow_impact?.explanation ??
                    "Compare the original and after-failure metrics below to assess the effect on the tested traffic."}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Step 3: Generate a solution</CardTitle>
              <CardDescription>
                Evaluate recovery options for the simulated network.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button onClick={modernize} disabled={busy || !result}>
                <Sparkles className="mr-2 size-4" />
                {busy ? "Calculating..." : "Generate Solution"}
              </Button>
              {!result && <p className="text-sm text-muted-foreground">Run a simulation first.</p>}
              {result?.modernization && (
                <div className="space-y-2 text-sm">
                  <p>
                    <strong>Recommended action: </strong>
                    {noChanges
                      ? "Keep the current surviving network; no configuration change is proposed."
                      : (selectedCandidate?.title ??
                        String(
                          result.modernization.recommendation["proposed_modification"] ??
                            result.modernization.summary,
                        ))}
                  </p>
                  <p>
                    <strong>Why: </strong>
                    {String(
                      result.modernization.recommendation["rationale"] ??
                        result.modernization.summary,
                    )}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Step 4: Show the proposed solution</CardTitle>
              <CardDescription>
                Proposals stay separate from your saved network. Dashed purple connections indicate
                proposed changes; red connections remain unavailable.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {result?.modernization && result.modernized_topology && result.modernized_metrics ? (
                <>
                  <SimulationTopology
                    compact
                    network={result.modernized_topology}
                    comparisonNetwork={result.failed_topology}
                    metrics={result.modernized_metrics}
                    {...(playbackStage === "modernization" && activeLinkId ? { activeLinkId } : {})}
                    title={
                      noChanges ? "Surviving network - no changes proposed" : "Proposed solution"
                    }
                  />
                  <PrimaryMetrics metrics={result.modernized_metrics} />
                  <p className="rounded-lg bg-muted p-3 text-sm">
                    {result.modernization.service_outcome ?? result.modernization.summary}
                  </p>
                  {result.modernized_metrics.failed_links > 0 && (
                    <p className="text-sm text-muted-foreground">
                      Unavailable connections remain isolated and red in this proposal.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Generate a solution to see its topology and predicted performance.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Step 5: Compare results</CardTitle>
              <CardDescription>
                Connectivity describes the tested source-to-destination flow.{" "}
                {result &&
                  comparisonDemandText(
                    result.baseline_metrics.offered_traffic_mbps,
                    result.failed_metrics.offered_traffic_mbps,
                  )}
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              {result ? (
                <table className="w-full min-w-[540px] text-left text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="p-2">Metric</th>
                      <th className="p-2">Original network</th>
                      <th className="p-2">After failure</th>
                      <th className="p-2">Proposed solution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison
                      .filter((row) =>
                        [
                          "Achieved throughput",
                          "Total packet loss",
                          "Average latency",
                          "Flow path reachability",
                        ].includes(row.label),
                      )
                      .map((row) => (
                        <tr key={row.label} className="border-b">
                          <th className="p-2 font-medium">
                            {{
                              "Achieved throughput": "Throughput",
                              "Total packet loss": "Packet loss",
                              "Flow path reachability": "Connectivity",
                            }[row.label] ?? row.label}
                          </th>
                          <td className="p-2">{row.baseline}</td>
                          <td className="p-2">{row.failed}</td>
                          <td className="p-2">{row.modernized}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Results will appear after running the simulation.
                </p>
              )}
              {result && !result.modernized_metrics && (
                <p className="mt-3 text-sm text-muted-foreground">
                  Generate a solution to complete the comparison.
                </p>
              )}
            </CardContent>
          </Card>

          <details className="rounded-lg border p-4">
            <summary className="cursor-pointer font-semibold">Advanced Details</summary>
            <div className="mt-4 space-y-5">
              <p className="text-sm text-muted-foreground">
                Optimization, alternative candidates, AI explanations, experiment history, playback,
                and technical evidence.
              </p>
              <div className="space-y-2">
                <Label htmlFor="duration">Evaluation interval (seconds)</Label>
                <Input
                  id="duration"
                  type="number"
                  min="1"
                  max="86400"
                  value={durationSeconds}
                  onChange={(event) => setDurationSeconds(Number(event.target.value))}
                />
              </div>

              <ExperimentTools
                result={result}
                disabled={busy || loading}
                onBusyChange={setBusy}
                onResult={(value) => {
                  setResult(value);
                  setPlaying(false);
                  setPlaybackIndex(0);
                  setPlaybackStage("failure");
                }}
              />
              {result && (
                <>
                  <p className="break-all text-xs">
                    Experiment {result.experiment_id} / {result.engine_version} / Fingerprint{" "}
                    {result.topology_fingerprint}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setPlaybackStage("failure");
                        setPlaybackIndex(0);
                        setPlaying((value) => !value);
                      }}
                      disabled={!result.failure_steps.length}
                    >
                      {playing && playbackStage === "failure" ? (
                        <Pause className="mr-2 size-4" />
                      ) : (
                        <Play className="mr-2 size-4" />
                      )}
                      {playing && playbackStage === "failure" ? "Pause" : "Play"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setPlaying(false);
                        setPlaybackStage("failure");
                        setPlaybackIndex(0);
                      }}
                    >
                      <RotateCcw className="mr-2 size-4" />
                      Replay
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      Step {Math.min(playbackIndex, result.failure_steps.length)} /{" "}
                      {result.failure_steps.length}
                    </span>
                    <div className="h-2 min-w-40 flex-1 rounded bg-muted">
                      <div
                        className="h-2 rounded bg-primary transition-all"
                        style={{
                          width: `${result.failure_steps.length ? Math.min(100, (playbackIndex / result.failure_steps.length) * 100) : 0}%`,
                        }}
                      />
                    </div>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!result.modernization_steps.length}
                    onClick={() => {
                      setPlaybackStage("modernization");
                      setPlaybackIndex(0);
                      setPlaying((value) => (playbackStage === "modernization" ? !value : true));
                    }}
                  >
                    {playing && playbackStage === "modernization"
                      ? "Pause proposed route"
                      : "Play proposed route"}
                  </Button>
                  <details>
                    <summary>Route IDs and playback events</summary>
                    <pre className="overflow-auto text-xs">
                      {JSON.stringify(
                        {
                          baseline: result.baseline_metrics.route_link_ids,
                          failure: result.failed_metrics.route_link_ids,
                          proposed: result.modernized_metrics?.route_link_ids,
                          failure_steps: result.failure_steps,
                          modernization_steps: result.modernization_steps,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </>
              )}
              {baselineTopology && (
                <section>
                  <h3 className="mb-3 font-medium">Topology inventory</h3>
                  {!!baselineTopology!.nodes.length && (
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="overflow-x-auto rounded-md border">
                        <table className="w-full min-w-[600px] text-left text-xs">
                          <thead className="bg-muted/40">
                            <tr>
                              <th className="p-2">Device / ID</th>
                              <th className="p-2">Type / IP</th>
                              <th className="p-2">Status</th>
                              <th className="p-2">Processing capacity</th>
                            </tr>
                          </thead>
                          <tbody>
                            {baselineTopology!.nodes.map((node) => {
                              const flow = convertNetworkToReactFlow({
                                ...baselineTopology!,
                                nodes: [node],
                                links: [],
                              }).nodes[0];
                              const config = flow?.data.config as
                                Record<string, unknown> | undefined;
                              return (
                                <tr key={node.id} className="border-t">
                                  <td className="p-2">
                                    {node.name}
                                    <div className="font-mono text-muted-foreground">{node.id}</div>
                                  </td>
                                  <td className="p-2">
                                    {node.device_type}
                                    <div className="text-muted-foreground">
                                      {String(config?.["ipAddress"] || "IP unconfigured")}
                                    </div>
                                  </td>
                                  <td className="p-2">{node.status}</td>
                                  <td className="p-2">
                                    {node.resources?.["processing_capacity_mbps"] ?? "Unconfigured"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      <div className="overflow-x-auto rounded-md border">
                        <table className="w-full min-w-[600px] text-left text-xs">
                          <thead className="bg-muted/40">
                            <tr>
                              <th className="p-2">Connection / ID</th>
                              <th className="p-2">Capacity</th>
                              <th className="p-2">Latency</th>
                              <th className="p-2">Loss / status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(baselineTopology!.links ?? []).map((link) => (
                              <tr key={link.id} className="border-t">
                                <td className="p-2">
                                  {linkTitle(baselineTopology!, link.id)}
                                  <div className="font-mono text-muted-foreground">{link.id}</div>
                                </td>
                                <td className="p-2">
                                  {link.bandwidth_mbps == null
                                    ? "Unconfigured"
                                    : `${link.bandwidth_mbps} Mbps`}
                                </td>
                                <td className="p-2">
                                  {link.delay_ms == null ? "Unconfigured" : `${link.delay_ms} ms`}
                                </td>
                                <td className="p-2">
                                  {link.packet_loss_pct == null
                                    ? "Unconfigured"
                                    : `${link.packet_loss_pct}%`}{" "}
                                  / {link.status}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </section>
              )}
              {result?.modernization && (
                <section>
                  <div className="rounded-lg border p-4">
                    <h3 className="font-medium">Recommended solution and implementation</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      The candidate graph below applies this proposal in the analytical model. Use
                      these steps to understand how the selected scenario could be addressed; no
                      change is deployed automatically.
                    </p>
                    <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <dt className="text-muted-foreground">Identified problem</dt>
                        <dd>{String(result.modernization.recommendation["problem"] ?? "")}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Root cause</dt>
                        <dd>{String(result.modernization.recommendation["root_cause"] ?? "")}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Proposed change</dt>
                        <dd>
                          {String(
                            result.modernization.recommendation["proposed_modification"] ?? "",
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Relative cost</dt>
                        <dd>
                          {String(
                            result.modernization.recommendation["relative_cost"] ?? "Undetermined",
                          )}{" "}
                          (relative design proxy; no monetary quote)
                        </dd>
                      </div>
                      <div className="sm:col-span-2">
                        <dt className="text-muted-foreground">Why this proposal</dt>
                        <dd>{String(result.modernization.recommendation["rationale"] ?? "")}</dd>
                      </div>
                    </dl>
                    <p className="mt-3 text-sm text-muted-foreground">
                      {Array.isArray(result.modernization.recommendation["trade_offs"])
                        ? (result.modernization.recommendation["trade_offs"] as string[]).join(" ")
                        : ""}
                    </p>
                    {Array.isArray(result.modernization.recommendation["implementation_steps"]) && (
                      <div className="mt-4">
                        <h4 className="text-sm font-medium">Implementation outline</h4>
                        <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
                          {(
                            result.modernization.recommendation["implementation_steps"] as string[]
                          ).map((step, index) => (
                            <li key={`${index}-${step}`}>{step}</li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </div>
                </section>
              )}
              {result && (
                <Card>
                  <CardHeader>
                    <CardTitle>Three-Way Comparison</CardTitle>
                    <CardDescription>
                      Original, scenario and selected candidate results.{" "}
                      {comparisonDemandText(
                        result.baseline_metrics.offered_traffic_mbps,
                        result.failed_metrics.offered_traffic_mbps,
                      )}{" "}
                      Blank latency indicates an unstable queue or unreachable demand. These are
                      simulated metrics.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-sm">
                      <thead>
                        <tr className="border-b text-left">
                          <th className="p-2">Metric</th>
                          <th className="p-2">Original baseline</th>
                          <th className="p-2">After failure</th>
                          <th className="p-2">After modernization</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.map((row) => (
                          <tr key={row.label} className="border-b">
                            <th className="p-2 text-left font-medium">{row.label}</th>
                            <td className="p-2">{row.baseline}</td>
                            <td className="p-2">{row.failed}</td>
                            <td className="p-2">{row.modernized}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="mt-5 space-y-2 text-sm">
                      <h3 className="font-medium">Model assumptions and provenance</h3>
                      {result.assumptions.map((assumption) => (
                        <p
                          key={assumption}
                          className="rounded-md bg-muted/30 p-2 text-muted-foreground"
                        >
                          {assumption}
                        </p>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </details>
          <AnomalyPanel topology={saved?.topology} />
          <p className="text-xs text-muted-foreground">
            Analytical simulation, not live network telemetry. No packets are transmitted or network
            changes deployed.
          </p>
        </div>
      </main>
    </AppShell>
  );
}
