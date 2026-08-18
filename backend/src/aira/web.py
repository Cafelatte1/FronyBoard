"""FronyBoard web layer — read-only JSON API plus static dashboard serving.

The dashboard itself is a separate npm project (frontend/); its build output
(frontend/dist, override with AIRA_WEB_DIR) is served by this process so the
deployment stays a single task. API routes require the same bearer key as MCP;
the static files do not — the dashboard asks for a key and sends it per request.
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import service
from .service import AiraError


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
    return service.list_projects()


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
        period=q.get("period"), status=q.get("status"),
        epic=q.get("epic"), month=q.get("month"),
        include_cancelled=q.get("include_cancelled") in ("1", "true"),
    )


def api_routes() -> list[Route]:
    return [
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
