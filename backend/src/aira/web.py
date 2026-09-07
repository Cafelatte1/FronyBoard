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
import time
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import auth, fauth, log, service, store
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
        include_content=True,
    )


async def _board(request):
    """Everything the dashboard needs in one round trip (AIR-072): server facts, the
    project list and, per project, status / roadmap / every task including cancelled ones
    and content. Replaces the 2 + 3n calls the SPA used to make on load.
    `?content=0` leaves task content out (~30 KB instead of ~190 KB gzipped): the SPA
    paints from that first and fetches the full board right after."""
    with_content = request.query_params.get("content") not in ("0", "false")
    board = service.board(include_content=with_content)
    return JSONResponse({"server": await _server_info(board["projects"]), **board})


async def _set_check(request):
    """Dashboard checklist toggle — the one write the web API offers. Logged to
    tools.jsonl like an MCP call so recent_activity shows who ticked what."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    done = body.get("done") if isinstance(body, dict) else None
    if not isinstance(done, bool):
        return JSONResponse({"error": 'body must be {"done": true|false}'}, status_code=400)
    p = request.path_params
    caller = (request.scope.get("state") or {}).get("caller") or "unknown"
    t0 = time.perf_counter()
    try:
        result = service.set_check(p["key"], p["year"], p["index"], done)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except AiraError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    log.tool_call(req=log.new_req(), tool="set_check", caller=caller, project=p["key"],
                  args={"year": p["year"], "index": p["index"], "done": done},
                  ms=round((time.perf_counter() - t0) * 1000, 1), ok=True, warnings=0)
    return JSONResponse(result)


async def _server(request):
    return JSONResponse(await _server_info())


async def _server_info(projects: list | None = None) -> dict:
    if projects is None:
        projects = service.list_projects()["projects"]
    open_periods = [{"project": p["key"], "period": pname}
                    for p in projects for pname in p["summary"]["open_periods"]]
    try:
        ver = pkg_version("aira")
    except PackageNotFoundError:
        ver = "dev"
    try:
        api_keys = len(await fauth.keys())
    except fauth.Unavailable:
        api_keys = None  # FronyAuth down — still answer, deploys verify against this route
    return {
        "version": ver,
        "started_at": str(_started_at),
        "data_root": str(store.data_root()),
        "projects": len(projects),
        "open_periods": open_periods,
        "api_keys": api_keys,
        "timezone": _timezone(),
    }


def _session_token(request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else None


def _require_admin(request) -> JSONResponse | None:
    if auth.verify_session(_session_token(request)):
        return None
    return JSONResponse({"error": "key management requires the dashboard login"}, status_code=403)


def _fauth_down() -> JSONResponse:
    return JSONResponse({"error": "auth service unavailable — try again shortly"}, status_code=503)


async def _keys(request):
    denied = _require_admin(request)
    if denied is not None:
        return denied
    try:
        if request.method == "GET":
            return JSONResponse({"keys": await fauth.keys()})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        name = str(body.get("name", "")).strip()
        status, result = await fauth.create_key(name)
    except fauth.Unavailable:
        return _fauth_down()
    if status != 201:
        # FronyAuth's 409 (duplicate) / 400 map onto the 400 this API always answered
        return JSONResponse({"error": result.get("error", "key creation failed")}, status_code=400)
    log.event("INFO", "auth", "key_created", name=name, ip=_ip(request))
    return JSONResponse({"name": result["name"], "key": result["key"]})


async def _delete_key(request):
    denied = _require_admin(request)
    if denied is not None:
        return denied
    name = request.path_params["name"]
    try:
        status, result = await fauth.delete_key(name)
    except fauth.Unavailable:
        return _fauth_down()
    if status != 200:
        return JSONResponse({"error": result.get("error", "revoke failed")}, status_code=404)
    log.event("INFO", "auth", "key_revoked", name=name, ip=_ip(request))
    fauth.clear_cache()  # a revoked key must stop working now, not when the cache expires
    return JSONResponse({"ok": True})


async def _login(request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    username = str(body.get("username", ""))
    ip = _ip(request)
    try:
        status, result = await fauth.admin_verify(username, str(body.get("password", "")), ip or "?")
    except fauth.Unavailable:
        return _fauth_down()
    if status == 429:
        return JSONResponse({"error": "too many failed logins — try again later"}, status_code=429)
    if status != 200 or not result.get("ok"):
        log.event("WARNING", "auth", "login_failed", user=username, ip=ip)
        return JSONResponse({"error": "invalid credentials"}, status_code=401)
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
        Route("/api/board", _board),
        Route("/api/keys", _keys, methods=["GET", "POST"]),
        Route("/api/keys/{name}", _delete_key, methods=["DELETE"]),
        Route("/api/projects", _projects),
        Route("/api/projects/{key}/roadmap", _roadmap),
        Route("/api/projects/{key}/status", _status),
        Route("/api/projects/{key}/tasks", _tasks),
        Route("/api/projects/{key}/years/{year}/checklist/{index:int}", _set_check,
              methods=["PATCH"]),
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
