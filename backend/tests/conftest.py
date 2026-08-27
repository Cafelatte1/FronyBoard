"""Shared fixtures and helpers for the FronyBoard test suite."""

import pytest

from aira import auth, service


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRONY_AUTH_FILE", str(tmp_path / "frony" / "auth.yaml"))
    monkeypatch.setattr(auth, "login_throttle", auth.LoginThrottle())  # lockouts must not leak across tests
    return tmp_path


def bootstrap(key="DLY"):
    """Create a project with an open 2026Q3 period and an active M1 month."""
    service.create_project(key, name="Dailying")
    service.set_overview(key, "2026", goal="ship it", now="build core",
                         next_="validate habit", later="expand")
    service.upsert_milestone(key, "2026", "Q3", goal="MVP", status="planned")
    service.open_period(key, "2026Q3")
    service.upsert_month(key, "2026Q3", "M1", month="2026-07", goal="core", status="active")
    return key
