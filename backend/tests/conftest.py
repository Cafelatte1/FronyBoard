"""Shared fixtures and helpers for the FronyBoard test suite."""

import json
from types import SimpleNamespace
from urllib.parse import urlencode

import anyio
import pytest

from aira import fauth, service


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    fauth.clear_cache()  # verdicts must not leak across tests
    return tmp_path


@pytest.fixture
def fake_fauth(monkeypatch):
    """Stand-in for the FronyAuth server: patches the fauth client's functions
    with an in-memory registry so no HTTP happens. Matches the contract in
    project-auth's docs/introspection.md. `state.down = True` simulates an
    outage; `state.oauth[token] = caller` plants an OAuth verdict."""
    state = SimpleNamespace(keys={}, oauth={}, admin=None, fails={}, limit=5, down=False)

    def _check_up():
        if state.down:
            raise fauth.Unavailable("fauth is down")

    async def verify(token):
        _check_up()
        if not token:
            return None
        for name, key in state.keys.items():
            if key == token:
                return f"key:{name}"
        return state.oauth.get(token)

    async def admin_verify(username, password, client_addr):
        _check_up()
        if state.fails.get(client_addr, 0) >= state.limit:
            return 429, {"error": "locked out", "retry_after_seconds": 60}
        if state.admin == (username, password):
            state.fails.pop(client_addr, None)
            return 200, {"ok": True, "username": username}
        state.fails[client_addr] = state.fails.get(client_addr, 0) + 1
        if state.fails[client_addr] >= state.limit:
            return 429, {"error": "locked out", "retry_after_seconds": 60}
        return 200, {"ok": False, "attempts_left": state.limit - state.fails[client_addr]}

    async def keys():
        _check_up()
        return [{"name": n, "fingerprint": "ab12…cd34", "created_at": "2026-08-31 00:00:00"}
                for n in state.keys]

    async def create_key(name):
        _check_up()
        if name in state.keys:
            return 409, {"error": f"a key named '{name}' already exists — revoke it first"}
        if not name.strip():
            return 400, {"error": "key name must not be empty"}
        token = f"frony_{name}fake"
        state.keys[name] = token
        return 201, {"name": name, "key": token}

    async def delete_key(name):
        _check_up()
        if name not in state.keys:
            return 404, {"error": f"no key named '{name}'"}
        del state.keys[name]
        return 200, {"revoked": name}

    monkeypatch.setattr(fauth, "verify", verify)
    monkeypatch.setattr(fauth, "admin_verify", admin_verify)
    monkeypatch.setattr(fauth, "keys", keys)
    monkeypatch.setattr(fauth, "create_key", create_key)
    monkeypatch.setattr(fauth, "delete_key", delete_key)
    return state


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
