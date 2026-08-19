"""Schema and rule validation for AIRA project data.

Validation runs as a gate before every mutation is persisted (errors block the
write) and is also exposed as the `validate` tool. Checks: required fields,
status enums, the task.month reference, period key <-> file consistency,
id formats, global task-id uniqueness, meta timestamp shape (naive UTC) and
ordering (updated_at >= created_at).
"""

from __future__ import annotations

import datetime
import re

from .store import ProjectState

MILESTONE_STATUS = {"planned", "active", "done"}
TASK_STATUS = {"todo", "in_progress", "done", "blocked", "cancelled"}
QUARTER_KEY = re.compile(r"^Q[1-4]$")
PERIOD_NAME = re.compile(r"^\d{4}Q[1-4]$")
MONTH_ID = re.compile(r"^M\d+$")
PROJECT_KEY = re.compile(r"^[A-Z]{2,5}$")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _check_meta(record: dict, where: str, r: Report) -> None:
    meta = record.get("meta")
    if not isinstance(meta, dict):
        r.err(f"{where}: missing meta map")
        return
    for field in ("created_at", "updated_at"):
        value = meta.get(field)
        if value is None:
            r.err(f"{where}: missing meta.{field}")
            return
        if not isinstance(value, datetime.datetime):
            r.err(f"{where}: meta.{field} is not a datetime ({value!r})")
            return
        if value.tzinfo is not None:
            r.err(f"{where}: meta.{field} carries a timezone — must be naive UTC")
    c, u = meta.get("created_at"), meta.get("updated_at")
    if isinstance(c, datetime.datetime) and isinstance(u, datetime.datetime) and u < c:
        r.err(f"{where}: meta.updated_at < meta.created_at")


def _check_roadmap(state: ProjectState, r: Report) -> dict[str, str]:
    """Validate roadmap and return {period folder name: milestone status}."""
    roadmap = state.roadmap
    if not isinstance(roadmap, dict):
        r.err("roadmap.yaml: top-level map required")
        return {}
    key = roadmap.get("key")
    if not isinstance(key, str) or not PROJECT_KEY.fullmatch(key):
        r.err(f"roadmap.yaml: key must be 2-5 uppercase letters ({key!r})")
    elif key != state.key:
        r.err(f"roadmap.yaml: key {key!r} does not match project folder '{state.key}'")

    years = roadmap.get("years")
    if years is None:
        return {}
    if not isinstance(years, dict):
        r.err("roadmap.yaml: years must be a map")
        return {}

    expected: dict[str, str] = {}
    for year, ydata in years.items():
        where = f"roadmap.yaml years.{year}"
        if not re.fullmatch(r"\d{4}", str(year)):
            r.err(f"{where}: year key must be a 'YYYY' string")
        overview = (ydata or {}).get("overview")
        if not isinstance(overview, dict):
            r.err(f"{where}: missing overview")
        else:
            for field in ("goal", "now", "next", "later"):
                if not overview.get(field):
                    r.err(f"{where}.overview: missing {field}")
            _check_meta(overview, f"{where}.overview", r)
        milestones = (ydata or {}).get("milestones")
        if milestones is None:
            continue
        if not isinstance(milestones, dict):
            r.err(f"{where}: milestones must be a map")
            continue
        for q, m in milestones.items():
            mwhere = f"{where}.milestones.{q}"
            if not QUARTER_KEY.fullmatch(str(q)):
                r.err(f"{mwhere}: quarter key must be Q1-Q4")
                continue
            if not isinstance(m, dict) or not m.get("goal"):
                r.err(f"{mwhere}: missing goal")
                continue
            if m.get("status") not in MILESTONE_STATUS:
                r.err(f"{mwhere}: status must be one of {sorted(MILESTONE_STATUS)}")
            _check_meta(m, mwhere, r)
            expected[f"{year}{q}"] = m.get("status")
    return expected


def _check_period(state: ProjectState, name: str, status: str, task_id_re: re.Pattern,
                  all_task_ids: set, r: Report) -> None:
    period = state.periods[name]
    data = period.data if isinstance(period.data, dict) else {}
    if status == "done" and not period.has_result:
        r.err(f"{name}: milestone is done but `result` is missing — the retrospective closes a period")
    if data.get("result") is not None and not isinstance(data["result"], str):
        r.err(f"{name}.yaml: result must be a markdown string")

    month_ids = set()
    months = data.get("months")
    if months is None:
        r.err(f"{name}.yaml: missing months")
    else:
        for m in months:
            where = f"{name}.yaml months[{m.get('id')}]"
            if not MONTH_ID.fullmatch(str(m.get("id", ""))):
                r.err(f"{where}: id must look like M1, M2, ...")
            if m.get("id") in month_ids:
                r.err(f"{where}: duplicate id")
            month_ids.add(m.get("id"))
            if not m.get("month") or not m.get("goal"):
                r.err(f"{where}: missing month/goal")
            if m.get("month") and not re.fullmatch(r"\d{4}-\d{2}", str(m["month"])):
                r.err(f"{where}: month must be 'YYYY-MM' ({m.get('month')!r})")
            if m.get("status") not in MILESTONE_STATUS:
                r.err(f"{where}: status must be one of {sorted(MILESTONE_STATUS)}")
            _check_meta(m, where, r)

    for t in data.get("tasks") or []:
        tid = t.get("id")
        where = f"{name}.yaml tasks[{tid}]"
        if not task_id_re.fullmatch(str(tid or "")):
            r.err(f"{where}: id must match '{task_id_re.pattern}'")
        if tid in all_task_ids:
            r.err(f"{where}: duplicate id — task numbers are a project-global sequence (never reused)")
        all_task_ids.add(tid)
        if not t.get("title"):
            r.err(f"{where}: missing title")
        if t.get("month") not in month_ids:
            r.err(f"{where}: month '{t.get('month')}' not found in objective months")
        if t.get("status") not in TASK_STATUS:
            r.err(f"{where}: status must be one of {sorted(TASK_STATUS)}")
        if t.get("status") == "cancelled":
            if not t.get("cancel_reason"):
                r.err(f"{where}: a cancelled task must record a cancel_reason")
        elif t.get("cancel_reason") is not None:
            r.err(f"{where}: cancel_reason is only valid on a cancelled task")
        meta = t.get("meta") if isinstance(t.get("meta"), dict) else {}
        for field in ("started_at", "completed_at"):
            value = meta.get(field)
            if value is not None and (not isinstance(value, datetime.datetime)
                                      or value.tzinfo is not None):
                r.err(f"{where}: meta.{field} must be a naive UTC datetime")
        if t.get("status") == "done":
            if not isinstance(meta.get("completed_at"), datetime.datetime):
                r.err(f"{where}: a done task must have meta.completed_at")
        elif meta.get("completed_at") is not None:
            r.err(f"{where}: meta.completed_at is only valid on a done task")
        week = t.get("week")
        if week is not None and not (isinstance(week, int) and 1 <= week <= 5):
            r.err(f"{where}: week must be an integer 1-5 (week of month) ({week!r})")
        if t.get("content") is not None and not isinstance(t["content"], str):
            r.err(f"{where}: content must be a markdown string")
        _check_meta(t, where, r)


def validate_state(state: ProjectState) -> Report:
    r = Report()
    expected = _check_roadmap(state, r)

    key = state.roadmap.get("key") if isinstance(state.roadmap, dict) else None
    prefix = key if isinstance(key, str) and PROJECT_KEY.fullmatch(key) else state.key
    task_id_re = re.compile(rf"^{re.escape(prefix)}-\d{{3,}}$")

    actual = {name for name in state.periods if PERIOD_NAME.fullmatch(name)}
    for stray in sorted(set(state.periods) - actual):
        r.warn(f"file '{stray}.yaml' does not look like a period file (YYYYQ#.yaml) — ignored")
    for missing in sorted(set(expected) - actual):
        # A planned period may not be opened yet — only active/done require a file.
        if expected[missing] == "planned":
            r.warn(f"planned period not opened yet: {missing}.yaml")
        else:
            r.err(f"milestone {missing} is {expected[missing]} but its period file is missing")
    for orphan in sorted(actual - set(expected)):
        r.warn(f"period file without a roadmap milestone (orphan): {orphan}.yaml")

    all_task_ids: set = set()
    for name in sorted(actual & set(expected)):
        _check_period(state, name, expected[name], task_id_re, all_task_ids, r)
    return r
