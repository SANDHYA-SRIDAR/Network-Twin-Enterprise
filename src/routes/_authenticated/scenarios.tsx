import { createFileRoute } from '@tanstack/react-router';
import { ArrowRight, Cable, Gauge, Network, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { AppShell } from '@/components/network/app-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SCENARIO_OPTIONS, type ScenarioType } from '@/lib/scenario';
import { supabase } from '@/integrations/supabase/custom-client';
import { convertReactFlowToNetwork } from '@/lib/network-schema';

export const Route = createFileRoute('/_authenticated/scenarios')({
  component: ScenarioStudio,
});

function ScenarioStudio() {
  const [selectedType, setSelectedType] = useState<ScenarioType>('traffic_increase');
  const [error, setError] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<any>(null);
  const [loadingTopology, setLoadingTopology] = useState(true);

  useEffect(() => {
    let active = true;
    void (async () => {
      const { data: auth } = await supabase.auth.getUser();
      if (!auth.user) { if (active) { setError('Sign in to simulate your saved topology.'); setLoadingTopology(false); } return; }
      const [{ data: nodeRows, error: nodeError }, { data: linkRows, error: linkError }] = await Promise.all([
        supabase.from('network_nodes').select('*').eq('user_id', auth.user.id),
        supabase.from('network_connections').select('*').eq('user_id', auth.user.id),
      ]);
      if (!active) return;
      if (nodeError || linkError) { setError('Could not load your saved topology from Supabase.'); setLoadingTopology(false); return; }
      const nodes = (nodeRows ?? []).map(row => {
        const configuration = row.configuration && typeof row.configuration === 'object' && !Array.isArray(row.configuration) ? row.configuration : {};
        return { id: row.id, position: { x: row.position_x, y: row.position_y }, data: { label: row.label, deviceType: row.node_type, model: typeof configuration['model'] === 'string' ? configuration['model'] : row.node_type, config: { ...configuration } as Record<string, unknown>, status: row.status } };
      });
      const edges = (linkRows ?? []).map(row => {
        const configuration = row.configuration && typeof row.configuration === 'object' && !Array.isArray(row.configuration) ? row.configuration : {};
        const metric = (key: string, fallback: number) => { const value = Number(configuration[key]); return Number.isFinite(value) ? value : fallback; };
        return { id: row.id, source: row.source_node_id, target: row.target_node_id, data: { cableType: typeof configuration['cableType'] === 'string' ? configuration['cableType'] : 'straight-through', baseLatencyMs: metric('base_latency_ms', 1), maxCapacityMbps: metric('max_capacity_mbps', 1000), currentLoadMbps: metric('current_load_mbps', 100) } };
      });
      const converted = convertReactFlowToNetwork(nodes, edges, 'Saved topology');
      converted.nodes.forEach(node => { node.status = nodes.find(row => row.id === node.id)?.data.status === 'offline' ? 'down' : 'active'; });
      converted.links?.forEach(link => {
        const row = (linkRows ?? []).find(item => item.id === link.id);
        const configuration = row?.configuration && typeof row.configuration === 'object' && !Array.isArray(row.configuration) ? row.configuration : {};
        link.status = row?.status === 'offline' ? 'down' : 'active';
        link.delay_ms = Number(configuration['base_latency_ms'] ?? 1);
        link.bandwidth_mbps = Number(configuration['max_capacity_mbps'] ?? 1000);
        link.metadata = { ...link.metadata, current_load_mbps: Number(configuration['current_load_mbps'] ?? 100) };
      });
      setBaseline(converted);
      setLoadingTopology(false);
    })();
    return () => { active = false; };
  }, []);

  const selectedScenario = useMemo(
    () => SCENARIO_OPTIONS.find((option) => option.type === selectedType) ?? SCENARIO_OPTIONS[0]!,
    [selectedType],
  );

  const executeScenario = async () => {
    if (!baseline?.nodes?.length) { setError('Add and save devices in Topology before running a scenario.'); return; }
    setError(null);
    try {
      if (baseline.nodes.length < 2) throw new Error('Add at least two saved devices so the failure simulation can evaluate a traffic flow.');
      const endpoints = baseline.nodes.filter((node: any) => !['router', 'switch', 'hub', 'access_point'].includes(node.device_type));
      const source = endpoints[0]?.id ?? baseline.nodes[0]?.id;
      const destination = endpoints.at(-1)?.id ?? baseline.nodes.at(-1)?.id;
      if (!source || !destination || source === destination) throw new Error('Choose two distinct devices for a traffic flow.');
      const firstLink = baseline.links?.[0];
      const firstNode = baseline.nodes[0];
      const params = new URLSearchParams({ scenario: selectedType, autoRun: '1', flow_source_id: source, flow_target_id: destination, offered_mbps: '100', duration_seconds: '60' });
      if (firstLink) params.set('link_id', firstLink.id);
      if (firstNode) params.set('node_id', firstNode.id);
      if (selectedType === 'traffic_increase') params.set('factor', '1.5');
      if (selectedType === 'capacity_increase') params.set('increase_mbps', '250');
      if (selectedType === 'bandwidth_change' && firstLink) params.set('bandwidth_mbps', String(Math.max(1, Number(firstLink.bandwidth_mbps ?? 1000) * 0.5)));
      if (selectedType === 'redundancy_add') {
        const pair = baseline.nodes.flatMap((left: any, index: number) => baseline.nodes.slice(index + 1).map((right: any) => ({ left, right })))
          .find(({ left, right }: any) => !(baseline.links ?? []).some((link: any) => new Set([link.source_node_id, link.target_node_id]).has(left.id) && new Set([link.source_node_id, link.target_node_id]).has(right.id)));
        if (!pair) throw new Error('No unconnected device pair is available for a redundancy scenario.');
        params.set('redundancy_source_id', pair.left.id);
        params.set('redundancy_target_id', pair.right.id);
      }
      window.location.assign(`/failure-simulation?${params.toString()}`);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Could not open failure simulation.');
    }
  };

  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-y-auto bg-background">
        <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="font-mono text-xs uppercase text-primary">Simulation control plane</p>
              <h1 className="mt-2 text-3xl font-semibold">Scenario Studio</h1>
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                Evaluate a modeled network transformation against route resilience, service redundancy, and expected risk before production rollout.
              </p>
            </div>
            <Badge variant="outline">AI-guided network assessment</Badge>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <Card>
              <CardHeader>
                <CardTitle>Simulation templates</CardTitle>
                <CardDescription>Choose the condition you want the engine to evaluate.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {SCENARIO_OPTIONS.map((item) => (
                  <button
                    key={item.type}
                    type="button"
                    onClick={() => setSelectedType(item.type)}
                    className={`w-full rounded-xl border p-4 text-left transition ${selectedType === item.type ? 'border-primary bg-primary/5' : 'bg-card hover:border-muted-foreground/40'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="font-medium">{item.title}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                      </div>
                      <ArrowRight className="size-4 text-primary" />
                    </div>
                  </button>
                ))}
                <Button className="mt-4 w-full" onClick={executeScenario} disabled={loadingTopology || !baseline?.nodes?.length}>
                  {loadingTopology ? 'Loading saved topology…' : 'Run scenario'}
                </Button>
                {!loadingTopology && !baseline?.nodes?.length && <p className="text-sm text-muted-foreground">Save a topology with at least one device before running scenarios.</p>}
                {error && <p className="text-sm text-destructive">{error}</p>}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Baseline overview</CardTitle>
                <CardDescription>{selectedScenario.title}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg border bg-muted/20 p-3"><p className="text-muted-foreground">Nodes</p><p className="mt-1 text-xl font-semibold">{baseline?.nodes?.length ?? 0}</p></div>
                  <div className="rounded-lg border bg-muted/20 p-3"><p className="text-muted-foreground">Links</p><p className="mt-1 text-xl font-semibold">{baseline?.links?.length ?? 0}</p></div>
                </div>
                <div className="space-y-2 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2"><Network className="size-4 text-primary" /> Current saved topology</div>
                  <div className="flex items-center gap-2"><Cable className="size-4 text-primary" /> Current canvas connections</div>
                  <div className="flex items-center gap-2"><ShieldCheck className="size-4 text-primary" /> Modeled scenario results</div>
                </div>
              </CardContent>
            </Card>
          </div>

        </div>
      </main>
    </AppShell>
  );
}
