"""FronyBoard read-only web API tests, driven through a bare Starlette app."""

import json

from starlette.applications import Starlette

from fronyboard import auth, service, web
from conftest import asgi_request, bootstrap


def _request(method, path, query="", body=None, token=None):
    app = Starlette(routes=web.api_routes())
    headers = [(b"authorization", f"Bearer {token}".encode())] if token is not None else []
    status, _, raw = asgi_request(app, method, path, query=query, headers=headers,
                                  json_body=body, scheme="http")
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


def test_board_bundles_everything_the_dashboard_loads(fake_fauth):
    key = bootstrap()
    service.create_task(key, "2026Q3", title="keep", month="M1", content="## objective\nwhy")
    service.create_task(key, "2026Q3", title="gone", month="M1")
    service.transition_task(key, "DLY-002", "cancelled", reason="no")
    status, body = _get("/api/board")
    assert status == 200
    assert set(body) == {"server", "projects", "statuses", "roadmaps", "tasks"}
    assert body["server"]["projects"] == 1 and body["server"]["timezone"]
    assert [p["key"] for p in body["projects"]] == ["DLY"]
    assert body["statuses"]["DLY"]["periods"]["2026Q3"]["months"][0]["id"] == "M1"
    assert body["roadmaps"]["DLY"]["years"]["2026"]["overview"]["goal"] == "ship it"
    assert [t["id"] for t in body["tasks"]["DLY"]] == ["DLY-001", "DLY-002"]  # cancelled included
    assert body["tasks"]["DLY"][0]["content"].startswith("## objective")  # content included
    status, light = _get("/api/board", "content=0")
    assert status == 200 and "content" not in light["tasks"]["DLY"][0]
    assert [t["id"] for t in light["tasks"]["DLY"]] == ["DLY-001", "DLY-002"]


def test_tasks_route_keeps_content_for_the_panel():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="keep", month="M1", content="body")
    status, body = _get("/api/projects/DLY/tasks")
    assert status == 200 and body["tasks"][0]["content"] == "body"


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


def test_login_issues_session_token(fake_fauth):
    fake_fauth.admin = ("admin", "1234")
    status, _ = _request("POST", "/api/login", body={"username": "admin", "password": "no"})
    assert status == 401
    status, body = _request("POST", "/api/login", body={"username": "admin", "password": "1234"})
    assert status == 200
    assert auth.verify_session(body["token"])
    assert body["username"] == "admin"


def test_login_answers_503_when_fauth_is_down(fake_fauth):
    fake_fauth.admin = ("admin", "1234")
    fake_fauth.down = True
    status, body = _request("POST", "/api/login", body={"username": "admin", "password": "1234"})
    assert status == 503
    assert "auth service unavailable" in body["error"]


def test_server_info(fake_fauth):
    bootstrap()
    fake_fauth.keys["pc1"] = "frony_pc1"
    status, body = _get("/api/server")
    assert status == 200
    assert body["version"]
    assert body["started_at"]
    assert body["projects"] == 1
    assert body["open_periods"] == [{"project": "DLY", "period": "2026Q3"}]
    assert body["api_keys"] == 1
    assert isinstance(body["timezone"]["offset_minutes"], int)
    assert body["timezone"]["name"] is None or body["timezone"]["name"].isascii()


def test_server_info_survives_fauth_outage(fake_fauth):
    bootstrap()
    fake_fauth.down = True
    status, body = _get("/api/server")
    assert status == 200  # deploys verify against this route — it must not depend on fauth
    assert body["api_keys"] is None


def test_server_timezone_honours_fronyboard_tz(monkeypatch):
    from fronyboard import web

    monkeypatch.setenv("FRONYBOARD_TZ", "Asia/Seoul")
    assert web._timezone() == {"name": "KST", "offset_minutes": 540}
    monkeypatch.setenv("FRONYBOARD_TZ", "Not/AZone")
    assert isinstance(web._timezone()["offset_minutes"], int)  # falls back, no crash


def test_key_management_requires_dashboard_session(fake_fauth):
    fake_fauth.keys["pc1"] = "frony_pc1"
    status, body = _request("GET", "/api/keys")
    assert status == 403
    status, body = _request("GET", "/api/keys", token="frony_pc1")  # API key is not enough
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
    assert fake_fauth.keys["pc2"] == body["key"]

    status, body = _request("POST", "/api/keys", body={"name": "pc2"}, token=session)
    assert status == 400  # FronyAuth's duplicate 409 maps onto this API's usual 400

    status, body = _request("DELETE", "/api/keys/pc2", token=session)
    assert status == 200
    assert list(fake_fauth.keys) == ["pc1"]

    status, body = _request("DELETE", "/api/keys/pc2", token=session)
    assert status == 404


def test_key_management_answers_503_when_fauth_is_down(fake_fauth):
    session = auth.create_session()
    fake_fauth.down = True
    assert _request("GET", "/api/keys", token=session)[0] == 503
    assert _request("POST", "/api/keys", body={"name": "x"}, token=session)[0] == 503
    assert _request("DELETE", "/api/keys/x", token=session)[0] == 503


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


def test_logout_drops_session(fake_fauth):
    fake_fauth.admin = ("admin", "1234")
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


def test_dashboard_login_locks_after_repeated_failures(fake_fauth):
    fake_fauth.admin = ("admin", "pw")
    for n in range(fake_fauth.limit - 1):
        status, _ = _request("POST", "/api/login", body={"username": "admin", "password": "nope"})
        assert status == 401
    status, _ = _request("POST", "/api/login", body={"username": "admin", "password": "nope"})
    assert status == 429  # the locking strike itself answers 429
    status, body = _request("POST", "/api/login", body={"username": "admin", "password": "pw"})
    assert status == 429 and "too many" in body["error"]
