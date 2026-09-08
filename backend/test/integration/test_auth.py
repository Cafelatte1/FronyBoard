"""Bearer-auth middleware (FronyAuth delegation) and fauth client tests."""

import json

import pytest

from fronyboard import auth, fauth
from conftest import asgi_request


def _run_middleware(headers: list, path: str = "/mcp", protected: tuple = ("/",),
                    open_paths: tuple = (), resource_metadata_url: str | None = None):
    """Drive the bare middleware (no app behind it beyond a 200 stub)."""

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = auth.BearerAuthMiddleware(inner_app, protected=protected, open_paths=open_paths,
                                           resource_metadata_url=resource_metadata_url)
    return asgi_request(middleware, "POST", path, headers=headers)


def _bearer(token: str) -> list:
    return [(b"authorization", f"Bearer {token}".encode())]


def test_middleware_rejects_missing_or_bad_credential(fake_fauth):
    fake_fauth.keys["pc1"] = "frony_real"
    assert _run_middleware([])[0] == 401
    assert _run_middleware(_bearer("bogus_token"))[0] == 401
    assert _run_middleware([(b"authorization", b"Basic abc")])[0] == 401


def test_middleware_passes_key_and_oauth_verdicts(fake_fauth):
    fake_fauth.keys["pc1"] = "frony_real"
    fake_fauth.oauth["fbat_tok"] = "oauth:Claude:admin"
    assert _run_middleware(_bearer("frony_real"))[0] == 200
    assert _run_middleware(_bearer("fbat_tok"))[0] == 200


def test_middleware_protects_only_listed_prefixes(fake_fauth):
    protected = ("/mcp", "/api")
    assert _run_middleware([], path="/", protected=protected)[0] == 200
    assert _run_middleware([], path="/assets/app.js", protected=protected)[0] == 200
    assert _run_middleware([], path="/api/projects", protected=protected)[0] == 401
    assert _run_middleware([], path="/mcp", protected=protected)[0] == 401
    assert _run_middleware([], path="/api/login", protected=protected,
                           open_paths=("/api/login",))[0] == 200


def test_middleware_answers_503_when_fauth_is_down(fake_fauth):
    fake_fauth.down = True
    status, _, body = _run_middleware(_bearer("frony_real"))
    assert status == 503
    assert "auth service unavailable" in json.loads(body)["error"]


def test_401_on_mcp_advertises_resource_metadata(fake_fauth):
    url = "https://auth.example.ts.net/.well-known/oauth-protected-resource/board/mcp"
    status, headers, _ = _run_middleware([], path="/mcp", resource_metadata_url=url)
    assert status == 401
    assert headers["www-authenticate"] == f'Bearer resource_metadata="{url}"'
    # only /mcp carries the pointer — an /api 401 does not
    status, headers, _ = _run_middleware([], path="/api/projects", resource_metadata_url=url)
    assert status == 401 and "www-authenticate" not in headers


def test_session_tokens_pass_middleware_locally_until_dropped(fake_fauth):
    fake_fauth.down = True  # sessions never touch FronyAuth
    token = auth.create_session()
    assert auth.verify_session(token)
    assert _run_middleware(_bearer(token))[0] == 200
    auth.drop_session(token)
    assert _run_middleware(_bearer(token))[0] == 503  # falls through to fauth, which is down


# -- fauth client: cache and outage behaviour ------------------------------------


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _patch_post(monkeypatch, replies):
    """Replace fauth._post with a scripted responder that counts calls."""
    calls = []

    async def post(path, payload):
        calls.append((path, payload))
        reply = replies[min(len(calls), len(replies)) - 1]
        if reply is None:
            raise fauth.Unavailable("down")
        return _Response(*reply)

    monkeypatch.setattr(fauth, "_post", post)
    return calls


def test_verify_caches_positive_verdicts(monkeypatch):
    calls = _patch_post(monkeypatch, [(200, {"active": True, "type": "key", "caller": "key:pc1",
                                             "expires_at": None})])
    import anyio
    assert anyio.run(fauth.verify, "frony_x") == "key:pc1"
    assert anyio.run(fauth.verify, "frony_x") == "key:pc1"
    assert len(calls) == 1  # second answer came from the cache


def test_verify_caches_negatives_and_serves_stale_on_outage(monkeypatch):
    import anyio
    calls = _patch_post(monkeypatch, [(200, {"active": False}), None])
    assert anyio.run(fauth.verify, "frony_x") is None
    fauth._cache.clear()

    # a cached positive with expired TTL still beats an outage
    calls = _patch_post(monkeypatch, [(200, {"active": True, "type": "key", "caller": "key:pc1",
                                             "expires_at": None}), None])
    assert anyio.run(fauth.verify, "frony_y") == "key:pc1"
    for digest in fauth._cache:
        fauth._cache[digest] = (0.0, fauth._cache[digest][1])  # force-expire
    assert anyio.run(fauth.verify, "frony_y") == "key:pc1"
    assert len(calls) == 2


def test_verify_raises_unavailable_with_no_cache(monkeypatch):
    import anyio
    _patch_post(monkeypatch, [None])
    with pytest.raises(fauth.Unavailable):
        anyio.run(fauth.verify, "frony_x")
