"""End-to-end tests for the FronyBoard service layer against a temp data root."""

import pytest

from fronyboard import service, store
from conftest import bootstrap


def test_full_lifecycle():
    key = bootstrap()
    task = service.create_task(key, "2026Q3", title="Login flow",
                               content="google login, terms gate")["task"]
    assert task["id"] == "DLY-001"
    assert task["status"] == "todo"

    service.transition_task(key, "DLY-001", "in_progress", branch="feat/DLY-001/login-flow")
    listed = service.list_tasks(key, status="in_progress")
    assert listed["count"] == 1
    assert listed["tasks"][0]["branch"] == "feat/DLY-001/login-flow"

    done = service.transition_task(key, "DLY-001", "done")
    assert done["from"] == "in_progress"
    task_after = service.list_tasks(key)["tasks"][0]
    assert "completed_at" in task_after["meta"]

    closed = service.close_period(key, "2026Q3", "# 2026Q3 result\n\n- shipped")
    assert closed["closed"] == "2026Q3"
    assert service.validate(key)["ok"]

    status = service.get_status(key)
    assert status["periods"]["2026Q3"]["milestone_status"] == "done"
    assert status["periods"]["2026Q3"]["task_counts"] == {"done": 1}
    assert status["periods"]["2026Q3"]["closed"] is True


def test_period_is_one_record():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="a")
    state = store.load_state(key)
    assert sorted(state.periods) == ["2026Q3"]
    data = state.periods["2026Q3"].data
    assert [t["id"] for t in data["tasks"]] == ["DLY-001"]


def test_close_period_stores_result_in_period_record():
    key = bootstrap()
    service.close_period(key, "2026Q3", "# result\n\n- fine")
    data = store.load_state(key).periods["2026Q3"].data
    assert data["result"].startswith("# result")
    assert service.get_status(key)["periods"]["2026Q3"]["closed"] is True


def test_task_ids_are_global_sequence_across_periods():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="a")
    service.create_task(key, "2026Q3", title="b")
    service.upsert_milestone(key, "2026", "Q4", goal="v2", status="planned")
    service.open_period(key, "2026Q4")
    task = service.create_task(key, "2026Q4", title="c")["task"]
    assert task["id"] == "DLY-003"


def test_invalid_mutations_are_rejected_and_not_written(data_root):
    key = bootstrap()
    with pytest.raises(service.FronyBoardError, match="validation failed"):
        service.create_task(key, "2026Q3", title="x", content="x" * 201)
    assert service.list_tasks(key)["count"] == 0

    service.create_task(key, "2026Q3", title="x")
    with pytest.raises(service.FronyBoardError, match="validation failed"):
        service.transition_task(key, "DLY-001", "shipped")
    assert service.list_tasks(key)["tasks"][0]["status"] == "todo"


def test_close_period_requires_tasks_finished():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="open work")
    with pytest.raises(service.FronyBoardError, match="open tasks"):
        service.close_period(key, "2026Q3", "# result")
    service.transition_task(key, "DLY-001", "blocked")
    service.close_period(key, "2026Q3", "# result")


def test_guardrails():
    key = bootstrap()
    with pytest.raises(service.FronyBoardError, match="already exists"):
        service.create_project(key)
    with pytest.raises(service.FronyBoardError, match="uppercase"):
        service.create_project("dly")
    with pytest.raises(service.FronyBoardError, match="already open"):
        service.open_period(key, "2026Q3")
    with pytest.raises(service.FronyBoardError, match="no milestone"):
        service.open_period(key, "2026Q1")
    with pytest.raises(service.FronyBoardError, match="not found"):
        service.transition_task(key, "DLY-999", "done")
    service.create_task(key, "2026Q3", title="x")
    with pytest.raises(service.FronyBoardError, match="nothing to update"):
        service.update_task(key, "DLY-001")


def test_update_task_empty_value_removes_optional_field():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", content="a note")
    service.update_task(key, "DLY-001", branch="feat/DLY-001/x")
    task = service.update_task(key, "DLY-001", content="", branch="")["task"]
    assert "content" not in task and "branch" not in task
    assert "content" not in service.list_tasks(key)["tasks"][0]  # gone from the file too
    with pytest.raises(service.FronyBoardError, match="missing title"):
        service.update_task(key, "DLY-001", title="")  # required fields cannot be cleared


def test_tags_are_cleaned_and_filterable():
    key = bootstrap()
    task = service.create_task(key, "2026Q3", title="drawer",
                               tags=[" frontend ", "ui", "frontend", ""])["task"]
    assert task["tags"] == ["frontend", "ui"]          # trimmed, de-duplicated, order kept
    service.create_task(key, "2026Q3", title="gate", tags=["backend", "ui"])
    service.create_task(key, "2026Q3", title="plain")
    assert "tags" not in service.list_tasks(key)["tasks"][2]   # omitted when none given

    ids = lambda **kw: [t["id"] for t in service.list_tasks(key, **kw)["tasks"]]
    assert ids(tags=["ui"]) == ["DLY-001", "DLY-002"]
    assert ids(tags=["ui", "frontend"]) == ["DLY-001"]         # all of them, not any
    assert ids(tags=["nope"]) == []


def test_update_task_replaces_the_whole_tag_list():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", tags=["bug"])
    task = service.update_task(key, "DLY-001", tags=["infra", "bug"])["task"]
    assert task["tags"] == ["infra", "bug"]
    task = service.update_task(key, "DLY-001", tags=[])["task"]
    assert "tags" not in task
    assert "tags" not in service.list_tasks(key)["tasks"][0]   # gone from the file too


def test_depends_on_points_at_predecessors():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="first")
    task = service.create_task(key, "2026Q3", title="second",
                               depends_on=[" DLY-001 ", "DLY-001"])["task"]
    assert task["depends_on"] == ["DLY-001"]               # trimmed, de-duplicated

    rows = {t["id"]: t for t in service.list_tasks(key)["tasks"]}
    assert rows["DLY-002"]["waiting_on"] == ["DLY-001"]
    assert "waiting_on" not in rows["DLY-001"]          # nothing to wait for

    service.transition_task(key, "DLY-001", "in_progress")
    service.transition_task(key, "DLY-001", "done")
    rows = {t["id"]: t for t in service.list_tasks(key)["tasks"]}
    assert "waiting_on" not in rows["DLY-002"]          # predecessor finished

    task = service.update_task(key, "DLY-002", depends_on=[])["task"]
    assert "depends_on" not in task
    assert "depends_on" not in service.list_tasks(key)["tasks"][1]   # gone from the file too


def test_depends_on_rejects_bad_references():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="first")
    with pytest.raises(service.FronyBoardError, match="itself"):
        service.update_task(key, "DLY-001", depends_on=["DLY-001"])
    with pytest.raises(service.FronyBoardError, match="unknown task"):
        service.update_task(key, "DLY-001", depends_on=["DLY-099"])
    with pytest.raises(service.FronyBoardError, match="project ZZ not found"):
        service.update_task(key, "DLY-001", depends_on=["ZZ-001"])
    service.create_task(key, "2026Q3", title="second", depends_on=["DLY-001"])
    with pytest.raises(service.FronyBoardError, match="cycle"):
        service.update_task(key, "DLY-001", depends_on=["DLY-002"])


def test_depends_on_crosses_projects():
    bootstrap("DLY")
    bootstrap("FAU")
    service.create_task("FAU", "2026Q3", title="auth")
    task = service.create_task("DLY", "2026Q3", title="use auth",
                               depends_on=["FAU-001"])["task"]
    assert task["depends_on"] == ["FAU-001"]
    assert service.list_tasks("DLY")["tasks"][0]["waiting_on"] == ["FAU-001"]

    service.transition_task("FAU", "FAU-001", "in_progress")
    service.transition_task("FAU", "FAU-001", "done")
    assert "waiting_on" not in service.list_tasks("DLY")["tasks"][0]

    with pytest.raises(service.FronyBoardError, match="not found in project FAU"):
        service.create_task("DLY", "2026Q3", title="x", depends_on=["FAU-002"])


def test_cancel_requires_reason():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="mistake")
    with pytest.raises(service.FronyBoardError, match="requires a reason"):
        service.transition_task(key, "DLY-001", "cancelled")
    service.transition_task(key, "DLY-001", "cancelled", reason="duplicate of DLY-002")
    task = service.list_tasks(key, include_cancelled=True)["tasks"][0]
    assert task["status"] == "cancelled"
    assert task["cancel_reason"] == "duplicate of DLY-002"


def test_cancelled_hidden_by_default_but_queryable():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="keep")
    service.create_task(key, "2026Q3", title="drop")
    service.transition_task(key, "DLY-002", "cancelled", reason="descoped")
    assert [t["id"] for t in service.list_tasks(key)["tasks"]] == ["DLY-001"]
    assert service.list_tasks(key, include_cancelled=True)["count"] == 2
    assert [t["id"] for t in service.list_tasks(key, status="cancelled")["tasks"]] == ["DLY-002"]
    assert service.get_status(key)["periods"]["2026Q3"]["task_counts"] == \
        {"todo": 1, "cancelled": 1}


def test_close_period_accepts_cancelled_tasks():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="abandoned")
    service.transition_task(key, "DLY-001", "cancelled", reason="descoped")
    service.close_period(key, "2026Q3", "# result")


def test_restoring_cancelled_task_clears_reason():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="back again")
    service.transition_task(key, "DLY-001", "cancelled", reason="on hold")
    service.transition_task(key, "DLY-001", "todo")
    task = service.list_tasks(key)["tasks"][0]
    assert task["status"] == "todo"
    assert "cancel_reason" not in task
    assert service.validate(key)["ok"]


def test_lifecycle_timestamps():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x")
    service.transition_task(key, "DLY-001", "in_progress")
    first_started = service.list_tasks(key)["tasks"][0]["meta"]["started_at"]
    service.transition_task(key, "DLY-001", "blocked")
    service.transition_task(key, "DLY-001", "in_progress")
    assert service.list_tasks(key)["tasks"][0]["meta"]["started_at"] == first_started
    service.transition_task(key, "DLY-001", "done")
    assert "completed_at" in service.list_tasks(key)["tasks"][0]["meta"]
    service.transition_task(key, "DLY-001", "todo")
    assert "completed_at" not in service.list_tasks(key)["tasks"][0]["meta"]
    assert service.validate(key)["ok"]


def test_create_task_needs_nothing_but_an_open_period():
    key = bootstrap()
    task = service.create_task(key, "2026Q3", title="straight after open_period")["task"]
    assert task == {"id": "DLY-001", "title": "straight after open_period", "status": "todo",
                    "meta": task["meta"]}


def test_clean_content_folds_to_one_line_and_clears_when_empty():
    assert service._clean_content("a\n b") == "a b"
    assert service._clean_content("  ") is None
    assert service._clean_content(None) is None
    with pytest.raises(service.FronyBoardError, match="content must be a string"):
        service._clean_content(3)


def test_get_status_is_the_resume():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="a")                       # todo
    service.create_task(key, "2026Q3", title="b", depends_on=["DLY-001"])  # blocked, waiting
    service.create_task(key, "2026Q3", title="c", content="one line", tags=["ui"])
    service.create_task(key, "2026Q3", title="d")
    service.transition_task(key, "DLY-002", "blocked")
    service.transition_task(key, "DLY-003", "in_progress", branch="feat/DLY-003/c")
    service.transition_task(key, "DLY-004", "in_progress")
    service.transition_task(key, "DLY-004", "done")

    status = service.get_status(key)
    assert status["overview"]["goal"] == "ship it"
    assert "meta" not in status["overview"]
    period = status["periods"]["2026Q3"]
    assert period["task_counts"] == {"todo": 1, "blocked": 1, "in_progress": 1, "done": 1}
    assert [t["id"] for t in period["open_tasks"]] == ["DLY-003", "DLY-002", "DLY-001"]
    assert period["open_tasks"][0] == {"id": "DLY-003", "title": "c", "status": "in_progress",
                                       "tags": ["ui"], "branch": "feat/DLY-003/c",
                                       "content": "one line"}
    assert period["open_tasks"][1]["waiting_on"] == ["DLY-001"]
    assert "waiting_on" not in period["open_tasks"][2]


def test_content_round_trips_as_one_line():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", content="  step one\n  step two  ")
    assert service.list_tasks(key)["tasks"][0]["content"] == "step one step two"
    assert service.get_task(f"{key}-001")["task"]["content"] == "step one step two"


def test_list_projects():
    bootstrap("DLY")
    service.create_project("AIR", name="FronyBoard itself")
    keys = [p["key"] for p in service.list_projects()["projects"]]
    assert keys == ["AIR", "DLY"]

def test_resolve_key_derives_and_checks():
    assert service.resolve_key(None, "DLY-042") == "DLY"
    assert service.resolve_key("DLY", "DLY-042") == "DLY"
    with pytest.raises(service.FronyBoardError, match="does not match"):
        service.resolve_key("AIR", "DLY-042")
    with pytest.raises(service.FronyBoardError, match="full id"):
        service.resolve_key(None, "042")


def test_update_project_renames():
    key = bootstrap()
    service.update_project(key, "FronyBoard")
    assert service.get_status(key)["name"] == "FronyBoard"
    assert service.list_projects()["projects"][0]["name"] == "FronyBoard"


def test_unknown_period_names_the_ones_that_exist():
    """A closed period is still a period — the only way to miss is a name that never existed."""
    key = bootstrap()
    for call in (lambda p: service.list_tasks(key, period=p),
                 lambda p: service.create_task(key, p, title="x"),
                 lambda p: service.close_period(key, p, "# r"),
                 lambda p: service.get_retrospective(key, p)):
        with pytest.raises(service.FronyBoardError, match=r"has no period 2026Q4 \(it has: 2026Q3\)"):
            call("2026Q4")
        with pytest.raises(service.FronyBoardError, match="has no period|must look like"):
            call("2026-Q3")

    # a closed period still answers
    service.close_period(key, "2026Q3", "# done")
    assert service.list_tasks(key, period="2026Q3")["count"] == 0


def test_get_retrospective_and_rewrite():
    key = bootstrap()
    with pytest.raises(service.FronyBoardError, match="not closed"):
        service.get_retrospective(key, "2026Q3")
    first = service.close_period(key, "2026Q3", "# v1")
    assert first["rewritten"] is False
    assert service.get_retrospective(key, "2026Q3")["result"] == "# v1"
    second = service.close_period(key, "2026Q3", "# v2 — revised")
    assert second["rewritten"] is True
    assert service.get_retrospective(key, "2026Q3")["result"] == "# v2 — revised"
    assert service.validate(key)["ok"]


def test_project_meta_fields_and_archive():
    key = bootstrap()
    service.update_project(key, description="a diary app", repo="me/dailying")
    p = service.list_projects()["projects"][0]
    assert (p["description"], p["repo"], p["status"]) == ("a diary app", "me/dailying", "active")
    assert p["meta"]["created_at"] <= p["meta"]["updated_at"]
    with pytest.raises(service.FronyBoardError, match="at least one"):
        service.update_project(key)
    with pytest.raises(service.FronyBoardError, match="status must be one of"):
        service.update_project(key, status="deleted")

    service.create_task(key, "2026Q3", "first")
    service.update_project(key, status="paused")
    service.update_task(key, f"{key}-001", title="still editable while paused")

    service.update_project(key, status="archived")
    assert service.list_projects()["projects"] == []
    assert service.list_projects(include_archived=True)["projects"][0]["status"] == "archived"
    with pytest.raises(service.FronyBoardError, match="archived"):
        service.update_task(key, f"{key}-001", title="nope")
    service.update_project(key, status="active")
    service.update_task(key, f"{key}-001", title="back")


def test_create_project_stamps_meta_and_legacy_roadmap_still_valid():
    service.create_project("AIR", name="FronyBoard", description="tracker", repo="x/fronyboard")
    p = service.list_projects()["projects"][0]
    assert p["status"] == "active" and p["meta"]["created_at"]
    # a pre-v0.6 roadmap has neither status nor meta — must read as active, no meta
    key = bootstrap("OLD")
    state = store.load_state(key)
    state.roadmap.pop("status"); state.roadmap.pop("meta")
    store.save_roadmap(state)
    old = [x for x in service.list_projects()["projects"] if x["key"] == key][0]
    assert old["status"] == "active" and old["meta"] is None
    assert service.validate(key)["errors"] == []
