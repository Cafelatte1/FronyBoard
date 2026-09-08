"""JSONL event logs: one tools.jsonl line per MCP tool call, server.jsonl for events."""

import json

import anyio
import pytest
from mcp.client import Client

from fronyboard import log, server
from conftest import bootstrap


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONYBOARD_LOG_DIR", str(tmp_path / "logs"))
    root = log.setup()
    yield root
    log.shutdown()


def test_tool_calls_land_in_tools_jsonl(logs):
    bootstrap("DLY")

    async def run():
        async with Client(server.mcp) as c:
            await c.call_tool("list_projects", {})
            await c.call_tool("create_task", {"key": "DLY", "period": "2026Q3", "title": "t",
                                              "month": "M1", "content": "x" * 50})
            await c.call_tool("update_task", {"task_id": "DLY-001"})  # nothing to update

    anyio.run(run)
    rows = _lines(logs / "tools.jsonl")
    assert [r["tool"] for r in rows] == ["list_projects", "create_task", "update_task"]
    assert all(r["caller"] == "stdio" and len(r["req"]) == 6 and r["ms"] >= 0 for r in rows)

    created = rows[1]
    assert created["ok"] is True and created["warnings"] == 0
    assert created["project"] == "DLY" and created["period"] == "2026Q3"
    assert created["args"] == {"title": "t", "month": "M1", "content_len": 50}
    assert "content" not in created["args"]

    rejected = rows[2]
    assert rejected["ok"] is False and rejected["error"] == "rejected"
    assert "nothing to update" in rejected["msg"]
    assert rejected["project"] == "DLY" and rejected["task"] == "DLY-001"

    server_rows = _lines(logs / "server.jsonl")
    follow = [r for r in server_rows if r["event"] == "rejected"]
    assert follow and follow[0]["req"] == rejected["req"] and follow[0]["level"] == "WARNING"


def test_event_lines_have_fixed_shape(logs):
    log.event("INFO", "auth", "login_ok", user="admin", ip="127.0.0.1")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("py", "unhandled", where="test")
    rows = _lines(logs / "server.jsonl")
    assert rows[0]["scope"] == "auth" and rows[0]["event"] == "login_ok" and rows[0]["user"] == "admin"
    assert set(rows[0]) >= {"ts", "level", "scope", "event"}
    assert rows[1]["level"] == "ERROR" and "RuntimeError: boom" in rows[1]["trace"]
    assert not (logs / "tools.jsonl").exists() or _lines(logs / "tools.jsonl") == []


def test_summarize_args_hides_prose():
    out = log.summarize_args({"title": "x", "content": "abc", "goal": "", "week": None, "status": "done",
                              "result_markdown": "## 회고"})  # close_period's argument name
    assert out == {"title": "x", "content_len": 3, "goal_len": 0, "status": "done", "result_markdown_len": 5}
