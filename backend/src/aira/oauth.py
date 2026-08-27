"""OAuth 2.1 authorization server for hosted MCP clients (Claude / ChatGPT connectors).

Those clients cannot attach a static API key: they discover this server's OAuth
metadata, register themselves (RFC 7591), send the user through /oauth/login
(the dashboard admin credential) and exchange the resulting code for tokens.
The protocol endpoints (/.well-known/*, /register, /authorize, /token, /revoke)
are the MCP SDK's; this module supplies the provider behind them — storage,
the login page, token minting — and is only mounted when `aira serve` has a
public URL.

State lives in the Frony-wide `<Frony root>/oauth.yaml` (override with
FRONY_OAUTH_FILE) rather than FronyBoard's data root, because the tokens are
not FronyBoard-only: this is the authorization server for every Frony service
on the machine. Another service exposed through Funnel needs no OAuth code of
its own — it points its protected-resource metadata at this issuer and checks
sha256(bearer) against the `grants` below, the same way API keys are shared
through auth.yaml. A file from before the shared location existed is moved over
on first read.

    clients: {client_id: <RFC 7591 client record; the secret stays in clear
                          because the SDK compares it on /token>}
    grants:  [{access_sha256, refresh_sha256, client_id, subject, scopes,
               access_expires_at, refresh_expires_at, created_at}]

Tokens are stored as hashes only, like API keys. Pending logins and
authorization codes are held in memory for minutes; a restart mid-login just
restarts the login.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, RefreshToken, construct_redirect_uri,
)
from mcp.server.auth.routes import (
    build_resource_metadata_url, create_auth_routes, create_protected_resource_routes,
    validate_issuer_url,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.routing import Route

from . import auth, log, oauth_pages, store

ACCESS_TTL = 24 * 3600          # access token lifetime (s)
REFRESH_TTL = 90 * 24 * 3600    # refresh token lifetime (s) — the app re-logs in after that
CODE_TTL = 5 * 60               # authorization code lifetime (s)
LOGIN_TTL = 10 * 60             # how long the login page stays valid (s)


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def oauth_path() -> Path:
    """The Frony-wide token store, readable by every service that accepts fbat_ tokens."""
    env = os.environ.get("FRONY_OAUTH_FILE")
    return Path(env) if env else store.frony_root() / "oauth.yaml"


class Provider:
    """The MCP SDK's OAuthAuthorizationServerProvider, backed by oauth.yaml."""

    def __init__(self, public_url: str, mcp_path: str = "/mcp"):
        """`public_url` is the issuer — the root every Frony service points its
        clients at. `mcp_path` is where FronyBoard's own MCP endpoint sits under
        it on the Funnel (`/board/mcp`; services get sibling prefixes)."""
        self.public_url = public_url.rstrip("/")
        self.mcp_path = "/" + mcp_path.strip("/")
        # AuthSettings keeps a path-less URL slash-free; RFC 8414 clients compare the
        # issuer string exactly, so a bare AnyHttpUrl (which appends "/") would not do.
        self.urls = AuthSettings(issuer_url=self.public_url,
                                 resource_server_url=self.public_url + self.mcp_path)
        validate_issuer_url(self.urls.issuer_url)
        self.resource_metadata_url = str(build_resource_metadata_url(self.urls.resource_server_url))
        self._logins: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams, float]] = {}
        self._codes: dict[str, AuthorizationCode] = {}

    # -- storage -----------------------------------------------------------------

    def _path(self):
        path = oauth_path()
        legacy = store.data_root() / "oauth.yaml"
        if not path.exists() and legacy.exists():
            # One-time move of the store from before it was shared across services.
            path.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(path)
            log.event("INFO", "auth", "oauth_migrated", to=str(path))
        return path

    def _load(self) -> dict:
        path = self._path()
        data = (store.load_yaml(path) or {}) if path.exists() else {}
        data.setdefault("clients", {})
        data.setdefault("grants", [])
        return data

    def _save(self, data: dict) -> None:
        now = time.time()
        data["grants"] = [g for g in data["grants"] if g["refresh_expires_at"] > now]
        store.save_yaml(self._path(), data)

    def _grant(self, field: str, token: str) -> dict | None:
        digest = _sha(token)
        for g in self._load()["grants"]:
            if secrets.compare_digest(digest, str(g.get(field, ""))):
                return g
        return None

    # -- clients -----------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        rec = self._load()["clients"].get(client_id)
        return OAuthClientInformationFull.model_validate(rec) if rec else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        data = self._load()
        data["clients"][client_info.client_id] = client_info.model_dump(mode="json", exclude_none=True)
        self._save(data)
        log.event("INFO", "auth", "oauth_client_registered", client=client_info.client_name,
                  client_id=client_info.client_id)

    def _client_label(self, client_id: str) -> str:
        rec = self._load()["clients"].get(client_id) or {}
        return rec.get("client_name") or client_id[:8]

    # -- authorization -----------------------------------------------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        now = time.time()
        self._logins = {k: v for k, v in self._logins.items() if v[2] > now}
        txn = secrets.token_urlsafe(16)
        self._logins[txn] = (client, params, now + LOGIN_TTL)
        return f"{self.public_url}/oauth/login?{urlencode({'txn': txn})}"

    def pending_client(self, txn: str | None) -> OAuthClientInformationFull | None:
        entry = self._logins.get(txn or "")
        return entry[0] if entry and entry[2] > time.time() else None

    def complete_login(self, txn: str, username: str, password: str) -> str | None:
        """Check the credential for a pending login; return the app's redirect URL
        (carrying the authorization code) on success, None on a bad credential."""
        client = self.pending_client(txn)
        if client is None:
            raise LookupError("login request expired")
        if not auth.verify_admin(username, password):
            return None
        _, params, _ = self._logins.pop(txn)
        code = secrets.token_urlsafe(32)
        self._codes = {k: v for k, v in self._codes.items() if v.expires_at > time.time()}
        self._codes[code] = AuthorizationCode(
            code=code, scopes=params.scopes or [], expires_at=time.time() + CODE_TTL,
            client_id=client.client_id, code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject=username.strip(),
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    def deny_login(self, txn: str) -> str:
        """Drop a pending login; return the app's redirect URL carrying access_denied."""
        if self.pending_client(txn) is None:
            raise LookupError("login request expired")
        _, params, _ = self._logins.pop(txn)
        return construct_redirect_uri(str(params.redirect_uri), error="access_denied", state=params.state)

    async def load_authorization_code(self, client, authorization_code: str) -> AuthorizationCode | None:
        code = self._codes.get(authorization_code)
        return code if code and code.expires_at > time.time() else None

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        self._codes.pop(authorization_code.code, None)
        return self._issue(client.client_id, authorization_code.subject, authorization_code.scopes)

    # -- tokens ------------------------------------------------------------------

    def _issue(self, client_id: str, subject: str | None, scopes: list[str],
               replace: str | None = None) -> OAuthToken:
        access = "fbat_" + secrets.token_hex(24)
        refresh = "fbrt_" + secrets.token_hex(24)
        now = int(time.time())
        data = self._load()
        if replace is not None:
            data["grants"] = [g for g in data["grants"] if g["refresh_sha256"] != replace]
        data["grants"].append({
            "access_sha256": _sha(access), "refresh_sha256": _sha(refresh),
            "client_id": client_id, "subject": subject, "scopes": list(scopes),
            "access_expires_at": now + ACCESS_TTL, "refresh_expires_at": now + REFRESH_TTL,
            "created_at": store.now(),
        })
        self._save(data)
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL,
                          scope=" ".join(scopes) or None, refresh_token=refresh)

    async def load_refresh_token(self, client, refresh_token: str) -> RefreshToken | None:
        g = self._grant("refresh_sha256", refresh_token)
        if g is None:
            return None
        return RefreshToken(token=refresh_token, client_id=g["client_id"], scopes=g["scopes"],
                            expires_at=g["refresh_expires_at"], subject=g.get("subject"))

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        return self._issue(client.client_id, refresh_token.subject, scopes,
                           replace=_sha(refresh_token.token))

    async def load_access_token(self, token: str) -> AccessToken | None:
        g = self._grant("access_sha256", token)
        if g is None or g["access_expires_at"] <= time.time():
            return None
        return AccessToken(token=token, client_id=g["client_id"], scopes=g["scopes"],
                           expires_at=g["access_expires_at"], subject=g.get("subject"))

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        digest = _sha(token.token)
        data = self._load()
        data["grants"] = [g for g in data["grants"]
                          if digest not in (g["access_sha256"], g["refresh_sha256"])]
        self._save(data)

    def caller(self, token: str | None) -> str | None:
        """Who a bearer access token stands for (for the request log), or None."""
        if not token or not token.startswith("fbat_"):
            return None
        g = self._grant("access_sha256", token)
        if g is None or g["access_expires_at"] <= time.time():
            return None
        return f"oauth:{self._client_label(g['client_id'])}:{g.get('subject')}"


def routes(provider: Provider) -> list[Route]:
    """The SDK's OAuth endpoints plus the login page."""
    throttle = auth.login_throttle

    def who(txn):
        client = provider.pending_client(txn)
        return (client.client_id, client.client_name or client.client_id[:8]) if client else (None, None)

    def expired(txn):
        return oauth_pages.result_page(
            "expired", txn, None, None, "요청이 만료됐어요",
            "앱에서 연결을 다시 시도하면 새 요청이 만들어집니다.", f"txn_{txn[:6]} · expired", 400)

    def locked(txn):
        return oauth_pages.result_page(
            "locked", txn, *who(txn), "잠시 후 다시 시도하세요",
            f"로그인 실패가 {throttle.limit}회에 도달했습니다. {throttle.window // 60}분 뒤에 다시 승인할 수 있습니다.",
            f"HTTP 429 · {throttle.window // 60}분 / {throttle.limit}회 제한", 429)

    async def login_get(request):
        txn = request.query_params.get("txn", "")
        client_id, name = who(txn)
        return oauth_pages.form_page(txn, client_id, name) if client_id else expired(txn)

    async def login_post(request):
        form = await request.form()
        txn = str(form.get("txn", ""))
        username = str(form.get("username", ""))
        ip = request.client.host if request.client else None
        if throttle.blocked(ip):
            return locked(txn)
        client_id, name = who(txn)
        try:
            target = provider.complete_login(txn, username, str(form.get("password", "")))
        except LookupError:
            return expired(txn)
        if target is None:
            throttle.fail(ip)
            log.event("WARNING", "auth", "oauth_login_failed", user=username, ip=ip)
            if throttle.blocked(ip):
                return locked(txn)
            return oauth_pages.form_page(
                txn, client_id, name,
                f"아이디 또는 비밀번호가 맞지 않아요. ({throttle.count(ip)}/{throttle.limit})")
        throttle.clear(ip)
        log.event("INFO", "auth", "oauth_login_ok", user=username, ip=ip)
        return oauth_pages.result_page(
            "done", txn, client_id, name, "연결 완료",
            f"{name}{oauth_pages.ro(name)} 돌아가는 중입니다. 이 창은 닫아도 됩니다.",
            oauth_pages.redirect_detail(target), redirect=target)

    async def deny_post(request):
        form = await request.form()
        txn = str(form.get("txn", ""))
        client_id, name = who(txn)
        try:
            target = provider.deny_login(txn)
        except LookupError:
            return expired(txn)
        log.event("INFO", "auth", "oauth_login_denied", client=name)
        return oauth_pages.result_page(
            "denied", txn, client_id, name, "연결을 거부했습니다", "앱에는 아무 권한도 발급되지 않았습니다.",
            "error=access_denied", redirect=target)

    issuer = provider.urls.issuer_url
    return [
        *create_auth_routes(
            provider, issuer_url=issuer,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
        *[route
          for path in {provider.mcp_path, "/mcp"}  # "/mcp" stays discoverable for connectors added before the prefix
          for route in create_protected_resource_routes(
              resource_url=AuthSettings(issuer_url=issuer, resource_server_url=provider.public_url + path).resource_server_url,
              authorization_servers=[issuer], resource_name="FronyBoard")],
        Route("/oauth/login", login_get, methods=["GET"]),
        Route("/oauth/login", login_post, methods=["POST"]),
        Route("/oauth/deny", deny_post, methods=["POST"]),
    ]
