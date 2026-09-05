# MCP tool surface

**When to read**: when adding, renaming or regrouping an `@mcp.tool()` or editing the server `instructions=` block
**Code**: `backend/src/aira/server.py`
**Related**: [data-model](data-model.md), [http-api](http-api.md), [frontend](frontend.md)

---

Why the 20 `@mcp.tool()` functions in `backend/src/aira/server.py` are named and structured the way
they are. Each tool's docstring is the description an MCP client shows an agent, and is the source of
truth for what that tool does and how to call it — read `server.py` directly. This page only covers
what a docstring cannot say by itself: the shape of the surface and the constraints it was built
under. The README's ["Tools"](../README.md#tools) table is the same 20 tools grouped by area.

## Shape

Grouped by lifecycle stage — the order a project actually moves through:

- `create_project`, `update_project`, `list_projects` — the project record
- `get_roadmap`, `set_overview`, `set_check`, `upsert_milestone` — yearly overview
  (goal / now / target / checklist; `set_check` ticks one item) + quarterly milestones
- `open_period`, `close_period`, `get_retrospective` — period lifecycle
- `upsert_month`, `create_task`, `update_task`, `transition_task` — in-period planning
- `list_tasks`, `get_status`, `validate` — reads
- `get_task`, `search_tasks`, `recent_activity` — agent-facing reads (v0.22.0 / AIR-064):
  one record by id, the dashboard's text search over every project, and the mutation
  history read back from `tools.jsonl`

Several pairs are easy to confuse, so their docstrings cross-reference each other instead of relying
on the name alone: `upsert_milestone` (a quarter, roadmap level) vs. `upsert_month` (M1/M2/M3 inside
an open period); `get_status` vs. `get_roadmap` vs. `list_tasks` (progress/counts vs. the plan as
written vs. task detail); `list_tasks` vs. `get_task` vs. `search_tasks` (one project's tasks vs. one
id vs. text across projects); `transition_task` vs. `update_task` (status vs. everything else);
`create_project` points forward to `open_period` for the rest of the setup flow.

## Naming convention

Tools otherwise follow `verb_object` (`create_project`, `upsert_milestone`,
`transition_task`, `list_tasks`). Two names break it, on purpose:

- `set_overview` behaves like an upsert (create-or-replace on a year) — the same semantics
  as `upsert_milestone`/`upsert_month` — but is named `set_`.
- `validate` has no object at all (compare `get_status`, `list_tasks`).

Renaming either to fit the convention was considered (v0.16.0 / AIR-052) and rejected: a hosted MCP
client that has already connected has this tool list cached by name, and a rename would silently
break it for anyone already using the server. This is a deliberate tradeoff, not an oversight — do
not "clean up" these two names without re-checking whether that constraint still applies.

## `instructions=` vs. tool docstrings

`MCPServer(..., instructions=...)` in `server.py` carries workflow-level guidance — which project a
codebase belongs to, when to transition a task, the soft-delete rule — that does not belong to any
single tool. Clients truncate this block once it grows — observed in Claude Code against both the
directly registered HTTP server and the claude.ai connector — so anything an agent must reliably see
cannot live there alone.

As of v0.16.0, parameter formats (`period` = YYYYQn, `month` = a month id like M1/M2/M3 and never
YYYY-MM, `week` = 1-5, the status enums) and the cross-tool pointers listed above live in the
individual tool docstrings for this reason, and the lifecycle order and soft-delete rule are stated
in both places on purpose. (The task-content template was always in `create_task`; `instructions=`
only points at it.) When adding guidance that must reach every client, put it in the relevant tool's
docstring, not in `instructions=` alone.
