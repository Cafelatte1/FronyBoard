import datetime
from pathlib import Path

import yaml

from fronyboard import service, store
from conftest import bootstrap


def test_data_root_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    assert store.data_root() == tmp_path


def test_data_root_defaults_to_localappdata(monkeypatch):
    monkeypatch.delenv("AIRA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\me\AppData\Local")
    assert store.data_root() == Path(r"C:\Users\me\AppData\Local") / "Frony" / "FronyBoard" / "data"


def test_data_root_falls_back_to_home_dot_frony(monkeypatch):
    monkeypatch.delenv("AIRA_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert store.data_root() == Path.home() / ".Frony" / "FronyBoard" / "data"


def test_timestamps_round_trip_through_sqlite():
    key = bootstrap()
    meta = store.load_state(key).roadmap["meta"]
    assert isinstance(meta["created_at"], datetime.datetime) and meta["created_at"].tzinfo is None
    assert store.db_path().is_file() and not (store.data_root() / "projects").exists()


def test_strip_legacy_drops_the_retired_fields_and_folds_content():
    key = bootstrap()
    state = store.load_state(key)
    # the gate would refuse legacy data, so seed the period record directly
    state.periods["2026Q3"].data = {
        "months": [{"id": "M1", "month": "2026-07", "goal": "core", "status": "active"}],
        "tasks": [{"id": "DLY-001", "title": "a", "month": "M1", "week": 2, "prd": "spec",
                   # the cut at 200 lands on a space; a second run must see no change
                   "status": "todo", "content": "line one\n" + "x" * 190 + " " + "y" * 100,
                   "meta": store.new_meta()}]}
    store.save_period(state, "2026Q3")

    assert store.strip_legacy() == {"periods_changed": 1, "tasks_changed": 1}
    data = store.load_state(key).periods["2026Q3"].data
    assert "months" not in data
    task = data["tasks"][0]
    assert not {"month", "week", "prd"} & set(task)
    assert task["content"] == "line one " + "x" * 190
    assert service.validate(key)["ok"]

    assert store.strip_legacy() == {"periods_changed": 0, "tasks_changed": 0}


def test_migrate_yaml_copies_the_tree_and_leaves_it_alone(tmp_path):
    src = tmp_path / "projects" / "DLY"
    src.mkdir(parents=True)
    created = datetime.datetime(2026, 7, 1, 0, 0, 0)
    (src / "roadmap.yaml").write_text(yaml.safe_dump({
        "key": "DLY", "name": "Dailying", "status": "active",
        "meta": {"created_at": created, "updated_at": created},
        "years": {"2026": {"overview": {"goal": "ship", "meta": {"created_at": created, "updated_at": created}},
                            "milestones": {"Q3": {"goal": "MVP", "status": "active", "meta": {"created_at": created, "updated_at": created}}}}}}), encoding="utf-8")
    (src / "2026Q3.yaml").write_text(yaml.safe_dump({
        "tasks": [{"id": "DLY-001", "title": "a", "status": "todo",
                   "content": "one then two", "meta": {"created_at": created, "updated_at": created}}]}),
        encoding="utf-8")

    dry = store.migrate_yaml(dry_run=True)
    assert dry["projects"] == [{"key": "DLY", "periods": ["2026Q3"]}] and not store.project_exists("DLY")

    report = store.migrate_yaml()
    assert report["periods"] == 1
    assert service.get_task("DLY-001")["task"]["content"] == "one then two"
    assert service.get_status("DLY")["periods"]["2026Q3"]["task_counts"] == {"todo": 1}
    assert service.validate("DLY")["ok"]
    assert (src / "roadmap.yaml").is_file() and (src / "2026Q3.yaml").is_file()  # backup untouched
