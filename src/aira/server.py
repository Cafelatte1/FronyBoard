"""AIRA MCP server — the tool surface.

Run with `aira` (stdio transport). Register in Claude Code:

    claude mcp add aira -- uv run --directory <path-to-project-aira> aira
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import service

mcp = MCPServer(
    "aira",
    instructions=(
        "AIRA is a project tracker for AI agents (AI + JIRA). Data lives in AIRA's own "
        "store, not in the codebase you are working on. Typical flow: create_project -> "
        "set_overview (year) -> upsert_milestone (quarter) -> open_period -> upsert_month, "
        "create_epic, create_task -> transition_task as work starts/finishes -> close_period "
        "with a retrospective. Task ids (e.g. DLY-042) are the only link to the codebase: use "
        "them in branch names like feat/DLY-042/short-desc and record that branch on the task. "
        "Every mutation is validated before it is written; timestamps are stamped automatically."
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
