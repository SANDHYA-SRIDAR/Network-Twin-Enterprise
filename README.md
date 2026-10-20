# NetTransform AI / NexusTwin

An enterprise topology workspace with deterministic analytical failure experiments and AI-assisted decision explanations. Built with React 19, TanStack Start/Router, React Flow, Tailwind, FastAPI/Pydantic and Supabase. This existing project remains connected to [Lovable](https://lovable.dev); preserve published Git history.

The primary pipeline uses no Mininet, VM, SSH, physical hardware, Open vSwitch or Containerlab. It is an analytical model, not packet-level simulation or measured telemetry.

## Start

From the repository root, create a Python environment and start the API:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8013
```

The stateless workflow works immediately without any account, database or AI provider. From another terminal at the repository root:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8013/api/analysis/experiment -ContentType application/json -Body (Get-Content -Raw examples/failure-experiment.json)
```

The example is explicitly configured synthetic input, never evidence from a physical network. The response contains baseline/failure/candidate graphs, metrics, ranking, constraints and assumptions. It is not persisted. Interactive API documentation: `http://127.0.0.1:8013/docs`; canonical contract: `/api/openapi.json`.

For the existing authenticated visual workspace, copy `.env.example` to `.env`, supply your Supabase URL and public project key, apply the SQL migrations in timestamp order, then:

```powershell
npm ci
npm run dev
```

Vite proxies `/api` to port 8013. For separate production API hosting, set `VITE_API_URL` and configure `CORS_ORIGINS` as a JSON array of allowed frontend origins. Backend settings load root `.env` then backend `.env`; environment variables override both. Never use a secret/service-role key as a browser publishable key.

Sign in, build/save a topology, run a scenario, compare recovery strategies, adjust weights/budget, inspect every candidate, and request an evidence explanation. History reload and JSON export retain experiment snapshots and recommendations. Saved topology remains canonical; candidate graphs are experiment proposals and are not deployed or automatically applied.

Optional API container: `docker compose up --build api` (frontend continues with `npm run dev`). Container definitions are supplied; Docker execution has not been verified here.

## AI explanations

Without a provider, the assistant returns a labeled deterministic evidence explanation. To enable generated explanations set server-only `ASSISTANT_URL`, `ASSISTANT_MODEL`, and optional `ASSISTANT_API_KEY`. The configured endpoint accepts chat-completion JSON (`model`, `temperature`, `messages`) and returns `choices[0].message.content`. It may be a local or hosted service. Only an explicit explanation request calls it. Provider failure retains the deterministic explanation; generated text never changes simulation scores or topology. Provider transport is covered with test doubles; a live provider has not been exercised.

## Verify

```powershell
cd backend
python -m unittest discover -s tests -p "test_*.py"
python export_contract.py --check
python -m compileall -q app
cd ..
npx tsc --noEmit
npm run build
git diff --check
```

Pydantic is the topology schema source of truth. `python export_contract.py` in backend regenerates the JSON Schema and frontend TypeScript contract. Existing Supabase row configurations map into this shape; no second topology store is introduced.

See [audit](docs/repository-audit.md), [model and API](docs/network-failure-simulation.md), and [actual verification status](project-status.md). Live Supabase/RLS, signed-in browser interactions, live AI and Docker remain separately identified verification requirements.

## Authentication and configuration diagnostics

The backend resolves root/backend `.env` files using absolute repository paths, with backend-local and then process-environment overrides. Use the same Supabase URL and public key for `SUPABASE_*` and `VITE_SUPABASE_*`; conflicting values fail safely. `SUPABASE_ANON_KEY` is a legacy fallback. Settings load once per process, so restart after editing environment values. `GET /api/configuration/supabase` exposes only the project reference, key category and configuration flags; local validity is not an upstream credential check.

Protected endpoints use the OpenAPI `SupabaseBearer` scheme. The API sends the project key in `apikey` and the user's session token in `Authorization: Bearer`. Opaque publishable keys are never used as user tokens. Missing/invalid/expired sessions return 401, Supabase project-key rejection returns 503, database permission denial returns 403, and unreachable/malformed upstream data returns 502. Experiment insert/update success requires database confirmation, not an empty response. No migrations need rerunning for these fixes.

The frontend reads the current session for every protected request and refreshes once after a 401; it does not retry configuration or persistence failures. Public analysis requests remain stateless. `VITE_API_URL` accepts an API origin or trailing `/api` without duplicating the route prefix. Run frontend request/proxy tests with `npm run test:api` (Node 24), type checking with `npm run typecheck`.

### NSGA-II and operator decisions

The failure-simulation workflow supports opt-in pymoo NSGA-II, evaluated Pareto alternatives, and owner-scoped experiment plan selection/acceptance/rejection. See [the implementation and verification report](docs/optimization-decision-milestones.md) for objective/constraint definitions, provider output requirements and remaining live verification gates. Candidate plans do not deploy or overwrite the saved topology.
