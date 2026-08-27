"""FronyBoard MCP server — the tool surface.

Commands:
    aira                                 stdio transport (local development)
    aira serve [--host H] [--port P]     streamable HTTP transport (home server)
               [--public-url URL]        also serve OAuth for hosted MCP clients
               [--public-mcp-path P]     where /mcp sits under that URL (default /mcp)
    aira keygen <name>                   issue an API key for a client machine

Register a remote server in Claude Code:

    claude mcp add --transport http --scope user FronyBoard http://<server>:8642/mcp \
        --header "Authorization: Bearer <api key>"
"""

from __future__ import annotations

import argparse
import os

from mcp.server.mcpserver import MCPServer

from . import auth, log, oauth, service, store, web

mcp = MCPServer(
    "fronyboard",
    middleware=[log.ToolLogMiddleware()],
    instructions=(
        "FronyBoard is a project tracker for AI agents. Data lives in FronyBoard's "
        "own store, not in the codebase you are working on.\n\n"
        "Which project: the codebase declares its FronyBoard project key in a "
        "`## FronyBoard` section of its CLAUDE.md (e.g. 'This project is tracked by "
        "FronyBoard (project key: DLY)'). No such declaration means the project is not "
        "FronyBoard-managed — do not ask for a key; at most, suggest registering it once. "
        "When registering a codebase (create_project), also add that `## FronyBoard` "
        "declaration to its CLAUDE.md.\n\n"
        "Task workflow: when starting branch-sized work, transition its task to in_progress "
        "and record the branch name (branch names look like feat/DLY-042/short-desc — the "
        "task id is the only link between FronyBoard and the codebase; update_task and "
        "transition_task derive the project from the task id, so key is optional there). "
        "When the work is merged, "
        "transition it to done; if you cannot observe the merge, ask the user before marking "
        "done. If branch-sized work has no task yet, offer create_task first; trivial fixes "
        "need no task. There is no hard delete: to drop a task, transition it to cancelled "
        "with a reason (blocked = may resume, cancelled = will not happen). Projects are not "
        "deleted either: update_project(status='archived') hides one and freezes its data; "
        "paused only changes the badge.\n\n"
        "Planning flow: create_project -> set_overview (year) -> upsert_milestone (quarter) "
        "-> open_period -> upsert_month, create_task -> transition_task as work "
        "progresses -> close_period with a retrospective. A task that outlives its period is "
        "not moved: recreate it in the next period under a new id, leave the old one blocked, "
        "and map old id -> new id in the closing retrospective. Record agreed plans and "
        "retrospectives through these tools — planning data never lives in the codebase. "
        "Every mutation is validated before it is written; ids and timestamps are issued by "
        "the server — never invent them.\n\n"
        "Task content: `content` is markdown that a human reads in a narrow side panel and "
        "an agent reads to pick the task up cold, so follow the template in create_task "
        "(Why / What / How / Done when, under ~25 lines) and keep What observable and How "
        "implementation-level."
    ),
)


@mcp.tool()
def create_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None) -> dict:
    """Create a new project. `key` is the task-id prefix (2-5 uppercase letters, e.g. DLY).

    `description` is one line saying what the project is (shown on the dashboard cards);
    `repo` is where its code lives (owner/name or a URL). Status starts as active.
    """
    return service.create_project(key, name, description, repo)


@mcp.tool()
def update_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None, status: str | None = None) -> dict:
    """Update project fields — pass at least one. The key (and task id prefix) never changes.

    `status`: active | paused | archived. paused only changes the badge; archived hides the
    project from list_projects and refuses every other mutation until it is set back to
    active. There is no hard delete.
    """
    return service.update_project(key, name, description, repo, status)


@mcp.tool()
def list_projects(include_archived: bool = False) -> dict:
    """List projects (key, name, description, repo, status, meta). Archived ones are
    left out unless `include_archived` is set."""
    return service.list_projects(include_archived)


@mcp.tool()
def get_roadmap(key: str) -> dict:
    """Get a project's roadmap (yearly overviews + quarterly milestones) and its open periods."""
    return service.get_roadmap(key)


@mcp.tool()
def set_overview(key: str, year: str, goal: str, now: str, next: str, later: str) -> dict:
    """Create or replace a year's overview: single-line goal plus now/next/later direction.

    Each of now/next/later is one short line of direction (current focus / coming up /
    someday) — concrete goals belong in the quarterly milestones, not here.
    """
    return service.set_overview(key, year, goal, now, next, later)


@mcp.tool()
def upsert_milestone(key: str, year: str, quarter: str,
                     goal: str | None = None, status: str | None = None) -> dict:
    """Create or update a quarterly milestone (quarter: Q1-Q4; status: planned/active/done)."""
    return service.upsert_milestone(key, year, quarter, goal, status)


@mcp.tool()
def open_period(key: str, period: str) -> dict:
    """Open a period (e.g. 2026Q3) derived from its roadmap milestone. Marks a planned milestone active."""
    return service.open_period(key, period)


@mcp.tool()
def close_period(key: str, period: str, result_markdown: str) -> dict:
    """Close a period: requires all tasks done, blocked, or cancelled; stores the retrospective as the period's `result`, marks the milestone done.

    The retrospective should stay under ~30 lines and hold judgment and reasons only —
    summary vs goal, per-month outcome, carried-over tasks (old id -> new id), lessons.
    Calling it again on a closed period rewrites the retrospective.
    """
    return service.close_period(key, period, result_markdown)


@mcp.tool()
def get_retrospective(key: str, period: str) -> dict:
    """Read a closed period's retrospective (the `result` markdown)."""
    return service.get_retrospective(key, period)


@mcp.tool()
def upsert_month(key: str, period: str, month_id: str, month: str | None = None,
                 goal: str | None = None, status: str | None = None) -> dict:
    """Create or update a monthly milestone in a period (month_id: M1/M2/M3, month: YYYY-MM)."""
    return service.upsert_month(key, period, month_id, month, goal, status)


@mcp.tool()
def create_task(key: str, period: str, title: str, month: str,
                week: int | None = None, content: str | None = None,
                prd: str | None = None) -> dict:
    """Create a task (issue/branch-sized unit of work) with status todo.

    The id is assigned from the project-global sequence (never reused). Every task belongs
    to a month: `month` references a month id (M#) that must exist in the period first
    (get_status lists them). `week` is the week-of-month (1-5) and `prd` is an optional
    link to or excerpt of the requirement behind it.

    `content` is markdown, read by a human in a narrow panel and by an agent picking the
    task up cold. Use this template (keep it under ~25 lines):

        ## Why
        1-3 sentences: the need, with context/date. For a bug: symptom -> cause.
        ## What
        - what changes, as observable behaviour (one bullet per user-visible unit)
        - Out of scope: ... (only if needed)
        ## How
        - approach and files to touch (may be left empty until work starts)
        ## Done when
        - verifiable completion conditions ("do X, see Y" — not "checked")

    Record decisions inline as "(YYYY-MM-DD decided)"; put implementation detail under
    How, not What. The same Why/What/How later seeds the commit message.
    """
    return service.create_task(key, period, title, month, week, content, prd)


@mcp.tool()
def update_task(task_id: str, title: str | None = None,
                month: str | None = None, week: int | None = None, content: str | None = None,
                prd: str | None = None, branch: str | None = None,
                key: str | None = None) -> dict:
    """Update task fields (not status — use transition_task). `branch` records the working branch name.
    `content` replaces the whole markdown body — keep the create_task template (Why / What /
    How / Done when); fill in How once the approach is known.

    Omitted fields are left as they are. To remove an optional field pass an empty value:
    `week=0`, `content=""`, `prd=""`, `branch=""` (title and month cannot be removed).

    `task_id` is the full id including the project prefix, e.g. DLY-042 — the project
    is derived from that prefix, so `key` may be omitted (if given it must match).
    """
    return service.update_task(service.resolve_key(key, task_id), task_id,
                               title, month, week, content, prd, branch)


@mcp.tool()
def transition_task(task_id: str, status: str, branch: str | None = None,
                    reason: str | None = None, key: str | None = None) -> dict:
    """Transition a task's status (todo/in_progress/done/blocked/cancelled). `task_id` is the full id, e.g. DLY-042.

    The project is derived from the task id prefix, so `key` may be omitted (if given
    it must match). Call when work starts (in_progress, ideally with the branch name)
    and when it finishes (done). The server stamps started_at on first in_progress and
    completed_at on done. `cancelled` is the soft delete: the record is kept but hidden
    from queries by default, and `reason` is required. Use blocked for work that may
    resume, cancelled for work that will not happen. Transitioning a cancelled task to
    any other status restores it.
    """
    return service.transition_task(service.resolve_key(key, task_id), task_id,
                                   status, branch, reason)


@mcp.tool()
def list_tasks(key: str, period: str | None = None, status: str | None = None,
               month: str | None = None, include_cancelled: bool = False) -> dict:
    """List tasks, optionally filtered by period, status, or month.

    Cancelled tasks are excluded unless `include_cancelled` is set or `status` is 'cancelled'.
    """
    return service.list_tasks(key, period, status, month, include_cancelled)


@mcp.tool()
def get_status(key: str) -> dict:
    """Project status rollup, per period: the milestone, months (each with its own
    task counts), overall task counts by status, whether the period is closed, and
    the list of in-progress task ids."""
    return service.get_status(key)


@mcp.tool()
def validate(key: str) -> dict:
    """Validate a project's data against the FronyBoard schema and rules. Mutations run this gate automatically."""
    return service.validate(key)


def serve(host: str, port: int, public_url: str | None = None, public_mcp_path: str = "/mcp") -> None:
    """Run the streamable HTTP server behind bearer-key auth.

    With `public_url` (the HTTPS address hosted MCP clients reach us at, e.g. a
    Tailscale Funnel name) the OAuth endpoints are mounted too and /mcp accepts
    the access tokens they issue alongside API keys.
    """
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    if not auth.has_keys():
        raise SystemExit("no API keys yet — run `aira keygen <name>` first")
    provider = None
    if public_url:
        try:
            provider = oauth.Provider(public_url, public_mcp_path)
        except ValueError as e:
            raise SystemExit(f"--public-url: {e}")
    # Host-header (DNS rebinding) checks are disabled: clients reach the server
    # under varying names (Tailscale name, LAN IP), and every request already
    # requires a bearer key that a rebound browser page cannot attach.
    app = mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    if provider is not None:
        app.router.routes.extend(oauth.routes(provider))  # before the dashboard's catch-all
    web.attach(app)
    _boot("http", host=f"{host}:{port}", public_url=public_url,
          public_mcp=provider.urls.resource_server_url if provider else None)
    try:
        uvicorn.run(auth.BearerAuthMiddleware(app, protected=("/mcp", "/api"),
                                              open_paths=("/api/login",), oauth=provider),
                    host=host, port=port, log_config=None)
    finally:
        log.event("INFO", "boot", "shutdown", mode="http")


def _boot(mode: str, **fields) -> None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        ver = version("aira")
    except PackageNotFoundError:
        ver = "dev"
    log.event("INFO", "boot", "start", mode=mode, version=ver, data=str(store.data_root()),
              logs=str(log.log_dir()), tz=os.environ.get("AIRA_TZ"), **fields)


def main() -> None:
    parser = argparse.ArgumentParser(prog="aira", description="FronyBoard MCP server")
    sub = parser.add_subparsers(dest="command")
    serve_p = sub.add_parser("serve", help="run the HTTP server (home server mode)")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8642)
    serve_p.add_argument("--public-url", default=os.environ.get("AIRA_PUBLIC_URL") or None,
                         help="HTTPS URL hosted MCP clients use (enables OAuth); "
                              "default: AIRA_PUBLIC_URL")
    serve_p.add_argument("--public-mcp-path", default=os.environ.get("AIRA_PUBLIC_MCP_PATH") or "/mcp",
                         help="path of the MCP endpoint under --public-url, e.g. /board/mcp; "
                              "default: AIRA_PUBLIC_MCP_PATH or /mcp")
    keygen_p = sub.add_parser("keygen", help="issue an API key for a client machine")
    keygen_p.add_argument("name", help="key label, e.g. the machine name")
    admin_p = sub.add_parser("admin", help="set the FronyBoard dashboard login (id/password)")
    admin_p.add_argument("username")
    admin_p.add_argument("password", nargs="?", default=None,
                         help="omit to be prompted without echo")
    args = parser.parse_args()

    if args.command == "serve":
        log.setup()
        serve(args.host, args.port, args.public_url, args.public_mcp_path)
    elif args.command == "keygen":
        try:
            token = auth.generate_key(args.name)
        except ValueError as e:
            raise SystemExit(str(e))
        print(f"API key for '{args.name}' (shown once — store it now):\n\n  {token}\n")
        print("Register in Claude Code:\n"
              f'  claude mcp add --transport http --scope user FronyBoard http://<server>:8642/mcp '
              f'--header "Authorization: Bearer {token}"')
    elif args.command == "admin":
        password = args.password
        if password is None:
            import getpass
            password = getpass.getpass("password: ")
        try:
            auth.set_admin(args.username, password)
        except ValueError as e:
            raise SystemExit(str(e))
        print(f"dashboard login set for '{args.username.strip()}'")
    else:
        log.setup(stderr=True)  # stdout is the MCP channel — never a log sink
        _boot("stdio")
        try:
            mcp.run()
        finally:
            log.event("INFO", "boot", "shutdown", mode="stdio")


if __name__ == "__main__":
    main()
