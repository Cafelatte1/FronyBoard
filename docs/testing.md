# Testing

**When to read**: when adding or changing backend/frontend tests, or touching a test helper
**Code**: `backend/test/`, `frontend/test/`
**Related**: [architecture](architecture.md), [frontend](frontend.md)

---

## Backend (pytest)

`uv run --directory backend pytest` — `[tool.pytest.ini_options] testpaths = ["test"]`
in `backend/pyproject.toml`. Layout follows `docs/templates/template_LAYOUT.md`:
`test/unit/` needs no HTTP layer and no fake FronyAuth; `test/integration/` drives the
Starlette app through `asgi_request` with the fake FronyAuth from `conftest.py`.
Currently 10 files, 79 tests.

| file | covers |
|---|---|
| `unit/test_store.py` | file IO |
| `unit/test_validation.py` | schema and rule gate |
| `unit/test_service.py` | operations (the largest) |
| `unit/test_concurrency.py` | per-project lock |
| `unit/test_server.py` | MCP tool wrappers called directly |
| `unit/test_reads.py` | `get_task`, `search_tasks`, `recent_activity`, `list_tasks` filters |
| `unit/test_log.py` | `tools.jsonl` / `server.jsonl` |
| `integration/test_auth.py` | bearer middleware, FronyAuth introspection, sessions |
| `integration/test_web.py` | `/api/*` JSON routes |
| `integration/test_overview.py` | yearly overview + `set_check` + the dashboard PATCH route |

### ASGI request helper

The logic for pushing a single HTTP request through an ASGI app is unified into one helper in `backend/test/conftest.py`:
`asgi_request(app, method, path, query="", headers=None, json_body=None, form=None, scheme="https") -> (status, headers, body)`
— every file in `test/integration/` pulls it in
(`from conftest import asgi_request`). When adding a new ASGI route test, reuse this
function; do not rebuild one per app.

In the same file, `bootstrap(key="DLY")` is a shared fixture helper that creates and
returns one project + an open `2026Q3` period + an active `M1` month.

The `data_root` autouse fixture points `AIRA_DATA_DIR` / `FRONY_AUTH_FILE` / `FRONY_OAUTH_FILE`
under `tmp_path` and resets login lockout state for every test — a new test file does
not need to set up the data root itself.

## Frontend (vitest)

`cd frontend; npm run test` (= `vitest run`) — `frontend/test/`, 8 files,
47 tests. No server is started; `fetch` is mocked with `vi.stubGlobal`.

| file | covers |
|---|---|
| `search.test.ts` | `search.ts` search logic |
| `SearchBar.test.tsx` | `SearchBar.tsx` |
| `api.test.ts` | API client |
| `Dashboard.test.tsx`, `Projects.test.tsx`, `Settings.test.tsx`, `TaskPanel.test.tsx` | screen components |
| `markdown.test.ts` | markdown rendering |
| `fixtures.ts` | shared test data (not a test file) |

Configuration lives in the `test` block of `frontend/vite.config.ts`: `environment: "jsdom"`,
`setupFiles: "./test/setup.ts"`, `include: ["test/**/*.test.{ts,tsx}"]`.
`test/setup.ts` fills in `window.matchMedia`, which jsdom lacks, with a desktop
(`matches: false`) stub so that `useIsPhone` works.

The `include` in `frontend/tsconfig.json` is only `["src"]`, so `npm run build`
(`tsc -b && vite build`) does not type-check `test/` — type errors in test code
surface only when `npm test` runs (vitest's esbuild transform), not at build
time.
