"""AIRA operations — the layer between the MCP tool surface and the store.

Every mutation follows the same contract: load project state, apply the change
in memory, validate the whole project, and only persist when there are no
errors. Timestamps are stamped by this layer (naive UTC) — callers never
provide them.
"""

from __future__ import annotations

import datetime
import functools
import re
import threading

from . import store, validation
from .store import PeriodState, ProjectState


class AiraError(ValueError):
    pass


_locks_guard = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}

# Mutations that may run against an archived project: creating it, and update_project
# (the only way to set its status back to active).
_ARCHIVE_EXEMPT = {"create_project", "update_project"}


def _refuse_archived(key: str) -> None:
    path = store.project_dir(key) / "roadmap.yaml"
    if not path.exists():
        return  # let the operation raise its own "unknown project" error
    roadmap = store.load_yaml(path) or {}
    if roadmap.get("status") == "archived":
        raise AiraError(f"project '{key}' is archived — update_project(status='active') to reactivate it first")


def _locked(fn):
    """Serialize mutations per project — tools may run concurrently for multiple clients.

    Also refuses every mutation on an archived project except the exempt ones."""

    @functools.wraps(fn)
    def wrapper(key: str, *args, **kwargs):
        with _locks_guard:
            lock = _project_locks.setdefault(key, threading.Lock())
        with lock:
            if fn.__name__ not in _ARCHIVE_EXEMPT:
                _refuse_archived(key)
            return fn(key, *args, **kwargs)

    return wrapper


def _jsonable(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _gate(state: ProjectState) -> list[str]:
    """Validate state; raise on errors, return warnings."""
    report = validation.validate_state(state)
    if report.errors:
        raise AiraError("validation failed — nothing was written:\n" + "\n".join(report.errors))
    return report.warnings


def _ok(payload: dict, warnings: list[str]) -> dict:
    result = _jsonable(payload)
    if warnings:
        result["warnings"] = warnings
    return result


# ---------------------------------------------------------------- projects


@_locked
def create_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None) -> dict:
    if not validation.PROJECT_KEY.fullmatch(key or ""):
        raise AiraError(f"project key must be 2-5 uppercase letters, got {key!r}")
    pdir = store.project_dir(key)
    if pdir.exists():
        raise AiraError(f"project '{key}' already exists at {pdir}")
    roadmap: dict = {"key": key}
    if name:
        roadmap["name"] = name
    if description:
        roadmap["description"] = description
    if repo:
        roadmap["repo"] = repo
    roadmap["status"] = "active"
    roadmap["meta"] = store.new_meta()
    roadmap["years"] = {}
    state = ProjectState(key=key, roadmap=roadmap)
    warnings = _gate(state)
    store.save_roadmap(state)
    return _ok({"created": key, "path": str(pdir)}, warnings)


@_locked
def update_project(key: str, name: str | None = None, description: str | None = None,
                   repo: str | None = None, status: str | None = None) -> dict:
    state = store.load_state(key)
    fields = {"name": name, "description": description, "repo": repo, "status": status}
    changed = {k: v for k, v in fields.items() if v is not None}
    if not changed:
        raise AiraError("nothing to update — pass at least one of name, description, repo, status")
    state.roadmap.update(changed)
    store.touch_meta(state.roadmap)
    warnings = _gate(state)
    store.save_roadmap(state)
    return _ok({"key": key, "project": _project_summary(key, state.roadmap)}, warnings)


def _project_summary(key: str, roadmap: dict) -> dict:
    return {"key": key, "name": roadmap.get("name"),
            "description": roadmap.get("description"), "repo": roadmap.get("repo"),
            "status": roadmap.get("status") or "active", "meta": roadmap.get("meta")}


def list_projects(include_archived: bool = False) -> dict:
    root = store.projects_dir()
    projects = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and (entry / "roadmap.yaml").exists():
                roadmap = store.load_yaml(entry / "roadmap.yaml") or {}
                summary = _project_summary(entry.name, roadmap)
                if include_archived or summary["status"] != "archived":
                    projects.append(summary)
    return _jsonable({"projects": projects, "data_root": str(store.data_root())})


def get_roadmap(key: str) -> dict:
    state = store.load_state(key)
    return _jsonable({"roadmap": state.roadmap, "periods": sorted(state.periods)})


# ----------------------------------------------------------------- roadmap


@_locked
def set_overview(key: str, year: str, goal: str, now: str, next_: str, later: str) -> dict:
    state = store.load_state(key)
    years = state.roadmap.setdefault("years", {})
    ydata = years.setdefault(str(year), {})
    overview = ydata.get("overview")
    if overview is None:
        overview = ydata["overview"] = {"meta": store.new_meta()}
    overview.update({"goal": goal, "now": now, "next": next_, "later": later})
    store.touch_meta(overview)
    warnings = _gate(state)
    store.save_roadmap(state)
    return _ok({"year": str(year), "overview": overview}, warnings)


@_locked
def upsert_milestone(key: str, year: str, quarter: str,
                     goal: str | None = None, status: str | None = None) -> dict:
    state = store.load_state(key)
    ydata = state.roadmap.get("years", {}).get(str(year))
    if ydata is None:
        raise AiraError(f"year {year} has no overview yet — call set_overview first")
    milestones = ydata.setdefault("milestones", {})
    m = milestones.get(quarter)
    if m is None:
        m = milestones[quarter] = {"goal": None, "status": "planned", "meta": store.new_meta()}
    if goal is not None:
        m["goal"] = goal
    if status is not None:
        m["status"] = status
    store.touch_meta(m)
    warnings = _gate(state)
    store.save_roadmap(state)
    return _ok({"milestone": f"{year}{quarter}", "goal": m["goal"], "status": m["status"]}, warnings)


# ----------------------------------------------------------------- periods


def _milestone_for(state: ProjectState, period: str) -> dict:
    if not validation.PERIOD_NAME.fullmatch(period):
        raise AiraError(f"period must look like 2026Q3, got {period!r}")
    year, quarter = period[:4], period[4:]
    m = state.roadmap.get("years", {}).get(year, {}).get("milestones", {}).get(quarter)
    if m is None:
        raise AiraError(f"no milestone {year}.{quarter} in the roadmap — call upsert_milestone first")
    return m


@_locked
def open_period(key: str, period: str) -> dict:
    state = store.load_state(key)
    milestone = _milestone_for(state, period)
    if period in state.periods:
        raise AiraError(f"period {period} is already open")
    state.periods[period] = PeriodState(data={"months": [], "tasks": []})
    if milestone["status"] == "planned":
        milestone["status"] = "active"
        store.touch_meta(milestone)
    warnings = _gate(state)
    store.save_roadmap(state)
    store.save_period(state, period)
    return _ok({"opened": period, "milestone_status": milestone["status"]}, warnings)


@_locked
def close_period(key: str, period: str, result_markdown: str) -> dict:
    state = store.load_state(key)
    milestone = _milestone_for(state, period)
    if period not in state.periods:
        raise AiraError(f"period {period} is not open")
    open_tasks = [t["id"] for t in state.periods[period].data.get("tasks") or []
                  if t.get("status") not in ("done", "blocked", "cancelled")]
    if open_tasks:
        raise AiraError(
            f"period {period} still has open tasks: {', '.join(open_tasks)} — "
            "finish them or recreate them in the next period (new id), then close")
    rewritten = state.periods[period].has_result
    milestone["status"] = "done"
    store.touch_meta(milestone)
    state.periods[period].data["result"] = result_markdown
    warnings = _gate(state)
    store.save_roadmap(state)
    store.save_period(state, period)
    return _ok({"closed": period, "rewritten": rewritten}, warnings)


def get_retrospective(key: str, period: str) -> dict:
    state = store.load_state(key)
    if period not in state.periods:
        raise AiraError(f"period {period} is not open")
    p = state.periods[period]
    if not p.has_result:
        raise AiraError(f"period {period} is not closed yet — no retrospective")
    return {"period": period, "result": p.data["result"]}


@_locked
def upsert_month(key: str, period: str, month_id: str, month: str | None = None,
                 goal: str | None = None, status: str | None = None) -> dict:
    state = store.load_state(key)
    if period not in state.periods:
        raise AiraError(f"period {period} is not open")
    months = state.periods[period].data.setdefault("months", [])
    m = next((m for m in months if m.get("id") == month_id), None)
    if m is None:
        m = {"id": month_id, "month": month, "goal": goal,
             "status": status or "planned", "meta": store.new_meta()}
        months.append(m)
    else:
        if month is not None:
            m["month"] = month
        if goal is not None:
            m["goal"] = goal
        if status is not None:
            m["status"] = status
    store.touch_meta(m)
    warnings = _gate(state)
    store.save_period(state, period)
    return _ok({"period": period, "month": m}, warnings)


# ------------------------------------------------------------------- tasks


def resolve_key(key: str | None, task_id: str) -> str:
    """Derive the project key from a task id (DLY-042 -> DLY); an explicit key must match."""
    m = re.fullmatch(r"([A-Z]{2,5})-\d+", str(task_id or ""))
    if not m:
        raise AiraError(f"task_id must be a full id like DLY-042, got {task_id!r}")
    derived = m.group(1)
    if key and key != derived:
        raise AiraError(f"key {key!r} does not match the task id prefix {derived!r}")
    return derived


def _next_task_id(state: ProjectState) -> str:
    numbers = [0]
    for p in state.periods.values():
        for t in p.data.get("tasks") or []:
            m = re.fullmatch(rf"{re.escape(state.key)}-(\d+)", str(t.get("id", "")))
            if m:
                numbers.append(int(m.group(1)))
    return f"{state.key}-{max(numbers) + 1:03d}"


def _find_task(state: ProjectState, task_id: str) -> tuple[str, dict]:
    for period, p in state.periods.items():
        for t in p.data.get("tasks") or []:
            if t.get("id") == task_id:
                return period, t
    raise AiraError(f"task {task_id} not found in project {state.key}")


@_locked
def create_task(key: str, period: str, title: str, month: str,
                week: int | None = None, content: str | None = None,
                prd: str | None = None) -> dict:
    state = store.load_state(key)
    if period not in state.periods:
        raise AiraError(f"period {period} is not open")
    task: dict = {"id": _next_task_id(state), "title": title,
                  "month": month, "status": "todo"}
    if week is not None:
        task["week"] = week
    if content is not None:
        task["content"] = content
    if prd is not None:
        task["prd"] = prd
    task["meta"] = store.new_meta()
    state.periods[period].data.setdefault("tasks", []).append(task)
    warnings = _gate(state)
    store.save_period(state, period)
    return _ok({"period": period, "task": task}, warnings)


# Optional task fields; an "empty" value (0 / "") passed to update_task removes them.
_CLEARABLE = {"week", "content", "prd", "branch"}


@_locked
def update_task(key: str, task_id: str, title: str | None = None,
                month: str | None = None, week: int | None = None, content: str | None = None,
                prd: str | None = None, branch: str | None = None) -> dict:
    state = store.load_state(key)
    period, task = _find_task(state, task_id)
    fields = {"title": title, "month": month, "week": week,
              "content": content, "prd": prd, "branch": branch}
    changed = {k: v for k, v in fields.items() if v is not None}
    if not changed:
        raise AiraError("nothing to update — pass at least one field (status changes go through transition_task)")
    for k, v in changed.items():
        if k in _CLEARABLE and v in (0, ""):
            task.pop(k, None)
        else:
            task[k] = v
    store.touch_meta(task)
    warnings = _gate(state)
    store.save_period(state, period)
    return _ok({"period": period, "task": task}, warnings)


@_locked
def transition_task(key: str, task_id: str, status: str, branch: str | None = None,
                    reason: str | None = None) -> dict:
    state = store.load_state(key)
    period, task = _find_task(state, task_id)
    previous = task.get("status")
    if status == "cancelled" and not reason:
        raise AiraError("cancelling a task requires a reason — pass reason=...")
    task["status"] = status
    if branch is not None:
        task["branch"] = branch
    if status == "cancelled":
        task["cancel_reason"] = reason
    elif previous == "cancelled":
        task.pop("cancel_reason", None)
    store.touch_meta(task)
    if status == "in_progress" and "started_at" not in task["meta"]:
        task["meta"]["started_at"] = store.now()
    if status == "done":
        task["meta"]["completed_at"] = store.now()
    elif previous == "done":
        task["meta"].pop("completed_at", None)
    warnings = _gate(state)
    store.save_period(state, period)
    return _ok({"task_id": task_id, "from": previous, "to": status, "period": period}, warnings)


# ----------------------------------------------------------------- queries


def list_tasks(key: str, period: str | None = None, status: str | None = None,
               month: str | None = None, include_cancelled: bool = False) -> dict:
    state = store.load_state(key)
    if period is not None and period not in state.periods:
        raise AiraError(f"period {period} is not open")
    results = []
    for pname, p in sorted(state.periods.items()):
        if period is not None and pname != period:
            continue
        for t in p.data.get("tasks") or []:
            if (t.get("status") == "cancelled" and not include_cancelled
                    and status != "cancelled"):
                continue
            if status is not None and t.get("status") != status:
                continue
            if month is not None and t.get("month") != month:
                continue
            results.append({"period": pname, **t})
    return _jsonable({"tasks": results, "count": len(results)})


def get_status(key: str) -> dict:
    state = store.load_state(key)
    periods = {}
    for pname in sorted(state.periods):
        p = state.periods[pname]
        milestone = state.roadmap.get("years", {}).get(pname[:4], {}) \
            .get("milestones", {}).get(pname[4:], {})
        counts: dict[str, int] = {}
        month_counts: dict[str, dict[str, int]] = {}
        for t in p.data.get("tasks") or []:
            status = t.get("status", "?")
            counts[status] = counts.get(status, 0) + 1
            per_month = month_counts.setdefault(t.get("month"), {})
            per_month[status] = per_month.get(status, 0) + 1
        periods[pname] = {
            "goal": milestone.get("goal"),
            "milestone_status": milestone.get("status"),
            "months": [{"id": m.get("id"), "month": m.get("month"), "goal": m.get("goal"),
                        "status": m.get("status"),
                        "task_counts": month_counts.get(m.get("id"), {})}
                       for m in p.data.get("months") or []],
            "task_counts": counts,
            "closed": p.has_result,
            "in_progress": [t["id"] for t in p.data.get("tasks") or []
                            if t.get("status") == "in_progress"],
        }
    return _jsonable({"project": state.key, "name": state.roadmap.get("name"), "periods": periods})


def validate(key: str) -> dict:
    report = validation.validate_state(store.load_state(key))
    return {"ok": not report.errors, "errors": report.errors, "warnings": report.warnings}
