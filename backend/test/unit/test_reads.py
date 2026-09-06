"""Agent-facing read tools (AIR-064): get_task, search_tasks, recent_activity, and the
compact / updated_since / summary additions to list_tasks and list_projects."""

import datetime
import gzip
import json

import pytest

from aira import log, service
from conftest import bootstrap


def _seed(key="DLY"):
    bootstrap(key)
    service.create_task(key, "2026Q3", title="Add login flow", month="M1",
                        content="## objective\nUsers sign in with email.\n## action\n- filter module")
    service.create_task(key, "2026Q3", title="Fix table filter", month="M1",
                        content="dropdown clips when the list is short")
    service.create_task(key, "2026Q3", title="Drop legacy sync", month="M1")
    service.transition_task(key, f"{key}-002", "in_progress", branch=f"fix/{key}-002/filter")
    service.transition_task(key, f"{key}-003", "cancelled", reason="not needed")
    return key


# ---------------------------------------------------------------- get_task

def test_get_task_by_id_without_key():
    _seed()
    got = service.get_task("DLY-002")
    assert got["project"] == "DLY"
    assert got["task"]["period"] == "2026Q3"
    assert got["task"]["title"] == "Fix table filter"
    assert got["task"]["branch"] == "fix/DLY-002/filter"


def test_get_task_unknown_id_and_bad_shape():
    _seed()
    with pytest.raises(service.AiraError, match="not found"):
        service.get_task("DLY-099")
    with pytest.raises(service.AiraError, match="full id"):
        service.get_task("2")


# ---------------------------------------------------------------- search_tasks

def test_search_matches_title_id_and_content_with_snippet():
    _seed()
    by_title = service.search_tasks("login")
    assert [h["id"] for h in by_title["hits"]] == ["DLY-001"]
    assert by_title["hits"][0]["match"] == "title"
    assert "snippet" not in by_title["hits"][0]
    assert "content" not in by_title["hits"][0]

    by_id = service.search_tasks("dly-002")
    assert by_id["hits"][0]["match"] == "id"

    by_content = service.search_tasks("clips")
    hit = by_content["hits"][0]
    assert hit["id"] == "DLY-002" and hit["match"] == "content"
    assert "clips" in hit["snippet"]
    assert hit["snippet"].endswith("short")  # short content: no trailing ellipsis


def test_search_orders_by_status_then_id_and_hides_cancelled():
    _seed()
    # "filter" hits DLY-001 (content), DLY-002 (title); DLY-003 is cancelled and unmatched anyway
    hits = service.search_tasks("filter")["hits"]
    assert [h["id"] for h in hits] == ["DLY-002", "DLY-001"]  # in_progress before todo
    # project-key hit includes every task; cancelled only on request
    assert [h["id"] for h in service.search_tasks("dly")["hits"]] == ["DLY-002", "DLY-001"]
    with_cancelled = service.search_tasks("dly", include_cancelled=True)["hits"]
    assert [h["id"] for h in with_cancelled] == ["DLY-002", "DLY-001", "DLY-003"]
    assert all(h["match"] == "key" for h in with_cancelled)


def test_search_across_projects_key_filter_limit_and_empty_query():
    _seed("DLY")
    _seed("AIR")
    everything = service.search_tasks("filter")
    assert everything["count"] == 4 and not everything["truncated"]
    assert [h["project"] for h in everything["hits"]] == ["AIR", "AIR", "DLY", "DLY"]

    capped = service.search_tasks("filter", limit=1)
    assert capped["count"] == 4 and capped["truncated"] and len(capped["hits"]) == 1

    only = service.search_tasks("filter", key="DLY")
    assert {h["project"] for h in only["hits"]} == {"DLY"}

    assert service.search_tasks("login", status="in_progress")["count"] == 0
    with pytest.raises(service.AiraError, match="empty"):
        service.search_tasks("   ")


# ---------------------------------------------------------------- list_tasks / list_projects

def test_list_tasks_compact_and_updated_since():
    key = _seed()
    compact = service.list_tasks(key, compact=True)["tasks"]
    assert compact and all("content" not in t for t in compact)
    assert set(compact[0]) == {"period", "id", "title", "status", "month", "tags", "updated_at"}

    assert service.list_tasks(key, updated_since="1h")["count"] == 2
    assert service.list_tasks(key, updated_since="2999-01-01T00:00:00")["count"] == 0
    with pytest.raises(service.AiraError, match="since must be"):
        service.list_tasks(key, updated_since="yesterday")


def test_list_projects_carries_summary():
    key = _seed()
    entry = service.list_projects()["projects"][0]
    assert entry["key"] == key
    assert entry["summary"]["open_periods"] == ["2026Q3"]
    assert entry["summary"]["task_counts"] == {"todo": 1, "in_progress": 1, "cancelled": 1}
    assert entry["summary"]["last_activity"] is not None


# ---------------------------------------------------------------- recent_activity

@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_LOG_DIR", str(tmp_path / "logs"))
    root = log.setup()
    yield root
    log.shutdown()


def _row(ts, tool, project="DLY", **extra):
    return json.dumps({"ts": ts.isoformat(timespec="milliseconds"), "req": "abc123",
                       "tool": tool, "caller": "key:frony", "project": project,
                       "args": {}, "ms": 1.0, "ok": True, **extra})


def test_recent_activity_reads_current_and_rotated_files_newest_first(logs):
    now = datetime.datetime.now(datetime.timezone.utc)
    fresh = now - datetime.timedelta(minutes=5)
    stale = now - datetime.timedelta(days=3)
    (logs / "tools.jsonl").write_text(
        _row(fresh, "create_task", task="DLY-001") + "\n"
        + _row(now - datetime.timedelta(minutes=1), "list_tasks") + "\n"
        + _row(stale, "transition_task", task="DLY-000") + "\n", encoding="utf-8")
    with gzip.open(logs / "tools.2026-01-01_00-00-00_000000.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write(_row(now - datetime.timedelta(hours=2), "update_task", project="AIR", task="AIR-001") + "\n")
        fh.write("not json\n")

    got = service.recent_activity()
    assert [r["tool"] for r in got["activity"]] == ["create_task", "update_task"]  # reads dropped, stale dropped
    assert got["count"] == 2 and not got["truncated"]

    assert [r["tool"] for r in service.recent_activity(writes_only=False)["activity"]] \
        == ["list_tasks", "create_task", "update_task"]
    assert [r["project"] for r in service.recent_activity(key="AIR")["activity"]] == ["AIR"]
    assert service.recent_activity(since="7d")["count"] == 3
    capped = service.recent_activity(limit=1)
    assert capped["count"] == 2 and capped["truncated"] and len(capped["activity"]) == 1


def test_recent_activity_without_logs_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_LOG_DIR", str(tmp_path / "nowhere"))
    got = service.recent_activity()
    assert got["activity"] == [] and got["count"] == 0
