"""OAuth flow for hosted MCP clients: discovery -> register -> login -> token -> /mcp."""

import base64
import hashlib
import html
import json
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlparse

import anyio
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from aira import auth, oauth, store

PUBLIC = "https://board.example.ts.net"
REDIRECT = "https://app.example/cb"


def _app(provider):
    async def mcp_stub(request):
        return JSONResponse({"caller": request.scope["state"]["caller"]})

    inner = Starlette(routes=[*oauth.routes(provider), Route("/mcp", mcp_stub, methods=["POST"])])
    return auth.with_mcp_cors(auth.BearerAuthMiddleware(inner, protected=("/mcp",), oauth=provider))


def _request(app, method, path, query="", headers=None, json_body=None, form=None):
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
             "query_string": query.encode(), "scheme": "https", "headers": hdrs,
             "server": ("test", 443), "client": ("test", 1), "root_path": ""}
    anyio.run(lambda: app(scope, receive, send))
    start = next(e for e in events if e["type"] == "http.response.start")
    out_headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    body = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
    return start["status"], out_headers, body


def _handoff(body):
    """The URL a result page sends the browser to (meta refresh; the link says the same)."""
    m = re.search(r"content='1;url=([^']+)'", body.decode())
    assert m, "no hand-off on the page"
    return html.unescape(m.group(1))


def _json(body):
    return json.loads(body)


def _pkce():
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _bearer(token):
    return [(b"authorization", f"Bearer {token}".encode())]


def _register(app, name="Claude"):
    status, _, body = _request(app, "POST", "/register", json_body={
        "redirect_uris": [REDIRECT], "client_name": name, "token_endpoint_auth_method": "none"})
    assert status == 201, body
    return _json(body)["client_id"]


def _login_url(app, client_id, challenge, state="xyz", **extra):
    status, headers, body = _request(app, "GET", "/authorize", query=urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state, **extra}))
    assert status == 302, body
    return headers["location"]


def _tokens(app, client_id, code, verifier):
    status, _, body = _request(app, "POST", "/token", form={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "code_verifier": verifier})
    assert status == 200, body
    return _json(body)


def test_metadata_points_at_public_url():
    app = _app(oauth.Provider(PUBLIC))
    status, _, body = _request(app, "GET", "/.well-known/oauth-authorization-server")
    assert status == 200
    meta = _json(body)
    assert meta["issuer"] == PUBLIC  # exact string — no trailing slash
    assert meta["registration_endpoint"] == PUBLIC + "/register"
    assert meta["code_challenge_methods_supported"] == ["S256"]

    status, _, body = _request(app, "GET", "/.well-known/oauth-protected-resource/mcp")
    assert status == 200
    assert _json(body)["resource"] == PUBLIC + "/mcp"
    assert _json(body)["authorization_servers"] == [PUBLIC]


def test_mcp_can_sit_under_a_service_prefix():
    """Public layout: the issuer stays at the root, FronyBoard's endpoint moves to
    /board/mcp like any other service's /<name>/mcp. The old /mcp metadata is
    still served for connectors registered before the move."""
    app = _app(oauth.Provider(PUBLIC, "/board/mcp"))
    auth.generate_key("pc1")
    status, headers, _ = _request(app, "POST", "/mcp")
    assert status == 401
    assert headers["www-authenticate"] == \
        f'Bearer resource_metadata="{PUBLIC}/.well-known/oauth-protected-resource/board/mcp"'
    status, _, body = _request(app, "GET", "/.well-known/oauth-protected-resource/board/mcp")
    assert status == 200
    assert _json(body)["resource"] == PUBLIC + "/board/mcp"
    assert _json(body)["authorization_servers"] == [PUBLIC]
    status, _, body = _request(app, "GET", "/.well-known/oauth-protected-resource/mcp")
    assert status == 200 and _json(body)["resource"] == PUBLIC + "/mcp"
    status, _, body = _request(app, "GET", "/.well-known/oauth-authorization-server")
    assert status == 200 and _json(body)["issuer"] == PUBLIC


def test_browser_clients_can_probe_mcp():
    """claude.ai's web app probes the connector from the browser: the preflight
    must pass with no credential, and the 401 must expose its WWW-Authenticate."""
    app = _app(oauth.Provider(PUBLIC))
    auth.generate_key("pc1")
    status, headers, _ = _request(app, "OPTIONS", "/mcp", headers=[
        (b"origin", b"https://claude.ai"), (b"access-control-request-method", b"POST"),
        (b"access-control-request-headers", b"authorization,content-type,mcp-protocol-version")])
    assert status == 200
    assert headers["access-control-allow-origin"] == "*"
    assert "authorization" in headers["access-control-allow-headers"].lower()
    status, headers, _ = _request(app, "POST", "/mcp", headers=[(b"origin", b"https://claude.ai")])
    assert status == 401
    assert headers["access-control-allow-origin"] == "*"
    assert "www-authenticate" in headers["access-control-expose-headers"].lower()
    # the SDK's own CORS on the OAuth routes is left alone — one header, not two
    status, headers, _ = _request(app, "OPTIONS", "/register", headers=[
        (b"origin", b"https://claude.ai"), (b"access-control-request-method", b"POST")])
    assert status == 200 and headers["access-control-allow-origin"] == "*"


def test_unauthenticated_mcp_advertises_resource_metadata():
    app = _app(oauth.Provider(PUBLIC))
    auth.generate_key("pc1")
    status, headers, _ = _request(app, "POST", "/mcp")
    assert status == 401
    assert headers["www-authenticate"] == \
        f'Bearer resource_metadata="{PUBLIC}/.well-known/oauth-protected-resource/mcp"'


def test_full_flow_login_token_refresh_revoke(data_root):
    auth.set_admin("admin", "pw")
    auth.generate_key("pc1")
    provider = oauth.Provider(PUBLIC)
    app = _app(provider)
    client_id = _register(app)
    verifier, challenge = _pkce()

    # /authorize hands the browser to our login page
    login_url = _login_url(app, client_id, challenge)
    assert login_url.startswith(PUBLIC + "/oauth/login?txn=")
    txn = parse_qs(urlparse(login_url).query)["txn"][0]
    status, headers, body = _request(app, "GET", "/oauth/login", query=f"txn={txn}")
    text = body.decode()
    assert status == 200 and "Claude가<br>Frony 연결을 요청합니다" in text
    assert f"txn_{txn[:6]} · client {client_id[:6]} · Claude" in text
    assert headers["cache-control"] == "no-store"

    # wrong password re-renders the form with the attempt count; the right one
    # shows the "connected" screen and hands the browser back with a code
    status, _, body = _request(app, "POST", "/oauth/login",
                               form={"txn": txn, "username": "admin", "password": "nope"})
    assert status == 200 and "아이디 또는 비밀번호가 맞지 않아요. (1/5)" in body.decode()
    status, _, body = _request(app, "POST", "/oauth/login",
                                  form={"txn": txn, "username": "admin", "password": "pw"})
    assert status == 200
    text = body.decode()
    assert "연결 완료" in text and "Claude로 돌아가는 중입니다" in text
    assert "→ app.example/cb?code=…" in text          # the code itself is not on the page
    assert "Claude로 돌아가기" in text
    back = urlparse(_handoff(body))
    assert f"{back.scheme}://{back.netloc}{back.path}" == REDIRECT
    q = parse_qs(back.query)
    assert q["state"] == ["xyz"]
    code = q["code"][0]

    assert q["code"][0] not in text.replace(html.escape(_handoff(body)), "")

    # the txn is single-use
    status, _, body = _request(app, "GET", "/oauth/login", query=f"txn={txn}")
    assert status == 400 and "요청이 만료됐어요" in body.decode()
    assert f"txn_{txn[:6]} · expired" in body.decode()

    # code -> tokens (PKCE checked by the SDK)
    tokens = _tokens(app, client_id, code, verifier)
    assert tokens["access_token"].startswith("fbat_")
    assert tokens["refresh_token"].startswith("fbrt_")
    assert tokens["expires_in"] == oauth.ACCESS_TTL
    status, _, body = _request(app, "POST", "/token", form={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "code_verifier": verifier})
    assert status == 400 and _json(body)["error"] == "invalid_grant"  # code is single-use

    # the access token opens /mcp and names its caller
    status, _, body = _request(app, "POST", "/mcp", headers=_bearer(tokens["access_token"]))
    assert status == 200
    assert _json(body)["caller"] == "oauth:Claude:admin"
    assert _request(app, "POST", "/mcp", headers=_bearer("fbat_bogus"))[0] == 401

    # refresh rotates both tokens
    status, _, body = _request(app, "POST", "/token", form={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
        "client_id": client_id})
    assert status == 200, body
    fresh = _json(body)
    assert fresh["access_token"] != tokens["access_token"]
    assert _request(app, "POST", "/mcp", headers=_bearer(tokens["access_token"]))[0] == 401
    assert _request(app, "POST", "/mcp", headers=_bearer(fresh["access_token"]))[0] == 200
    status, _, body = _request(app, "POST", "/token", form={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
        "client_id": client_id})
    assert status == 400 and _json(body)["error"] == "invalid_grant"

    # revoking the access token drops the whole grant
    status, _, _ = _request(app, "POST", "/revoke", form={  # SDK model wants the key present
        "token": fresh["access_token"], "client_id": client_id, "client_secret": ""})
    assert status == 200
    assert _request(app, "POST", "/mcp", headers=_bearer(fresh["access_token"]))[0] == 401
    status, _, body = _request(app, "POST", "/token", form={
        "grant_type": "refresh_token", "refresh_token": fresh["refresh_token"],
        "client_id": client_id})
    assert status == 400

    # only hashes reach disk — in the Frony-wide store, not FronyBoard's data root
    text = (data_root / "frony" / "oauth.yaml").read_text(encoding="utf-8")
    for secret in (tokens["access_token"], tokens["refresh_token"],
                   fresh["access_token"], fresh["refresh_token"]):
        assert secret not in text
    assert "Claude" in text
    assert not (data_root / "oauth.yaml").exists()


def _approve(app, client_id, verifier, challenge, **extra):
    """Run the browser leg for a registered client and return the token response."""
    txn = parse_qs(urlparse(_login_url(app, client_id, challenge, **extra)).query)["txn"][0]
    status, _, body = _request(app, "POST", "/oauth/login",
                               form={"txn": txn, "username": "admin", "password": "pw"})
    assert status == 200
    code = parse_qs(urlparse(_handoff(body)).query)["code"][0]
    return _tokens(app, client_id, code, verifier)


def test_tokens_are_issued_for_other_frony_services_too(data_root):
    """An app connecting to a sibling service (its own Funnel path, this issuer)
    sends that service as the RFC 8707 resource; the token must still be minted
    and land in the shared store, where the sibling verifies it by hash."""
    auth.set_admin("admin", "pw")
    auth.generate_key("pc1")
    app = _app(oauth.Provider(PUBLIC))
    client_id = _register(app, name="ChatGPT")
    verifier, challenge = _pkce()
    tokens = _approve(app, client_id, verifier, challenge, resource=PUBLIC + "/cache/mcp")
    assert tokens["access_token"].startswith("fbat_")
    digest = hashlib.sha256(tokens["access_token"].encode()).hexdigest()
    grants = store.load_yaml(data_root / "frony" / "oauth.yaml")["grants"]
    assert [g["access_sha256"] for g in grants] == [digest]
    assert grants[0]["subject"] == "admin"


def test_legacy_store_moves_to_the_shared_location(data_root):
    auth.set_admin("admin", "pw")
    auth.generate_key("pc1")
    legacy = data_root / "oauth.yaml"
    store.save_yaml(legacy, {"clients": {"c1": {"client_id": "c1", "client_name": "Old", "redirect_uris": [REDIRECT],
                                                "token_endpoint_auth_method": "none"}}, "grants": []})
    app = _app(oauth.Provider(PUBLIC))
    verifier, challenge = _pkce()
    tokens = _approve(app, "c1", verifier, challenge)
    assert not legacy.exists()
    assert "Old" in (data_root / "frony" / "oauth.yaml").read_text(encoding="utf-8")
    assert _request(app, "POST", "/mcp", headers=_bearer(tokens["access_token"]))[0] == 200


def test_api_keys_still_work_next_to_oauth():
    token = auth.generate_key("pc1")
    app = _app(oauth.Provider(PUBLIC))
    status, _, body = _request(app, "POST", "/mcp", headers=_bearer(token))
    assert status == 200 and _json(body)["caller"] == "key:pc1"


def test_denying_sends_the_app_access_denied(data_root):
    auth.set_admin("admin", "pw")
    provider = oauth.Provider(PUBLIC)
    app = _app(provider)
    client_id = _register(app)
    _, challenge = _pkce()
    txn = parse_qs(urlparse(_login_url(app, client_id, challenge)).query)["txn"][0]
    status, _, body = _request(app, "POST", "/oauth/deny", form={"txn": txn})
    assert status == 200 and "연결을 거부했습니다" in body.decode()
    back = urlparse(_handoff(body))
    assert f"{back.scheme}://{back.netloc}{back.path}" == REDIRECT
    assert parse_qs(back.query) == {"error": ["access_denied"], "state": ["xyz"]}
    # the request is gone: no login, no second deny
    assert _request(app, "GET", "/oauth/login", query=f"txn={txn}")[0] == 400
    assert _request(app, "POST", "/oauth/deny", form={"txn": txn})[0] == 400
    assert not (data_root / "frony" / "oauth.yaml").exists() or \
        store.load_yaml(data_root / "frony" / "oauth.yaml").get("grants", []) == []


def test_login_locks_after_repeated_failures():
    auth.set_admin("admin", "pw")
    provider = oauth.Provider(PUBLIC)
    app = _app(provider)
    client_id = _register(app)
    _, challenge = _pkce()
    txn = parse_qs(urlparse(_login_url(app, client_id, challenge)).query)["txn"][0]
    limit = auth.login_throttle.limit
    for n in range(1, limit):
        status, _, body = _request(app, "POST", "/oauth/login",
                                   form={"txn": txn, "username": "admin", "password": "nope"})
        assert status == 200 and f"({n}/{limit})" in body.decode()
    # the last strike locks right away, and even the right password is refused after that
    status, _, body = _request(app, "POST", "/oauth/login",
                               form={"txn": txn, "username": "admin", "password": "nope"})
    assert status == 429 and f"로그인 실패가 {limit}회에 도달했습니다" in body.decode()
    status, _, body = _request(app, "POST", "/oauth/login",
                               form={"txn": txn, "username": "admin", "password": "pw"})
    assert status == 429 and f"HTTP 429 · 15분 / {limit}회 제한" in body.decode()


def test_public_url_must_be_https():
    try:
        oauth.Provider("http://board.example.ts.net")
    except ValueError as e:
        assert "HTTPS" in str(e)
    else:
        raise AssertionError("http public url accepted")
    oauth.Provider("http://127.0.0.1:8642")  # loopback is allowed for local testing
