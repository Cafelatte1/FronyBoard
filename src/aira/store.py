"""File-backed storage for AIRA project data.

Layout (under the data root, default ~/.aira, override with AIRA_DATA_DIR):

    projects/
    └── {KEY}/                  one folder per project, named by its key (e.g. DLY)
        ├── roadmap.yaml        yearly overview + quarterly milestones
        └── {YYYY}{Q#}/         one folder per opened period (e.g. 2026Q3)
            ├── objective.yaml  monthly milestones
            ├── tasks.yaml      epics + tasks
            └── result.md       retrospective, written when the period is closed
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def data_root() -> Path:
    root = os.environ.get("AIRA_DATA_DIR")
    return Path(root) if root else Path.home() / ".aira"


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
    path.write_text(text, encoding="utf-8")


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
    objective: dict
    tasks: dict
    has_result: bool = False


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
    for entry in sorted(pdir.iterdir()):
        if entry.is_dir():
            state.periods[entry.name] = PeriodState(
                objective=load_yaml(entry / "objective.yaml") or {} if (entry / "objective.yaml").exists() else {},
                tasks=load_yaml(entry / "tasks.yaml") or {} if (entry / "tasks.yaml").exists() else {},
                has_result=(entry / "result.md").exists(),
            )
    return state


def save_roadmap(state: ProjectState) -> None:
    save_yaml(project_dir(state.key) / "roadmap.yaml", state.roadmap)


def save_period(state: ProjectState, period: str) -> None:
    pdir = project_dir(state.key) / period
    save_yaml(pdir / "objective.yaml", state.periods[period].objective)
    save_yaml(pdir / "tasks.yaml", state.periods[period].tasks)
