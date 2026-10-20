export function assertPublicProjectKey(key: string): void {
  if (key.startsWith("sb_publishable_")) return;
  try {
    const part = key.split(".")[1] ?? "";
    const payload = JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.role === "anon") return;
  } catch {
    /* Report configuration category only, never key contents. */
  }
  throw new Error(
    "Configure a Supabase publishable key or legacy anon project key; secret keys and user tokens are not browser project keys.",
  );
}

export function createSupabaseFetch(
  supabaseKey: string,
  fetcher: typeof fetch = fetch,
): typeof fetch {
  assertPublicProjectKey(supabaseKey);
  return (input, init) => {
    const headers = new Headers(
      typeof Request !== "undefined" && input instanceof Request ? input.headers : undefined,
    );
    if (init?.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
    // Opaque API keys belong only in apikey; legacy anon JWT fallback remains valid.
    if (
      supabaseKey.startsWith("sb_publishable_") &&
      headers.get("Authorization") === `Bearer ${supabaseKey}`
    )
      headers.delete("Authorization");
    headers.set("apikey", supabaseKey);
    return fetcher(input, { ...init, headers });
  };
}
