# Authentication and API repair - 2026-10-16

## Confirmed causes

1. The ignored root environment file contained different SUPABASE_PUBLISHABLE_KEY and VITE_SUPABASE_PUBLISHABLE_KEY values. Backend alias priority selected the incorrect server value. Safe live probes of the project's Auth settings returned 401/Invalid API key for that value and 200 for the dashboard-verified frontend value. The local server value has been synchronized without printing or committing credentials.
2. Vite targeted port 8003 while the working backend runs on 8013: direct health returned 200 and proxy health returned 502 before the fix.
3. Raw Header parameters did not declare an OpenAPI security scheme. Also, generic upstream error handling mislabeled project-key rejection as a user-session failure. Supabase can return 403/bad JWT for invalid sessions; it now becomes application 401 while database permission failures retain 403.
4. Working-directory-relative environment paths could read different files depending on startup location. Separate explicit configuration fields now retain both backend/frontend values for conflict checking; overlapping AliasChoices could consume frontend aliases and hide conflicts.
5. Empty persistence responses were incorrectly accepted as successful writes. Confirmed insert/update rows are now required. Legacy scenario validation also accepted nonexistent demand endpoints and normalized parameters differently from execution; both are corrected.

## Files changed for this repair

- Local configuration: ignored `.env` (backend key synchronized; never committed).
- Backend: `app/config.py`, `app/api/auth.py` (new), `app/api/failure_simulation.py`, `app/api/scenario.py`, `app/main.py`, `app/services/supabase_repository.py`, `app/services/scenario_engine.py`.
- Frontend: `src/lib/api-config.ts`, `api-request.ts`, `api.ts` (new shared client), `constants.ts`, `failure-simulation.ts`, `network-simulation.ts`, `scenario.ts`; `src/integrations/supabase/custom-client.ts`, `public-client-options.ts` (new header/key helper).
- Runtime/tooling: `vite.config.ts`, `package.json` (test/type-check scripts), `backend/Dockerfile`, `docker-compose.yml` (port consistency).
- Tests: `backend/tests/test_auth_configuration.py` and `tests/frontend-api.test.mjs` (new).
- Evidence/docs: `README.md`, `docs/network-failure-simulation.md`, `docs/api-verification.json`, this report and `project-status.md`.

All pre-existing working-tree changes from the analytical implementation were retained. No database migrations were run or modified for this repair, and no data or RLS policies were changed.

## Results

- Backend virtual environment: 48 tests passed, including configuration precedence/conflicts, bearer parsing, upstream headers, valid/invalid/expired auth mocks, safe upstream failure mapping, write confirmation, scenario execution and existing deterministic simulation cases.
- `npm run test:api`: 8 passed, covering API prefixes, actual proxy target, current-token refresh/retry, public analysis, publishable versus legacy anon headers and failure propagation.
- `npm run typecheck`, production `npm run build`, focused ESLint for changed shared API/client modules, schema drift check, Python compilation and diff whitespace validation passed. Windows sandbox restrictions required unrestricted execution of the production build and temporary-file backend tests.
- Existing native servers were reused; live public and invalid-token requests tested directly and through Vite. Full evidence contains 24 matching HTTP checks. OpenAPI Bearer scheme and authorization CORS headers were checked on both origins.

| Method | Path | Expected | Direct 8013 | Proxy 8080 | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | /api/health | 200 | 200 | 200 | Healthy API/proxy |
| GET | /api/failure-simulation/scenarios | 200 | 200 | 200 | Public catalogue |
| GET | /api/configuration/supabase | 200 | 200 | 200 | Only safe configuration categories/flags |
| POST | /api/analysis/evaluate | 200 | 200 | 200 | Valid sample; simulated provenance |
| POST | /api/analysis/experiment | 200 | 200 | 200 | Full analytical pipeline; not persisted |
| POST | /api/scenario/run | 200 | 200 | 200 | Legacy adapter |
| GET | /api/failure-simulation/topology | 401 | 401 | 401 | Missing token |
| GET | /api/failure-simulation/topology | 401 | 401 | 401 | Invalid dummy token validated against real Supabase |
| GET | /api/analysis/evaluate | 405 | 405 | 405 | Wrong method intentionally rejected |
| POST | /api/analysis/evaluate | 422 | 422 | 422 | Missing request data intentionally rejected |
| GET | /api/api/health | 404 | 404 | 404 | Duplicate prefix intentionally rejected |
| OPTIONS | /api/failure-simulation/topology | 200/204 | 200 | 204 | Backend and Vite valid CORS preflight |

A valid-user topology request and persistence are verified with mocked Supabase transport/repository tests only; there is no production token in the fixtures. The agent cannot access the user's authenticated browser session. Live positive authentication and database writes therefore remain unverified. The remaining interaction is to retry the saved-topology workflow in the signed-in UI; there is no need to share tokens or edit files.

Supabase's documented header contract is public project key in `apikey`, session JWT in `Authorization`: https://supabase.com/docs/guides/getting-started/api-keys . Both publishable and legacy anon keys remain supported here. Generated explanations, network VM deployment and database migrations are unrelated to this repair and were not used to bypass authentication.
