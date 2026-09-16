"""FronyBoard MCP server — the tool surface.

Commands:
    fronyboard                                 stdio transport (local development)
    fronyboard serve [--host H] [--port P]     streamable HTTP transport (home server)
               [--public-url URL]        this server's public origin (https://board.frony.app);
               [--public-auth-url URL]   FronyAuth's public issuer — together they publish the
                                         RFC 9728 metadata that 401s on /mcp advertise
    fronyboard serve --local                   same, loopback only, no FronyAuth, no credentials

Keys and the admin credential are issued by FronyAuth (`fauth keygen` /
`fauth admin`, project-auth repo) — FronyBoard delegates every bearer check to it.

Register a remote server in Claude Code:

    claude mcp add --transport http --scope user FronyBoard http://<server>:8642/mcp \
        --header "Authorization: Bearer <api key>"
"""

from __future__ import annotations

import argparse
import json
import os

from mcp.server.mcpserver import MCPServer

from . import auth, fauth, log, service, store, web

_LOOPBACK = ("127.0.0.1", "localhost", "::1")

mcp = MCPServer(
    "fronyboard",
    middleware=[log.ToolLogMiddleware()],
    instructions=(
        "FronyBoard is a project tracker for AI agents. Data lives in FronyBoard's own store, not in the codebase you are working on — record plans, tasks and retrospectives through these tools, never as files in the repo.\n\n"
        "Which project: the codebase declares its FronyBoard project key in a `## FronyBoard` section of its CLAUDE.md (e.g. 'This project is tracked by FronyBoard (project key: DLY)'). No such declaration means the project is not FronyBoard-managed — do not ask for a key; at most, suggest registering it once. When registering a codebase (create_project), also add that `## FronyBoard` declaration to its CLAUDE.md.\n\n"
        "Session rhythm — two calls, not a conversation: call get_status once when you start on a project (it is the whole resume: the year's overview, each period's goal and every open task with its one-line note) and do not poll it again. Then create_task / transition_task as the work actually changes state. Every call is a full turn for you, so no second read unless the board itself is the subject.\n\n"
        "Tasks: one task per branch-sized piece of work; trivial fixes need none. Create it yourself when you start such work — there is no one to ask — then transition it to in_progress with the branch name (feat/DLY-042/short-desc; the id is the only link between FronyBoard and the codebase) and to done when the work is merged (if you cannot observe the merge, ask the user first). A task is a title plus an optional one-line `content` of at most 200 characters: the one fact the next agent cannot get from the code — an interpretation you chose, a scope you left out, the check that proves it done. Everything else lives in the code and the commits. `follows` lists the tasks this one continues from (other projects allowed); it is a pointer, not a lock.\n\n"
        "Planning: create_project -> set_overview (year) -> upsert_milestone (quarter) -> open_period; create_task works right after open_period, nothing else has to exist first. A task that outlives its period is not moved: recreate it in the next period under a new id, leave the old one blocked, and map old id -> new id in the closing retrospective. The roadmap and the retrospective are written with the user; the tasks are yours.\n\n"
        "Every mutation is validated before it is written; ids and timestamps are issued by the server — never invent them. Nothing is ever hard-deleted: transition_task to cancelled drops a task, update_project(status='archived') retires a project.\n\n"
        "Language: task titles and content are English. Planning prose people read on the dashboard — project description, yearly overview (goal / now / target / checklist), quarterly milestones and retrospectives — is written in the language the user speaks with you; keep one language per board.\n\n"
        "Other reads: get_task for one id, list_tasks to narrow by period / status / tags, search_tasks for text across projects, recent_activity for what changed and who did it; list_projects already carries a per-project summary."
    ),
)


@mcp.tool()
def create_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None) -> dict:
    """Register a new project — once per codebase, before any planning happens.

    `key` is the task-id prefix (2-5 uppercase letters, e.g. DLY); `description` is one
    line saying what the project is, in the user's language (shown on the dashboard cards);
    `repo` is where its code lives (owner/name or a URL). Status starts as active.

    A fresh project holds nothing yet: set_overview (year) -> upsert_milestone (quarter)
    -> open_period must run before create_task will accept a task.
    """
    return service.create_project(key, name, description, repo)


@mcp.tool()
def update_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None, status: str | None = None) -> dict:
    """Update a project's own fields — pass at least one of name, description, repo, status.
    The key (and with it the task id prefix) never changes, and nothing here touches the
    roadmap, periods or tasks. `name` and `description` follow create_project's language rule.

    `status`: active | paused | archived. paused only changes the badge; archived hides the
    project from list_projects and refuses every other mutation until it is set back to
    active. Archived is as far as removal goes — there is no hard delete.
    """
    return service.update_project(key, name, description, repo, status)


@mcp.tool()
def list_projects(include_archived: bool = False) -> dict:
    """List every project (key, name, description, repo, status, meta) — how to find out
    which keys exist. Archived ones are left out unless `include_archived` is set.

    Each entry carries a `summary`: its open periods, task counts by status and
    `last_activity` (the newest task update). No milestones or task detail: get_roadmap
    for the plan, get_status for per-period progress, list_tasks for the tasks.
    """
    return service.list_projects(include_archived)


@mcp.tool()
def get_roadmap(key: str, include_meta: bool = False) -> dict:
    """Read a project's plan as written: yearly overviews (goal, now, target, checklist),
    quarterly milestones, and the names of its periods.

    Goals only, no counts — get_status for progress and the current period, list_tasks for
    the tasks themselves. Timestamps (`meta`) are left out unless `include_meta` is set.
    """
    return service.get_roadmap(key, include_meta)


@mcp.tool()
def set_overview(key: str, year: str, goal: str, now: str | None = None,
                 target: str | None = None, checklist: list[str | dict] | None = None) -> dict:
    """Create or replace a year's overview: the one-line yearly `goal`, plus the three
    blocks the dashboard shows for the current year — `now` (what is being worked on),
    `target` (what that work is meant to reach) and `checklist` (the concrete steps to get
    there, ticked off as they land). A year needs an overview before upsert_milestone will
    add a quarter to it.

    `year` is YYYY. All prose here is in the user's language. `now` and `target` are one
    short line each. `checklist` items are strings (not done yet) or {text, done} maps,
    in display order. Calling it again
    replaces the whole overview — resend the checklist to keep it; use set_check to tick a
    single item. Quarterly goals belong in upsert_milestone, not here.
    """
    return service.set_overview(key, year, goal, now, target, checklist)


@mcp.tool()
def set_check(key: str, year: str, index: int, done: bool = True) -> dict:
    """Tick or untick one item of a year's overview checklist: `index` is its 0-based
    position in get_roadmap's `checklist`, `done` the new state. Returns the updated
    overview. To add, remove or reword items use set_overview.
    """
    return service.set_check(key, year, index, done)


@mcp.tool()
def upsert_milestone(key: str, year: str, quarter: str,
                     goal: str | None = None, status: str | None = None) -> dict:
    """Create or update a quarterly milestone — a year's goal for one quarter.

    `year` is YYYY (its overview must exist), `quarter` is Q1-Q4, `goal` is one line in the
    user's language, `status` is planned | active | done (open_period flips planned to
    active, close_period sets done).
    Omitted fields keep their current value.
    """
    return service.upsert_milestone(key, year, quarter, goal, status)


@mcp.tool()
def open_period(key: str, period: str) -> dict:
    """Start working in a quarter: opens its period and flips a planned milestone to active.
    Required before create_task will accept that period.

    `period` is YYYYQn (e.g. 2026Q3) and its roadmap milestone must already exist —
    upsert_milestone first.
    """
    return service.open_period(key, period)


@mcp.tool()
def close_period(key: str, period: str, result_markdown: str) -> dict:
    """Close a period (YYYYQn) and record its retrospective — call when its work is over.

    Refuses while any task is still todo or in_progress. Stores `result_markdown` as the
    period's `result` and marks the milestone done.

    The retrospective is written in the user's language, stays under ~30 lines and holds
    judgment and reasons only — summary vs goal, what landed and what did not, carried-over tasks
    (old id -> new id), lessons.
    Calling it again on a closed period rewrites the retrospective and changes nothing else.
    """
    return service.close_period(key, period, result_markdown)


@mcp.tool()
def get_retrospective(key: str, period: str) -> dict:
    """Read a closed period's (YYYYQn) retrospective — the `result` markdown close_period
    wrote. Errors while the period is still open; get_status says which ones are closed.
    """
    return service.get_retrospective(key, period)


@mcp.tool()
def create_task(key: str, period: str, title: str, content: str | None = None,
                tags: list[str] | None = None, follows: list[str] | None = None) -> dict:
    """Create a task — one issue/branch-sized unit of work — with status todo.

    The id is assigned from the project-global sequence and never reused. `period` is
    YYYYQn and must be open; nothing else has to exist first.

    `title` is a short English imperative ("Add multi-select status filter") — it is what
    every reader sees, so it has to say the whole thing.

    `content` is optional: one line, at most 200 characters, English. It carries the one
    fact the next agent cannot recover from the code — the interpretation you chose, the
    scope you left out, or the check that proves it done. Line breaks are folded into
    spaces; a longer text is rejected, not cut. Rationale beyond that goes in the commit.

    `tags` are free-form labels ("frontend", "bug", "infra"): up to 8 per task, 24
    characters each, no commas. Reuse the wording already in use on the project
    (list_tasks shows it) instead of coining a new spelling for the same thing.

    `follows` lists the task ids this one continues from — the earlier tasks whose result
    this one builds on, or the one that handed it this scope. Full ids, other projects
    allowed. It points backwards only, and it is a pointer, not a dependency lock: nothing
    blocks. `list_tasks` and `get_status` flag the entries not yet done as `waiting_on`.
    """
    return service.create_task(key, period, title, content, tags, follows)


@mcp.tool()
def update_task(task_id: str, title: str | None = None, content: str | None = None,
                branch: str | None = None, tags: list[str] | None = None,
                follows: list[str] | None = None, key: str | None = None) -> dict:
    """Update a task's fields — everything except status, which is transition_task.
    `branch` records the working branch name; `content` replaces the one-line note
    (same rule as create_task: one line, at most 200 characters).

    `tags` replaces the whole label list — pass the tags the task should end up with,
    not just the new ones. `follows` likewise replaces the whole predecessor list.

    Omitted fields are left as they are. To remove an optional field pass an empty value:
    `content=""`, `branch=""`, `tags=[]`, `follows=[]` (title cannot be removed).

    `task_id` is the full id including the project prefix, e.g. DLY-042 — the project
    is derived from that prefix, so `key` may be omitted (if given it must match).
    """
    return service.update_task(service.resolve_key(key, task_id), task_id,
                               title, content, branch, tags, follows)


@mcp.tool()
def transition_task(task_id: str, status: str, branch: str | None = None,
                    reason: str | None = None, key: str | None = None) -> dict:
    """Move a task to a new status: todo | in_progress | done | blocked | cancelled. The
    only tool that changes status — title, content and tags are update_task.

    `task_id` is the full id, e.g. DLY-042; the project is derived from that prefix, so
    `key` may be omitted (if given it must match). Call when work starts (in_progress,
    ideally with the branch name) and when it finishes (done); the server stamps
    started_at and completed_at itself.

    `cancelled` is the soft delete — there is no hard one: the record is kept but hidden
    from queries by default, and `reason` is required. Use blocked for work that may
    resume, cancelled for work that will not happen. Transitioning a cancelled task to
    any other status restores it.
    """
    return service.transition_task(service.resolve_key(key, task_id), task_id,
                                   status, branch, reason)


@mcp.tool()
def list_tasks(key: str, period: str | None = None, status: str | None = None,
               include_cancelled: bool = False, tags: list[str] | None = None,
               updated_since: str | None = None) -> dict:
    """List one project's tasks, optionally narrowed by period, status, tags or recency.
    get_status already lists the open ones; use this for done or cancelled tasks, a closed
    period, or a tag cut. get_task when you know the id, search_tasks for text across
    projects.

    `period` is YYYYQn (all periods, closed ones included, when omitted), `status` is one of
    todo | in_progress | done | blocked | cancelled. `tags` narrows to the tasks carrying
    *all* of the given labels; pass one tag to match on it alone, and call again per tag
    when you want the union. `updated_since` keeps tasks touched after a duration ("24h",
    "7d") or ISO timestamp. A row carries `waiting_on` (the ids from its `follows` not yet
    done) only when there are any. Cancelled tasks are excluded unless `include_cancelled`
    is set or `status` is 'cancelled'.
    """
    return service.list_tasks(key, period, status, include_cancelled, tags, updated_since)


@mcp.tool()
def get_status(key: str) -> dict:
    """The resume: everything an agent needs to pick a project up cold, in one call. The
    latest year's overview (goal / now / target / checklist), and per period its milestone
    goal and status, task counts by status, whether it is closed, and `open_tasks` — every
    todo / blocked / in_progress task with its title, tags, branch, one-line content and
    `waiting_on`. Closed periods are included.

    Call it once at the start of a session; there is nothing to poll for afterwards.
    Done and cancelled tasks are list_tasks; the plan as written is get_roadmap.
    """
    return service.get_status(key)


@mcp.tool()
def get_task(task_id: str) -> dict:
    """Read one task in full by id (DLY-042) — the project comes from the prefix, so no key
    is needed. Returns the record with its period. Use this instead of list_tasks whenever
    you already know the id; search_tasks when you only know a word from it. The record also
    carries `waiting_on` when it applies.
    """
    return service.get_task(task_id)


@mcp.tool()
def search_tasks(query: str, key: str | None = None, status: str | None = None,
                 include_cancelled: bool = False, limit: int = 20) -> dict:
    """Find tasks by text across all projects, with the dashboard's rules: case-insensitive
    substring over project key, task id, title and content (not branch or tags); a
    matching project key returns all of its tasks. Closed periods are included; cancelled
    tasks only with `include_cancelled` (or `status='cancelled'`).

    Hits are compact, ordered by project, then in_progress -> blocked -> todo
    -> done -> cancelled, then id; `match` says which field hit; a task's one-line `content`
    is included when it has one. `key` narrows to one project, `limit` (default 20) caps the
    hits while `count` still reports the total. Follow up with get_task for the full record.
    """
    return service.search_tasks(query, key, status, include_cancelled, limit)


@mcp.tool()
def recent_activity(key: str | None = None, since: str | None = None, limit: int = 50,
                    writes_only: bool = True) -> dict:
    """What changed recently and who did it: the tool calls recorded in tools.jsonl,
    newest first — `ts`, `tool`, `caller` (key:<name> / session:<user> / oauth:… / stdio / local),
    `project`, `task` and `args` (argument names; prose fields appear as `<name>_len`);
    `ok: false` marks a rejected call. This is the mutation history; task records
    themselves keep only timestamps.

    `since` is a duration ("24h" default, "7d", "90m") or an ISO timestamp; `key` narrows
    to one project; `limit` caps the rows (default 50) while `count` reports the total.
    Read-only calls are dropped unless `writes_only=False`.
    """
    return service.recent_activity(key, since, limit, writes_only)


@mcp.tool()
def validate(key: str) -> dict:
    """Check a project's stored data against the FronyBoard schema and rules, returning
    errors and warnings.

    Rarely needed on its own — every mutation runs this same gate and refuses to write when
    it fails. Use it after the store was edited outside these tools.
    """
    return service.validate(key)


def build_app(host: str, public_url: str | None = None, public_auth_url: str | None = None,
              local: bool = False):
    """The ASGI stack `serve` runs: MCP + dashboard behind bearer auth delegated to FronyAuth.

    OAuth itself lives in FronyAuth (AIR-056). Every Frony service has its own host since
    the Cloudflare Tunnel move (board.frony.app / auth.frony.app), so this server publishes
    its own RFC 9728 resource metadata at /.well-known/oauth-protected-resource/mcp:
    `public_url` is this service's origin, `public_auth_url` FronyAuth's public issuer.
    A 401 on /mcp points at that document, so hosted clients find their way to the login.
    `local` is the single-user mode: loopback only, no FronyAuth, no credentials (AIR-083).
    """
    if local and host not in _LOOPBACK:
        raise SystemExit(f"--local serves the loopback interface only; --host {host!r} is not allowed")
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.middleware.gzip import GZipMiddleware

    resource_metadata_url = None
    metadata_routes = []
    if public_url:
        if not public_auth_url:
            raise SystemExit("--public-url needs --public-auth-url (FronyAuth's public issuer)")
        from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
        from mcp.server.auth.settings import AuthSettings
        # AuthSettings keeps a path-less URL slash-free (a bare AnyHttpUrl appends "/"); RFC 8414
        # clients compare the issuer string exactly, and FronyAuth publishes it the same way.
        urls = AuthSettings(issuer_url=public_auth_url.rstrip("/"),
                            resource_server_url=f"{public_url.rstrip('/')}/mcp")
        resource_metadata_url = str(build_resource_metadata_url(urls.resource_server_url))
        metadata_routes = create_protected_resource_routes(
            urls.resource_server_url, [urls.issuer_url], resource_name="FronyBoard")
    if local:
        # Nothing authenticates here, so a rebound browser page could otherwise reach
        # this server — keep the host check on and pin it to the loopback names.
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*"])
    else:
        # Host-header (DNS rebinding) checks are disabled: clients reach the server
        # under varying names (Tailscale name, LAN IP), and every request already
        # requires a bearer key that a rebound browser page cannot attach.
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=security)
    # The metadata route is open by design (RFC 9728 discovery happens before any credential)
    # and sits outside the protected prefixes; it must precede the dashboard's "/" mount.
    app.router.routes.extend(metadata_routes)
    web.LOCAL_MODE = local
    web.attach(app)
    # gzip sits inside auth so /mcp streams are untouched (minimum_size keeps them out)
    # and the board JSON (~130 KB) shrinks ~5x for the dashboard.
    if local:
        return auth.LocalCallerMiddleware(GZipMiddleware(app, minimum_size=2048))
    return auth.with_mcp_cors(
        auth.BearerAuthMiddleware(GZipMiddleware(app, minimum_size=2048),
                                  protected=("/mcp", "/api"),
                                  open_paths=("/api/login",),
                                  resource_metadata_url=resource_metadata_url))


def serve(host: str, port: int, public_url: str | None = None, public_auth_url: str | None = None,
          local: bool = False) -> None:
    """Run the streamable HTTP server (see `build_app`)."""
    import uvicorn

    stack = build_app(host, public_url, public_auth_url, local=local)
    _boot("http", host=f"{host}:{port}", public_url=public_url,
          fauth=None if local else fauth.base_url(), local=local)
    try:
        uvicorn.run(stack, host=host, port=port, log_config=None)
    finally:
        log.event("INFO", "boot", "shutdown", mode="http")


def _boot(mode: str, **fields) -> None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        ver = version("fronyboard")
    except PackageNotFoundError:
        ver = "dev"
    log.event("INFO", "boot", "start", mode=mode, version=ver, data=str(store.data_root()),
              logs=str(log.log_dir()), tz=os.environ.get("FRONYBOARD_TZ"), **fields)


def _strip_legacy() -> None:
    """Drop the fields the task model no longer has; silent when there was nothing to drop."""
    report = store.strip_legacy()
    if any(report.values()):
        log.event("INFO", "boot", "strip_legacy", **report)


def main() -> None:
    parser = argparse.ArgumentParser(prog="fronyboard", description="FronyBoard MCP server")
    sub = parser.add_subparsers(dest="command")
    serve_p = sub.add_parser("serve", help="run the HTTP server (shared server, or --local for one machine)")
    serve_p.add_argument("--host", default=None)
    serve_p.add_argument("--port", type=int, default=8642)
    serve_p.add_argument("--local", action="store_true",
                         help="single-user mode: bind to 127.0.0.1, no FronyAuth, no credentials "
                              "— the dashboard opens without a login")
    serve_p.add_argument("--public-url", default=os.environ.get("FRONYBOARD_PUBLIC_URL") or None,
                         help="this server's public HTTPS origin, e.g. https://board.frony.app "
                              "(enables OAuth for hosted MCP clients); default: FRONYBOARD_PUBLIC_URL")
    serve_p.add_argument("--public-auth-url", default=os.environ.get("FRONYBOARD_PUBLIC_AUTH_URL") or None,
                         help="public URL of FronyAuth, the OAuth issuer (required with --public-url); "
                              "default: FRONYBOARD_PUBLIC_AUTH_URL")
    mig_p = sub.add_parser("migrate", help="copy the pre-v0.25 YAML tree into fronyboard.db (once)")
    mig_p.add_argument("--source", default=None, help="projects/ folder; default <data root>/projects")
    mig_p.add_argument("--dry-run", action="store_true", help="list what would be copied, write nothing")
    args = parser.parse_args()

    if args.command == "migrate":
        from pathlib import Path
        report = store.migrate_yaml(Path(args.source) if args.source else None, dry_run=args.dry_run)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if args.command == "serve":
        log.setup()
        _strip_legacy()
        host = args.host or ("127.0.0.1" if args.local else "0.0.0.0")
        serve(host, args.port, args.public_url, args.public_auth_url, local=args.local)
    else:
        log.setup(stderr=True)  # stdout is the MCP channel — never a log sink
        _strip_legacy()
        _boot("stdio")
        try:
            mcp.run()
        finally:
            log.event("INFO", "boot", "shutdown", mode="stdio")


if __name__ == "__main__":
    main()
