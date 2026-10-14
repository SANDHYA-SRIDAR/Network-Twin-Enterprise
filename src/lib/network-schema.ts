export type DeviceType = 'router' | 'switch' | 'hub' | 'access_point' | 'pc' | 'server' | 'load_balancer';
export type InterfaceType = 'ethernet' | 'serial' | 'console';
export type CableType = 'straight-through' | 'crossover' | 'fiber' | 'serial' | 'console';

export type IpConfiguration = {
  ip_address: string;
  subnet_mask?: string;
  prefix_length?: number;
  gateway?: string | null;
};

export type InterfaceDefinition = {
  id: string;
  name: string;
  type?: InterfaceType;
  status?: string;
  bandwidth_mbps?: number | null;
  ip_configuration?: IpConfiguration | null;
  mac_address?: string | null;
  metadata?: Record<string, unknown>;
};

export type NodeDefinition = {
  id: string;
  name: string;
  device_type: DeviceType;
  role?: string;
  status?: string;
  interfaces?: InterfaceDefinition[];
  resources?: Record<string, number>;
  security_zone?: string | null;
  metadata?: Record<string, unknown>;
};

export type LinkDefinition = {
  id: string;
  source_node_id: string;
  target_node_id: string;
  source_interface_id?: string | null;
  target_interface_id?: string | null;
  cable_type?: CableType;
  bandwidth_mbps?: number;
  delay_ms?: number;
  packet_loss_pct?: number;
  status?: string;
  metadata?: Record<string, unknown>;
};

export type RoutingConfiguration = {
  static_routes?: Array<Record<string, string>>;
  default_gateway?: string | null;
};

export type SecurityConfiguration = {
  zone?: string;
  segmentation?: string[];
  firewall_rules?: string[];
};

export type SimulationConfiguration = {
  traffic_profile?: string;
  scenario_id?: string | null;
  experiment_id?: string | null;
  duration_seconds?: number;
};

export type NetworkDefinition = {
  version?: string;
  name: string;
  description?: string;
  nodes: NodeDefinition[];
  links?: LinkDefinition[];
  routing?: RoutingConfiguration;
  security?: SecurityConfiguration;
  simulation?: SimulationConfiguration;
  metadata?: Record<string, unknown>;
};

export type ValidationIssue = {
  path: string;
  code: string;
  message: string;
};

export type ReactFlowNodeLike = {
  id: string;
  position: { x: number; y: number };
  data?: {
    label?: string;
    deviceType?: string;
    model?: string;
    status?: string;
    config?: Record<string, unknown>;
  };
};

export type ReactFlowEdgeLike = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  data?: {
    cableType?: string;
    status?: string;
    maxCapacityMbps?: number;
    baseLatencyMs?: number;
    packetLossPct?: number;
    currentLoadMbps?: number;
    qos?: boolean;
  };
};

const supportedDeviceTypes = new Set<DeviceType>(['router', 'switch', 'hub', 'access_point', 'pc', 'server', 'load_balancer']);
const supportedCableTypes = new Set<CableType>(['straight-through', 'crossover', 'fiber', 'serial', 'console']);

export function isValidIpv4(value: string): boolean {
  if (!value) return false;
  const parts = value.split('.');
  if (parts.length !== 4) return false;
  return parts.every((part) => {
    if (!/^\d+$/.test(part)) return false;
    const num = Number(part);
    return num >= 0 && num <= 255;
  });
}

function prefixFromMask(mask: string): number {
  if (!isValidSubnetMask(mask)) return 24;
  return mask.split('.').reduce((total, octet) => total + Number(octet).toString(2).replaceAll('0', '').length, 0);
}

export function isValidSubnetMask(value: string): boolean {
  if (!value) return false;
  const parts = value.split('.');
  if (parts.length !== 4) return false;
  const octets = parts.map((part) => Number(part));
  if (octets.some((n) => Number.isNaN(n) || n < 0 || n > 255)) return false;
  const binaryMask = octets.map((n) => n.toString(2).padStart(8, '0')).join('');
  const prefix = binaryMask.split('0');
  return binaryMask.includes('0') ? binaryMask.indexOf('0') > binaryMask.indexOf('1') && !binaryMask.includes('01') : true;
}

export function validateNetworkDefinition(network: NetworkDefinition): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const nodeIds = new Set<string>();
  const linkIds = new Set<string>();
  const usedIps = new Map<string, string>();

  for (const node of network.nodes) {
    if (nodeIds.has(node.id)) {
      issues.push({ path: `nodes.${node.id}`, code: 'duplicate_node_id', message: `Duplicate node id '${node.id}'.` });
    } else {
      nodeIds.add(node.id);
    }

    if (!supportedDeviceTypes.has(node.device_type)) {
      issues.push({ path: `nodes.${node.id}.device_type`, code: 'unsupported_device_type', message: `Unsupported device type '${node.device_type}'.` });
    }

    const seenInterfaces = new Set<string>();
    for (const iface of node.interfaces ?? []) {
      if (seenInterfaces.has(iface.id)) {
        issues.push({ path: `nodes.${node.id}.interfaces`, code: 'duplicate_interface_id', message: `Duplicate interface id '${iface.id}'.` });
      } else {
        seenInterfaces.add(iface.id);
      }
      const ip = iface.ip_configuration?.ip_address;
      if (ip) {
        if (!isValidIpv4(ip)) {
          issues.push({ path: `nodes.${node.id}.interfaces.${iface.id}.ip_configuration.ip_address`, code: 'invalid_ipv4', message: `Invalid IPv4 address '${ip}'.` });
        } else if (usedIps.has(ip)) {
          issues.push({ path: `nodes.${node.id}.interfaces.${iface.id}.ip_configuration.ip_address`, code: 'duplicate_ip', message: `IP address '${ip}' is already assigned to '${usedIps.get(ip)}'.` });
        } else {
          usedIps.set(ip, `${node.id}:${iface.id}`);
        }
      }
    }
  }

  for (const link of network.links ?? []) {
    if (linkIds.has(link.id)) {
      issues.push({ path: `links.${link.id}`, code: 'duplicate_link_id', message: `Duplicate link id '${link.id}'.` });
    } else {
      linkIds.add(link.id);
    }

    if (!supportedCableTypes.has(link.cable_type ?? 'straight-through')) {
      issues.push({ path: `links.${link.id}.cable_type`, code: 'unsupported_cable_type', message: `Unsupported cable type '${link.cable_type}'.` });
    }
    if (!nodeIds.has(link.source_node_id)) {
      issues.push({ path: `links.${link.id}.source_node_id`, code: 'missing_source_node', message: `Source node '${link.source_node_id}' does not exist.` });
    }
    if (!nodeIds.has(link.target_node_id)) {
      issues.push({ path: `links.${link.id}.target_node_id`, code: 'missing_target_node', message: `Target node '${link.target_node_id}' does not exist.` });
    }
    if (link.source_node_id === link.target_node_id) {
      issues.push({ path: `links.${link.id}`, code: 'self_link', message: 'A link cannot connect a node to itself.' });
    }
    if (typeof link.bandwidth_mbps === 'number' && link.bandwidth_mbps <= 0) {
      issues.push({ path: `links.${link.id}.bandwidth_mbps`, code: 'invalid_bandwidth', message: 'Bandwidth must be greater than zero.' });
    }
    if (typeof link.delay_ms === 'number' && link.delay_ms < 0) {
      issues.push({ path: `links.${link.id}.delay_ms`, code: 'invalid_delay', message: 'Delay cannot be negative.' });
    }
    if (typeof link.packet_loss_pct === 'number' && (link.packet_loss_pct < 0 || link.packet_loss_pct > 100)) {
      issues.push({ path: `links.${link.id}.packet_loss_pct`, code: 'invalid_packet_loss', message: 'Packet loss must be between 0 and 100.' });
    }
  }

  return issues;
}

export function convertReactFlowToNetwork(nodes: ReactFlowNodeLike[], edges: ReactFlowEdgeLike[], name = 'NetworkDefinition'): NetworkDefinition {
  const deviceTypeMap: Record<string, DeviceType> = {
    'core-router': 'router',
    'distribution-switch': 'switch',
    'cloud-server': 'server',
    'load-balancer': 'load_balancer',
    router: 'router',
    switch: 'switch',
    hub: 'hub',
    access_point: 'access_point',
    pc: 'pc',
    server: 'server',
    load_balancer: 'load_balancer',
  };
  return {
    version: '1.0',
    name,
    description: 'Converted from a React Flow topology',
    nodes: nodes.map((node) => {
      const model = node.data?.model;
      const mappedType = deviceTypeMap[node.data?.deviceType ?? 'switch'] ?? 'switch';
      const deviceType = model === 'pc-pt' ? 'pc' : model === 'server-pt' ? 'server' : mappedType;
      const config = node.data?.config ?? {};
      const rawIps = String(config['ipAddress'] ?? '').split(',').map((value) => value.trim()).filter(Boolean);
      const ports = String(config['interfacePorts'] ?? '').split(',').map((value) => value.trim()).filter(Boolean);
      const interfaceIps = deviceType === 'router' ? rawIps : rawIps.slice(0, 1);
      return {
      id: node.id,
      name: node.data?.label ?? node.id,
      device_type: deviceType,
      role: deviceType === 'router' || deviceType === 'switch' ? 'network' : 'endpoint',
      status: node.data?.status === 'offline' ? 'down' : node.data?.status === 'warning' ? 'degraded' : 'active',
      interfaces: interfaceIps.map((value, index) => {
        const [ipAddress, prefixText] = value.split('/');
        const prefixLength = prefixText ? Number(prefixText) : prefixFromMask(String(config['subnetMask'] ?? '255.255.255.0'));
        const portName = ports[index] ?? `eth${index}`;
        return {
          id: `${node.id}-if${index}`,
          name: portName,
          type: 'ethernet' as const,
          status: 'up',
          ip_configuration: {
            ip_address: ipAddress ?? '',
            subnet_mask: prefixToMask(prefixLength),
            prefix_length: prefixLength,
            gateway: index === 0 && isValidIpv4(String(config['defaultGateway'] ?? '')) ? String(config['defaultGateway']) : null,
          },
        };
      }),
      resources: {
        ...(typeof config['processingCapacityMbps'] === 'number' ? { processing_capacity_mbps: config['processingCapacityMbps'] } : {}),
        ...(typeof config['bandwidthMbps'] === 'number' ? { bandwidth_mbps: config['bandwidthMbps'] } : {}),
      },
      security_zone: 'default',
      metadata: {
        position: node.position,
        model: model ?? node.data?.deviceType ?? 'unknown',
        configuration: config,
        http_service: deviceType === 'server' || deviceType === 'load_balancer' ? { enabled: true, port: Number(config['httpPort']) || 80 } : undefined,
      },
    };
    }),
    links: edges.map((edge) => {
      const interfaceId = (nodeId: string, handle: string | null | undefined) => {
        if (handle) return handle;
        const node = nodes.find((item) => item.id === nodeId);
        if (deviceTypeMap[node?.data?.deviceType ?? ''] !== 'router') return null;
        const linkIndex = edges.filter((item) => item.source === nodeId || item.target === nodeId).findIndex((item) => item.id === edge.id);
        return `${nodeId}-if${linkIndex}`;
      };
      return {
        id: edge.id,
        source_node_id: edge.source,
        target_node_id: edge.target,
        source_interface_id: interfaceId(edge.source, edge.sourceHandle),
        target_interface_id: interfaceId(edge.target, edge.targetHandle),
        cable_type: (edge.data?.cableType as CableType) ?? 'straight-through',
        ...(typeof edge.data?.maxCapacityMbps === 'number' ? { bandwidth_mbps: edge.data.maxCapacityMbps } : {}),
        ...(typeof edge.data?.baseLatencyMs === 'number' ? { delay_ms: edge.data.baseLatencyMs } : {}),
        ...(typeof edge.data?.packetLossPct === 'number' ? { packet_loss_pct: edge.data.packetLossPct } : {}),
        status: edge.data?.status === 'offline' ? 'down' : edge.data?.status === 'degraded' ? 'degraded' : 'active',
        metadata: {
          ...(typeof edge.data?.currentLoadMbps === 'number' ? { current_load_mbps: edge.data.currentLoadMbps } : {}),
          ...(typeof edge.data?.qos === 'boolean' ? { qos: edge.data.qos } : {}),
        },
      };
    }),
    routing: { static_routes: [], default_gateway: '10.0.0.1' },
    security: { zone: 'default', segmentation: [], firewall_rules: [] },
    simulation: { traffic_profile: 'baseline', duration_seconds: 300 },
    metadata: { source: 'react-flow' },
  };
}

function prefixToMask(prefix: number): string {
  const bits = Math.max(0, Math.min(32, prefix));
  const value = bits === 0 ? 0 : (0xffffffff << (32 - bits)) >>> 0;
  return [24, 16, 8, 0].map((shift) => (value >>> shift) & 255).join('.');
}

export function convertNetworkToReactFlow(network: NetworkDefinition) {
  return {
    nodes: network.nodes.map((node) => ({
      id: node.id,
      type: 'device',
      position: (node.metadata?.['position'] as { x: number; y: number }) ?? { x: 0, y: 0 },
      data: {
        label: node.name,
        deviceType: node.device_type === 'router' ? 'core-router' : node.device_type === 'switch' ? 'distribution-switch' : node.device_type === 'load_balancer' ? 'load-balancer' : 'cloud-server',
        model: node.metadata?.['model'] ?? node.device_type,
        status: node.status === 'down' || node.status === 'offline' ? 'offline' : node.status === 'degraded' || node.status === 'warning' ? 'warning' : 'healthy',
        config: (() => {
          const saved = node.metadata?.['configuration'] && typeof node.metadata['configuration'] === 'object' && !Array.isArray(node.metadata['configuration']) ? node.metadata['configuration'] as Record<string, unknown> : {};
          const derivedIp = node.interfaces?.filter((iface) => iface.ip_configuration).map((iface) => `${iface.ip_configuration?.ip_address}${iface.ip_configuration?.prefix_length != null ? `/${iface.ip_configuration.prefix_length}` : ''}`).join(', ');
          return {
            ...saved,
            ipAddress: typeof saved['ipAddress'] === 'string' ? saved['ipAddress'] : derivedIp ?? '',
            subnetMask: typeof saved['subnetMask'] === 'string' ? saved['subnetMask'] : node.interfaces?.[0]?.ip_configuration?.subnet_mask ?? '',
            defaultGateway: typeof saved['defaultGateway'] === 'string' ? saved['defaultGateway'] : node.interfaces?.[0]?.ip_configuration?.gateway ?? '',
            interfacePorts: typeof saved['interfacePorts'] === 'string' ? saved['interfacePorts'] : node.interfaces?.map((iface) => iface.name).join(', ') ?? '',
            httpPort: typeof saved['httpPort'] === 'string' ? saved['httpPort'] : String((node.metadata?.['http_service'] as { port?: number } | undefined)?.port ?? ''),
          };
        })(),
      },
    })),
    edges: network.links?.map((link) => ({
      id: link.id,
      source: link.source_node_id,
      target: link.target_node_id,
        sourceHandle: link.source_interface_id ?? (typeof link.metadata?.['source_handle'] === 'string' ? link.metadata['source_handle'] : null),
        targetHandle: link.target_interface_id ?? (typeof link.metadata?.['target_handle'] === 'string' ? link.metadata['target_handle'] : null),
      data: {
        cableType: link.cable_type ?? 'straight-through',
        status: link.status === 'down' || link.status === 'offline' ? 'offline' : link.status === 'degraded' ? 'degraded' : 'active',
        ...(typeof link.bandwidth_mbps === 'number' ? { maxCapacityMbps: link.bandwidth_mbps } : {}),
        ...(typeof link.delay_ms === 'number' ? { baseLatencyMs: link.delay_ms } : {}),
        ...(typeof link.packet_loss_pct === 'number' ? { packetLossPct: link.packet_loss_pct } : {}),
        ...(typeof link.metadata?.['current_load_mbps'] === 'number' ? { currentLoadMbps: link.metadata['current_load_mbps'] } : {}),
        ...(typeof link.metadata?.['qos'] === 'boolean' ? { qos: link.metadata['qos'] } : {}),
      },
    })) ?? [],
  };
}
