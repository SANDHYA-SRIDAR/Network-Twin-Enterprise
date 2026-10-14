import { createFileRoute } from '@tanstack/react-router';
import { Activity, AlertTriangle, Check, Pause, Play, RotateCcw, ShieldAlert, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AppShell } from '@/components/network/app-shell';
import { SimulationTopology } from '@/components/network/simulation-topology';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { supabase } from '@/integrations/supabase/custom-client';
import { loadSavedSimulationTopology, modernizeSimulation, runFailureSimulation, type FailureSimulationResult, type SimulationMetrics } from '@/lib/failure-simulation';
import { convertNetworkToReactFlow, type NetworkDefinition } from '@/lib/network-schema';
import { SCENARIO_OPTIONS, type ScenarioType } from '@/lib/scenario';

export const Route = createFileRoute('/_authenticated/failure-simulation')({ component: FailureSimulationPage });

type TopologyState = { topology: NetworkDefinition; topology_fingerprint: string };
const EMPTY_METRICS: SimulationMetrics = {
  packets_sent: 0, packets_delivered: 0, packets_dropped: 0, packet_loss_pct: 0,
  average_latency_ms: null, maximum_latency_ms: null, offered_traffic_mbps: 0, throughput_mbps: 0,
  path_capacity_mbps: 0, mean_link_utilization_pct: 0, reachable_nodes: 0, total_nodes: 0,
  unreachable_nodes: 0, active_links: 0, failed_links: 0, congested_links: 0, bottleneck_link_ids: [],
  connectivity_pct: 0, flow_connected: false, route_node_ids: [], route_link_ids: [], links: [], provenance: 'simulated', stage: 'baseline',
};
const deviceTitle = (topology: NetworkDefinition, id: string) => topology.nodes.find(node => node.id === id)?.name ?? id;
const linkTitle = (topology: NetworkDefinition, id: string) => {
  const link = topology.links?.find(edge => edge.id === id);
  return link ? `${deviceTitle(topology, link.source_node_id)} ↔ ${deviceTitle(topology, link.target_node_id)}` : id;
};
const format = (value: number | null | undefined, digits = 2) => value == null || !Number.isFinite(value) ? 'Unreachable' : value.toFixed(digits);

function MetricCard({ label, value, unit, detail }: { label: string; value: string | number; unit?: string; detail?: string }) {
  return <div className="rounded-lg border bg-background p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold">{value}{unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}</p>{detail && <p className="mt-1 text-[11px] text-muted-foreground">{detail}</p>}</div>;
}

function metricRows(result: FailureSimulationResult | null): Array<{ label: string; baseline: string; failed: string; modernized: string }> {
  if (!result) return [];
  const values: [SimulationMetrics, SimulationMetrics, SimulationMetrics | null] = [result.baseline_metrics, result.failed_metrics, result.modernized_metrics ?? null];
  const show = (metric: SimulationMetrics | null, key: keyof SimulationMetrics, suffix = '') => {
    const value = metric?.[key];
    return typeof value === 'number' ? `${format(value)}${suffix}` : '—';
  };
  return [
    { label: 'Packet loss', baseline: show(values[0], 'packet_loss_pct', '%'), failed: show(values[1], 'packet_loss_pct', '%'), modernized: show(values[2], 'packet_loss_pct', '%') },
    { label: 'Average latency', baseline: show(values[0], 'average_latency_ms', ' ms'), failed: show(values[1], 'average_latency_ms', ' ms'), modernized: show(values[2], 'average_latency_ms', ' ms') },
    { label: 'Achieved throughput', baseline: show(values[0], 'throughput_mbps', ' Mbps'), failed: show(values[1], 'throughput_mbps', ' Mbps'), modernized: show(values[2], 'throughput_mbps', ' Mbps') },
    { label: 'Mean link utilization', baseline: show(values[0], 'mean_link_utilization_pct', '%'), failed: show(values[1], 'mean_link_utilization_pct', '%'), modernized: show(values[2], 'mean_link_utilization_pct', '%') },
    { label: 'Reachable devices', baseline: values[0] ? `${values[0].reachable_nodes}/${values[0].total_nodes}` : '—', failed: values[1] ? `${values[1].reachable_nodes}/${values[1].total_nodes}` : '—', modernized: values[2] ? `${values[2].reachable_nodes}/${values[2].total_nodes}` : '—' },
    { label: 'Active / failed links', baseline: values[0] ? `${values[0].active_links} / ${values[0].failed_links}` : '—', failed: values[1] ? `${values[1].active_links} / ${values[1].failed_links}` : '—', modernized: values[2] ? `${values[2].active_links} / ${values[2].failed_links}` : '—' },
    { label: 'Congested links', baseline: values[0] ? String(values[0].congested_links) : '—', failed: values[1] ? String(values[1].congested_links) : '—', modernized: values[2] ? String(values[2].congested_links) : '—' },
    { label: 'Bottleneck links', baseline: values[0] ? String(values[0].bottleneck_link_ids.length) : '—', failed: values[1] ? String(values[1].bottleneck_link_ids.length) : '—', modernized: values[2] ? String(values[2].bottleneck_link_ids.length) : '—' },
  ];
}

function FailureSimulationPage() {
  const launchParams = useMemo(() => typeof window === 'undefined' ? new URLSearchParams() : new URLSearchParams(window.location.search), []);
  const requestedScenario = launchParams.get('scenario') as ScenarioType | null;
  const initialScenario = SCENARIO_OPTIONS.some(option => option.type === requestedScenario) ? requestedScenario! : 'link_failure';
  const autoRunRef = useRef(false);
  const [saved, setSaved] = useState<TopologyState | null>(null);
  const [result, setResult] = useState<FailureSimulationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenarioType, setScenarioType] = useState<ScenarioType>(initialScenario);
  const [nodeTarget, setNodeTarget] = useState(launchParams.get('node_id') ?? '');
  const [linkTarget, setLinkTarget] = useState(launchParams.get('link_id') ?? '');
  const [source, setSource] = useState(launchParams.get('flow_source_id') ?? '');
  const [destination, setDestination] = useState(launchParams.get('flow_target_id') ?? '');
  const [trafficMbps, setTrafficMbps] = useState(Number(launchParams.get('offered_mbps') ?? 100));
  const [durationSeconds, setDurationSeconds] = useState(Number(launchParams.get('duration_seconds') ?? 60));
  const [parameterValue, setParameterValue] = useState(Number(launchParams.get('factor') ?? launchParams.get('bandwidth_mbps') ?? launchParams.get('increase_mbps') ?? 250));
  const [redundancySource, setRedundancySource] = useState(launchParams.get('redundancy_source_id') ?? '');
  const [redundancyTarget, setRedundancyTarget] = useState(launchParams.get('redundancy_target_id') ?? '');
  const [playing, setPlaying] = useState(false);
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [playbackStage, setPlaybackStage] = useState<'failure' | 'modernization'>('failure');

  useEffect(() => {
    let active = true;
    void (async () => {
      const { data: sessionResult, error: sessionError } = await supabase.auth.getSession();
      if (sessionError || !sessionResult.session) { if (active) { setError('Sign in to load your saved topology.'); setLoading(false); } return; }
      try {
        const topology = await loadSavedSimulationTopology(sessionResult.session.access_token);
        if (!active) return;
        setSaved(topology);
        const endpoints = topology.topology.nodes.filter(node => !['router', 'switch', 'hub', 'access_point'].includes(node.device_type));
        setSource(current => current || endpoints[0]?.id || topology.topology.nodes[0]?.id || '');
        setDestination(current => current || endpoints.at(-1)?.id || topology.topology.nodes.at(-1)?.id || '');
        setNodeTarget(current => current || topology.topology.nodes[0]?.id || '');
        setLinkTarget(current => current || topology.topology.links?.[0]?.id || '');
        setRedundancySource(current => current || topology.topology.nodes[0]?.id || '');
        setRedundancyTarget(current => current || topology.topology.nodes[1]?.id || '');
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Could not load the saved topology.');
      } finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, []);

  const scenario = useMemo(() => SCENARIO_OPTIONS.find(option => option.type === scenarioType) ?? SCENARIO_OPTIONS[0]!, [scenarioType]);
  const params = useMemo(() => {
    switch (scenario.parameter) {
      case 'link': return { link_id: linkTarget };
      case 'node': return { node_id: nodeTarget };
      case 'traffic-factor': return { factor: parameterValue };
      case 'bandwidth': return scenarioType === 'capacity_increase' ? { link_id: linkTarget, increase_mbps: parameterValue } : { link_id: linkTarget, bandwidth_mbps: parameterValue };
      case 'redundancy': return { source_node_id: redundancySource, target_node_id: redundancyTarget, bandwidth_mbps: parameterValue };
      case 'placement': return { node_id: nodeTarget };
    }
  }, [linkTarget, nodeTarget, parameterValue, redundancySource, redundancyTarget, scenario.parameter, scenarioType]);
  const parameterValid = useMemo(() => {
    if (!saved) return false;
    if (scenario.parameter === 'link') return saved.topology.links?.some(link => link.id === linkTarget) ?? false;
    if (scenario.parameter === 'node' || scenario.parameter === 'placement') return saved.topology.nodes.some(node => node.id === nodeTarget);
    if (scenario.parameter === 'traffic-factor' || scenario.parameter === 'bandwidth') return Number.isFinite(parameterValue) && parameterValue > 0 && (scenario.parameter !== 'bandwidth' || Boolean(linkTarget));
    return Boolean(redundancySource && redundancyTarget && redundancySource !== redundancyTarget);
  }, [linkTarget, nodeTarget, parameterValue, redundancySource, redundancyTarget, saved, scenario.parameter]);
  const playbackEvents = playbackStage === 'failure' ? result?.failure_steps ?? [] : result?.modernization_steps ?? [];
  const activeLinkId = playing && playbackEvents[playbackIndex]?.['kind'] === 'forward' ? String(playbackEvents[playbackIndex]?.['link_id'] ?? '') : undefined;
  const baselineTopology = result?.baseline_topology ?? saved?.topology;
  const failedTopology = result?.failed_topology;
  const modernizedTopology = result?.modernized_topology;

  useEffect(() => {
    if (!playing) return;
    if (playbackIndex >= playbackEvents.length) { setPlaying(false); return; }
    const timer = window.setTimeout(() => setPlaybackIndex(index => index + 1), 850);
    return () => window.clearTimeout(timer);
  }, [playing, playbackEvents.length, playbackIndex]);

  const run = async () => {
    if (!saved || !parameterValid || !source || !destination || source === destination) return;
    setBusy(true); setError(null); setResult(null); setPlaying(false); setPlaybackIndex(0); setPlaybackStage('failure');
    try {
      const { data: session } = await supabase.auth.getSession();
      if (!session.session) throw new Error('Sign in again to run a simulation.');
      const next = await runFailureSimulation(session.session.access_token, {
        scenario_type: scenarioType, parameters: params,
        traffic: { source_node_id: source, target_node_id: destination, offered_mbps: trafficMbps, duration_seconds: durationSeconds, packet_size_bytes: 1500 },
        topology_fingerprint: saved.topology_fingerprint,
      });
      setResult(next); setSaved({ topology: next.baseline_topology, topology_fingerprint: next.topology_fingerprint });
    } catch (runError) { setError(runError instanceof Error ? runError.message : 'Simulation failed.'); }
    finally { setBusy(false); }
  };

  const modernize = async () => {
    if (!result) return;
    setBusy(true); setError(null);
    try {
      const { data: session } = await supabase.auth.getSession();
      if (!session.session) throw new Error('Sign in again to request modernization.');
      const next = await modernizeSimulation(session.session.access_token, result.experiment_id);
      setResult(next); setPlaybackStage('modernization'); setPlaybackIndex(0); setPlaying(false);
    } catch (modernizeError) { setError(modernizeError instanceof Error ? modernizeError.message : 'Modernization failed.'); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    if (launchParams.get('autoRun') !== '1' || loading || !saved || !parameterValid || !source || !destination || source === destination || autoRunRef.current) return;
    autoRunRef.current = true;
    void run();
  }, [launchParams, loading, saved, parameterValid, source, destination]);

  const comparison = metricRows(result);
  const currentMetrics = result ? playbackStage === 'failure' ? result.failed_metrics : result.modernized_metrics ?? result.failed_metrics : EMPTY_METRICS;
  const currentNetwork = playbackStage === 'failure' ? failedTopology : modernizedTopology;
  const busyLabel = loading ? 'Loading saved topology…' : busy ? 'Calculating…' : 'Run Simulation';

  return <AppShell><main className="min-h-0 flex-1 overflow-y-auto bg-background">
    <div className="mx-auto max-w-[1500px] space-y-6 px-5 py-7 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="font-mono text-xs uppercase text-primary">Analytical simulation · provenance: simulated</p><h1 className="mt-2 text-3xl font-semibold">Network Failure Simulation &amp; Modernization</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Run deterministic failure and traffic analysis against the authenticated topology saved in Supabase. The original rows remain unchanged.</p></div>
        {result && <Badge variant="outline">Experiment {result.experiment_id.slice(0, 8)} · {result.engine_version}</Badge>}
      </header>

      <Card>
        <CardHeader><CardTitle>Select Failure Scenario</CardTitle><CardDescription>Scenario identifiers and names are shared with Scenario Studio. Each run uses a separate simulation copy.</CardDescription></CardHeader>
        <CardContent className="grid gap-5 xl:grid-cols-[1fr_1.2fr_1fr]">
          <div className="space-y-2"><Label htmlFor="failure-scenario">Scenario</Label><select id="failure-scenario" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={scenarioType} onChange={event => setScenarioType(event.target.value as ScenarioType)}>{SCENARIO_OPTIONS.map(item => <option key={item.type} value={item.type}>{item.title}</option>)}</select><p className="text-sm text-muted-foreground">{scenario.description}</p></div>
          <div className="grid gap-3 sm:grid-cols-2">
            {(scenario.parameter === 'link' || scenario.parameter === 'bandwidth') && <div className="space-y-2 sm:col-span-2"><Label htmlFor="failure-link">Affected connection</Label><select id="failure-link" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={linkTarget} onChange={event => setLinkTarget(event.target.value)}><option value="">Choose saved connection</option>{saved?.topology.links?.map(link => <option key={link.id} value={link.id}>{linkTitle(saved.topology, link.id)} · {link.id.slice(0, 8)}</option>)}</select></div>}
            {(scenario.parameter === 'node' || scenario.parameter === 'placement') && <div className="space-y-2 sm:col-span-2"><Label htmlFor="failure-node">Affected device</Label><select id="failure-node" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={nodeTarget} onChange={event => setNodeTarget(event.target.value)}><option value="">Choose saved device</option>{saved?.topology.nodes.map(node => <option key={node.id} value={node.id}>{node.name} · {node.id.slice(0, 8)}</option>)}</select></div>}
            {scenario.parameter === 'traffic-factor' && <div className="space-y-2"><Label htmlFor="traffic-factor">Traffic increase factor</Label><Input id="traffic-factor" type="number" min="0.01" step="0.1" value={parameterValue} onChange={event => setParameterValue(Number(event.target.value))} /></div>}
            {scenario.parameter === 'bandwidth' && <div className="space-y-2"><Label htmlFor="capacity-value">{scenarioType === 'capacity_increase' ? 'Capacity increase (Mbps)' : 'New capacity (Mbps)'}</Label><Input id="capacity-value" type="number" min="1" step="10" value={parameterValue} onChange={event => setParameterValue(Number(event.target.value))} /></div>}
            {scenario.parameter === 'redundancy' && <><div className="space-y-2"><Label htmlFor="redundancy-source">Candidate link source</Label><select id="redundancy-source" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={redundancySource} onChange={event => setRedundancySource(event.target.value)}>{saved?.topology.nodes.map(node => <option key={node.id} value={node.id}>{node.name}</option>)}</select></div><div className="space-y-2"><Label htmlFor="redundancy-target">Candidate link destination</Label><select id="redundancy-target" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={redundancyTarget} onChange={event => setRedundancyTarget(event.target.value)}>{saved?.topology.nodes.map(node => <option key={node.id} value={node.id}>{node.name}</option>)}</select></div><div className="space-y-2"><Label htmlFor="redundancy-capacity">Candidate capacity (Mbps)</Label><Input id="redundancy-capacity" type="number" min="1" step="10" value={parameterValue} onChange={event => setParameterValue(Number(event.target.value))} /></div></>}
            {scenario.parameter === 'placement' && <p className="text-xs text-amber-700 sm:col-span-2">This is an existing Scenario Studio option. The saved schema has no site or cloud-latency model, so the engine reports unchanged network metrics and explains the limitation.</p>}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="traffic-source">Traffic source</Label><select id="traffic-source" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={source} onChange={event => setSource(event.target.value)}>{saved?.topology.nodes.map(node => <option key={node.id} value={node.id}>{node.name} · {node.id.slice(0, 8)}</option>)}</select></div>
            <div className="space-y-2"><Label htmlFor="traffic-destination">Traffic destination</Label><select id="traffic-destination" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={destination} onChange={event => setDestination(event.target.value)}>{saved?.topology.nodes.map(node => <option key={node.id} value={node.id}>{node.name} · {node.id.slice(0, 8)}</option>)}</select></div>
            <div className="space-y-2"><Label htmlFor="offered-load">Offered traffic (Mbps)</Label><Input id="offered-load" type="number" min="0.01" step="10" value={trafficMbps} onChange={event => setTrafficMbps(Number(event.target.value))} /></div>
            <div className="space-y-2"><Label htmlFor="duration">Evaluation interval (seconds)</Label><Input id="duration" type="number" min="1" max="86400" value={durationSeconds} onChange={event => setDurationSeconds(Number(event.target.value))} /></div>
            <Button className="sm:col-span-2" onClick={run} disabled={busy || loading || !saved || !saved.topology.nodes.length || !parameterValid || !source || !destination || source === destination}><Activity className="mr-2 size-4" />{busyLabel}</Button>
          </div>
        </CardContent>
        {error && <div className="mx-6 mb-5 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
      </Card>

      {loading && <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Loading the authenticated user's saved topology from Supabase…</CardContent></Card>}
      {!loading && saved && <Card>
        <CardHeader><CardTitle>Baseline Network — Current Saved Topology</CardTitle><CardDescription>Exact node IDs, link IDs, device positions, and configured properties returned by the backend from Supabase. Fingerprint {saved.topology_fingerprint.slice(0, 16)}…</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          {!saved.topology.nodes.length && <p className="text-sm text-muted-foreground">This account has no saved devices. Add and save devices in Topology Workspace first.</p>}
          {saved.topology.nodes.length > 0 && <SimulationTopology network={baselineTopology!} metrics={result?.baseline_metrics ?? EMPTY_METRICS} title="Original Baseline" />}
          {!!saved.topology.nodes.length && <div className="grid gap-4 lg:grid-cols-2">
            <div className="overflow-x-auto rounded-md border"><table className="w-full min-w-[600px] text-left text-xs"><thead className="bg-muted/40"><tr><th className="p-2">Device / ID</th><th className="p-2">Type / IP</th><th className="p-2">Status</th><th className="p-2">Processing capacity</th></tr></thead><tbody>{saved.topology.nodes.map(node => { const flow = convertNetworkToReactFlow({ ...saved.topology, nodes: [node], links: [] }).nodes[0]; const config = flow?.data.config as Record<string, unknown> | undefined; return <tr key={node.id} className="border-t"><td className="p-2">{node.name}<div className="font-mono text-muted-foreground">{node.id}</div></td><td className="p-2">{node.device_type}<div className="text-muted-foreground">{String(config?.['ipAddress'] || 'IP unconfigured')}</div></td><td className="p-2">{node.status}</td><td className="p-2">{node.resources?.['processing_capacity_mbps'] ?? 'Unconfigured'}</td></tr>; })}</tbody></table></div>
            <div className="overflow-x-auto rounded-md border"><table className="w-full min-w-[600px] text-left text-xs"><thead className="bg-muted/40"><tr><th className="p-2">Connection / ID</th><th className="p-2">Capacity</th><th className="p-2">Latency</th><th className="p-2">Loss / status</th></tr></thead><tbody>{(saved.topology.links ?? []).map(link => <tr key={link.id} className="border-t"><td className="p-2">{linkTitle(saved.topology, link.id)}<div className="font-mono text-muted-foreground">{link.id}</div></td><td className="p-2">{link.bandwidth_mbps == null ? 'Unconfigured' : `${link.bandwidth_mbps} Mbps`}</td><td className="p-2">{link.delay_ms == null ? 'Unconfigured' : `${link.delay_ms} ms`}</td><td className="p-2">{link.packet_loss_pct == null ? 'Unconfigured' : `${link.packet_loss_pct}%`} / {link.status}</td></tr>)}</tbody></table></div>
          </div>}
        </CardContent>
      </Card>}

      {result && failedTopology && <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert className="size-5 text-destructive" />After Failure — Simulation Playback</CardTitle><CardDescription>Calculated snapshot; playback animates the recorded route steps. No packets are sent and no saved topology rows are modified.</CardDescription></CardHeader><CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2"><Button variant="outline" size="sm" onClick={() => { setPlaybackStage('failure'); setPlaybackIndex(0); setPlaying(value => !value); }} disabled={!result.failure_steps.length}>{playing && playbackStage === 'failure' ? <Pause className="mr-2 size-4" /> : <Play className="mr-2 size-4" />}{playing && playbackStage === 'failure' ? 'Pause' : 'Play'}</Button><Button variant="outline" size="sm" onClick={() => { setPlaying(false); setPlaybackStage('failure'); setPlaybackIndex(0); }}><RotateCcw className="mr-2 size-4" />Replay</Button><span className="text-xs text-muted-foreground">Step {Math.min(playbackIndex, result.failure_steps.length)} / {result.failure_steps.length}</span><div className="h-2 min-w-40 flex-1 rounded bg-muted"><div className="h-2 rounded bg-primary transition-all" style={{ width: `${result.failure_steps.length ? Math.min(100, playbackIndex / result.failure_steps.length * 100) : 0}%` }} /></div></div>
        <SimulationTopology network={failedTopology} metrics={result.failed_metrics} {...(playbackStage === 'failure' && activeLinkId ? { activeLinkId } : {})} title="Failed Topology" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><MetricCard label="Sent / delivered / dropped" value={`${currentMetrics.packets_sent.toLocaleString()} / ${currentMetrics.packets_delivered.toLocaleString()} / ${currentMetrics.packets_dropped.toLocaleString()}`} /><MetricCard label="Packet loss" value={format(currentMetrics.packet_loss_pct)} unit="%" /><MetricCard label="Offered / achieved throughput" value={`${format(currentMetrics.offered_traffic_mbps)} / ${format(currentMetrics.throughput_mbps)}`} unit="Mbps" detail={`Route capacity ${format(currentMetrics.path_capacity_mbps)} Mbps`} /><MetricCard label="Average / maximum latency" value={`${format(currentMetrics.average_latency_ms)} / ${format(currentMetrics.maximum_latency_ms)}`} unit="ms" /><MetricCard label="Reachable devices" value={`${currentMetrics.reachable_nodes} / ${currentMetrics.total_nodes}`} /><MetricCard label="Link utilization" value={format(currentMetrics.mean_link_utilization_pct)} unit="% mean" /><MetricCard label="Congestion / bottlenecks" value={`${currentMetrics.congested_links} / ${currentMetrics.bottleneck_link_ids.length}`} /><MetricCard label="Active / failed links" value={`${currentMetrics.active_links} / ${currentMetrics.failed_links}`} /></div>
        <div className="flex flex-wrap items-center gap-2"><Button onClick={modernize} disabled={busy}><Sparkles className="mr-2 size-4" />{result.modernization ? 'Refresh Solution Simulation' : 'Generate Solution Simulation'}</Button>{result.modernization && <Badge variant={result.modernization.resolved ? 'default' : 'destructive'}>{result.modernization.resolved ? 'Candidate improves modeled service' : 'No supported recovery found'}</Badge>}</div>
      </CardContent></Card>}

      {result?.modernization && result.modernized_topology && result.modernized_metrics && <Card><CardHeader><CardTitle>Modernized Network — Proposed Resolution</CardTitle><CardDescription>{result.modernization.summary} Candidate topology is an experiment snapshot; accepting or saving it to Topology Workspace is not part of this operation.</CardDescription></CardHeader><CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2"><Button variant="outline" size="sm" onClick={() => { setPlaybackStage('modernization'); setPlaybackIndex(0); setPlaying(value => !value); }} disabled={!result.modernization_steps.length}>{playing && playbackStage === 'modernization' ? <Pause className="mr-2 size-4" /> : <Play className="mr-2 size-4" />}{playing && playbackStage === 'modernization' ? 'Pause' : 'Play proposed route'}</Button><Button variant="outline" size="sm" onClick={() => { setPlaying(false); setPlaybackStage('modernization'); setPlaybackIndex(0); }}><RotateCcw className="mr-2 size-4" />Replay</Button><span className="text-xs text-muted-foreground">Candidate remains separate from the saved topology.</span></div>
        <SimulationTopology network={result.modernized_topology} metrics={result.modernized_metrics} {...(playbackStage === 'modernization' && activeLinkId ? { activeLinkId } : {})} title="Modernized Network — Proposed Resolution" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><MetricCard label="Packets delivered" value={result.modernized_metrics.packets_delivered.toLocaleString()} /><MetricCard label="Packet loss" value={format(result.modernized_metrics.packet_loss_pct)} unit="%" /><MetricCard label="Throughput" value={format(result.modernized_metrics.throughput_mbps)} unit="Mbps" /><MetricCard label="Latency" value={format(result.modernized_metrics.average_latency_ms)} unit="ms" /></div>
        <div className="rounded-lg border p-4"><h3 className="font-medium">Recommended solution and implementation</h3><p className="mt-1 text-sm text-muted-foreground">The candidate graph below applies this proposal in the analytical model. Use these steps to understand how the selected scenario could be addressed; no change is deployed automatically.</p><dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-muted-foreground">Identified problem</dt><dd>{String(result.modernization.recommendation['problem'] ?? '')}</dd></div><div><dt className="text-muted-foreground">Root cause</dt><dd>{String(result.modernization.recommendation['root_cause'] ?? '')}</dd></div><div><dt className="text-muted-foreground">Proposed change</dt><dd>{String(result.modernization.recommendation['proposed_modification'] ?? '')}</dd></div><div><dt className="text-muted-foreground">Relative cost</dt><dd>{String(result.modernization.recommendation['relative_cost'] ?? 'Undetermined')} (no monetary cost model)</dd></div><div className="sm:col-span-2"><dt className="text-muted-foreground">Why this proposal</dt><dd>{String(result.modernization.recommendation['rationale'] ?? '')}</dd></div></dl>{Array.isArray(result.modernization.recommendation['implementation_steps']) && <div className="mt-4"><h4 className="text-sm font-medium">Implementation outline</h4><ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-muted-foreground">{(result.modernization.recommendation['implementation_steps'] as string[]).map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol></div>}</div>
      </CardContent></Card>}

      {result && <Card><CardHeader><CardTitle>Three-Way Comparison</CardTitle><CardDescription>Original, failed, and candidate modernized results under equivalent traffic inputs. These are simulated metrics.</CardDescription></CardHeader><CardContent className="overflow-x-auto"><table className="w-full min-w-[640px] text-sm"><thead><tr className="border-b text-left"><th className="p-2">Metric</th><th className="p-2">Original baseline</th><th className="p-2">After failure</th><th className="p-2">After modernization</th></tr></thead><tbody>{comparison.map(row => <tr key={row.label} className="border-b"><th className="p-2 text-left font-medium">{row.label}</th><td className="p-2">{row.baseline}</td><td className="p-2">{row.failed}</td><td className="p-2">{row.modernized}</td></tr>)}</tbody></table>
        <div className="mt-5 space-y-2 text-sm"><h3 className="font-medium">Model assumptions and provenance</h3>{result.assumptions.map(assumption => <p key={assumption} className="rounded-md bg-muted/30 p-2 text-muted-foreground">{assumption}</p>)}</div>
      </CardContent></Card>}
      {result && <div className="flex items-start gap-2 rounded-md border p-3 text-xs text-muted-foreground"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" /><p>Results are deterministic analytical simulations, not measured network telemetry. Supabase experiment record {result.experiment_id} is stored with topology snapshots and engine version. Candidate changes have not been deployed.</p>{result.modernization?.resolved && <Check className="mt-0.5 size-4 text-green-600" />}</div>}
      {saved && result === null && saved.topology.nodes.length > 0 && <p className="text-xs text-muted-foreground">Saved topology loaded with {saved.topology.nodes.length} devices and {saved.topology.links?.length ?? 0} connections.</p>}
    </div>
  </main></AppShell>;
}
