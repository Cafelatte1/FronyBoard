"""FronyBoard MCP server — the tool surface.

Commands:
    aira                                 stdio transport (local development)
    aira serve [--host H] [--port P]     streamable HTTP transport (home server)
               [--public-url URL]        the shared Funnel domain (401s advertise
               [--public-mcp-path P]     the resource metadata FronyAuth serves there)

Keys and the admin credential are issued by FronyAuth (`fauth keygen` /
`fauth admin`, project-auth repo) — aira delegates every bearer check to it.

Register a remote server in Claude Code:

    claude mcp add --transport http --scope user FronyBoard http://<server>:8642/mcp \
        --header "Authorization: Bearer <api key>"
"""

from __future__ import annotations

import argparse
import os

from mcp.server.mcpserver import MCPServer

from . import auth, fauth, log, service, store, web

mcp = MCPServer(
    "fronyboard",
    middleware=[log.ToolLogMiddleware()],
    instructions=(
        "FronyBoard is a project tracker for AI agents. Data lives in FronyBoard's "
        "own store, not in the codebase you are working on — record agreed plans, "
        "tasks and retrospectives through these tools, never as files in the repo.\n\n"
        "Which project: the codebase declares its FronyBoard project key in a "
        "`## FronyBoard` section of its CLAUDE.md (e.g. 'This project is tracked by "
        "FronyBoard (project key: DLY)'). No such declaration means the project is not "
        "FronyBoard-managed — do not ask for a key; at most, suggest registering it once. "
        "When registering a codebase (create_project), also add that `## FronyBoard` "
        "declaration to its CLAUDE.md.\n\n"
        "Task workflow: when starting branch-sized work, transition its task to in_progress "
        "and record the branch name (branch names look like feat/DLY-042/short-desc — the "
        "task id is the only link between FronyBoard and the codebase). When the work is "
        "merged, transition it to done; if you cannot observe the merge, ask the user before "
        "marking done. If branch-sized work has no task yet, offer create_task first; trivial "
        "fixes need no task.\n\n"
        "Planning flow: create_project -> set_overview (year) -> upsert_milestone (quarter) "
        "-> open_period -> upsert_month + create_task -> transition_task as work progresses "
        "-> close_period with a retrospective. A task that outlives its period is not moved: "
        "recreate it in the next period under a new id, leave the old one blocked, and map "
        "old id -> new id in the closing retrospective.\n\n"
        "Every mutation is validated before it is written; ids and timestamps are issued by "
        "the server — never invent them. Nothing is ever hard-deleted: transition_task to "
        "cancelled drops a task, update_project(status='archived') retires a project.\n\n"
        "Task content: `content` is markdown that a human reads in a narrow side panel and "
        "an agent reads to pick the task up cold, so follow the template in create_task "
        "(objective / action / criteria, under ~25 lines): objective says why and what will "
        "be observably different, action is implementation-level, criteria are verifiable. "
        "Task titles and content are written in English. Planning prose that people read on "
        "the dashboard — project description, yearly overview (goal / now / target / "
        "checklist), quarterly milestones, month goals and retrospectives — is written in "
        "Korean.\n\n"
        "Reading: get_task for one id, search_tasks for text across projects, "
        "recent_activity for what changed and who did it; list_projects already carries "
        "a per-project summary."
    ),
)


@mcp.tool()
def create_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None) -> dict:
    """Register a new project — once per codebase, before any planning happens.

    `key` is the task-id prefix (2-5 uppercase letters, e.g. DLY); `description` is one
    line in Korean saying what the project is (shown on the dashboard cards); `repo` is
    where its code lives (owner/name or a URL). Status starts as active.

    A fresh project holds nothing yet: set_overview (year) -> upsert_milestone (quarter)
    -> open_period must run before create_task will accept a task.
    """
    return service.create_project(key, name, description, repo)


@mcp.tool()
def update_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None, status: str | None = None) -> dict:
    """Update a project's own fields — pass at least one of name, description, repo, status.
    The key (and with it the task id prefix) never changes, and nothing here touches the
    roadmap, periods or tasks. `name` and `description` are Korean, as in create_project.

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

    `year` is YYYY. All prose here is Korean. `now` and `target` are one short line each. `checklist` items are
    strings (not done yet) or {text, done} maps, in display order. Calling it again
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

    `year` is YYYY (its overview must exist), `quarter` is Q1-Q4, `goal` is one Korean line, `status` is
    planned | active | done (open_period flips planned to active, close_period sets done).
    Omitted fields keep their current value.

    This is the roadmap level. The months inside a quarter that is already running are
    upsert_month.
    """
    return service.upsert_milestone(key, year, quarter, goal, status)


@mcp.tool()
def open_period(key: str, period: str) -> dict:
    """Start working in a quarter: opens its period and flips a planned milestone to active.
    Required before upsert_month or create_task will accept that period.

    `period` is YYYYQn (e.g. 2026Q3) and its roadmap milestone must already exist —
    upsert_milestone first.
    """
    return service.open_period(key, period)


@mcp.tool()
def close_period(key: str, period: str, result_markdown: str) -> dict:
    """Close a period (YYYYQn) and record its retrospective — call when its work is over.

    Refuses while any task is still todo or in_progress. Stores `result_markdown` as the
    period's `result` and marks the milestone done.

    The retrospective is written in Korean, stays under ~30 lines and holds judgment and reasons only —
    summary vs goal, per-month outcome, carried-over tasks (old id -> new id), lessons.
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
def upsert_month(key: str, period: str, month_id: str, month: str | None = None,
                 goal: str | None = None, status: str | None = None) -> dict:
    """Create or update a month inside an open period — the quarter's goal split into
    thirds, and what a task's `month` points at.

    `period` is YYYYQn and must be open, `month_id` is M1/M2/M3, `month` is YYYY-MM,
    `goal` is one Korean line, `status` is planned | active | done. Omitted fields keep their current value.

    This is the in-period level. The quarter's own goal is upsert_milestone.
    """
    return service.upsert_month(key, period, month_id, month, goal, status)


@mcp.tool()
def create_task(key: str, period: str, title: str, month: str,
                week: int | None = None, content: str | None = None,
                prd: str | None = None, tags: list[str] | None = None) -> dict:
    """Create a task — one issue/branch-sized unit of work — with status todo.

    The id is assigned from the project-global sequence and never reused.
    `period` is YYYYQn and must be open. Every task belongs to a month: `month` is a month
    id (M1/M2/M3), not YYYY-MM, and must already exist in that period (get_status lists
    them, upsert_month creates them). `week` is the week-of-month (1-5) and `prd` is an
    optional link to or excerpt of the requirement behind it.

    `tags` are free-form labels for cutting across months and status ("frontend",
    "bug", "infra"): up to 8 per task, 24 characters each, no commas. Reuse the
    wording already in use on the project (list_tasks shows it) instead of coining
    a new spelling for the same thing.

    `title` is a short English imperative ("Add multi-select status filter").
    Returns the stored record without `content`/`prd` (you already have them); get_task
    reads the full record back.

    `content` is markdown, read by a human in a narrow panel and by an agent picking the
    task up cold. Write it in English and use this template (keep it under ~25 lines):

        ## objective
        1-3 sentences: why this work exists and what will be observably different once
        it is done. For a bug: symptom -> cause. "Out of scope: ..." only if needed.
        ## action
        - implementation-level approach and files to touch (may be left empty until
          work starts; fill it in with update_task once the approach is known)
        ## criteria
        - verifiable completion conditions ("do X, see Y" — not "checked")

    Record decisions inline as "(YYYY-MM-DD decided)". The rationale lives here and
    only here: commit messages list what changed and reference the task id.
    """
    return service.create_task(key, period, title, month, week, content, prd, tags)


@mcp.tool()
def update_task(task_id: str, title: str | None = None,
                month: str | None = None, week: int | None = None, content: str | None = None,
                prd: str | None = None, branch: str | None = None,
                tags: list[str] | None = None, key: str | None = None) -> dict:
    """Update a task's fields — everything except status, which is transition_task.
    `branch` records the working branch name, `month` is a month id (M1/M2/M3) that exists
    in the task's period, `week` is 1-5.

    `content` replaces the whole markdown body — keep the create_task template (objective /
    action / criteria); fill in action once the approach is known.

    `tags` replaces the whole label list — pass the tags the task should end up with,
    not just the new ones. Returns the record without `content`/`prd`.

    Omitted fields are left as they are. To remove an optional field pass an empty value:
    `week=0`, `content=""`, `prd=""`, `branch=""`, `tags=[]` (title and month cannot
    be removed).

    `task_id` is the full id including the project prefix, e.g. DLY-042 — the project
    is derived from that prefix, so `key` may be omitted (if given it must match).
    """
    return service.update_task(service.resolve_key(key, task_id), task_id,
                               title, month, week, content, prd, branch, tags)


@mcp.tool()
def transition_task(task_id: str, status: str, branch: str | None = None,
                    reason: str | None = None, key: str | None = None) -> dict:
    """Move a task to a new status: todo | in_progress | done | blocked | cancelled. The
    only tool that changes status — title, month, content and tags are update_task.

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
               month: str | None = None, include_cancelled: bool = False,
               tags: list[str] | None = None, updated_since: str | None = None,
               include_content: bool = False) -> dict:
    """List one project's tasks, optionally narrowed by period, status, month, tags or
    recency. Use get_status when the counts are all you need, get_task when you know the
    id, search_tasks to find tasks by text across projects.

    `period` is YYYYQn (all periods, closed ones included, when omitted), `status` is one of
    todo | in_progress | done | blocked | cancelled, `month` is a month id (M1/M2/M3), not
    YYYY-MM. `tags` narrows to the tasks carrying *all* of the given labels; pass one tag to
    match on it alone, and call again per tag when you want the union.
    `updated_since` keeps tasks touched after a duration ("24h", "7d") or ISO timestamp.
    Rows carry everything but the markdown bodies (`content`, `prd`); pass
    `include_content=True` to get them, or get_task for one task.
    Cancelled tasks are excluded unless `include_cancelled` is set or `status` is 'cancelled'.
    """
    return service.list_tasks(key, period, status, month, include_cancelled, tags,
                              updated_since, include_content)


@mcp.tool()
def get_status(key: str) -> dict:
    """Where a project stands, per period: the milestone goal and status, its months (each
    with its own task counts), overall task counts by status, whether the period is closed,
    and the ids of in-progress tasks. Closed periods are included.

    The quickest way to find the current period and the month ids create_task needs.
    No task detail — list_tasks for the tasks themselves, get_roadmap for the plan as written.
    """
    return service.get_status(key)


@mcp.tool()
def get_task(task_id: str) -> dict:
    """Read one task in full by id (DLY-042) — the project comes from the prefix, so no key
    is needed. Returns the record with its period. Use this instead of list_tasks whenever
    you already know the id; search_tasks when you only know a word from it.
    """
    return service.get_task(task_id)


@mcp.tool()
def search_tasks(query: str, key: str | None = None, status: str | None = None,
                 include_cancelled: bool = False, limit: int = 20) -> dict:
    """Find tasks by text across all projects, with the dashboard's rules: case-insensitive
    substring over project key, task id, title and content (not branch or tags); a
    matching project key returns all of its tasks. Closed periods are included; cancelled
    tasks only with `include_cancelled` (or `status='cancelled'`).

    Hits are compact (no content), ordered by project, then in_progress -> blocked -> todo
    -> done -> cancelled, then id; `match` says which field hit and a content-only hit adds
    a ~60-character `snippet`. `key` narrows to one project, `limit` (default 20) caps the
    hits while `count` still reports the total. Follow up with get_task for the full record.
    """
    return service.search_tasks(query, key, status, include_cancelled, limit)


@mcp.tool()
def recent_activity(key: str | None = None, since: str | None = None, limit: int = 50,
                    writes_only: bool = True) -> dict:
    """What changed recently and who did it: the tool calls recorded in tools.jsonl,
    newest first — `ts`, `tool`, `caller` (key:<name> / session:<user> / oauth:… / stdio),
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


def serve(host: str, port: int, public_url: str | None = None, public_mcp_path: str = "/mcp") -> None:
    """Run the streamable HTTP server behind bearer auth delegated to FronyAuth.

    OAuth itself lives in FronyAuth now (AIR-056): with `public_url` (the shared
    Funnel domain) a 401 on /mcp advertises the resource metadata that FronyAuth
    serves on that domain, so hosted clients still find their way to the login.
    """
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    resource_metadata_url = None
    if public_url:
        path = "/" + public_mcp_path.strip("/")
        resource_metadata_url = f"{public_url.rstrip('/')}/.well-known/oauth-protected-resource{path}"
    # Host-header (DNS rebinding) checks are disabled: clients reach the server
    # under varying names (Tailscale name, LAN IP), and every request already
    # requires a bearer key that a rebound browser page cannot attach.
    app = mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    web.attach(app)
    _boot("http", host=f"{host}:{port}", public_url=public_url, fauth=fauth.base_url())
    try:
        uvicorn.run(auth.with_mcp_cors(
                        auth.BearerAuthMiddleware(app, protected=("/mcp", "/api"),
                                                  open_paths=("/api/login",),
                                                  resource_metadata_url=resource_metadata_url)),
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
    args = parser.parse_args()

    if args.command == "serve":
        log.setup()
        serve(args.host, args.port, args.public_url, args.public_mcp_path)
    else:
        log.setup(stderr=True)  # stdout is the MCP channel — never a log sink
        _boot("stdio")
        try:
            mcp.run()
        finally:
            log.event("INFO", "boot", "shutdown", mode="stdio")


if __name__ == "__main__":
    main()
