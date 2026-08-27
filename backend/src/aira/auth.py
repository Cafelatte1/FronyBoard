"""API key management and HTTP bearer auth for the AIRA server.

API keys are issued per device and shared by every Frony service on the home
server, so they live in the Frony-wide registry `<Frony root>/auth.yaml`
(override with FRONY_AUTH_FILE), not in FronyBoard's own data root:

    keys:
    - name: pc1
      sha256: <hex digest of the key>
      created_at: 2026-08-17 12:00:00

Only the SHA-256 digest is stored — the key itself is shown once at generation
(`aira keygen <name>`) and sent by clients as `Authorization: Bearer <key>`.
Revoke a key by deleting its entry. Any other service verifies the same way:
sha256(bearer) against this list.

FronyBoard-only credentials (the dashboard admin) stay in `<data root>/auth.yaml`.
Keys found there from before the shared registry existed are moved over on
first use.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from starlette.middleware.cors import CORSMiddleware

from . import log, store


def _auth_path():
    """FronyBoard's own credential file (dashboard admin)."""
    return store.data_root() / "auth.yaml"


def keys_path():
    """The Frony-wide API key registry."""
    env = os.environ.get("FRONY_AUTH_FILE")
    return Path(env) if env else store.frony_root() / "auth.yaml"


def _read(path) -> dict:
    if not path.exists():
        return {}
    return store.load_yaml(path) or {}


def _load_auth() -> dict:
    return _read(_auth_path())


def _load_keys() -> list[dict]:
    registry = _read(keys_path())
    if "keys" not in registry:
        legacy = _load_auth()
        if legacy.get("keys"):
            # One-time move of keys issued before the shared registry existed.
            _save_keys(legacy.pop("keys"))
            store.save_yaml(_auth_path(), legacy)
            log.event("INFO", "auth", "keys_migrated", to=str(keys_path()))
            return _read(keys_path()).get("keys") or []
    return registry.get("keys") or []


def _save_keys(keys: list[dict]) -> None:
    data = _read(keys_path())
    data["keys"] = keys
    store.save_yaml(keys_path(), data)


def has_keys() -> bool:
    return bool(_load_keys())


def generate_key(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("key name must not be empty")
    name = name.strip()
    keys = _load_keys()
    if any(k.get("name") == name for k in keys):
        raise ValueError(f"a key named '{name}' already exists — revoke it first")
    token = "frony_" + secrets.token_hex(24)
    keys.append({
        "name": name,
        "sha256": hashlib.sha256(token.encode()).hexdigest(),
        "created_at": store.now(),
    })
    _save_keys(keys)
    return token


def key_info() -> list[dict]:
    """Public view of the issued keys — name, hash fingerprint, created_at. Never the key."""
    out = []
    for k in _load_keys():
        digest = str(k.get("sha256", ""))
        out.append({
            "name": k.get("name"),
            "fingerprint": f"{digest[:4]}…{digest[-4:]}" if digest else None,
            "created_at": str(k.get("created_at", "")),
        })
    return out


def revoke_key(name: str) -> None:
    keys = _load_keys()
    kept = [k for k in keys if k.get("name") != name]
    if len(kept) == len(keys):
        raise FileNotFoundError(f"no key named '{name}'")
    _save_keys(kept)


def set_admin(username: str, password: str) -> None:
    """Set (or replace) the dashboard admin credential — hash only, like API keys."""
    if not username or not username.strip() or not password:
        raise ValueError("admin username and password must not be empty")
    salt = secrets.token_hex(8)
    data = _load_auth()
    data["admin"] = {
        "username": username.strip(),
        "salt": salt,
        "sha256": hashlib.sha256((salt + password).encode()).hexdigest(),
        "created_at": store.now(),
    }
    store.save_yaml(_auth_path(), data)


def verify_admin(username: str, password: str) -> bool:
    admin = _load_auth().get("admin") or {}
    if not admin or username != admin.get("username"):
        return False
    digest = hashlib.sha256((str(admin.get("salt", "")) + password).encode()).hexdigest()
    return secrets.compare_digest(digest, str(admin.get("sha256", "")))


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


class LoginThrottle:
    """Lock an address out of password login after repeated failures.

    Counted per client address; behind a proxy (Tailscale Funnel) all public
    traffic shares one address and so one lock — that fails closed, which is
    the intent."""

    def __init__(self, limit: int = 5, window: int = 15 * 60):
        self.limit = limit
        self.window = window
        self._fails: dict[str, list[float]] = {}

    def _recent(self, ip: str | None) -> list[float]:
        cutoff = time.time() - self.window
        recent = [t for t in self._fails.get(ip or "?", []) if t > cutoff]
        self._fails[ip or "?"] = recent
        return recent

    def blocked(self, ip: str | None) -> bool:
        return len(self._recent(ip)) >= self.limit

    def fail(self, ip: str | None) -> None:
        self._recent(ip).append(time.time())

    def clear(self, ip: str | None) -> None:
        self._fails.pop(ip or "?", None)


login_throttle = LoginThrottle()


def verify_key(token: str | None) -> str | None:
    """Return the key's name if the token is valid, else None."""
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    for k in _load_keys():
        if secrets.compare_digest(digest, str(k.get("sha256", ""))):
            return k.get("name")
    return None


def with_mcp_cors(app):
    """Answer browser CORS on /mcp only. claude.ai's web app probes a connector
    from the browser itself, so the preflight must pass without a credential and
    the 401 must be readable (it carries the WWW-Authenticate pointer). The SDK's
    OAuth routes already wrap themselves in CORS — wrapping the whole app would
    double their headers, which browsers reject."""
    cors = CORSMiddleware(app, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                          allow_headers=["*"], expose_headers=["Mcp-Session-Id", "WWW-Authenticate"])

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            await cors(scope, receive, send)
        else:
            await app(scope, receive, send)
    return wrapped


class BearerAuthMiddleware:
    """Pure ASGI middleware: reject HTTP requests without a valid API key.

    Only paths starting with one of `protected` require a credential (default:
    all) — the FronyBoard static files stay open while /mcp and /api stay keyed.
    `open_paths` are exact-match exceptions inside protected space (the login
    endpoint). A bearer token may be an API key, a dashboard session token or —
    when an `oauth` provider is given — an OAuth access token it issued.
    """

    def __init__(self, app, protected: tuple[str, ...] = ("/",),
                 open_paths: tuple[str, ...] = (), oauth=None):
        self.app = app
        self.protected = protected
        self.open_paths = open_paths
        self.oauth = oauth

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
        caller = self._caller(token)
        if caller is None:
            client = scope.get("client") or ("?", 0)
            log.event("WARNING", "auth", "key_rejected", ip=str(client[0]), path=path,
                      prefix=(token or "")[:9] or None)
            body = json.dumps({"error": "unauthorized — send 'Authorization: Bearer <api key>'"}).encode()
            headers = [(b"content-type", b"application/json"),
                       (b"content-length", str(len(body)).encode())]
            if self.oauth is not None and path.startswith("/mcp"):
                # RFC 9728 discovery: tells an OAuth-capable client where to start.
                headers.append((b"www-authenticate",
                                f'Bearer resource_metadata="{self.oauth.resource_metadata_url}"'.encode()))
            await send({"type": "http.response.start", "status": 401, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return
        # Tag the request so the MCP tool log can name its caller.
        scope.setdefault("state", {})["caller"] = caller
        await self.app(scope, receive, send)

    def _caller(self, token: str | None) -> str | None:
        key_name = verify_key(token)
        if key_name is not None:
            return f"key:{key_name}"
        if verify_session(token):
            return f"session:{session_user(token)}"
        return self.oauth.caller(token) if self.oauth is not None else None
