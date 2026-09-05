# Testing

**When to read**: when adding or changing backend/frontend tests, or touching a test helper
**Code**: `backend/tests/`, `frontend/tests/`
**Related**: [architecture](architecture.md), [frontend](frontend.md)

---

## Backend (pytest)

`uv run --directory backend pytest` — `[tool.pytest.ini_options] testpaths = ["tests"]`
in `backend/pyproject.toml` collects only `backend/tests/`.
Currently 10 files, 79 tests.

| file | covers |
|---|---|
| `test_store.py` | file IO |
| `test_validation.py` | schema and rule gate |
| `test_service.py` | operations (24 — the largest) |
| `test_concurrency.py` | per-project lock |
| `test_server.py` | MCP tool surface |
| `test_auth.py` | API keys, sessions, lockout |
| `test_oauth.py` | OAuth flow — asserts status codes, the `class='result <kind>'` marker and the handoff URL instead of page copy |
| `test_oauth_pages.py` | OAuth page (`oauth_pages.py`) rendering and copy — the only file that asserts these strings |
| `test_web.py` | `/api/*` JSON routes |
| `test_log.py` | `tools.jsonl` / `server.jsonl` |

The split between `test_oauth.py` and `test_oauth_pages.py` is deliberate: when page
copy changes only `test_oauth_pages.py` breaks, while the flow (status codes,
redirects, token issuance) is guarded separately by `test_oauth.py` (`backend/tests/test_oauth_pages.py:1-6`).

### ASGI request helper

The logic for pushing a single HTTP request through an ASGI app is unified into one helper in `backend/tests/conftest.py`:
`asgi_request(app, method, path, query="", headers=None, json_body=None, form=None, scheme="https") -> (status, headers, body)`
— `test_web.py`, `test_oauth.py` and `test_auth.py` all pull it in
(`from conftest import asgi_request`). When adding a new ASGI route test, reuse this
function; do not rebuild one per app.

In the same file, `bootstrap(key="DLY")` is a shared fixture helper that creates and
returns one project + an open `2026Q3` period + an active `M1` month.

The `data_root` autouse fixture points `AIRA_DATA_DIR` / `FRONY_AUTH_FILE` / `FRONY_OAUTH_FILE`
under `tmp_path` and resets login lockout state for every test — a new test file does
not need to set up the data root itself.

## Frontend (vitest)

`cd frontend; npm run test` (= `vitest run`) — `frontend/tests/`, 8 files,
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
`setupFiles: "./tests/setup.ts"`, `include: ["tests/**/*.test.{ts,tsx}"]`.
`tests/setup.ts` fills in `window.matchMedia`, which jsdom lacks, with a desktop
(`matches: false`) stub so that `useIsPhone` works.

The `include` in `frontend/tsconfig.json` is only `["src"]`, so `npm run build`
(`tsc -b && vite build`) does not type-check `tests/` — type errors in test code
surface only when `npm test` runs (vitest's esbuild transform), not at build
time.
