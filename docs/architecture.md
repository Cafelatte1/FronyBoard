# Architecture

**When to read**: when adding a component, changing how an MCP call or dashboard request reaches disk, or asking why the server is shaped this way
**Code**: `backend/src/aira/server.py`, `backend/src/aira/web.py`, `backend/src/aira/service.py`
**Related**: [data-model](data-model.md), [tool-surface](tool-surface.md), [http-api](http-api.md), [auth](auth.md), [operations](operations.md), [frontend](frontend.md)

---

## What it is

FronyBoard is a project tracker whose first-class user is an AI agent. Agents plan and record work through MCP tools; humans watch through a read-mostly dashboard served by the same process. Where Jira assumes a person in the loop, FronyBoard assumes the agent is: every write passes a validation gate, ids and timestamps are issued by the server, and nothing is hard-deleted.

Plan data is not in this repo. It lives in the server's data root (`%LOCALAPPDATA%\Frony\FronyBoard\data`, moved with `AIRA_DATA_DIR`), one folder per project.

## Components

| Component | Path | Owns |
|---|---|---|
| MCP tool surface + CLI | `backend/src/aira/server.py` | The 20 `@mcp.tool()` wrappers, the server `instructions=` block, the `aira` (stdio) and `aira serve` (HTTP) entry points, per-call logging |
| HTTP layer | `backend/src/aira/web.py` | Starlette app: streamable-HTTP MCP transport, `/api/*` JSON for the dashboard, static serving of `frontend/dist` |
| Auth | `backend/src/aira/auth.py`, `backend/src/aira/fauth.py` | Bearer middleware; every token is verified by FronyAuth introspection (`FRONY_AUTH_URL`, `FRONY_SERVICE_KEY`) |
| Service | `backend/src/aira/service.py` | One function per operation; a per-project lock; stamps `meta.created/updated`; runs the validation gate before every write |
| Validation | `backend/src/aira/validation.py` | Schema and rule checks. An error rejects the write; a warning is returned alongside the result |
| Store | `backend/src/aira/store.py` | Data-root resolution, YAML load/save, `meta` helpers |
| Logging | `backend/src/aira/log.py` | loguru sinks: `server.jsonl` (process events) and `tools.jsonl` (one line per tool call) |
| Dashboard | `frontend/` | React + Vite SPA. `frontend/dist` is committed and served by the backend, so deploy is one process |

## Request flow

1. A client connects. Claude Code speaks MCP over HTTP with an API key; a browser loads the SPA and calls `/api/*` with a dashboard session.
2. The bearer middleware extracts the token and asks FronyAuth whether it is valid. The caller identity (`key:<name>`, `session:<user>`, …) is attached to the request.
3. A tool wrapper in `server.py`, or a route in `web.py`, calls the matching `service.*` function.
4. `service` takes the project lock, loads state from disk, applies the change and runs `validation.validate_state`. Errors raise `AiraError` and nothing is written.
5. `store` saves YAML. The wrapper logs one line to `tools.jsonl` and returns the result plus any warnings.

Stdio mode (`aira` with no subcommand) runs the same tool surface for a local MCP client: no HTTP, no auth, same data root.

## Deployment shape

One always-on Windows home server runs `aira serve` on `:8642` under Task Scheduler, next to FronyAuth (`:8640`, the project-auth repo). Every device sits on a Tailscale tailnet; nothing is exposed publicly. Code reaches the server only as release tags (`vX.Y.Z`) pulled from GitHub. Details in [operations](operations.md).

## Decisions

- **Files, not a database.** One YAML tree per project keeps the data diffable and the server a single process with no schema migrations to run. Concurrency is a per-project lock, not transactions.
- **Server-issued ids and timestamps.** Agents must not invent either; it keeps the record trustworthy.
- **Soft delete only.** Tasks are cancelled, projects archived. History is input to the retrospective.
- **Auth delegated to FronyAuth** (v0.18.0). One place issues keys and dashboard logins for every Frony service; aira holds no credential store.
- **Committed `frontend/dist`.** The home server needs no Node toolchain; deploy is `git checkout <tag>` + `uv sync`.
- **`tools.jsonl` doubles as the activity feed.** `recent_activity` reads the log rather than a second store (AIR-064).
