"""AIRA operations — the layer between the MCP tool surface and the store.

Every mutation follows the same contract: load project state, apply the change
in memory, validate the whole project, and only persist when there are no
errors. Timestamps are stamped by this layer (naive UTC) — callers never
provide them.
"""

from __future__ import annotations

import datetime
import functools
import gzip
import json
import re
import threading

from . import log, store, validation
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


def _project_keys(include_archived: bool = False) -> list[str]:
    root = store.projects_dir()
    keys = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and (entry / "roadmap.yaml").exists():
                roadmap = store.load_yaml(entry / "roadmap.yaml") or {}
                if include_archived or (roadmap.get("status") or "active") != "archived":
                    keys.append(entry.name)
    return keys


def _activity_summary(state: ProjectState) -> dict:
    """Open periods, task counts by status and the newest task update — the one-line
    "where is this project" that list_projects attaches to every entry."""
    counts: dict[str, int] = {}
    last = None
    for p in state.periods.values():
        for t in p.data.get("tasks") or []:
            st = t.get("status", "?")
            counts[st] = counts.get(st, 0) + 1
            u = (t.get("meta") or {}).get("updated_at")
            if isinstance(u, datetime.datetime) and (last is None or u > last):
                last = u
    return {"open_periods": [n for n, p in sorted(state.periods.items()) if not p.has_result],
            "task_counts": counts, "last_activity": last}


def list_projects(include_archived: bool = False) -> dict:
    projects = []
    for key in _project_keys(include_archived):
        state = store.load_state(key)
        entry = _project_summary(key, state.roadmap)
        entry["summary"] = _activity_summary(state)
        projects.append(entry)
    return _jsonable({"projects": projects, "data_root": str(store.data_root())})


def _without_meta(value):
    """Drop every nested `meta` block — agents reading a plan never need the timestamps."""
    if isinstance(value, dict):
        return {k: _without_meta(v) for k, v in value.items() if k != "meta"}
    if isinstance(value, list):
        return [_without_meta(v) for v in value]
    return value


def get_roadmap(key: str, include_meta: bool = False) -> dict:
    state = store.load_state(key)
    roadmap = state.roadmap if include_meta else _without_meta(state.roadmap)
    return _jsonable({"roadmap": roadmap, "periods": sorted(state.periods)})


# ----------------------------------------------------------------- roadmap


def _clean_checklist(items) -> list:
    """Accept plain strings (not done yet) or {text, done} maps; anything else is passed
    through unchanged so validation reports it."""
    out = []
    for item in items:
        if isinstance(item, str):
            out.append({"text": item, "done": False})
        elif isinstance(item, dict):
            out.append({"text": item.get("text"), "done": bool(item.get("done", False))})
        else:
            out.append(item)
    return out


@_locked
def set_overview(key: str, year: str, goal: str, now: str | None = None,
                 target: str | None = None, checklist: list | None = None) -> dict:
    """Replace the year's overview wholesale. Legacy now/next/later keys are dropped
    here — there is no migration; rewriting the overview is the migration."""
    state = store.load_state(key)
    years = state.roadmap.setdefault("years", {})
    ydata = years.setdefault(str(year), {})
    old = ydata.get("overview") or {}
    overview: dict = {"goal": goal}
    if now:
        overview["now"] = now
    if target:
        overview["target"] = target
    if checklist is not None:
        overview["checklist"] = _clean_checklist(checklist)
    overview["meta"] = old.get("meta") or store.new_meta()
    ydata["overview"] = overview
    store.touch_meta(overview)
    warnings = _gate(state)
    store.save_roadmap(state)
    return _ok({"year": str(year), "overview": overview}, warnings)


@_locked
def set_check(key: str, year: str, index: int, done: bool) -> dict:
    state = store.load_state(key)
    overview = ((state.roadmap.get("years") or {}).get(str(year)) or {}).get("overview")
    items = (overview or {}).get("checklist")
    if not items:
        raise AiraError(f"year {year} has no checklist — set_overview writes one")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(items):
        raise AiraError(f"index must be 0..{len(items) - 1}, got {index!r}")
    items[index]["done"] = bool(done)
    store.touch_meta(overview)
    warnings = _gate(state)
    store.save_roadmap(state)
    return _ok({"year": str(year), "index": index, "overview": overview}, warnings)


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


def _require_period(state: ProjectState, period: str) -> None:
    """Refuse an unknown period by name — closed periods are still in here, so the
    only way to miss is a period that was never opened (or a typo in its name)."""
    if period not in state.periods:
        known = ", ".join(sorted(state.periods)) or "none — open_period starts one"
        raise AiraError(
            f"project {state.key} has no period {period} (it has: {known})")


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
    # the period first: a quarter that was never opened cannot be closed, and pointing
    # at its missing milestone would send the caller off to upsert_milestone instead
    _require_period(state, period)
    milestone = _milestone_for(state, period)
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
    _require_period(state, period)
    p = state.periods[period]
    if not p.has_result:
        raise AiraError(f"period {period} is not closed yet — no retrospective")
    return {"period": period, "result": p.data["result"]}


@_locked
def upsert_month(key: str, period: str, month_id: str, month: str | None = None,
                 goal: str | None = None, status: str | None = None) -> dict:
    state = store.load_state(key)
    _require_period(state, period)
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


def _clean_tags(tags: list[str] | None) -> list[str]:
    """Trim, drop blanks and de-duplicate while keeping the order given."""
    if not tags:
        return []
    if not isinstance(tags, list):
        raise AiraError("tags must be a list of strings")
    cleaned: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            raise AiraError(f"tags must be a list of strings ({tag!r})")
        tag = tag.strip()
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return cleaned


@_locked
def create_task(key: str, period: str, title: str, month: str,
                week: int | None = None, content: str | None = None,
                prd: str | None = None, tags: list[str] | None = None) -> dict:
    state = store.load_state(key)
    _require_period(state, period)
    task: dict = {"id": _next_task_id(state), "title": title,
                  "month": month, "status": "todo"}
    if week is not None:
        task["week"] = week
    tags = _clean_tags(tags)
    if tags:
        task["tags"] = tags
    if content is not None:
        task["content"] = content
    if prd is not None:
        task["prd"] = prd
    task["meta"] = store.new_meta()
    state.periods[period].data.setdefault("tasks", []).append(task)
    warnings = _gate(state)
    store.save_period(state, period)
    return _ok({"period": period, "task": _without_prose(task)}, warnings)


# Optional task fields; an "empty" value (0 / "" / []) passed to update_task removes them.
_CLEARABLE = {"week", "content", "prd", "branch", "tags"}
_PROSE = ("content", "prd")


def _without_prose(task: dict) -> dict:
    """The task record minus its markdown bodies. Writes echo this shape (the caller already
    has the text) and list_tasks returns it by default; get_task carries the full record."""
    return {k: v for k, v in task.items() if k not in _PROSE}


@_locked
def update_task(key: str, task_id: str, title: str | None = None,
                month: str | None = None, week: int | None = None, content: str | None = None,
                prd: str | None = None, branch: str | None = None,
                tags: list[str] | None = None) -> dict:
    state = store.load_state(key)
    period, task = _find_task(state, task_id)
    if tags is not None:
        tags = _clean_tags(tags)
    fields = {"title": title, "month": month, "week": week,
              "content": content, "prd": prd, "branch": branch, "tags": tags}
    changed = {k: v for k, v in fields.items() if v is not None}
    if not changed:
        raise AiraError("nothing to update — pass at least one field (status changes go through transition_task)")
    for k, v in changed.items():
        if k in _CLEARABLE and v in (0, "", []):
            task.pop(k, None)
        else:
            task[k] = v
    store.touch_meta(task)
    warnings = _gate(state)
    store.save_period(state, period)
    return _ok({"period": period, "task": _without_prose(task)}, warnings)


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
               month: str | None = None, include_cancelled: bool = False,
               tags: list[str] | None = None, updated_since: str | None = None,
               include_content: bool = False) -> dict:
    state = store.load_state(key)
    if period is not None:
        _require_period(state, period)
    wanted = set(_clean_tags(tags))   # a task must carry all of them
    cutoff = _naive_utc(_since(updated_since)) if updated_since else None
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
            if wanted and not wanted <= set(t.get("tags") or []):
                continue
            if cutoff is not None:
                u = (t.get("meta") or {}).get("updated_at")
                if not isinstance(u, datetime.datetime) or u < cutoff:
                    continue
            results.append({"period": pname, **(t if include_content else _without_prose(t))})
    return _jsonable({"tasks": results, "count": len(results)})


# ---------------------------------------------------------------- reads

_STATUS_ORDER = ("in_progress", "blocked", "todo", "done", "cancelled")
_SNIPPET_AROUND = 30   # same window as the dashboard search (frontend/src/search.ts)
_READ_TOOLS = frozenset({"list_projects", "get_roadmap", "get_retrospective", "list_tasks",
                         "get_status", "validate", "get_task", "search_tasks",
                         "recent_activity"})
_DURATION = re.compile(r"^\s*(\d+)\s*([mhd])\s*$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def _since(value: str | None, default: str = "24h") -> datetime.datetime:
    """A cutoff (aware UTC) from a duration like "24h" / "7d" / "90m" or an ISO timestamp."""
    raw = value or default
    m = _DURATION.match(raw)
    if m:
        delta = datetime.timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})
        return datetime.datetime.now(datetime.timezone.utc) - delta
    try:
        ts = datetime.datetime.fromisoformat(raw.strip())
    except ValueError:
        raise AiraError("since must be a duration like 24h / 7d / 90m or an ISO timestamp, "
                        f"got {raw!r}") from None
    return ts if ts.tzinfo else ts.replace(tzinfo=datetime.timezone.utc)


def _naive_utc(ts: datetime.datetime) -> datetime.datetime:
    """Records store naive UTC (store.now); compare cutoffs in the same shape."""
    return ts.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _compact(period: str, t: dict) -> dict:
    return {"period": period, "id": t.get("id"), "title": t.get("title"),
            "status": t.get("status"), "month": t.get("month"), "tags": t.get("tags") or [],
            "updated_at": (t.get("meta") or {}).get("updated_at")}


def get_task(task_id: str) -> dict:
    key = resolve_key(None, task_id)
    state = store.load_state(key)
    period, task = _find_task(state, task_id)
    return _jsonable({"project": key, "task": {"period": period, **task}})


def _snippet(content: str, q: str) -> str | None:
    flat = re.sub(r"\s+", " ", content)
    i = flat.lower().find(q)
    if i < 0:
        return None
    start = max(0, i - _SNIPPET_AROUND)
    end = min(len(flat), i + len(q) + _SNIPPET_AROUND)
    return ("…" if start > 0 else "") + flat[start:end] + ("…" if end < len(flat) else "")


def search_tasks(query: str, key: str | None = None, status: str | None = None,
                 include_cancelled: bool = False, limit: int = 20) -> dict:
    """Dashboard search rules (frontend/src/search.ts): case-insensitive substring over
    project key, task id, title and content; a key hit includes every task of that project.
    Ordered by project, then status (in_progress first), then id."""
    q = (query or "").strip().lower()
    if not q:
        raise AiraError("query must not be empty")
    if limit < 1:
        raise AiraError("limit must be at least 1")
    hits = []
    for pkey in ([key] if key else _project_keys()):
        state = store.load_state(pkey)
        key_hit = q in pkey.lower()
        for pname, p in sorted(state.periods.items()):
            for t in p.data.get("tasks") or []:
                if (t.get("status") == "cancelled" and not include_cancelled
                        and status != "cancelled"):
                    continue
                if status is not None and t.get("status") != status:
                    continue
                tid, title = str(t.get("id") or ""), str(t.get("title") or "")
                content = str(t.get("content") or "")
                if key_hit:
                    match = "key"
                elif q in tid.lower():
                    match = "id"
                elif q in title.lower():
                    match = "title"
                elif q in content.lower():
                    match = "content"
                else:
                    continue
                hit = {"project": pkey, **_compact(pname, t), "match": match}
                if match == "content":
                    hit["snippet"] = _snippet(content, q)
                hits.append(hit)

    def order(h):
        st = h["status"]
        rank = _STATUS_ORDER.index(st) if st in _STATUS_ORDER else len(_STATUS_ORDER)
        return (h["project"], rank, h["id"] or "")

    hits.sort(key=order)
    return _jsonable({"hits": hits[:limit], "count": len(hits), "truncated": len(hits) > limit})


def _activity_files(root) -> list:
    """tools.jsonl first, then rotated days newest-first (tools.YYYY-MM-DD_....jsonl[.gz])."""
    files = [root / "tools.jsonl"] if (root / "tools.jsonl").exists() else []
    files += sorted(root.glob("tools.*.jsonl*"), reverse=True)
    return files


def _read_jsonl(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def recent_activity(key: str | None = None, since: str | None = None, limit: int = 50,
                    writes_only: bool = True) -> dict:
    """Tool calls from tools.jsonl newer than `since`, newest first. Files are read
    newest-first and reading stops at the first file entirely older than the cutoff."""
    if limit < 1:
        raise AiraError("limit must be at least 1")
    cutoff = _since(since)
    root = log.log_dir()
    utc = datetime.timezone.utc
    rows: list[tuple[datetime.datetime, dict]] = []
    for path in _activity_files(root):
        newest = None
        for r in _read_jsonl(path):
            try:
                ts = datetime.datetime.fromisoformat(str(r["ts"]))
            except (KeyError, ValueError):
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=utc)
            if newest is None or ts > newest:
                newest = ts
            if ts < cutoff:
                continue
            if key and r.get("project") != key:
                continue
            if writes_only and r.get("tool") in _READ_TOOLS:
                continue
            rows.append((ts, _activity_row(r)))
        if newest is not None and newest < cutoff:
            break
    rows.sort(key=lambda x: x[0], reverse=True)
    return {"activity": [r for _, r in rows[:limit]], "count": len(rows),
            "truncated": len(rows) > limit, "since": cutoff.isoformat()}


_ACTIVITY_FIELDS = ("ts", "tool", "caller", "project", "task", "args")


def _activity_row(r: dict) -> dict:
    """What an agent needs from a tools.jsonl line: who did what, where, when. Request ids,
    timings and warning counts stay in the log; `ok` is shown only when the call failed."""
    row = {k: r[k] for k in _ACTIVITY_FIELDS if k in r}
    if r.get("ok") is False:
        row["ok"] = False
    return row


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
