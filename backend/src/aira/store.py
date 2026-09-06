"""SQLite-backed storage for FronyBoard project data (v0.25.0, AIR-073).

One database under the data root (default %LOCALAPPDATA%/Frony/FronyBoard/data, or
~/.Frony/FronyBoard/data where LOCALAPPDATA is unset; override with AIRA_DATA_DIR):

    fronyboard.db
    ├── projects(key, status, roadmap)      roadmap = the whole roadmap record as JSON
    └── periods(key, name, data)            data = one period record (months + tasks + result)

The records are the same dicts the YAML files held until v0.24 — a document store, not a
relational one — so the service layer and the validation gate work on `ProjectState`
exactly as before. Timestamps inside the JSON are tagged ({"__dt__": iso}) so they come
back as naive-UTC datetimes.

`migrate_yaml()` copies a pre-v0.25 `projects/` tree into the database once; the tree is
left untouched as a backup and never read again.
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DB_NAME = "fronyboard.db"


def frony_root() -> Path:
    """The folder every Frony service on this machine shares (%LOCALAPPDATA%/Frony,
    or ~/.Frony where LOCALAPPDATA is unset) — the API key registry lives here."""
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "Frony" if local else Path.home() / ".Frony"


def data_root() -> Path:
    root = os.environ.get("AIRA_DATA_DIR")
    if root:
        return Path(root)
    return frony_root() / "FronyBoard" / "data"


def db_path() -> Path:
    return data_root() / DB_NAME


# ------------------------------------------------------------------ connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    key     TEXT PRIMARY KEY,
    status  TEXT NOT NULL DEFAULT 'active',
    roadmap TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS periods (
    key  TEXT NOT NULL REFERENCES projects(key),
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (key, name)
);
"""


def connect() -> sqlite3.Connection:
    """One connection per operation: the database is tiny and SQLite serialises writers
    itself; WAL keeps readers from blocking on a write."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


# ------------------------------------------------------------------ JSON codec

def _encode(o):
    if isinstance(o, datetime.datetime):
        return {"__dt__": o.isoformat()}
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def _decode(d: dict):
    if "__dt__" in d and len(d) == 1:
        return datetime.datetime.fromisoformat(d["__dt__"])
    return d


def dumps(value) -> str:
    return json.dumps(value, default=_encode, ensure_ascii=False)


def loads(text: str):
    return json.loads(text, object_hook=_decode)


# ------------------------------------------------------------------ timestamps

def now() -> datetime.datetime:
    """Naive UTC timestamp — display conversion is the viewer's responsibility."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)


def new_meta() -> dict:
    ts = now()
    return {"created_at": ts, "updated_at": ts}


def touch_meta(record: dict) -> None:
    record.setdefault("meta", {"created_at": now()})["updated_at"] = now()


# ------------------------------------------------------------------ state

@dataclass
class PeriodState:
    data: dict  # {"months": [...], "tasks": [...], "result": str (once closed)}

    @property
    def has_result(self) -> bool:
        return bool(self.data.get("result"))


@dataclass
class ProjectState:
    key: str
    roadmap: dict
    periods: dict[str, PeriodState] = field(default_factory=dict)


def project_keys(include_archived: bool = False) -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, status FROM projects ORDER BY key").fetchall()
    return [k for k, st in rows if include_archived or st != "archived"]


def project_exists(key: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM projects WHERE key = ?", (key,)).fetchone() is not None


def load_roadmap(key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT roadmap FROM projects WHERE key = ?", (key,)).fetchone()
    return loads(row[0]) if row else None


def load_state(key: str) -> ProjectState:
    with connect() as conn:
        row = conn.execute("SELECT roadmap FROM projects WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"Unknown project '{key}' — not in {db_path()}")
        state = ProjectState(key=key, roadmap=loads(row[0]) or {})
        for name, data in conn.execute(
                "SELECT name, data FROM periods WHERE key = ? ORDER BY name", (key,)):
            state.periods[name] = PeriodState(data=loads(data) or {})
    return state


def save_roadmap(state: ProjectState) -> None:
    status = state.roadmap.get("status") or "active"
    with connect() as conn:
        conn.execute(
            "INSERT INTO projects (key, status, roadmap) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET status = excluded.status, roadmap = excluded.roadmap",
            (state.key, status, dumps(state.roadmap)))


def save_period(state: ProjectState, period: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO periods (key, name, data) VALUES (?, ?, ?) "
            "ON CONFLICT(key, name) DO UPDATE SET data = excluded.data",
            (state.key, period, dumps(state.periods[period].data)))


# ------------------------------------------------------------------ migration

def migrate_yaml(src: Path | None = None, dry_run: bool = False) -> dict:
    """Copy the pre-v0.25 YAML tree (`<data root>/projects/<KEY>/*.yaml`) into the
    database. Existing rows are overwritten, so running it twice is harmless; the YAML
    files are never modified or deleted."""
    import yaml  # only needed here

    src = src or data_root() / "projects"
    report: dict = {"source": str(src), "database": str(db_path()), "projects": [], "periods": 0,
                    "dry_run": dry_run}
    if not src.is_dir():
        return report
    with connect() as conn:
        for pdir in sorted(p for p in src.iterdir() if p.is_dir()):
            roadmap_path = pdir / "roadmap.yaml"
            if not roadmap_path.exists():
                continue
            roadmap = yaml.safe_load(roadmap_path.read_text(encoding="utf-8")) or {}
            state = ProjectState(key=pdir.name, roadmap=roadmap)
            for entry in sorted(pdir.glob("*.yaml")):
                if entry.name != "roadmap.yaml":
                    state.periods[entry.stem] = PeriodState(
                        data=yaml.safe_load(entry.read_text(encoding="utf-8")) or {})
            report["projects"].append({"key": state.key, "periods": sorted(state.periods)})
            report["periods"] += len(state.periods)
            if dry_run:
                continue
            conn.execute(
                "INSERT INTO projects (key, status, roadmap) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET status = excluded.status, roadmap = excluded.roadmap",
                (state.key, roadmap.get("status") or "active", dumps(roadmap)))
            for name, p in state.periods.items():
                conn.execute(
                    "INSERT INTO periods (key, name, data) VALUES (?, ?, ?) "
                    "ON CONFLICT(key, name) DO UPDATE SET data = excluded.data",
                    (state.key, name, dumps(p.data)))
    return report
