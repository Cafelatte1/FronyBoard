"""AIRA MCP server — the tool surface.

Commands:
    aira                                 stdio transport (local development)
    aira serve [--host H] [--port P]     streamable HTTP transport (home server)
    aira keygen <name>                   issue an API key for a client machine

Register a remote server in Claude Code:

    claude mcp add --transport http aira http://<server>:8642/mcp \
        --header "Authorization: Bearer <api key>"
"""

from __future__ import annotations

import argparse

from mcp.server.mcpserver import MCPServer

from . import auth, service

mcp = MCPServer(
    "aira",
    instructions=(
        "AIRA is a project tracker for AI agents (AI + JIRA). Data lives in AIRA's own "
        "store, not in the codebase you are working on.\n\n"
        "Which project: the codebase declares its AIRA project key in a `## AIRA` section "
        "of its CLAUDE.md (e.g. 'This project is tracked by AIRA, key: DLY'). No such "
        "declaration means the project is not AIRA-managed — do not ask for a key; at most, "
        "suggest registering it once.\n\n"
        "Task workflow: when starting branch-sized work, transition its task to in_progress "
        "and record the branch name (branch names look like feat/DLY-042/short-desc — the "
        "task id is the only link between AIRA and the codebase). When the work is merged, "
        "transition it to done; if you cannot observe the merge, ask the user before marking "
        "done. If branch-sized work has no task yet, offer create_task first; trivial fixes "
        "need no task.\n\n"
        "Planning flow: create_project -> set_overview (year) -> upsert_milestone (quarter) "
        "-> open_period -> upsert_month, create_epic, create_task -> transition_task as work "
        "progresses -> close_period with a retrospective. Record agreed plans and "
        "retrospectives through these tools — planning data never lives in the codebase. "
        "Every mutation is validated before it is written; ids and timestamps are issued by "
        "the server — never invent them."
    ),
)


@mcp.tool()
def create_project(key: str, name: str | None = None) -> dict:
    """Create a new project. `key` is the task-id prefix (2-5 uppercase letters, e.g. DLY)."""
    return service.create_project(key, name)


@mcp.tool()
def list_projects() -> dict:
    """List all projects in the AIRA data store."""
    return service.list_projects()


@mcp.tool()
def get_roadmap(key: str) -> dict:
    """Get a project's roadmap (yearly overviews + quarterly milestones) and its open periods."""
    return service.get_roadmap(key)


@mcp.tool()
def set_overview(key: str, year: str, goal: str, now: str, next: str, later: str) -> dict:
    """Create or replace a year's overview: single-line goal plus now/next/later direction."""
    return service.set_overview(key, year, goal, now, next, later)


@mcp.tool()
def upsert_milestone(key: str, year: str, quarter: str,
                     goal: str | None = None, status: str | None = None) -> dict:
    """Create or update a quarterly milestone (quarter: Q1-Q4; status: planned/active/done)."""
    return service.upsert_milestone(key, year, quarter, goal, status)


@mcp.tool()
def open_period(key: str, period: str) -> dict:
    """Open a period folder (e.g. 2026Q3) derived from its roadmap milestone. Marks a planned milestone active."""
    return service.open_period(key, period)


@mcp.tool()
def close_period(key: str, period: str, result_markdown: str) -> dict:
    """Close a period: requires all tasks done or blocked, writes result.md (retrospective), marks the milestone done.

    result.md should stay under ~30 lines and hold judgment and reasons only —
    summary vs goal, per-month outcome, carried-over tasks (old id -> new id), lessons.
    """
    return service.close_period(key, period, result_markdown)


@mcp.tool()
def upsert_month(key: str, period: str, month_id: str, month: str | None = None,
                 goal: str | None = None, status: str | None = None) -> dict:
    """Create or update a monthly milestone in a period (month_id: M1/M2/M3, month: YYYY-MM)."""
    return service.upsert_month(key, period, month_id, month, goal, status)


@mcp.tool()
def create_epic(key: str, period: str, goal: str) -> dict:
    """Create an epic (a bundle of related tasks) in a period. The id (E1, E2, ...) is assigned automatically."""
    return service.create_epic(key, period, goal)


@mcp.tool()
def create_task(key: str, period: str, title: str, epic: str, month: str,
                week: int | None = None, content: str | None = None,
                prd: str | None = None) -> dict:
    """Create a task (issue/branch-sized unit of work) with status todo.

    The id is assigned from the project-global sequence (never reused). `epic` references
    an epic id (E#), `month` a month id (M#), `week` is the week-of-month (1-5), `content`
    is implementation detail in markdown — enough for a model to pick the task up cold.
    """
    return service.create_task(key, period, title, epic, month, week, content, prd)


@mcp.tool()
def update_task(key: str, task_id: str, title: str | None = None, epic: str | None = None,
                month: str | None = None, week: int | None = None, content: str | None = None,
                prd: str | None = None, branch: str | None = None) -> dict:
    """Update task fields (not status — use transition_task). `branch` records the working branch name."""
    return service.update_task(key, task_id, title, epic, month, week, content, prd, branch)


@mcp.tool()
def transition_task(key: str, task_id: str, status: str, branch: str | None = None) -> dict:
    """Transition a task's status (todo/in_progress/done/blocked). Stamps completed_at when done.

    Call when work starts (in_progress, ideally with the branch name) and when it finishes (done).
    """
    return service.transition_task(key, task_id, status, branch)


@mcp.tool()
def list_tasks(key: str, period: str | None = None, status: str | None = None,
               epic: str | None = None, month: str | None = None) -> dict:
    """List tasks, optionally filtered by period, status, epic, or month."""
    return service.list_tasks(key, period, status, epic, month)


@mcp.tool()
def get_status(key: str) -> dict:
    """Project status rollup: per period, the milestone, months, task counts, and in-progress tasks."""
    return service.get_status(key)


@mcp.tool()
def validate(key: str) -> dict:
    """Validate a project's data against the AIRA schema and rules. Mutations run this gate automatically."""
    return service.validate(key)


def serve(host: str, port: int) -> None:
    """Run the streamable HTTP server behind bearer-key auth."""
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    if not auth.has_keys():
        raise SystemExit("no API keys yet — run `aira keygen <name>` first")
    # Host-header (DNS rebinding) checks are disabled: clients reach the server
    # under varying names (Tailscale name, LAN IP), and every request already
    # requires a bearer key that a rebound browser page cannot attach.
    app = auth.BearerAuthMiddleware(mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)))
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="aira", description="AIRA MCP server")
    sub = parser.add_subparsers(dest="command")
    serve_p = sub.add_parser("serve", help="run the HTTP server (home server mode)")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8642)
    keygen_p = sub.add_parser("keygen", help="issue an API key for a client machine")
    keygen_p.add_argument("name", help="key label, e.g. the machine name")
    args = parser.parse_args()

    if args.command == "serve":
        serve(args.host, args.port)
    elif args.command == "keygen":
        try:
            token = auth.generate_key(args.name)
        except ValueError as e:
            raise SystemExit(str(e))
        print(f"API key for '{args.name}' (shown once — store it now):\n\n  {token}\n")
        print("Register in Claude Code:\n"
              f'  claude mcp add --transport http aira http://<server>:8642/mcp '
              f'--header "Authorization: Bearer {token}"')
    else:
        mcp.run()


if __name__ == "__main__":
    main()
