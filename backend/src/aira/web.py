"""FronyBoard web layer — read-only JSON API plus static dashboard serving.

The dashboard itself is a separate npm project (frontend/); its build output
(frontend/dist, override with AIRA_WEB_DIR) is served by this process so the
deployment stays a single task. API routes require the same bearer key as MCP;
the static files do not — the dashboard asks for a key and sends it per request.
The only writes here are API key management, and those require the dashboard
login (a session token), never an API key — plan data stays MCP-only.
"""

from __future__ import annotations

import datetime
import zoneinfo

import os
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import auth, log, service, store
from .service import AiraError

_started_at = store.now()  # module import happens at process start — close enough for uptime


def _timezone() -> dict:
    """The zone this server is serving from, for display conversion of the naive-UTC
    timestamps. AIRA_TZ (an IANA name) wins; otherwise the process-local offset.
    `name` is only reported when it is a short ASCII abbreviation (KST, CET…) —
    Windows hands back localized long names, which are useless as a label."""
    tz = None
    override = os.environ.get("AIRA_TZ")
    if override:
        try:
            tz = zoneinfo.ZoneInfo(override)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            tz = None
    local = datetime.datetime.now(tz).astimezone(tz)
    offset = local.utcoffset() or datetime.timedelta(0)
    name = local.tzname() or ""
    if not (name.isascii() and 2 <= len(name) <= 5):
        name = None
    return {"name": name, "offset_minutes": int(offset.total_seconds() // 60)}


def _ip(request) -> str | None:
    client = getattr(request, "client", None)
    return client.host if client else None


def _endpoint(fn):
    async def handle(request):
        try:
            return JSONResponse(fn(request))
        except FileNotFoundError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except AiraError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    return handle


@_endpoint
def _projects(request):
    include_archived = request.query_params.get("include_archived") in ("1", "true")
    return service.list_projects(include_archived=include_archived)


@_endpoint
def _roadmap(request):
    return service.get_roadmap(request.path_params["key"])


@_endpoint
def _status(request):
    return service.get_status(request.path_params["key"])


@_endpoint
def _tasks(request):
    q = request.query_params
    return service.list_tasks(
        request.path_params["key"],
        period=q.get("period"), status=q.get("status"), month=q.get("month"),
        include_cancelled=q.get("include_cancelled") in ("1", "true"),
    )


@_endpoint
def _server(request):
    projects = service.list_projects()["projects"]
    open_periods = []
    for p in projects:
        state = store.load_state(p["key"])
        for pname in sorted(state.periods):
            if not state.periods[pname].has_result:
                open_periods.append({"project": p["key"], "period": pname})
    try:
        ver = pkg_version("aira")
    except PackageNotFoundError:
        ver = "dev"
    return {
        "version": ver,
        "started_at": str(_started_at),
        "data_root": str(store.data_root()),
        "projects": len(projects),
        "open_periods": open_periods,
        "api_keys": len(auth.key_info()),
        "timezone": _timezone(),
    }


def _session_token(request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else None


def _require_admin(request) -> JSONResponse | None:
    if auth.verify_session(_session_token(request)):
        return None
    return JSONResponse({"error": "key management requires the dashboard login"}, status_code=403)


async def _keys(request):
    denied = _require_admin(request)
    if denied is not None:
        return denied
    if request.method == "GET":
        return JSONResponse({"keys": auth.key_info()})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    name = str(body.get("name", "")).strip()
    try:
        key = auth.generate_key(name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    log.event("INFO", "auth", "key_created", name=name, ip=_ip(request))
    return JSONResponse({"name": name, "key": key})


async def _delete_key(request):
    denied = _require_admin(request)
    if denied is not None:
        return denied
    try:
        auth.revoke_key(request.path_params["name"])
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    log.event("INFO", "auth", "key_revoked", name=request.path_params["name"], ip=_ip(request))
    return JSONResponse({"ok": True})


async def _login(request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    username = str(body.get("username", ""))
    ip = _ip(request)
    if auth.login_throttle.blocked(ip):
        return JSONResponse({"error": "too many failed logins — try again later"}, status_code=429)
    if not auth.verify_admin(username, str(body.get("password", ""))):
        auth.login_throttle.fail(ip)
        log.event("WARNING", "auth", "login_failed", user=username, ip=ip)
        return JSONResponse({"error": "invalid credentials"}, status_code=401)
    auth.login_throttle.clear(ip)
    log.event("INFO", "auth", "login_ok", user=username, ip=ip)
    return JSONResponse({"token": auth.create_session(username), "username": username})


async def _logout(request):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        auth.drop_session(header[7:])
    return JSONResponse({"ok": True})


def api_routes() -> list[Route]:
    return [
        Route("/api/login", _login, methods=["POST"]),
        Route("/api/logout", _logout, methods=["POST"]),
        Route("/api/server", _server),
        Route("/api/keys", _keys, methods=["GET", "POST"]),
        Route("/api/keys/{name}", _delete_key, methods=["DELETE"]),
        Route("/api/projects", _projects),
        Route("/api/projects/{key}/roadmap", _roadmap),
        Route("/api/projects/{key}/status", _status),
        Route("/api/projects/{key}/tasks", _tasks),
    ]


def web_dir() -> Path | None:
    """The built dashboard, if present (frontend/dist next to backend/)."""
    env = os.environ.get("AIRA_WEB_DIR")
    path = Path(env) if env else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return path if (path / "index.html").is_file() else None


def attach(app) -> None:
    """Add the API routes (and the dashboard, when built) to the MCP Starlette app."""
    app.router.routes.extend(api_routes())
    dist = web_dir()
    if dist is not None:
        app.router.routes.append(Mount("/", app=StaticFiles(directory=dist, html=True)))
