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
    if ((link.bandwidth_mbps ?? 0) <= 0) {
      issues.push({ path: `links.${link.id}.bandwidth_mbps`, code: 'invalid_bandwidth', message: 'Bandwidth must be greater than zero.' });
    }
    if ((link.delay_ms ?? 0) < 0) {
      issues.push({ path: `links.${link.id}.delay_ms`, code: 'invalid_delay', message: 'Delay cannot be negative.' });
    }
    if ((link.packet_loss_pct ?? 0) < 0 || (link.packet_loss_pct ?? 0) > 100) {
      issues.push({ path: `links.${link.id}.packet_loss_pct`, code: 'invalid_packet_loss', message: 'Packet loss must be between 0 and 100.' });
    }
  }

  return issues;
}

export function convertReactFlowToNetwork(nodes: ReactFlowNodeLike[], edges: ReactFlowEdgeLike[], name = 'NetworkDefinition'): NetworkDefinition {
  return {
    version: '1.0',
    name,
    description: 'Converted from a React Flow topology',
    nodes: nodes.map((node) => ({
      id: node.id,
      name: node.data?.label ?? node.id,
      device_type: (node.data?.deviceType as DeviceType) ?? 'switch',
      role: 'endpoint',
      interfaces: [{
        id: `${node.id}-eth0`,
        name: 'eth0',
        type: 'ethernet',
        status: 'up',
        ip_configuration: {
          ip_address: '10.0.0.10',
          subnet_mask: '255.255.255.0',
          prefix_length: 24,
          gateway: '10.0.0.1',
        },
      }],
      resources: {},
      security_zone: 'default',
      metadata: {
        position: node.position,
        model: node.data?.model ?? node.data?.deviceType ?? 'unknown',
      },
    })),
    links: edges.map((edge) => ({
      id: edge.id,
      source_node_id: edge.source,
      target_node_id: edge.target,
      source_interface_id: edge.sourceHandle ?? null,
      target_interface_id: edge.targetHandle ?? null,
      cable_type: (edge.data?.cableType as CableType) ?? 'straight-through',
      bandwidth_mbps: 1000,
      delay_ms: 1,
      packet_loss_pct: 0,
      status: 'active',
      metadata: {},
    })),
    routing: { static_routes: [], default_gateway: '10.0.0.1' },
    security: { zone: 'default', segmentation: [], firewall_rules: [] },
    simulation: { traffic_profile: 'baseline', duration_seconds: 300 },
    metadata: { source: 'react-flow' },
  };
}

export function convertNetworkToReactFlow(network: NetworkDefinition) {
  return {
    nodes: network.nodes.map((node) => ({
      id: node.id,
      type: 'device',
      position: (node.metadata?.position as { x: number; y: number }) ?? { x: 0, y: 0 },
      data: {
        label: node.name,
        deviceType: node.device_type,
        model: node.metadata?.model ?? node.device_type,
        status: 'healthy',
        config: {
          ipAddress: node.interfaces?.[0]?.ip_configuration?.ip_address ?? '',
          subnetMask: node.interfaces?.[0]?.ip_configuration?.subnet_mask ?? '255.255.255.0',
          defaultGateway: node.interfaces?.[0]?.ip_configuration?.gateway ?? '',
          interfacePorts: node.interfaces?.map((iface) => iface.name).join(', ') ?? 'GigabitEthernet0/0',
        },
      },
    })),
    edges: network.links?.map((link) => ({
      id: link.id,
      source: link.source_node_id,
      target: link.target_node_id,
      sourceHandle: link.source_interface_id ?? null,
      targetHandle: link.target_interface_id ?? null,
      data: { cableType: link.cable_type ?? 'straight-through' },
    })) ?? [],
  };
}
