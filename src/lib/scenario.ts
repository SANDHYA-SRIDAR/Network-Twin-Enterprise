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
