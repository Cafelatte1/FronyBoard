"""HTTP bearer auth for the AIRA server — delegation to FronyAuth since AIR-056.

API keys and OAuth tokens are issued and judged by FronyAuth (see fauth.py for
the client and its configuration); aira no longer reads auth.yaml/oauth.yaml.
The only credential that stays local is the dashboard session token, which
lives in this process's memory and never leaves the machine.
"""

from __future__ import annotations

import json
import secrets

from starlette.middleware.cors import CORSMiddleware

from . import fauth, log

# Dashboard sessions are held in memory only — a server restart signs everyone out.
_sessions: dict[str, str] = {}  # token -> username


def create_session(username: str = "admin") -> str:
    token = "fbsession_" + secrets.token_hex(24)
    _sessions[token] = username
    return token


def session_user(token: str | None) -> str | None:
    return _sessions.get(token or "")


def verify_session(token: str | None) -> bool:
    return bool(token) and token in _sessions


def drop_session(token: str | None) -> None:
    _sessions.pop(token or "", None)


def with_mcp_cors(app):
    """Answer browser CORS on /mcp only. claude.ai's web app probes a connector
    from the browser itself, so the preflight must pass without a credential and
    the 401 must be readable (it carries the WWW-Authenticate pointer)."""
    cors = CORSMiddleware(app, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                          allow_headers=["*"], expose_headers=["Mcp-Session-Id", "WWW-Authenticate"])

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            await cors(scope, receive, send)
        else:
            await app(scope, receive, send)
    return wrapped


class BearerAuthMiddleware:
    """Pure ASGI middleware: reject HTTP requests without a valid credential.

    Only paths starting with one of `protected` require a credential (default:
    all) — the FronyBoard static files stay open while /mcp and /api stay keyed.
    `open_paths` are exact-match exceptions inside protected space (the login
    endpoint). A bearer token may be a dashboard session token (checked locally)
    or an API key / OAuth access token (judged by FronyAuth). When FronyAuth is
    unreachable the answer is 503, never 401 — a client must not conclude its
    key was revoked because the auth server blinked.

    `resource_metadata_url` is what a 401 on /mcp advertises via
    WWW-Authenticate (RFC 9728) so OAuth-capable clients know where to start.
    """

    def __init__(self, app, protected: tuple[str, ...] = ("/",),
                 open_paths: tuple[str, ...] = (), resource_metadata_url: str | None = None):
        self.app = app
        self.protected = protected
        self.open_paths = open_paths
        self.resource_metadata_url = resource_metadata_url

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or path in self.open_paths or \
                not any(path.startswith(p) for p in self.protected):
            await self.app(scope, receive, send)
            return
        auth_header = ""
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                auth_header = value.decode("latin-1")
                break
        token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None
        client = scope.get("client") or ("?", 0)
        if verify_session(token):
            caller = f"session:{session_user(token)}"
        else:
            try:
                caller = await fauth.verify(token)
            except fauth.Unavailable as e:
                log.event("ERROR", "auth", "fauth_unavailable", ip=str(client[0]), path=path,
                          error=str(e))
                await self._reject(send, 503, "auth service unavailable — try again shortly")
                return
        if caller is None:
            log.event("WARNING", "auth", "key_rejected", ip=str(client[0]), path=path,
                      prefix=(token or "")[:9] or None)
            headers = []
            if self.resource_metadata_url is not None and path.startswith("/mcp"):
                # RFC 9728 discovery: tells an OAuth-capable client where to start.
                headers.append((b"www-authenticate",
                                f'Bearer resource_metadata="{self.resource_metadata_url}"'.encode()))
            await self._reject(send, 401, "unauthorized — send 'Authorization: Bearer <api key>'",
                               headers)
            return
        # Tag the request so the MCP tool log can name its caller.
        scope.setdefault("state", {})["caller"] = caller
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, status: int, message: str, extra_headers: list | None = None) -> None:
        body = json.dumps({"error": message}).encode()
        headers = [(b"content-type", b"application/json"),
                   (b"content-length", str(len(body)).encode())] + (extra_headers or [])
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
