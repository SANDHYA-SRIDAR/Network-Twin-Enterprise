// Prefer same-origin API requests in local development (Vite proxies /api to FastAPI).
// Set VITE_API_URL for deployments that host the API on another origin.
export const API_URL = import.meta.env['VITE_API_URL'] || '';
