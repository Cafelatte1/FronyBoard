"""Direct validation-gate tests — rules and warnings the service layer cannot produce.

The service gate blocks invalid mutations, so broken states are built in memory
(or written straight to disk) and fed to validate_state.
"""

import datetime

from fronyboard import service, store, validation
from conftest import bootstrap


def _report(key):
    return validation.validate_state(store.load_state(key))


def test_planned_milestone_without_period_file_is_a_warning():
    key = bootstrap()
    service.upsert_milestone(key, "2026", "Q4", goal="v2", status="planned")
    report = _report(key)
    assert not report.errors
    assert any("planned period not opened yet: 2026Q4" in w for w in report.warnings)


def test_orphan_period_record_is_a_warning():
    key = bootstrap()
    state = store.load_state(key)
    state.periods["2025Q1"] = store.PeriodState(data={"months": [], "tasks": []})
    store.save_period(state, "2025Q1")
    report = _report(key)
    assert not report.errors
    assert any("orphan" in w and "2025Q1" in w for w in report.warnings)


def test_done_milestone_requires_result():
    key = bootstrap()
    state = store.load_state(key)
    state.roadmap["years"]["2026"]["milestones"]["Q3"]["status"] = "done"
    report = validation.validate_state(state)
    assert any("retrospective closes a period" in e for e in report.errors)


def test_active_milestone_without_period_file_is_an_error():
    key = bootstrap()
    state = store.load_state(key)
    state.roadmap["years"]["2026"]["milestones"]["Q4"] = {
        "goal": "v2", "status": "active", "meta": store.new_meta()}
    report = validation.validate_state(state)
    assert any("2026Q4 is active but its period record is missing" in e
               for e in report.errors)


def test_meta_timestamps_must_be_ordered_naive_utc():
    key = bootstrap()
    state = store.load_state(key)
    meta = state.roadmap["years"]["2026"]["overview"]["meta"]
    meta["updated_at"] = meta["created_at"] - datetime.timedelta(seconds=1)
    report = validation.validate_state(state)
    assert any("updated_at < meta.created_at" in e for e in report.errors)

    state = store.load_state(key)
    meta = state.roadmap["years"]["2026"]["overview"]["meta"]
    meta["created_at"] = datetime.datetime.now(datetime.timezone.utc)
    report = validation.validate_state(state)
    assert any("carries a timezone" in e for e in report.errors)


def test_task_status_field_invariants():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")

    state = store.load_state(key)
    state.periods["2026Q3"].data["tasks"][0]["cancel_reason"] = "leftover"
    report = validation.validate_state(state)
    assert any("only valid on a cancelled task" in e for e in report.errors)

    state = store.load_state(key)
    state.periods["2026Q3"].data["tasks"][0]["meta"]["completed_at"] = store.now()
    report = validation.validate_state(state)
    assert any("only valid on a done task" in e for e in report.errors)


def test_month_format_and_task_month_reference():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")
    state = store.load_state(key)
    state.periods["2026Q3"].data["months"][0]["month"] = "2026/07"
    report = validation.validate_state(state)
    assert any("must be 'YYYY-MM'" in e for e in report.errors)

    state = store.load_state(key)
    state.periods["2026Q3"].data["tasks"][0]["month"] = "M9"
    report = validation.validate_state(state)
    assert any("'M9' not found" in e for e in report.errors)


def test_duplicate_task_ids_are_an_error():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")
    state = store.load_state(key)
    tasks = state.periods["2026Q3"].data["tasks"]
    tasks.append(dict(tasks[0]))
    report = validation.validate_state(state)
    assert any("duplicate id" in e for e in report.errors)


def test_tag_rules_are_enforced():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")
    state = store.load_state(key)
    task = state.periods["2026Q3"].data["tasks"][0]

    def errors(tags):
        task["tags"] = tags
        return " ".join(validation.validate_state(state).errors)

    assert "list of strings" in errors("frontend")
    assert "non-empty string" in errors([""])
    assert "longer than 24" in errors(["x" * 25])
    assert "must not contain a comma" in errors(["a,b"])
    assert "leading/trailing whitespace" in errors([" ui"])
    assert "duplicate tag" in errors(["ui", "ui"])
    assert "at most 8 tags" in errors([f"t{n}" for n in range(9)])
    assert not errors(["ui", "backend"])
