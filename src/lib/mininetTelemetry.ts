import { API_URL } from '@/lib/constants';

/**
 * Fetches mock Mininet telemetry data from the FastAPI backend.
 * The backend exposes GET /api/mininet/telemetry which returns a JSON
 * payload with fields like `cpu_usage_pct`, `latency_ms`, and `throughput_mbps`.
 *
 * This helper abstracts the fetch logic and returns the parsed JSON.
 */
const USE_REAL_TELEMETRY = false; // Set to true to fetch real telemetry from VM

export async function fetchMininetTelemetry(): Promise<any> {
    const endpoint = USE_REAL_TELEMETRY ? `${API_URL}/api/mininet/real-telemetry` : `${API_URL}/api/mininet/telemetry`;
    const response = await fetch(endpoint);
    if (!response.ok) {
        throw new Error(`Failed to fetch telemetry: ${response.status}`);
    }
    return response.json();
}
const response = await fetch(`${API_URL}/api/mininet/telemetry`);
if (!response.ok) {
    throw new Error(`Failed to fetch telemetry: ${response.status}`);
}
return response.json();
}
