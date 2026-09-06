"""Concurrent mutations must serialize per project — no duplicate ids, no lost writes."""

from concurrent.futures import ThreadPoolExecutor

from aira import service
from conftest import bootstrap


def test_parallel_create_task_yields_unique_sequential_ids():
    key = bootstrap()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(
            lambda i: service.create_task(key, "2026Q3", title=f"task {i}", month="M1"),
            range(10)))

    ids = sorted(r["task"]["id"] for r in results)
    assert ids == [f"DLY-{n:03d}" for n in range(1, 11)]
    assert service.list_tasks(key)["count"] == 10


def test_parallel_update_and_transition_keep_both_writes():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.update_task, key, "DLY-001", "renamed"),
                   pool.submit(service.transition_task, key, "DLY-001", "in_progress")]
        for f in futures:
            f.result()

    task = service.list_tasks(key)["tasks"][0]
    assert task["title"] == "renamed"
    assert task["status"] == "in_progress"
    assert service.validate(key)["ok"]
