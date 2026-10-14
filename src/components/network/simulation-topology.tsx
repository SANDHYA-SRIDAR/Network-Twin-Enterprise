import { useMemo } from 'react';
import { ReactFlow, ReactFlowProvider, Background, BackgroundVariant, BaseEdge, Controls, MiniMap, getBezierPath, type Edge, type EdgeProps, type Node } from '@xyflow/react';
import { convertNetworkToReactFlow, type NetworkDefinition } from '@/lib/network-schema';
import { DeviceNodeCard, type DeviceData } from '@/components/network/network-workspace';

type RenderEdgeData = {
  cableType?: string;
  simulationStatus?: string;
  onRoute?: boolean;
  congested?: boolean;
  flowActive?: boolean;
};
type RenderEdge = Edge<RenderEdgeData, 'simulation'>;

function SimulationEdge({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps<RenderEdge>) {
  const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  const failed = data?.simulationStatus === 'failed' || data?.simulationStatus === 'offline' || data?.simulationStatus === 'down';
  const color = failed ? '#dc2626' : data?.congested ? '#f59e0b' : data?.flowActive ? '#2563eb' : data?.onRoute ? '#16a34a' : '#64748b';
  return <BaseEdge id={id} path={path} style={{ stroke: color, strokeWidth: data?.flowActive ? 4 : 2.5, strokeDasharray: data?.cableType === 'crossover' ? '9 6' : data?.flowActive ? '5 5' : undefined, animation: data?.flowActive ? 'simulation-flow 0.8s linear infinite' : undefined }} />;
}

const nodeTypes = { device: DeviceNodeCard };
const edgeTypes = { simulation: SimulationEdge };
const supportedModels = new Set(['pc-pt', '1941-router', 'server-pt', 'hub-pt', 'accesspoint-pt', '2960-24tt-switch', 'smart-load-balancer']);

export function SimulationTopology({
  network,
  metrics,
  activeLinkId,
  title,
}: {
  network: NetworkDefinition;
  metrics: { links: Array<{ id: string; congested: boolean; on_route: boolean }> };
  activeLinkId?: string;
  title: string;
}) {
  const { nodes, edges } = useMemo(() => {
    const converted = convertNetworkToReactFlow(network);
    const renderNodes = converted.nodes.map(node => ({
      ...node,
      data: {
        ...node.data,
        model: supportedModels.has(String(node.data.model)) ? String(node.data.model) : ({ 'core-router': '1941-router', 'distribution-switch': '2960-24tt-switch', 'load-balancer': 'smart-load-balancer' } as Record<string, string>)[String(node.data.deviceType)] ?? 'server-pt',
        config: node.data.config as DeviceData['config'],
      },
    })) as Node<DeviceData>[];
    const renderEdges = converted.edges.map(edge => {
      const metric = metrics.links.find(item => item.id === edge.id);
      const status = edge.data.status;
      return {
        ...edge,
        type: 'simulation',
        data: {
          ...edge.data,
          simulationStatus: status === 'offline' ? 'failed' : status,
          onRoute: metric?.on_route ?? false,
          congested: metric?.congested ?? false,
          flowActive: edge.id === activeLinkId,
        },
      };
    }) as RenderEdge[];
    return { nodes: renderNodes, edges: renderEdges };
  }, [activeLinkId, metrics.links, network]);

  return <section className="overflow-hidden rounded-lg border bg-card">
    <div className="border-b px-3 py-2 text-sm font-medium">{title} <span className="ml-2 text-xs font-normal text-muted-foreground">Analytically simulated</span></div>
    <div className="h-[360px]">
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }}>
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--canvas-dot)" />
          <Controls showInteractive={false} />
          <MiniMap nodeColor="var(--primary)" maskColor="color-mix(in oklch, var(--canvas) 75%, transparent)" />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
    <div className="flex flex-wrap gap-x-4 gap-y-1 border-t px-3 py-2 text-[11px] text-muted-foreground">
      <span><i className="mr-1 inline-block size-2 rounded-full bg-green-600" />Operational route</span>
      <span><i className="mr-1 inline-block size-2 rounded-full bg-red-600" />Failed link or device</span>
      <span><i className="mr-1 inline-block size-2 rounded-full bg-amber-500" />Congested link</span>
      <span><i className="mr-1 inline-block size-2 rounded-full bg-blue-600" />Current playback packet</span>
    </div>
  </section>;
}
