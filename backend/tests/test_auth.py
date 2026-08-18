"""API key management and bearer-auth middleware tests."""

import anyio
import pytest

from aira import auth


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    return tmp_path


def test_keygen_and_verify_roundtrip():
    assert not auth.has_keys()
    token = auth.generate_key("pc1")
    assert token.startswith("aira_")
    assert auth.has_keys()
    assert auth.verify_key(token) == "pc1"
    assert auth.verify_key("aira_wrong") is None
    assert auth.verify_key(None) is None
    assert auth.verify_key("") is None


def test_keygen_rejects_duplicates_and_stores_only_hash(data_root):
    token = auth.generate_key("pc1")
    with pytest.raises(ValueError, match="already exists"):
        auth.generate_key("pc1")
    assert token not in (data_root / "auth.yaml").read_text(encoding="utf-8")


def _run_middleware(headers: list, path: str = "/mcp",
                    protected: tuple = ("/",), open_paths: tuple = ()) -> int:
    """Drive the ASGI middleware with a minimal http scope; return the response status."""

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    events = []

    async def send(event):
        events.append(event)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "POST", "path": path, "headers": headers}
    middleware = auth.BearerAuthMiddleware(inner_app, protected=protected, open_paths=open_paths)
    anyio.run(lambda: middleware(scope, receive, send))
    return next(e["status"] for e in events if e["type"] == "http.response.start")


def test_middleware_rejects_missing_or_bad_key():
    auth.generate_key("pc1")
    assert _run_middleware([]) == 401
    assert _run_middleware([(b"authorization", b"Bearer aira_bogus")]) == 401
    assert _run_middleware([(b"authorization", b"Basic abc")]) == 401


def test_middleware_passes_valid_key():
    token = auth.generate_key("pc1")
    assert _run_middleware([(b"authorization", f"Bearer {token}".encode())]) == 200


def test_middleware_protects_only_listed_prefixes():
    auth.generate_key("pc1")
    protected = ("/mcp", "/api")
    assert _run_middleware([], path="/", protected=protected) == 200
    assert _run_middleware([], path="/assets/app.js", protected=protected) == 200
    assert _run_middleware([], path="/api/projects", protected=protected) == 401
    assert _run_middleware([], path="/mcp", protected=protected) == 401
    assert _run_middleware([], path="/api/login", protected=protected,
                           open_paths=("/api/login",)) == 200


def test_admin_roundtrip_and_hash_only(data_root):
    auth.set_admin("admin", "1234")
    assert auth.verify_admin("admin", "1234")
    assert not auth.verify_admin("admin", "wrong")
    assert not auth.verify_admin("other", "1234")
    assert "1234" not in (data_root / "auth.yaml").read_text(encoding="utf-8")
    auth.generate_key("pc1")  # must not wipe the admin entry
    assert auth.verify_admin("admin", "1234")


def test_session_tokens_pass_middleware_until_dropped():
    auth.generate_key("pc1")
    token = auth.create_session()
    assert auth.verify_session(token)
    assert _run_middleware([(b"authorization", f"Bearer {token}".encode())]) == 200
    auth.drop_session(token)
    assert _run_middleware([(b"authorization", f"Bearer {token}".encode())]) == 401
