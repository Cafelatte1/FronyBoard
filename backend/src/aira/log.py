"""JSON Lines event logs, written for agents rather than people.

Two files under the log root (`AIRA_LOG_DIR`, default `<data root>/../logs`):

    tools.jsonl   one line per MCP tool call — who called what, on which record,
                  how long it took, and whether it was accepted (kept 180 days)
    server.jsonl  boot/shutdown, auth events, HTTP 4xx/5xx, rejected tool calls
                  and unhandled exceptions with tracebacks (kept 30 days)

Every line is a flat JSON object with a fixed field set (see docs/logging.md).
Nothing is emitted until `setup()` runs, so importing this module (tests, CLI
subcommands) stays silent. stdout is never a sink — in stdio mode it carries MCP.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import secrets
import sys
import time
import traceback
import zoneinfo
from pathlib import Path
from typing import Any

from loguru import logger

from . import store

logger.remove()

# Free-text fields are logged as their length only: they are long, and they are
# the user's planning prose, not telemetry.
TEXT_FIELDS = {"content", "prd", "goal", "now", "next", "later", "result_markdown", "description"}

_tz: datetime.tzinfo | None = None


def log_dir() -> Path:
    override = os.environ.get("AIRA_LOG_DIR")
    return Path(override) if override else store.data_root().parent / "logs"


def setup(*, stderr: bool = False) -> Path:
    """Install the two file sinks (and optionally a WARNING+ stderr echo); returns the log root."""
    global _tz
    name = os.environ.get("AIRA_TZ")
    try:
        _tz = zoneinfo.ZoneInfo(name) if name else None
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        _tz = None
    root = log_dir()
    root.mkdir(parents=True, exist_ok=True)
    logger.remove()
    common = {"format": "{message}", "level": "INFO", "rotation": "00:00",
              "compression": "gz", "encoding": "utf-8"}
    logger.add(root / "server.jsonl", retention="30 days",
               filter=lambda r: r["extra"].get("stream") != "tools", **common)
    logger.add(root / "tools.jsonl", retention="180 days",
               filter=lambda r: r["extra"].get("stream") == "tools", **common)
    if stderr:
        logger.add(sys.stderr, format="{message}", level="WARNING",
                   filter=lambda r: r["extra"].get("stream") != "tools")
    # Route the stdlib loggers (uvicorn, mcp) through the same sinks.
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)
    for lg_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(lg_name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False
    return root


def shutdown() -> None:
    logger.remove()


def _ts() -> str:
    """ISO 8601 with offset, in AIRA_TZ or the process-local zone."""
    return datetime.datetime.now(_tz).astimezone(_tz).isoformat(timespec="milliseconds")


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def event(level: str, scope: str, evt: str, **fields: Any) -> None:
    """One server.jsonl line: {ts, level, scope, event, ...fields}."""
    payload = {"ts": _ts(), "level": level, "scope": scope, "event": evt, **fields}
    logger.bind(stream="server").log(level, _dump(payload))


def exception(scope: str, evt: str, **fields: Any) -> None:
    """`event` at ERROR with the current exception's traceback attached."""
    event("ERROR", scope, evt, trace=traceback.format_exc(), **fields)


def tool_call(**fields: Any) -> None:
    """One tools.jsonl line."""
    logger.bind(stream="tools").info(_dump({"ts": _ts(), **fields}))


def new_req() -> str:
    """Short correlation id shared by a tools.jsonl line and its server.jsonl follow-ups."""
    return secrets.token_hex(3)


def summarize_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in args.items():
        if v is None:
            continue
        if k in TEXT_FIELDS:
            out[f"{k}_len"] = len(str(v))
        else:
            out[k] = v
    return out


class InterceptHandler(logging.Handler):
    """stdlib logging → server.jsonl. Access lines below 400 are dropped (the
    dashboard polls every minute); everything else keeps its logger name."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == "uvicorn.access":
            try:
                addr, method, path, _http, status = record.args  # type: ignore[misc]
                status = int(status)
            except (TypeError, ValueError):
                return
            if status < 400:
                return
            if method == "GET" and path == "/mcp" and status in (404, 405):
                return  # a client opening the optional SSE listen stream — protocol chatter, not a fault
            event("WARNING" if status < 500 else "ERROR", "http", "response",
                  status=status, method=method, path=path, ip=str(addr).rsplit(":", 1)[0])
            return
        if record.levelno < logging.WARNING:
            return  # startup chatter
        level = "ERROR" if record.levelno >= logging.ERROR else "WARNING"
        fields: dict[str, Any] = {"logger": record.name, "msg": record.getMessage()}
        if record.exc_info:
            fields["trace"] = "".join(traceback.format_exception(*record.exc_info))
        event(level, "py", "log", **fields)


class ToolLogMiddleware:
    """MCP server middleware: one tools.jsonl line per tools/call.

    The caller comes from `scope["state"]["caller"]`, which the bearer-auth ASGI
    middleware fills in for HTTP transports; stdio has no request and logs as `stdio`.
    """

    async def __call__(self, ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params or {}
        name = params.get("name")
        args = dict(params.get("arguments") or {})
        req = new_req()
        caller = "stdio"
        request = getattr(ctx, "request", None)
        if request is not None:
            state = (getattr(request, "scope", None) or {}).get("state") or {}
            caller = state.get("caller") or "unknown"
        line: dict[str, Any] = {"req": req, "tool": name, "caller": caller}
        key = args.pop("key", None)
        task = args.pop("task_id", None)
        period = args.pop("period", None)
        project = key or (task.split("-", 1)[0] if isinstance(task, str) and "-" in task else None)
        if project:
            line["project"] = project
        if period:
            line["period"] = period
        if task:
            line["task"] = task
        line["args"] = summarize_args(args)

        t0 = time.perf_counter()
        try:
            result = await call_next(ctx)
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            tool_call(**line, ms=ms, ok=False, error=type(e).__name__, msg=str(e))
            exception("tool", "exception", req=req, tool=name, error=type(e).__name__, msg=str(e))
            raise
        ms = round((time.perf_counter() - t0) * 1000, 1)
        is_error, content, structured = _result_parts(result)
        if is_error:
            # The SDK turns any exception raised by a tool into an is_error result;
            # for this server that is a validation/argument rejection (AiraError).
            msg = "; ".join(_text(c) for c in content)
            msg = msg.removeprefix(f"Error executing tool {name}: ")[:500]  # SDK boilerplate
            tool_call(**line, ms=ms, ok=False, error="rejected", msg=msg)
            event("WARNING", "tool", "rejected", req=req, tool=name, msg=msg)
        else:
            sc = structured
            if isinstance(sc, dict) and "warnings" not in sc and isinstance(sc.get("result"), dict):
                sc = sc["result"]
            warnings = len(sc.get("warnings") or []) if isinstance(sc, dict) else 0
            tool_call(**line, ms=ms, ok=True, warnings=warnings)
        return result


def _result_parts(result: Any) -> tuple[bool, list[Any], Any]:
    """(is_error, content, structured_content) from a CallToolResult, whether the
    middleware sees the model or its wire-format dict."""
    if isinstance(result, dict):
        return (bool(result.get("isError") or result.get("is_error")),
                list(result.get("content") or []),
                result.get("structuredContent") or result.get("structured_content") or {})
    return (bool(getattr(result, "is_error", False)),
            list(getattr(result, "content", None) or []),
            getattr(result, "structured_content", None) or {})


def _text(part: Any) -> str:
    if isinstance(part, dict):
        return str(part.get("text", ""))
    return str(getattr(part, "text", ""))
