"""FronyBoard read-only web API tests, driven through a bare Starlette app."""

import json

import anyio
import pytest
from starlette.applications import Starlette

from aira import service, web


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
    service.create_epic(key, "2026Q3", goal="MVP core")
    return key


def _get(path, query=""):
    app = Starlette(routes=web.api_routes())
    events = []

    async def send(event):
        events.append(event)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
             "query_string": query.encode(), "headers": [], "scheme": "http",
             "server": ("test", 80), "client": ("test", 1), "root_path": ""}
    anyio.run(lambda: app(scope, receive, send))
    status = next(e["status"] for e in events if e["type"] == "http.response.start")
    body = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
    return status, json.loads(body) if body else None


def test_projects_and_status():
    bootstrap()
    status, body = _get("/api/projects")
    assert status == 200
    assert [p["key"] for p in body["projects"]] == ["DLY"]

    status, body = _get("/api/projects/DLY/status")
    assert status == 200
    assert body["periods"]["2026Q3"]["epics"][0]["id"] == "E1"

    status, body = _get("/api/projects/DLY/roadmap")
    assert status == 200
    assert body["roadmap"]["years"]["2026"]["overview"]["goal"] == "ship it"


def test_tasks_filters_and_cancelled_toggle():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="keep", epic="E1", month="M1")
    service.create_task(key, "2026Q3", title="drop", epic="E1", month="M1")
    service.transition_task(key, "DLY-002", "cancelled", reason="descoped")

    status, body = _get("/api/projects/DLY/tasks")
    assert status == 200
    assert [t["id"] for t in body["tasks"]] == ["DLY-001"]

    status, body = _get("/api/projects/DLY/tasks", query="include_cancelled=true")
    assert body["count"] == 2


def test_unknown_project_is_404():
    status, body = _get("/api/projects/NOPE/status")
    assert status == 404
    assert "error" in body
