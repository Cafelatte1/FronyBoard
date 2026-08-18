# AIRA — AI + JIRA

An MCP server that gives AI agents (Claude Code and friends) a first-class project tracker.

Where Jira is an issue tracker for humans behind a web UI, AIRA replaces each part with
something an agent can use natively:

| Jira | AIRA |
|---|---|
| Database | Plain files in a dedicated data directory |
| Records | YAML / Markdown |
| API | MCP tools |
| Workflow engine | Schema + rule validation, run as a gate before every write |
| State transition | An MCP tool call (`transition_task`) |

The schema and operating rules were extracted from a real product's management system
(31 tasks shipped through it), then generalized.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/Cafelatte1/project-aira
cd project-aira/backend
uv sync
```

The repo is a monorepo: `backend/` holds the MCP server (a uv project), `frontend/`
the FronyBoard web dashboard. Commands below run from `backend/`.

Data lives under `~/.aira/` by default; set `AIRA_DATA_DIR` to relocate it.

## Run

### Remote (home server)

AIRA is designed to run on one always-on machine, with every client PC talking
to it over MCP streamable HTTP. Issue one API key per client machine, then start
the server:

```powershell
uv run aira keygen pc1        # prints the key once — store it on that PC
uv run aira serve             # binds 0.0.0.0:8642, requires a valid key on every request
```

Register on each client (any project, or `--scope user` for everywhere):

```powershell
claude mcp add --transport http aira http://<server>:8642/mcp --header "Authorization: Bearer <api key>"
```

Keys are stored hash-only in `<data root>/auth.yaml`; revoke one by deleting its
entry. For access across networks (e.g. a laptop at a cafe), put the server and
clients on a [Tailscale](https://tailscale.com/) tailnet and use the server's
Tailscale name as `<server>` — only your enrolled devices can reach it, from
anywhere.

### Local (stdio)

```powershell
claude mcp add aira -- uv run --directory <path-to-project-aira>\backend aira
```

## Project setup

Connecting the MCP server gives every session the tools and the general workflow
(delivered as server instructions). What it cannot know is **which AIRA project a
codebase belongs to** — declare that in the codebase itself by adding this section
to its `CLAUDE.md` (create the file if the project has none):

```markdown
## AIRA

This project is tracked by AIRA (project key: DLY).
Manage tasks through the aira MCP tools, following the aira server instructions.
```

Replace `DLY` with the project's key (register one first with `create_project`).
The section is also the opt-in signal: a codebase without it is treated as not
AIRA-managed.

## Deploy — Windows home server

The server machine only deploys; development happens on client PCs and flows
through git (`push` on a dev PC → `pull` + restart here).

1. Install [Tailscale](https://tailscale.com/download), log in with the same
   account as your client PCs, and enable **Settings → Run unattended** so the
   tailnet stays up with nobody logged in. In the
   [admin console](https://login.tailscale.com/admin/machines), disable key
   expiry for this machine.
2. Install the server:

   ```powershell
   git clone https://github.com/Cafelatte1/project-aira
   cd project-aira/backend
   uv sync
   uv run aira keygen <client-pc-name>   # once per client PC, save each key
   ```

3. Keep it running across reboots with Task Scheduler (`taskschd.msc` → Create
   Task): trigger **At startup**, action = path from `(Get-Command uv).Source`
   with arguments `run --directory <path-to-project-aira>\backend aira serve`, and check
   **Run whether user is logged on or not**.
4. To update: `git pull`, `uv sync` (in `backend/`), then restart the task (or reboot).

Clients then connect with the server's Tailscale name (see "Remote" above).

## Model

```
projects/
└── {KEY}/                  one folder per project, named by its key (e.g. DLY)
    ├── roadmap.yaml        yearly overview (goal / now / next / later) + quarterly milestones
    └── {YYYY}{Q#}/         one folder per opened period (e.g. 2026Q3)
        ├── objective.yaml  monthly milestones (M1, M2, ...)
        ├── tasks.yaml      epics (E1, E2, ...) + tasks ({KEY}-001, ...)
        └── result.md       retrospective, written once when the period is closed
```

- **Task ids are a project-global sequence** (`DLY-042`) — they keep counting across
  periods and are never reused. They are the only link between AIRA and a codebase:
  use them in branch names (`feat/DLY-042/short-desc`) and record the branch on the task.
- **Reference chain**: `task.epic → epics[].id`, `task.month → months[].id`,
  `period folder → roadmap milestone`. Rollups follow this chain.
- **Statuses** — milestones and months: `planned | active | done`;
  tasks: `todo | in_progress | done | blocked | cancelled`.
- **`cancelled` is the soft delete** — there is no hard delete. Cancelling requires a
  reason, keeps the record (and its id) forever, and hides the task from queries by
  default (`list_tasks` takes `include_cancelled`). `blocked` = may resume,
  `cancelled` = will not happen; transitioning a cancelled task restores it.
- **Carry-over**: a task that outlives its period is not moved — recreate it in the next
  period under a new id and note the mapping in `result.md`.
- **Timestamps** (`meta.created_at` / `updated_at` / `started_at` / `completed_at`) are
  stamped by the server in naive UTC — `started_at` on the first `in_progress` transition,
  `completed_at` on `done` (and removed again if the task leaves `done`). Agents never
  write them.
- **`result.md` closes a period** — YAML holds only current state, so the "why it turned
  out this way" lives there: judgment and reasons, not counts.

## Tools

| Area | Tools |
|---|---|
| Projects | `create_project`, `list_projects`, `get_roadmap`, `get_status`, `validate` |
| Roadmap | `set_overview`, `upsert_milestone` |
| Periods | `open_period`, `close_period` |
| Planning | `upsert_month`, `create_epic`, `update_epic`, `create_task`, `update_task`, `transition_task` |
| Queries | `list_tasks` |

Typical flow:

```
create_project → set_overview → upsert_milestone → open_period
→ upsert_month / create_epic / create_task
→ transition_task in_progress (with branch) → ... → transition_task done
→ close_period (retrospective)
```

Every mutation is validated before anything is written; invalid changes are rejected
with the full error list. `close_period` refuses while tasks are still `todo` or
`in_progress`. Writes are serialized per project, so concurrent clients cannot
collide on ids or lose updates.

## Development

```powershell
uv run --directory backend pytest
```

Layout: `backend/src/aira/` — `store.py` (file IO, data root), `validation.py`
(schema gate), `service.py` (operations), `server.py` (MCP tool surface);
`frontend/` — the FronyBoard dashboard, built to static files served by the backend.
