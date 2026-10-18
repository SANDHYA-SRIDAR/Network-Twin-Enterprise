export const DEV_API_TARGET = "http://127.0.0.1:8013";

export function normalizeApiBaseUrl(value: string | undefined): string {
  const base = (value ?? "")
    .trim()
    .replace(/\/+$/, "")
    .replace(/\/api$/, "");
  if (!base) return "";
  const url = new URL(base);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      "VITE_API_URL must be an HTTP(S) API origin without credentials or query parameters.",
    );
  }
  return base;
}

export function apiUrl(base: string | undefined, path: string): string {
  return `${normalizeApiBaseUrl(base)}/api/${path.replace(/^\/?api\//, "").replace(/^\/+/, "")}`;
}
