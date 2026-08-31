"""Client for FronyAuth — the central auth server every Frony service delegates to.

Since AIR-056 aira no longer reads auth.yaml/oauth.yaml itself: every bearer
credential (API key or OAuth access token) is judged by FronyAuth's
POST /introspect, the dashboard login by POST /admin/verify, and the Settings
key management by its /keys API. The contract is FronyAuth's
docs/introspection.md (project-auth repo).

Configuration (set in the launcher next to AIRA_DATA_DIR):

    FRONY_AUTH_URL     FronyAuth base URL   (default http://127.0.0.1:8640)
    FRONY_SERVICE_KEY  this service's own frony_ API key, used to call FronyAuth

Verdicts are cached in memory by sha256(token) — positives for 60s (or until
the token's own expiry), negatives for 5s — so a FronyAuth blip does not drop
every request. When FronyAuth cannot be reached and no cached verdict exists,
`Unavailable` is raised and the middleware answers 503 (fail closed, never 401:
a client must not conclude its key was revoked).
"""

from __future__ import annotations

import hashlib
import os
import time

import httpx

POSITIVE_TTL = 60
NEGATIVE_TTL = 5
TIMEOUT = 2.0

_cache: dict[str, tuple[float, str | None]] = {}  # sha256(token) -> (expires, caller|None)


class Unavailable(Exception):
    """FronyAuth could not be reached and no cached verdict exists."""


def base_url() -> str:
    return (os.environ.get("FRONY_AUTH_URL") or "http://127.0.0.1:8640").rstrip("/")


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('FRONY_SERVICE_KEY', '')}"}


async def _post(path: str, payload: dict) -> httpx.Response:
    last_error: Exception | None = None
    for _ in range(2):  # one retry, per the contract
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                return await client.post(base_url() + path, json=payload, headers=_headers())
        except httpx.HTTPError as e:
            last_error = e
    raise Unavailable(str(last_error))


async def verify(token: str | None) -> str | None:
    """The caller label for a bearer token (`key:…` / `oauth:…`), or None."""
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    cached = _cache.get(digest)
    if cached and cached[0] > now:
        return cached[1]
    try:
        response = await _post("/introspect", {"token": token})
    except Unavailable:
        if cached:  # expired entry beats an outage — the contract's cache rule
            return cached[1]
        raise
    if response.status_code != 200:
        raise Unavailable(f"introspect answered {response.status_code}")
    result = response.json()
    if result.get("active"):
        caller, ttl = str(result.get("caller")), POSITIVE_TTL
    else:
        caller, ttl = None, NEGATIVE_TTL
    _cache[digest] = (now + ttl, caller)
    return caller


async def admin_verify(username: str, password: str, client_addr: str) -> tuple[int, dict]:
    """Delegate a dashboard login; returns FronyAuth's (status, body) as-is."""
    response = await _post("/admin/verify",
                           {"username": username, "password": password, "client_addr": client_addr})
    return response.status_code, response.json()


async def keys() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(base_url() + "/keys", headers=_headers())
    except httpx.HTTPError as e:
        raise Unavailable(str(e))
    if response.status_code != 200:
        raise Unavailable(f"/keys answered {response.status_code}")
    return response.json()["keys"]


async def create_key(name: str) -> tuple[int, dict]:
    response = await _post("/keys", {"name": name})
    return response.status_code, response.json()


async def delete_key(name: str) -> tuple[int, dict]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.delete(base_url() + f"/keys/{name}", headers=_headers())
    except httpx.HTTPError as e:
        raise Unavailable(str(e))
    return response.status_code, response.json()


def clear_cache() -> None:
    _cache.clear()
