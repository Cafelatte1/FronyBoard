"""Concurrent mutations must serialize per project — no duplicate ids, no lost writes."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from aira import service


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    return tmp_path


def test_parallel_create_task_yields_unique_sequential_ids():
    key = "DLY"
    service.create_project(key)
    service.set_overview(key, "2026", goal="g", now="n", next_="x", later="l")
    service.upsert_milestone(key, "2026", "Q3", goal="mvp", status="planned")
    service.open_period(key, "2026Q3")
    service.upsert_month(key, "2026Q3", "M1", month="2026-07", goal="m", status="active")

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(
            lambda i: service.create_task(key, "2026Q3", title=f"task {i}", month="M1"),
            range(10)))

    ids = sorted(r["task"]["id"] for r in results)
    assert ids == [f"DLY-{n:03d}" for n in range(1, 11)]
    assert service.list_tasks(key)["count"] == 10
