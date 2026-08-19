from pathlib import Path

from aira import store


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
