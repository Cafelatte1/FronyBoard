# FronyBoard

An MCP server that gives AI agents (Claude Code and friends) a first-class project
tracker.

Where Jira is an issue tracker for humans behind a web UI, FronyBoard replaces each
part with something an agent can use natively:

| Jira | FronyBoard |
|---|---|
| Database | One SQLite file in a dedicated data directory |
| Records | JSON documents (roadmap, period) + Markdown |
| API | MCP tools |
| Workflow engine | Schema + rule validation, run as a gate before every write |
| State transition | An MCP tool call (`transition_task`) |

The schema and operating rules were extracted from a real product's management system
(31 tasks shipped through it), then generalized.

## Install

Requires [uv](https://docs.astral.sh/uv/). One line registers FronyBoard in Claude Code;
`uvx` fetches the package from PyPI on first use and caches it:

```powershell
claude mcp add FronyBoard -- uvx fronyboard
```

Any MCP client that can launch a stdio command works the same way — the command is
`uvx fronyboard`. It is also listed in the
[MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.Cafelatte1/fronyboard`.
From a clone, point at the checkout instead (this needs `git`):

```powershell
git clone https://github.com/Cafelatte1/fronyboard
claude mcp add FronyBoard -- uv run --directory <path-to-clone>\backend fronyboard
```

This is the local (stdio) mode: the client starts the server as a child process and
talks to it over a pipe. No HTTP, no network, no credentials — `web.py` and
`fauth.py` are never called. Data is written to `%LOCALAPPDATA%\Frony\FronyBoard\data`
(`~/.Frony/FronyBoard/data` where `LOCALAPPDATA` is unset); set `AIRA_DATA_DIR` to
relocate it. Logs (JSON Lines, one line per MCP tool call plus server events) go to
the sibling `logs` folder — `FRONYBOARD_LOG_DIR` overrides; see
[docs/logging.md](docs/logging.md).

To share one FronyBoard between several machines, or to use it from the Claude and
ChatGPT apps, run it as an HTTP server instead — see
[docs/self-hosting.md](docs/self-hosting.md).

## Project setup

Connecting the MCP server gives every session the tools and the general workflow
(delivered as server instructions). What it cannot know is **which FronyBoard project
a codebase belongs to** — declare that in the codebase itself by adding this section
to its `CLAUDE.md` (create the file if the project has none):

```markdown
## FronyBoard

This project is tracked by FronyBoard (project key: DLY).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
```

Replace `DLY` with the project's key (register one first with `create_project`).
The section is also the opt-in signal: a codebase without it is treated as not
FronyBoard-managed.

## Model

```
fronyboard.db
├── projects   one row per project (key e.g. DLY): the roadmap record —
│              yearly overview (goal / now / target / checklist) + quarterly milestones
└── periods    one row per opened period (e.g. 2026Q3): monthly milestones (M1, M2, ...)
               + tasks ({KEY}-001, ...) + `result` (retrospective, written when the period closes)
```

A project is two kinds of records — the roadmap, and one record per period. Both are
JSON documents; the shapes are in [docs/data-model.md](docs/data-model.md).

- **Task ids are a project-global sequence** (`DLY-042`) — they keep counting across
  periods and are never reused. They are the only link between FronyBoard and a codebase:
  use them in branch names (`feat/DLY-042/short-desc`) and record the branch on the task.
- **Reference chain**: `task.month → months[].id`, `period file → roadmap milestone`.
  Rollups follow this chain — months are the grouping unit.
- **Statuses** — milestones and months: `planned | active | done`;
  tasks: `todo | in_progress | done | blocked | cancelled`.
- **`cancelled` is the soft delete** — there is no hard delete. Cancelling requires a
  reason, keeps the record (and its id) forever, and hides the task from queries by
  default (`list_tasks` takes `include_cancelled`). `blocked` = may resume,
  `cancelled` = will not happen; transitioning a cancelled task restores it.
- **Carry-over**: a task that outlives its period is not moved — recreate it in the next
  period under a new id and note the mapping in the closing retrospective.
- **`after`** on a task lists the tasks it continues from (other projects allowed). It is a
  pointer, not a lock: `get_task` shows the reverse as `followed_by`, `list_tasks` flags
  `waiting_on` while predecessors are open, and nothing is ever blocked.
- **Timestamps** (`meta.created_at` / `updated_at` / `started_at` / `completed_at`) are
  stamped by the server in naive UTC — `started_at` on the first `in_progress` transition,
  `completed_at` on `done` (and removed again if the task leaves `done`). Agents never
  write them.
- **The `result` field closes a period** — the rest of the file holds only current
  state, so the "why it turned out this way" lives there: judgment and reasons,
  not counts. Its presence is what marks a period closed.

## Tools

| Area | Tools |
|---|---|
| Projects | `create_project`, `update_project`, `list_projects`, `get_roadmap`, `get_status`, `validate` |
| Roadmap | `set_overview`, `set_check`, `upsert_milestone` |
| Periods | `open_period`, `close_period`, `get_retrospective` |
| Planning | `upsert_month`, `create_task`, `update_task`, `transition_task` |
| Queries | `list_tasks`, `get_task`, `search_tasks`, `recent_activity` |

`update_task` and `transition_task` derive the project from the task id prefix
(`DLY-042` → `DLY`), so their `key` parameter is optional. Re-calling
`close_period` on a closed period rewrites its retrospective.

The two `upsert_*` tools sit at different levels: `upsert_milestone` is a quarter
in the roadmap, `upsert_month` is one of the three months inside a period that is
already open. A task's `month` is a month id (`M1`/`M2`/`M3`), never `YYYY-MM`.

Typical flow:

```
create_project → set_overview → upsert_milestone → open_period
→ upsert_month / create_task
→ transition_task in_progress (with branch) → ... → transition_task done
→ close_period (retrospective)
```

Every mutation is validated before anything is written; invalid changes are rejected
with the full error list. `close_period` refuses while tasks are still `todo` or
`in_progress`. Writes are serialized per project, so concurrent clients cannot
collide on ids or lose updates.

## Self-hosting

The same package also runs as an always-on HTTP server (`fronyboard serve`): MCP over
streamable HTTP for every machine on your network, a read-only web dashboard for
humans, API keys per device, and OAuth for the hosted Claude / ChatGPT apps.
Authentication is delegated to [FronyAuth](https://github.com/Cafelatte1/project-auth),
a separate service. None of it is needed for the stdio install above.
[docs/self-hosting.md](docs/self-hosting.md) covers the setup;
[docs/operations.md](docs/operations.md) is the day-2 runbook.

## Development

```powershell
uv run --directory backend pytest      # backend
cd frontend; npm test                  # dashboard
```

The repo is a monorepo. `backend/src/fronyboard/` — `store.py` (SQLite, data root),
`validation.py` (schema gate), `service.py` (operations), `auth.py` (bearer
middleware) + `fauth.py` (FronyAuth client), `log.py`, `web.py` (JSON API + static
serving), `server.py` (MCP tool surface + CLI). `frontend/` — the dashboard (React +
Vite), built to static files that the backend serves; its build output
`frontend/dist` is committed so a server needs no Node toolchain.

More docs under [docs/](docs/INDEX.md):

- [docs/self-hosting.md](docs/self-hosting.md) — running FronyBoard as a shared server: clients, dashboard, hosted apps, deploy
- [docs/auth.md](docs/auth.md) — access channels (CLI agents, desktop, dashboard, hosted apps) and how each authenticates
- [docs/http-api.md](docs/http-api.md) — the FronyBoard JSON API
- [docs/data-model.md](docs/data-model.md) — field-level schema and validation rules
- [docs/operations.md](docs/operations.md) — home server runbook
