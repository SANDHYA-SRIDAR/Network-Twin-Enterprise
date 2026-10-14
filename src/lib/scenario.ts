import { API_URL } from '@/lib/constants';

export type ScenarioType =
  | 'link_failure'
  | 'traffic_increase'
  | 'bandwidth_change'
  | 'redundancy_add'
  | 'device_failure'
  | 'segment_isolation'
  | 'capacity_increase'
  | 'cloud_migration';

export type ScenarioOption = {
  type: ScenarioType;
  title: string;
  description: string;
  parameter: 'link' | 'node' | 'traffic-factor' | 'bandwidth' | 'redundancy' | 'placement';
};

export const SCENARIO_OPTIONS: ScenarioOption[] = [
  { type: 'link_failure', title: 'Link failure', description: 'Fail a selected connection and calculate rerouting or loss.', parameter: 'link' },
  { type: 'traffic_increase', title: 'Traffic increase', description: 'Increase offered traffic and evaluate congestion and delivery.', parameter: 'traffic-factor' },
  { type: 'bandwidth_change', title: 'Bandwidth change', description: 'Set a selected connection capacity for the simulation.', parameter: 'bandwidth' },
  { type: 'redundancy_add', title: 'Redundancy add', description: 'Add a candidate connection between saved devices in the simulation copy.', parameter: 'redundancy' },
  { type: 'device_failure', title: 'Device failure', description: 'Fail a selected device and its forwarding paths.', parameter: 'node' },
  { type: 'segment_isolation', title: 'Segment isolation', description: 'Isolate a selected device and its attached traffic paths.', parameter: 'node' },
  { type: 'capacity_increase', title: 'Capacity increase', description: 'Increase the capacity of a selected connection.', parameter: 'bandwidth' },
  { type: 'cloud_migration', title: 'Cloud migration', description: 'Placement-only analysis; network effects are unavailable without site and cloud-latency data.', parameter: 'placement' },
];

export interface ScenarioMutation {
  type: ScenarioType;
  target?: string;
  node_id?: string;
  link_id?: string;
  value?: number;
  metadata?: Record<string, unknown>;
}

export interface ScenarioRequest {
  name: string;
  description: string;
  baseline: Record<string, unknown>;
  scenario: ScenarioMutation;
  assumptions?: Record<string, unknown>;
}

export async function runScenario(request: ScenarioRequest): Promise<any> {
  const response = await fetch(`${API_URL}/api/scenario/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Scenario execution failed');
  }

  return response.json();
}
