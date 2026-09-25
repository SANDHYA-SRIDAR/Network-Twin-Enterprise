import { API_URL } from '@/lib/constants';

/**
 * Sends the current topology (nodes and edges) to the FastAPI backend for deployment.
 * The backend expects a JSON payload with a `topology` field.
 */
export async function deployTopology(topology: any): Promise<void> {
    const response = await fetch(`${API_URL}/api/deploy/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ topology }),
    });

    if (!response.ok) {
        const err = await response.text();
        throw new Error(`Deployment failed: ${response.status} – ${err}`);
    }
}
