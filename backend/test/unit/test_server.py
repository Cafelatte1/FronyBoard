"""MCP tool-surface wiring tests — the glue between the tools and the service layer."""

import asyncio

import pytest

from fronyboard import server, service
from conftest import bootstrap


def test_task_tools_derive_key_from_task_id():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x")

    out = server.update_task(task_id="DLY-001", title="renamed")
    assert out["task"]["title"] == "renamed"

    out = server.transition_task(task_id="DLY-001", status="in_progress",
                                 branch="feat/DLY-001/renamed")
    assert out["to"] == "in_progress"

    task = service.list_tasks(key)["tasks"][0]
    assert task["title"] == "renamed"
    assert task["status"] == "in_progress"


def test_task_tools_accept_matching_key_and_reject_mismatch():
    key = bootstrap()
    service.create_task(key, "2026Q3", title="x")

    out = server.update_task(task_id="DLY-001", title="ok", key="DLY")
    assert out["task"]["title"] == "ok"
    with pytest.raises(service.FronyBoardError, match="does not match"):
        server.update_task(task_id="DLY-001", title="nope", key="AIR")
    with pytest.raises(service.FronyBoardError, match="does not match"):
        server.transition_task(task_id="DLY-001", status="done", key="AIR")


def _tools():
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def test_instructions_fit_what_clients_keep_and_point_to_help():
    assert len(server.mcp.instructions) <= 512
    assert "help" in server.mcp.instructions


def test_help_is_one_markdown_text_block_naming_every_tool():
    result = asyncio.run(server.mcp.call_tool("help", {}))
    assert result.structured_content is None
    assert [c.type for c in result.content] == ["text"]
    guide = result.content[0].text
    assert guide.startswith("# FronyBoard guide")
    missing = [name for name in _tools() if f"`{name}`" not in guide]
    assert missing == []


def test_help_description_names_the_working_tools_but_none_of_their_words():
    tools = _tools()
    description = tools["help"].description
    for name in ("get_status", "create_task", "transition_task", "list_tasks", "search_tasks"):
        assert name in description
    words = description
    for name in tools:
        words = words.replace(name, "")
    words = words.lower()
    for term in ("task", "project", "quarter", "roadmap", "milestone", "retrospective",
                 "태스크", "프로젝트", "분기", "회고"):
        assert term not in words, term


def test_tool_descriptions_open_with_when_to_use_and_fit_2kb():
    for name, tool in _tools().items():
        assert tool.description.startswith("Use it "), name
        assert len(tool.description.encode()) <= 2048, name


def test_serve_local_refuses_a_non_loopback_host():
    with pytest.raises(SystemExit, match="loopback"):
        server.serve("0.0.0.0", 8642, local=True)
