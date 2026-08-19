"""End-to-end tests for the AIRA service layer against a temp data root."""

import pytest

from aira import service, store


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    return tmp_path


def bootstrap(key="DLY"):
    service.create_project(key, name="Dailying")
    service.set_overview(key, "2026", goal="ship it", now="build core",
                         next_="validate habit", later="expand")
    service.upsert_milestone(key, "2026", "Q3", goal="MVP", status="planned")
    service.open_period(key, "2026Q3")
    service.upsert_month(key, "2026Q3", "M1", month="2026-07", goal="core", status="active")
    return key


def test_full_lifecycle():
    key = bootstrap()
    task = service.create_task(key, "2026Q3", title="Login flow", month="M1",
                               week=2, content="- google login\n- terms gate")["task"]
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


def test_period_lives_in_a_single_file():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="a", month="M1")
    pdir = store.project_dir(key)
    assert (pdir / "2026Q3.yaml").is_file()
    assert sorted(p.name for p in pdir.iterdir()) == ["2026Q3.yaml", "roadmap.yaml"]
    data = store.load_yaml(pdir / "2026Q3.yaml")
    assert [m["id"] for m in data["months"]] == ["M1"]
    assert [t["id"] for t in data["tasks"]] == ["DLY-001"]


def test_close_period_stores_result_in_period_file():
    key = bootstrap()
    service.close_period(key, "2026Q3", "# result\n\n- fine")
    data = store.load_yaml(store.project_dir(key) / "2026Q3.yaml")
    assert data["result"].startswith("# result")
    assert service.get_status(key)["periods"]["2026Q3"]["closed"] is True


def test_task_ids_are_global_sequence_across_periods():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="a", month="M1")
    service.create_task(key, "2026Q3", title="b", month="M1")
    service.upsert_milestone(key, "2026", "Q4", goal="v2", status="planned")
    service.open_period(key, "2026Q4")
    service.upsert_month(key, "2026Q4", "M1", month="2026-10", goal="v2", status="planned")
    task = service.create_task(key, "2026Q4", title="c", month="M1")["task"]
    assert task["id"] == "DLY-003"


def test_invalid_mutations_are_rejected_and_not_written(data_root):
    key = bootstrap()
    with pytest.raises(service.AiraError, match="validation failed"):
        service.create_task(key, "2026Q3", title="x", month="M9")
    with pytest.raises(service.AiraError, match="validation failed"):
        service.create_task(key, "2026Q3", title="x", month="M1", week=7)
    assert service.list_tasks(key)["count"] == 0

    service.create_task(key, "2026Q3", title="x", month="M1")
    with pytest.raises(service.AiraError, match="validation failed"):
        service.transition_task(key, "DLY-001", "shipped")
    assert service.list_tasks(key)["tasks"][0]["status"] == "todo"


def test_close_period_requires_tasks_finished():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="open work", month="M1")
    with pytest.raises(service.AiraError, match="open tasks"):
        service.close_period(key, "2026Q3", "# result")
    service.transition_task(key, "DLY-001", "blocked")
    service.close_period(key, "2026Q3", "# result")


def test_guardrails():
    key = bootstrap()
    with pytest.raises(service.AiraError, match="already exists"):
        service.create_project(key)
    with pytest.raises(service.AiraError, match="uppercase"):
        service.create_project("dly")
    with pytest.raises(service.AiraError, match="already open"):
        service.open_period(key, "2026Q3")
    with pytest.raises(service.AiraError, match="no milestone"):
        service.open_period(key, "2026Q1")
    with pytest.raises(service.AiraError, match="not found"):
        service.transition_task(key, "DLY-999", "done")
    service.create_task(key, "2026Q3", title="x", month="M1")
    with pytest.raises(service.AiraError, match="nothing to update"):
        service.update_task(key, "DLY-001")


def test_cancel_requires_reason():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="mistake", month="M1")
    with pytest.raises(service.AiraError, match="requires a reason"):
        service.transition_task(key, "DLY-001", "cancelled")
    service.transition_task(key, "DLY-001", "cancelled", reason="duplicate of DLY-002")
    task = service.list_tasks(key, include_cancelled=True)["tasks"][0]
    assert task["status"] == "cancelled"
    assert task["cancel_reason"] == "duplicate of DLY-002"


def test_cancelled_hidden_by_default_but_queryable():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="keep", month="M1")
    service.create_task(key, "2026Q3", title="drop", month="M1")
    service.transition_task(key, "DLY-002", "cancelled", reason="descoped")
    assert [t["id"] for t in service.list_tasks(key)["tasks"]] == ["DLY-001"]
    assert service.list_tasks(key, include_cancelled=True)["count"] == 2
    assert [t["id"] for t in service.list_tasks(key, status="cancelled")["tasks"]] == ["DLY-002"]
    assert service.get_status(key)["periods"]["2026Q3"]["task_counts"] == \
        {"todo": 1, "cancelled": 1}


def test_close_period_accepts_cancelled_tasks():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="abandoned", month="M1")
    service.transition_task(key, "DLY-001", "cancelled", reason="descoped")
    service.close_period(key, "2026Q3", "# result")


def test_restoring_cancelled_task_clears_reason():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="back again", month="M1")
    service.transition_task(key, "DLY-001", "cancelled", reason="on hold")
    service.transition_task(key, "DLY-001", "todo")
    task = service.list_tasks(key)["tasks"][0]
    assert task["status"] == "todo"
    assert "cancel_reason" not in task
    assert service.validate(key)["ok"]


def test_lifecycle_timestamps():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")
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


def test_get_status_rolls_up_per_month():
    key = bootstrap()
    service.upsert_month(key, "2026Q3", "M2", month="2026-08", goal="polish", status="planned")
    service.create_task(key, "2026Q3", title="a", month="M1")
    service.create_task(key, "2026Q3", title="b", month="M1")
    service.create_task(key, "2026Q3", title="c", month="M2")
    service.transition_task(key, "DLY-001", "in_progress")
    months = service.get_status(key)["periods"]["2026Q3"]["months"]
    assert months[0]["id"] == "M1"
    assert months[0]["task_counts"] == {"in_progress": 1, "todo": 1}
    assert months[1]["task_counts"] == {"todo": 1}


def test_content_round_trips_as_multiline_markdown():
    key = bootstrap()
    content = "- step one\n- step two\n- step three"
    service.create_task(key, "2026Q3", title="x", month="M1", content=content)
    text = (store.project_dir(key) / "2026Q3.yaml").read_text(encoding="utf-8")
    assert "content: |-" in text or "content: |" in text
    assert service.list_tasks(key)["tasks"][0]["content"] == content


def test_list_projects():
    bootstrap("DLY")
    service.create_project("AIR", name="AIRA itself")
    keys = [p["key"] for p in service.list_projects()["projects"]]
    assert keys == ["AIR", "DLY"]

def test_resolve_key_derives_and_checks():
    assert service.resolve_key(None, "DLY-042") == "DLY"
    assert service.resolve_key("DLY", "DLY-042") == "DLY"
    with pytest.raises(service.AiraError, match="does not match"):
        service.resolve_key("AIR", "DLY-042")
    with pytest.raises(service.AiraError, match="full id"):
        service.resolve_key(None, "042")


def test_update_project_renames():
    key = bootstrap()
    service.update_project(key, "FronyBoard")
    assert service.get_status(key)["name"] == "FronyBoard"
    assert service.list_projects()["projects"][0]["name"] == "FronyBoard"


def test_get_retrospective_and_rewrite():
    key = bootstrap()
    with pytest.raises(service.AiraError, match="not closed"):
        service.get_retrospective(key, "2026Q3")
    first = service.close_period(key, "2026Q3", "# v1")
    assert first["rewritten"] is False
    assert service.get_retrospective(key, "2026Q3")["result"] == "# v1"
    second = service.close_period(key, "2026Q3", "# v2 — revised")
    assert second["rewritten"] is True
    assert service.get_retrospective(key, "2026Q3")["result"] == "# v2 — revised"
    assert service.validate(key)["ok"]
