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


def _load_keys() -> list[dict]:
    path = _auth_path()
    if not path.exists():
        return []
    data = store.load_yaml(path) or {}
    return data.get("keys") or []


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
    store.save_yaml(_auth_path(), {"keys": keys})
    return token


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
    """Pure ASGI middleware: reject HTTP requests without a valid API key."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        auth_header = ""
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                auth_header = value.decode("latin-1")
                break
        token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None
        if verify_key(token) is None:
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
