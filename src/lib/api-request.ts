import { apiUrl, DEV_API_TARGET } from "./api-config.ts";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type RequestOptions = {
  baseUrl?: string;
  // Called on every protected request and once more after a 401 to refresh.
  accessToken?: (refresh: boolean) => Promise<string>;
  fetcher?: typeof fetch;
};

export async function requestApi<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const fetcher = options.fetcher ?? fetch;
  const send = async (refresh: boolean) => {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (options.accessToken) {
      const token = await options.accessToken(refresh);
      if (!token) throw new ApiError(401, "Sign in to access your saved experiments.");
      headers.set("Authorization", `Bearer ${token}`);
    }
    try {
      return await fetcher(apiUrl(options.baseUrl, path), { ...init, headers });
    } catch (error) {
      if (error instanceof TypeError)
        throw new ApiError(
          0,
          `Cannot reach the API. Local Vite /api requests require FastAPI at ${DEV_API_TARGET}.`,
        );
      throw error;
    }
  };
  let response = await send(false);
  if (response.status === 401 && options.accessToken) response = await send(true);
  if (!response.ok) {
    let detail = `API request failed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* A proxy can return a non-JSON error; retain status and useful target. */
    }
    if (response.status === 502)
      detail += ` Check backend availability at ${DEV_API_TARGET} and any reported upstream failure.`;
    throw new ApiError(response.status, detail);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(502, "The API returned an invalid JSON response.");
  }
}
