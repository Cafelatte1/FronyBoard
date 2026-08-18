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


def _request(method, path, query="", body=None, token=None):
    app = Starlette(routes=web.api_routes())
    events = []
    payload = json.dumps(body).encode() if body is not None else b""

    async def send(event):
        events.append(event)

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    headers = [(b"content-type", b"application/json")] if body is not None else []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(),
             "query_string": query.encode(), "scheme": "http", "headers": headers,
             "server": ("test", 80), "client": ("test", 1), "root_path": ""}
    anyio.run(lambda: app(scope, receive, send))
    status = next(e["status"] for e in events if e["type"] == "http.response.start")
    raw = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
    return status, json.loads(raw) if raw else None


def _get(path, query=""):
    return _request("GET", path, query)


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


def test_login_issues_session_token():
    from aira import auth

    auth.set_admin("admin", "1234")
    status, _ = _request("POST", "/api/login", body={"username": "admin", "password": "no"})
    assert status == 401
    status, body = _request("POST", "/api/login", body={"username": "admin", "password": "1234"})
    assert status == 200
    assert auth.verify_session(body["token"])
    assert body["username"] == "admin"


def test_server_info():
    from aira import auth

    bootstrap()
    auth.generate_key("pc1")
    status, body = _get("/api/server")
    assert status == 200
    assert body["version"]
    assert body["started_at"]
    assert body["projects"] == 1
    assert body["open_periods"] == [{"project": "DLY", "period": "2026Q3"}]
    assert body["api_keys"] == 1


def test_key_management_requires_dashboard_session():
    from aira import auth

    api_key = auth.generate_key("pc1")
    status, body = _request("GET", "/api/keys")
    assert status == 403
    status, body = _request("GET", "/api/keys", token=api_key)  # API key is not enough
    assert status == 403

    session = auth.create_session()
    status, body = _request("GET", "/api/keys", token=session)
    assert status == 200
    assert [k["name"] for k in body["keys"]] == ["pc1"]
    assert body["keys"][0]["fingerprint"] and "…" in body["keys"][0]["fingerprint"]
    assert "sha256" not in body["keys"][0]

    status, body = _request("POST", "/api/keys", body={"name": "pc2"}, token=session)
    assert status == 200
    assert body["key"].startswith("aira_")
    assert auth.verify_key(body["key"]) == "pc2"

    status, body = _request("POST", "/api/keys", body={"name": "pc2"}, token=session)
    assert status == 400

    status, body = _request("DELETE", "/api/keys/pc2", token=session)
    assert status == 200
    assert auth.verify_key(body.get("key")) is None
    assert [k["name"] for k in auth.key_info()] == ["pc1"]

    status, body = _request("DELETE", "/api/keys/pc2", token=session)
    assert status == 404


def test_unknown_project_is_404():
    status, body = _get("/api/projects/NOPE/status")
    assert status == 404
    assert "error" in body
