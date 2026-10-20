// Prefer same-origin API requests in local development (Vite proxies /api to FastAPI).
// Set VITE_API_URL for deployments that host the API on another origin.
import { normalizeApiBaseUrl } from "./api-config";
export const API_URL = normalizeApiBaseUrl(import.meta.env["VITE_API_URL"]);
