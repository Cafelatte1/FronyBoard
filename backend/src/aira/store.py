"""File-backed storage for AIRA project data.

Layout (under the data root — default %LOCALAPPDATA%/Frony/FronyBoard/data, or
~/.Frony/FronyBoard/data where LOCALAPPDATA is unset; override with AIRA_DATA_DIR):

    projects/
    └── {KEY}/                  one folder per project, named by its key (e.g. DLY)
        ├── roadmap.yaml        yearly overview + quarterly milestones
        └── {YYYY}{Q#}.yaml     one file per opened period (e.g. 2026Q3.yaml):
                                monthly milestones + tasks + `result`
                                (retrospective, written when the period closes)
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def data_root() -> Path:
    root = os.environ.get("AIRA_DATA_DIR")
    if root:
        return Path(root)
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) / "Frony" if local else Path.home() / ".Frony"
    return base / "FronyBoard" / "data"


def projects_dir() -> Path:
    return data_root() / "projects"


def project_dir(key: str) -> Path:
    return projects_dir() / key


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data) -> bool:
        # Records are human-readable files — never emit YAML anchors/aliases.
        return True


def _str_representer(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_representer)


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)
    # Atomic replace so concurrent readers never see a half-written file.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def now() -> datetime.datetime:
    """Naive UTC timestamp — display conversion is the viewer's responsibility."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)


def new_meta() -> dict:
    ts = now()
    return {"created_at": ts, "updated_at": ts}


def touch_meta(record: dict) -> None:
    record.setdefault("meta", {"created_at": now()})["updated_at"] = now()


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


def load_state(key: str) -> ProjectState:
    pdir = project_dir(key)
    roadmap_path = pdir / "roadmap.yaml"
    if not roadmap_path.exists():
        raise FileNotFoundError(f"Unknown project '{key}' — no roadmap.yaml under {pdir}")
    state = ProjectState(key=key, roadmap=load_yaml(roadmap_path) or {})
    for entry in sorted(pdir.glob("*.yaml")):
        if entry.name == "roadmap.yaml":
            continue
        state.periods[entry.stem] = PeriodState(data=load_yaml(entry) or {})
    return state


def save_roadmap(state: ProjectState) -> None:
    save_yaml(project_dir(state.key) / "roadmap.yaml", state.roadmap)


def save_period(state: ProjectState, period: str) -> None:
    save_yaml(project_dir(state.key) / f"{period}.yaml", state.periods[period].data)
