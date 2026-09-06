"""Yearly overview v0.23.0 (AIR-065): goal / now / target / checklist, set_check, and the
dashboard's PATCH toggle. Legacy now/next/later files must keep validating."""

import json

import pytest
from starlette.applications import Starlette

from aira import service, store, web
from conftest import asgi_request, bootstrap


def _overview(key, year="2026"):
    return service.get_roadmap(key)["roadmap"]["years"][year]["overview"]


def _write_legacy(key):
    state = store.load_state(key)
    state.roadmap["years"]["2026"]["overview"] = {
        "goal": "ship it", "now": "build", "next": "validate", "later": "expand",
        "meta": store.new_meta()}
    store.save_roadmap(state)


def test_legacy_now_next_later_still_validates_and_is_dropped_on_rewrite():
    key = bootstrap()
    _write_legacy(key)
    assert service.validate(key)["ok"]
    assert set(_overview(key)) == {"goal", "now", "next", "later", "meta"}

    service.set_overview(key, "2026", goal="ship it", now="build core", target="v1 out",
                         checklist=["design", {"text": "build", "done": True}])
    ov = _overview(key)
    assert set(ov) == {"goal", "now", "target", "checklist", "meta"}
    assert ov["checklist"] == [{"text": "design", "done": False}, {"text": "build", "done": True}]


def test_set_overview_optional_blocks_and_validation():
    key = bootstrap()
    service.set_overview(key, "2026", goal="only a goal")
    assert set(_overview(key)) == {"goal", "meta"}

    with pytest.raises(service.AiraError, match=r"checklist\[0\]: text"):
        service.set_overview(key, "2026", goal="g", checklist=[{"text": "  ", "done": False}])
    with pytest.raises(service.AiraError, match=r"checklist\[0\]: must be a map"):
        service.set_overview(key, "2026", goal="g", checklist=[3])
    assert set(_overview(key)) == {"goal", "meta"}  # rejected writes leave the file alone


def test_set_check_flips_one_item_and_guards_index():
    key = bootstrap()
    service.set_overview(key, "2026", goal="g", checklist=["a", "b", "c"])
    got = service.set_check(key, "2026", 1, True)
    assert got["index"] == 1
    assert [i["done"] for i in got["overview"]["checklist"]] == [False, True, False]
    assert [i["done"] for i in _overview(key)["checklist"]] == [False, True, False]
    service.set_check(key, "2026", 1, False)
    assert [i["done"] for i in _overview(key)["checklist"]] == [False, False, False]

    with pytest.raises(service.AiraError, match="index must be 0..2"):
        service.set_check(key, "2026", 3, True)
    with pytest.raises(service.AiraError, match="no checklist"):
        service.set_check(key, "2027", 0, True)


def _patch(path, body):
    app = Starlette(routes=web.api_routes())
    status, _, raw = asgi_request(app, "PATCH", path, json_body=body, scheme="http")
    return status, json.loads(raw) if raw else None


def test_patch_checklist_toggle_route():
    key = bootstrap()
    service.set_overview(key, "2026", goal="g", checklist=["a", "b"])

    status, body = _patch("/api/projects/DLY/years/2026/checklist/1", {"done": True})
    assert status == 200
    assert body["overview"]["checklist"][1]["done"] is True
    assert _overview(key)["checklist"][1]["done"] is True

    status, body = _patch("/api/projects/DLY/years/2026/checklist/1", {"done": "yes"})
    assert status == 400 and "done" in body["error"]
    status, body = _patch("/api/projects/DLY/years/2026/checklist/9", {"done": True})
    assert status == 400 and "index" in body["error"]
    status, _ = _patch("/api/projects/ZZ/years/2026/checklist/0", {"done": True})
    assert status == 404
