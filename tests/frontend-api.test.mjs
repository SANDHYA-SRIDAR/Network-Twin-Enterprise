import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { paretoPoints, comparisonDemandText } from "../src/lib/optimization-view.ts";
import { trafficChartRows, trafficParetoPoints } from "../src/lib/traffic-experiment.ts";

test("event charts preserve calculated values and absent candidate data", () => {
  const before = {
    series: [
      { time_seconds: 0.5, throughput_mbps: 2 },
      { time_seconds: 1, throughput_mbps: 4 },
    ],
  };
  const after = {
    series: [
      { time_seconds: 0.5, throughput_mbps: 1 },
      { time_seconds: 1, throughput_mbps: 0 },
    ],
  };
  assert.deepEqual(trafficChartRows(before, after), [
    { time: 0.5, original: 2, scenario: 1, proposed: null },
    { time: 1, original: 4, scenario: 0, proposed: null },
  ]);
});

test("event Pareto views retain connectivity without inventing undefined delay", () => {
  const candidates = [
    {
      id: "cut",
      title: "Cut",
      feasible: true,
      cost_units: 0,
      metrics: { average_latency_ms: null, connectivity_pct: 0 },
    },
  ];
  assert.deepEqual(trafficParetoPoints(candidates, ["cut"], "latency"), []);
  assert.deepEqual(trafficParetoPoints(candidates, ["cut"], "connectivity"), [
    { id: "cut", title: "Cut", cost: 0, value: 0 },
  ]);
});

test("Pareto projection excludes rejected and unsupported latency rather than plotting zero", () => {
  const item = (id, feasible, latency) => ({
    id,
    feasible,
    title: id,
    change_units: 3,
    metrics: { average_latency_ms: latency, throughput_mbps: 100 },
  });
  const points = paretoPoints(
    [
      item("valid", true, 2),
      item("unreachable", false, null),
      item("undefined", true, null),
      item("not-front", true, 1),
    ],
    ["valid", "unreachable", "undefined"],
  );
  assert.deepEqual(points, [{ id: "valid", title: "valid", cost: 3, latency: 2, throughput: 100 }]);
  assert.deepEqual(paretoPoints([], []), []);
});

test("comparison wording follows stored demand values including old exports", () => {
  assert.match(comparisonDemandText(100, 200), /Baseline offered load is 100 Mbps/);
  assert.match(comparisonDemandText(100, 200), /Scenario and recovery use 200 Mbps/);
  assert.match(comparisonDemandText(200, 200), /same offered load \(200 Mbps\)/);
});
import { apiUrl, DEV_API_TARGET, normalizeApiBaseUrl } from "../src/lib/api-config.ts";
import { requestApi, ApiError } from "../src/lib/api-request.ts";
import {
  createSupabaseFetch,
  assertPublicProjectKey,
} from "../src/integrations/supabase/public-client-options.ts";

test("API URL normalization keeps exactly one /api prefix", () => {
  assert.equal(apiUrl("", "/analysis/evaluate"), "/api/analysis/evaluate");
  assert.equal(
    apiUrl("http://127.0.0.1:8013/api/", "/api/failure-simulation/topology"),
    "http://127.0.0.1:8013/api/failure-simulation/topology",
  );
  assert.equal(normalizeApiBaseUrl(undefined), "");
  assert.throws(() => normalizeApiBaseUrl("http://user:password@localhost:8013"));
});

test("actual Vite proxy uses the shared backend port 8013", async () => {
  const config = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  assert.equal(DEV_API_TARGET, "http://127.0.0.1:8013");
  assert.match(config, /target: DEV_API_TARGET/);
  assert.match(config, /"\/api":/);
  assert.doesNotMatch(config, /8003|target:.*8080/);
});

test("public evaluation preserves method/path/body and needs no session", async () => {
  const body = JSON.stringify({ topology: {}, traffic: {} });
  const result = await requestApi(
    "analysis/evaluate",
    { method: "POST", body },
    {
      fetcher: async (url, init) => {
        assert.equal(url, "/api/analysis/evaluate");
        assert.equal(init.method, "POST");
        assert.equal(init.body, body);
        assert.equal(init.headers.get("Authorization"), null);
        return Response.json({ metrics: { provenance: "simulated" }, persisted: false });
      },
    },
  );
  assert.equal(result.metrics.provenance, "simulated");
});

test("protected requests use the current token and refresh exactly once after 401", async () => {
  const refreshes = [],
    headers = [];
  const result = await requestApi(
    "failure-simulation/topology",
    {},
    {
      accessToken: async (refresh) => {
        refreshes.push(refresh);
        return refresh ? "refreshed-test-token" : "current-test-token";
      },
      fetcher: async (_url, init) => {
        headers.push(init.headers.get("Authorization"));
        return headers.length === 1
          ? Response.json({ detail: "Expired" }, { status: 401 })
          : Response.json({ topology: {} });
      },
    },
  );
  assert.deepEqual(refreshes, [false, true]);
  assert.deepEqual(headers, ["Bearer current-test-token", "Bearer refreshed-test-token"]);
  assert.deepEqual(result, { topology: {} });
});

test("failed authentication is never retried indefinitely", async () => {
  let calls = 0;
  await assert.rejects(
    requestApi(
      "failure-simulation/topology",
      {},
      {
        accessToken: async () => "invalid-test-token",
        fetcher: async () => {
          calls++;
          return Response.json({ detail: "Invalid session" }, { status: 401 });
        },
      },
    ),
    (error) => error instanceof ApiError && error.status === 401,
  );
  assert.equal(calls, 2);
});

test("configuration/upstream/persistence errors retain status and are not retried", async () => {
  for (const status of [403, 404, 422, 500, 502, 503]) {
    let calls = 0;
    await assert.rejects(
      requestApi(
        "failure-simulation/run",
        { method: "POST", body: "{}" },
        {
          accessToken: async () => "test-user-token",
          fetcher: async () => {
            calls++;
            return Response.json({ detail: "Meaningful failure" }, { status });
          },
        },
      ),
      (error) =>
        error instanceof ApiError &&
        error.status === status &&
        error.message.includes("Meaningful failure"),
    );
    assert.equal(calls, 1);
  }
});

test("Supabase publishable header never replaces the user token", async () => {
  const key = "sb_publishable_test-project-key";
  const calls = [];
  const wrapped = createSupabaseFetch(key, async (_input, init) => {
    calls.push(init.headers);
    return Response.json({});
  });
  await wrapped("https://test.invalid/auth/v1/user", {
    headers: { Authorization: "Bearer test-user-session" },
  });
  await wrapped("https://test.invalid/auth/v1/settings", {
    headers: { Authorization: `Bearer ${key}` },
  });
  assert.equal(calls[0].get("apikey"), key);
  assert.equal(calls[0].get("Authorization"), "Bearer test-user-session");
  assert.equal(calls[1].get("Authorization"), null);
});

test("legacy anon JWT fallback is preserved; secret/user-token keys rejected", async () => {
  const legacy = `eyJhbGciOiJIUzI1NiJ9.${Buffer.from(JSON.stringify({ role: "anon" })).toString("base64url")}.test-signature`;
  const wrapped = createSupabaseFetch(legacy, async (_input, init) => {
    assert.equal(init.headers.get("apikey"), legacy);
    assert.equal(init.headers.get("Authorization"), `Bearer ${legacy}`);
    return Response.json({});
  });
  await wrapped("https://test.invalid/auth/v1/settings", {
    headers: { Authorization: `Bearer ${legacy}` },
  });
  assert.throws(() => assertPublicProjectKey("sb_secret_test-key"));
  const user = `header.${Buffer.from(JSON.stringify({ role: "authenticated" })).toString("base64url")}.signature`;
  assert.throws(() => assertPublicProjectKey(user));
});
