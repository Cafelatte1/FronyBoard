"""FronyBoard read-only web API tests, driven through a bare Starlette app."""

import json

import anyio
from starlette.applications import Starlette

from aira import auth, service, web
from conftest import bootstrap


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
    assert body["periods"]["2026Q3"]["months"][0]["id"] == "M1"

    status, body = _get("/api/projects/DLY/roadmap")
    assert status == 200
    assert body["roadmap"]["years"]["2026"]["overview"]["goal"] == "ship it"


def test_tasks_filters_and_cancelled_toggle():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="keep", month="M1")
    service.create_task(key, "2026Q3", title="drop", month="M1")
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
    assert isinstance(body["timezone"]["offset_minutes"], int)
    assert body["timezone"]["name"] is None or body["timezone"]["name"].isascii()


def test_server_timezone_honours_aira_tz(monkeypatch):
    from aira import web

    monkeypatch.setenv("AIRA_TZ", "Asia/Seoul")
    assert web._timezone() == {"name": "KST", "offset_minutes": 540}
    monkeypatch.setenv("AIRA_TZ", "Not/AZone")
    assert isinstance(web._timezone()["offset_minutes"], int)  # falls back, no crash


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
    assert body["key"].startswith("frony_")
    assert auth.verify_key(body["key"]) == "pc2"

    status, body = _request("POST", "/api/keys", body={"name": "pc2"}, token=session)
    assert status == 400

    status, body = _request("DELETE", "/api/keys/pc2", token=session)
    assert status == 200
    assert auth.verify_key(body.get("key")) is None
    assert [k["name"] for k in auth.key_info()] == ["pc1"]

    status, body = _request("DELETE", "/api/keys/pc2", token=session)
    assert status == 404


def test_tasks_period_status_month_filters():
    key = bootstrap()
    service.upsert_month(key, "2026Q3", "M2", month="2026-08", goal="polish", status="planned")
    service.create_task(key, "2026Q3", title="a", month="M1")
    service.create_task(key, "2026Q3", title="b", month="M2")
    service.transition_task(key, "DLY-001", "in_progress")

    status, body = _get("/api/projects/DLY/tasks", query="period=2026Q3")
    assert status == 200
    assert body["count"] == 2
    _, body = _get("/api/projects/DLY/tasks", query="status=in_progress")
    assert [t["id"] for t in body["tasks"]] == ["DLY-001"]
    _, body = _get("/api/projects/DLY/tasks", query="month=M2")
    assert [t["id"] for t in body["tasks"]] == ["DLY-002"]
    status, body = _get("/api/projects/DLY/tasks", query="period=1999Q1")
    assert status == 400


def test_logout_drops_session():
    from aira import auth

    auth.set_admin("admin", "1234")
    _, body = _request("POST", "/api/login", body={"username": "admin", "password": "1234"})
    token = body["token"]
    assert auth.verify_session(token)
    status, body = _request("POST", "/api/logout", token=token)
    assert status == 200
    assert not auth.verify_session(token)


def test_unknown_project_is_404():
    status, body = _get("/api/projects/NOPE/status")
    assert status == 404
    assert "error" in body


def test_login_locks_after_repeated_failures():
    auth.set_admin("admin", "pw")
    for _ in range(auth.login_throttle.limit):
        status, _ = _request("POST", "/api/login", body={"username": "admin", "password": "nope"})
        assert status == 401
    status, body = _request("POST", "/api/login", body={"username": "admin", "password": "pw"})
    assert status == 429 and "too many" in body["error"]
