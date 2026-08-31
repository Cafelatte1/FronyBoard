"""Shared fixtures and helpers for the FronyBoard test suite."""

import json
from urllib.parse import urlencode

import anyio
import pytest

from aira import auth, service


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRONY_AUTH_FILE", str(tmp_path / "frony" / "auth.yaml"))
    monkeypatch.setenv("FRONY_OAUTH_FILE", str(tmp_path / "frony" / "oauth.yaml"))
    monkeypatch.setattr(auth, "login_throttle", auth.LoginThrottle())  # lockouts must not leak across tests
    return tmp_path


def bootstrap(key="DLY"):
    """Create a project with an open 2026Q3 period and an active M1 month."""
    service.create_project(key, name="Dailying")
    service.set_overview(key, "2026", goal="ship it", now="build core",
                         next_="validate habit", later="expand")
    service.upsert_milestone(key, "2026", "Q3", goal="MVP", status="planned")
    service.open_period(key, "2026Q3")
    service.upsert_month(key, "2026Q3", "M1", month="2026-07", goal="core", status="active")
    return key


def asgi_request(app, method, path, query="", headers=None, json_body=None, form=None,
                 scheme="https"):
    """Drive an ASGI app through one http request; return (status, headers, body)."""
    events = []
    hdrs = list(headers or [])
    if json_body is not None:
        payload = json.dumps(json_body).encode()
        hdrs.append((b"content-type", b"application/json"))
    elif form is not None:
        payload = urlencode(form).encode()
        hdrs.append((b"content-type", b"application/x-www-form-urlencoded"))
    else:
        payload = b""
    hdrs.append((b"content-length", str(len(payload)).encode()))

    async def send(event):
        events.append(event)

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(),
             "query_string": query.encode(), "scheme": scheme, "headers": hdrs,
             "server": ("test", 443 if scheme == "https" else 80), "client": ("test", 1),
             "root_path": ""}
    anyio.run(lambda: app(scope, receive, send))
    start = next(e for e in events if e["type"] == "http.response.start")
    out_headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    body = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
    return start["status"], out_headers, body
