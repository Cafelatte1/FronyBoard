"""API key management and HTTP bearer auth for the AIRA server.

Keys live in `auth.yaml` at the data root:

    keys:
    - name: pc1
      sha256: <hex digest of the key>
      created_at: 2026-08-17 12:00:00

Only the SHA-256 digest is stored — the key itself is shown once at generation
(`aira keygen <name>`) and sent by clients as `Authorization: Bearer <key>`.
Revoke a key by deleting its entry from auth.yaml.
"""

from __future__ import annotations

import hashlib
import json
import secrets

from . import store


def _auth_path():
    return store.data_root() / "auth.yaml"


def _load_auth() -> dict:
    path = _auth_path()
    if not path.exists():
        return {}
    return store.load_yaml(path) or {}


def _load_keys() -> list[dict]:
    return _load_auth().get("keys") or []


def has_keys() -> bool:
    return bool(_load_keys())


def generate_key(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("key name must not be empty")
    name = name.strip()
    keys = _load_keys()
    if any(k.get("name") == name for k in keys):
        raise ValueError(f"a key named '{name}' already exists — revoke it in auth.yaml first")
    token = "aira_" + secrets.token_hex(24)
    keys.append({
        "name": name,
        "sha256": hashlib.sha256(token.encode()).hexdigest(),
        "created_at": store.now(),
    })
    data = _load_auth()
    data["keys"] = keys
    store.save_yaml(_auth_path(), data)
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
    data = _load_auth()
    keys = data.get("keys") or []
    kept = [k for k in keys if k.get("name") != name]
    if len(kept) == len(keys):
        raise FileNotFoundError(f"no key named '{name}'")
    data["keys"] = kept
    store.save_yaml(_auth_path(), data)


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
_sessions: set[str] = set()


def create_session() -> str:
    token = "fbsession_" + secrets.token_hex(24)
    _sessions.add(token)
    return token


def verify_session(token: str | None) -> bool:
    return bool(token) and token in _sessions


def drop_session(token: str | None) -> None:
    _sessions.discard(token)


def verify_key(token: str | None) -> str | None:
    """Return the key's name if the token is valid, else None."""
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    for k in _load_keys():
        if secrets.compare_digest(digest, str(k.get("sha256", ""))):
            return k.get("name")
    return None


class BearerAuthMiddleware:
    """Pure ASGI middleware: reject HTTP requests without a valid API key.

    Only paths starting with one of `protected` require a credential (default:
    all) — the FronyBoard static files stay open while /mcp and /api stay keyed.
    `open_paths` are exact-match exceptions inside protected space (the login
    endpoint). A bearer token may be an API key or a dashboard session token.
    """

    def __init__(self, app, protected: tuple[str, ...] = ("/",),
                 open_paths: tuple[str, ...] = ()):
        self.app = app
        self.protected = protected
        self.open_paths = open_paths

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
        if verify_key(token) is None and not verify_session(token):
            body = json.dumps({"error": "unauthorized — send 'Authorization: Bearer <api key>'"}).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
