import { createFileRoute } from '@tanstack/react-router';
import { ArrowRight, Cable, Gauge, Network, ShieldCheck, TrendingUp } from 'lucide-react';
import { useMemo, useState } from 'react';
import { AppShell } from '@/components/network/app-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { runScenario, type ScenarioType } from '@/lib/scenario';

const sampleNetwork = {
  name: 'Enterprise Edge',
  description: 'Branch modernization candidate',
  nodes: [
    { id: 'core', name: 'Core Router', device_type: 'router', status: 'active', interfaces: [{ id: 'eth0', name: 'eth0', ip_configuration: { ip_address: '10.10.10.1', subnet_mask: '255.255.255.0', gateway: '10.10.10.254' } }] },
    { id: 'fw', name: 'Security Gateway', device_type: 'router', status: 'active', interfaces: [{ id: 'eth1', name: 'eth1', ip_configuration: { ip_address: '10.10.10.2', subnet_mask: '255.255.255.0', gateway: '10.10.10.254' } }] },
    { id: 'app', name: 'Application Server', device_type: 'server', status: 'active', interfaces: [{ id: 'eth2', name: 'eth2', ip_configuration: { ip_address: '10.10.10.10', subnet_mask: '255.255.255.0', gateway: '10.10.10.254' } }] },
    { id: 'db', name: 'Database Cluster', device_type: 'server', status: 'active', interfaces: [{ id: 'eth3', name: 'eth3', ip_configuration: { ip_address: '10.10.10.11', subnet_mask: '255.255.255.0', gateway: '10.10.10.254' } }] },
  ],
  links: [
    { id: 'l1', source_node_id: 'core', target_node_id: 'fw', cable_type: 'fiber', bandwidth_mbps: 2000, delay_ms: 2, packet_loss_pct: 0 },
    { id: 'l2', source_node_id: 'fw', target_node_id: 'app', cable_type: 'fiber', bandwidth_mbps: 1000, delay_ms: 4, packet_loss_pct: 0 },
    { id: 'l3', source_node_id: 'fw', target_node_id: 'db', cable_type: 'fiber', bandwidth_mbps: 1000, delay_ms: 5, packet_loss_pct: 0 },
  ],
};

const scenarioOptions: { type: ScenarioType; title: string; description: string }[] = [
  { type: 'link_failure', title: 'Link failure', description: 'Fail a primary circuit and assess failover resilience.' },
  { type: 'traffic_increase', title: 'Traffic increase', description: 'Model a higher user and app demand profile.' },
  { type: 'bandwidth_change', title: 'Bandwidth change', description: 'Rebalance WAN and service policy for capacity changes.' },
  { type: 'redundancy_add', title: 'Redundancy add', description: 'Add redundant pathing for resilience planning.' },
  { type: 'device_failure', title: 'Device failure', description: 'Test critical service outage behavior.' },
];

export const Route = createFileRoute('/_authenticated/scenarios')({
  component: ScenarioStudio,
});

function ScenarioStudio() {
  const [selectedType, setSelectedType] = useState<ScenarioType>('traffic_increase');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedScenario = useMemo(
    () => scenarioOptions.find((option) => option.type === selectedType) ?? scenarioOptions[0],
    [selectedType],
  );

  const executeScenario = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await runScenario({
        name: `Scenario: ${selectedScenario.title}`,
        description: selectedScenario.description,
        baseline: sampleNetwork,
        scenario: { type: selectedType, target: 'core', node_id: 'fw', value: 1.5 },
        assumptions: { region: 'global-east', seasonality: 'normal' },
      });
      setResult(response);
    } catch (apiError) {
      const message = apiError instanceof Error ? apiError.message : 'Scenario request failed';
      setError(message);
    } finally {
      setBusy(false);
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
                {scenarioOptions.map((item) => (
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
                <Button className="mt-4 w-full" onClick={executeScenario} disabled={busy}>
                  {busy ? 'Simulating…' : 'Run scenario'}
                </Button>
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
                  <div className="rounded-lg border bg-muted/20 p-3"><p className="text-muted-foreground">Nodes</p><p className="mt-1 text-xl font-semibold">{sampleNetwork.nodes.length}</p></div>
                  <div className="rounded-lg border bg-muted/20 p-3"><p className="text-muted-foreground">Links</p><p className="mt-1 text-xl font-semibold">{sampleNetwork.links.length}</p></div>
                </div>
                <div className="space-y-2 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2"><Network className="size-4 text-primary" /> Enterprise edge topology</div>
                  <div className="flex items-center gap-2"><Cable className="size-4 text-primary" /> Fiber backbone with path redundancy</div>
                  <div className="flex items-center gap-2"><ShieldCheck className="size-4 text-primary" /> Policy-aligned resilience posture</div>
                </div>
              </CardContent>
            </Card>
          </div>

          {result && (
            <div className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
              <Card>
                <CardHeader className="pb-3"><CardTitle className="text-sm">Risk score</CardTitle></CardHeader>
                <CardContent><p className="text-3xl font-semibold">{result.summary.risk_score}</p></CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-3"><CardTitle className="text-sm">Redundancy</CardTitle></CardHeader>
                <CardContent><p className="text-3xl font-semibold">{result.summary.service_redundancy}</p></CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-3"><CardTitle className="text-sm">Throughput</CardTitle></CardHeader>
                <CardContent><p className="text-3xl font-semibold">{result.summary.throughput_mbps} Mbps</p></CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-3"><CardTitle className="text-sm">Latency</CardTitle></CardHeader>
                <CardContent><p className="text-3xl font-semibold">{result.summary.latency_ms} ms</p></CardContent>
              </Card>
            </div>
          )}

          {result && (
            <Card className="mt-8">
              <CardHeader>
                <CardTitle>Decision summary</CardTitle>
                <CardDescription>{result.summary.decision}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary"><TrendingUp className="mr-1 size-3" /> {result.scenario_type}</Badge>
                  <Badge variant="secondary"><Gauge className="mr-1 size-3" /> baseline: {result.baseline.risk_score}</Badge>
                  <Badge variant="secondary"><ShieldCheck className="mr-1 size-3" /> provenance: {result.provenance}</Badge>
                </div>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {result.evidence.map((item: string, index: number) => (
                    <li key={`${item}-${index}`} className="rounded-md border bg-muted/20 p-3">{item}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </AppShell>
  );
}
