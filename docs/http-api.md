# HTTP API

**When to read**: when adding or changing an `/api/*` route the dashboard calls
**Code**: `backend/src/aira/web.py`, `backend/src/aira/auth.py`
**Related**: [auth](auth.md), [operations](operations.md), [data-model](data-model.md)

---

The JSON API behind the FronyBoard dashboard, served by `aira serve` alongside
the MCP endpoint (`/mcp`) and the static dashboard (`/`). It is read-only over
plan data — every plan mutation goes through the MCP tools. The one writable
surface is API key management, which is restricted to the dashboard login.

## Authentication

`/mcp` answers browser CORS (`Access-Control-Allow-Origin: *`, preflight without
a credential, `Mcp-Session-Id` and `WWW-Authenticate` exposed) so claude.ai's
web app can probe a connector from the browser; the OAuth endpoints carry the
SDK's own CORS. `/api` does not — it is the dashboard's, same origin.

Every `/api/*` route requires `Authorization: Bearer <token>`, where the token
is an **API key** (`frony_…`, issued per client machine), a **dashboard session
token** (`fbsession_…`, issued by `/api/login`) or — when the server runs with a
public URL — an **OAuth access token** (`fbat_…`, issued to a hosted MCP client
through `/authorize` + `/token`; see [operations.md](operations.md)). Exceptions:

- `POST /api/login` is open (it is how you get a session token).
- `/api/keys` routes accept **only a session token** — requests with an API key
  get `403`, so an agent holding a key cannot list, mint, or revoke keys.

Session tokens live in server memory: a server restart invalidates all of them.

Requests without a valid token get `401` with a JSON body (on `/mcp` the
response also carries a `WWW-Authenticate` header pointing at the OAuth
resource metadata, which is how the hosted clients discover the login).

## Errors

Errors are always `{"error": "<message>"}`. Status codes: `400` (bad input),
`401` (missing/invalid token), `403` (API key used where a session is
required), `404` (unknown project or key name).

All timestamps in responses are **naive UTC** strings (e.g.
`2026-08-18T09:15:00` or `2026-08-18 09:15:00`).

## Session

### POST /api/login

Body: `{"username": "...", "password": "..."}` — the credential set with
`aira admin <username>`. Returns `{"token": "fbsession_…", "username": "..."}`,
or `401` on a bad credential. Five failures from one address within 15 minutes
lock that address out with `429` until the window passes.

### POST /api/logout

Drops the bearer session token. Returns `{"ok": true}`.

## Plan data (read-only)

### GET /api/projects

Archived projects are left out unless `?include_archived=true`.

```json
{"projects": [{"key": "AIR", "name": "FronyBoard", "description": "…", "repo": "owner/aira",
               "status": "active", "meta": {"created_at": "2026-08-18T06:00:00", "updated_at": "…"}}],
 "data_root": "C:\\Users\\me\\AppData\\Local\\Frony\\FronyBoard\\data"}
```

### GET /api/projects/{key}/roadmap

The project's `roadmap.yaml` as JSON plus the list of period folder names:

```json
{"roadmap": {"key": "AIR", "name": "FronyBoard", "years": {"2026": {"overview": {...}, "milestones": {"Q3": {...}}}}},
 "periods": ["2026Q3"]}
```

### GET /api/projects/{key}/status

Rollup per period (closed periods included). For each period: the quarterly
milestone goal/status, months with their own task counts, total task counts,
whether the period is closed, and in-progress task ids:

```json
{"project": "AIR", "name": "FronyBoard", "periods": {
  "2026Q3": {
    "goal": "...", "milestone_status": "active",
    "months": [{"id": "M1", "month": "2026-08", "goal": "...", "status": "active",
                "task_counts": {"done": 5, "todo": 1}}],
    "task_counts": {"done": 9, "todo": 1, "cancelled": 1},
    "closed": false,
    "in_progress": ["AIR-011"]}}}
```

### GET /api/projects/{key}/tasks

Full task records (including `meta` timestamps), across all periods unless
filtered. Query parameters, all optional:

| param | meaning |
|---|---|
| `period` | only this period (e.g. `2026Q3`) |
| `status` | only this status |
| `month` | only this month id (e.g. `M1`) |
| `include_cancelled` | `1` or `true` to include cancelled tasks (hidden by default unless `status=cancelled`) |

```json
{"tasks": [{"period": "2026Q3", "id": "AIR-011", "title": "...",
            "month": "M1", "status": "done", "branch": "feat/AIR-011/...",
            "meta": {"created_at": "...", "updated_at": "...",
                     "started_at": "...", "completed_at": "..."}}],
 "count": 1}
```

## Server

### GET /api/server

Runtime facts for the Settings screen:

```json
{"version": "0.5.2", "started_at": "2026-08-18 12:59:46",
 "data_root": "C:\\Users\\me\\AppData\\Local\\Frony\\FronyBoard\\data", "projects": 1,
 "open_periods": [{"project": "AIR", "period": "2026Q3"}], "api_keys": 1,
 "timezone": {"name": "KST", "offset_minutes": 540}}
```

`open_periods` lists periods whose file has no `result` (retrospective) yet.
Uptime is `now - started_at` (the process start).

`timezone` is the zone the server is serving from — the dashboard shifts the
stored naive-UTC timestamps by `offset_minutes` for display. Set `AIRA_TZ` to an
IANA name (`Asia/Seoul`) to pin it; otherwise it is the process-local offset, and
`name` is null when the OS only offers a localized long name (Windows).

## API keys (dashboard session required)

### GET /api/keys

```json
{"keys": [{"name": "pc1", "fingerprint": "04bc…b5e7", "created_at": "2026-08-18 05:49:35"}]}
```

Only the name, a fingerprint of the stored SHA-256 digest, and the creation
time — the key itself is never retrievable after issuance.

### POST /api/keys

Body: `{"name": "<machine name>"}`. Returns `{"name": "...", "key": "frony_…"}` —
**the only time the key is shown**. `400` if the name is empty or taken.

### DELETE /api/keys/{name}

Revokes the key; the machine holding it loses access immediately. Returns
`{"ok": true}`, or `404` for an unknown name.
