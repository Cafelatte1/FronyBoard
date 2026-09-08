"""MCP tool-surface wiring tests — the glue between the tools and the service layer."""

import pytest

from fronyboard import server, service
from conftest import bootstrap


def test_task_tools_derive_key_from_task_id():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")

    out = server.update_task(task_id="DLY-001", title="renamed")
    assert out["task"]["title"] == "renamed"

    out = server.transition_task(task_id="DLY-001", status="in_progress",
                                 branch="feat/DLY-001/renamed")
    assert out["to"] == "in_progress"

    task = service.list_tasks(key)["tasks"][0]
    assert task["title"] == "renamed"
    assert task["status"] == "in_progress"


def test_task_tools_accept_matching_key_and_reject_mismatch():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x", month="M1")

    out = server.update_task(task_id="DLY-001", title="ok", key="DLY")
    assert out["task"]["title"] == "ok"
    with pytest.raises(service.FronyBoardError, match="does not match"):
        server.update_task(task_id="DLY-001", title="nope", key="AIR")
    with pytest.raises(service.FronyBoardError, match="does not match"):
        server.transition_task(task_id="DLY-001", status="done", key="AIR")
