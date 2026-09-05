# Docs index

Every doc opens with **When to read / Code / Related**; the middle column below is that first line. Conventions and skeletons for other Frony repos are in [templates/README](templates/template_README.md).

## Core

| Doc | When to read |
|---|---|
| [architecture](architecture.md) | when adding a component, changing how an MCP call or dashboard request reaches disk, or asking why the server is shaped this way |
| [data-model](data-model.md) | when changing the roadmap.yaml / period-file schema or the validation rules |
| [tool-surface](tool-surface.md) | when adding, renaming or regrouping an `@mcp.tool()` or editing the server `instructions=` block |
| [http-api](http-api.md) | when adding or changing an `/api/*` route the dashboard calls |
| [auth](auth.md) | when changing how a request is authenticated (API key, dashboard session, OAuth) or which access channel serves it |
| [operations](operations.md) | when deploying, restarting, backing up or diagnosing the home-server instance |
| [logging](logging.md) | when adding a log field or event, or reading tools.jsonl / server.jsonl |
| [frontend](frontend.md) | when changing a dashboard page, the data loading, or a UI-only feature such as the header search |
| [testing](testing.md) | when adding or changing backend (pytest) or frontend (vitest) tests |

## Templates (shared with other Frony repos)

| Doc | When to read |
|---|---|
| [templates/README](templates/template_README.md) | when setting up or auditing the `docs/` folder of a Frony service repo |
| [templates/CLAUDE](templates/template_CLAUDE.md), [templates/AGENTS](templates/template_AGENTS.md) | when writing a repo's `CLAUDE.md` / `AGENTS.md` (same content, two names) |
| [templates/logging-spec](templates/template_logging-spec.md) | when a Frony service adopts the shared JSON Lines logging or changes its sink configuration |
| `templates/*.md` (skeletons) | when starting one of the docs above in another repo |
