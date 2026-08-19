"""One-off migration to the v0.2.0 layout: period folders -> single period files.

For every `projects/{KEY}/{YYYYQ#}/` folder: merge objective.yaml (months) and
tasks.yaml (tasks, minus their `epic` field — epics are gone in v0.2.0) into
`projects/{KEY}/{YYYYQ#}.yaml`, move result.md into the `result` field, then
remove the folder. Idempotent: a project with no period folders is left as is.

Run from backend/ against the live data root (stop the server first):

    uv run python scripts/migrate_v020.py [data-root]    # default: ~/.aira
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aira import store  # noqa: E402


def migrate(root: Path) -> None:
    projects = root / "projects"
    if not projects.is_dir():
        raise SystemExit(f"no projects directory under {root}")
    for pdir in sorted(projects.iterdir()):
        if not pdir.is_dir():
            continue
        for period_dir in sorted(p for p in pdir.iterdir() if p.is_dir()):
            objective = period_dir / "objective.yaml"
            tasks_file = period_dir / "tasks.yaml"
            if not objective.exists() and not tasks_file.exists():
                print(f"skip {period_dir} — not a period folder")
                continue
            obj = store.load_yaml(objective) or {} if objective.exists() else {}
            tsk = store.load_yaml(tasks_file) or {} if tasks_file.exists() else {}
            data = {"months": obj.get("months") or [], "tasks": []}
            for t in tsk.get("tasks") or []:
                t.pop("epic", None)
                data["tasks"].append(t)
            result_md = period_dir / "result.md"
            if result_md.exists():
                data["result"] = result_md.read_text(encoding="utf-8")
            out = pdir / f"{period_dir.name}.yaml"
            store.save_yaml(out, data)
            shutil.rmtree(period_dir)
            print(f"migrated {period_dir} -> {out.name} "
                  f"({len(data['months'])} months, {len(data['tasks'])} tasks)")


if __name__ == "__main__":
    migrate(Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / ".aira")
