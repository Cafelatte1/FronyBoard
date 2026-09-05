# Data model

Field-level reference for the files under the data root
(`%LOCALAPPDATA%\Frony\FronyBoard\data`, or `~/.Frony/FronyBoard/data` where
`LOCALAPPDATA` is unset; override with `AIRA_DATA_DIR`). The conceptual overview lives in the README ("Model");
this page documents what the validation gate (`validation.py`) actually
enforces. Validation runs before every mutation — errors block the write —
and is also exposed as the `validate` MCP tool.

A project is **two kinds of files**: one `roadmap.yaml`, plus one YAML file
per opened period.

## File layout

```
<data root>/
├── auth.yaml               dashboard admin (hash only — API keys live one level up, see below)
└── projects/
    └── {KEY}/              project folder, named by its key
        ├── roadmap.yaml    yearly overview + quarterly milestones
        └── 2026Q3.yaml     one file per opened period: months + tasks + result
```

## Identifiers

| id | format | scope |
|---|---|---|
| project key | `[A-Z]{2,5}` (e.g. `AIR`) | global; folder name must match `roadmap.yaml key` |
| period | `YYYYQ#` (e.g. `2026Q3`) | file name; must match a roadmap milestone `{year}{quarter}` |
| month | `M1`, `M2`, … | per period |
| task | `{KEY}-NNN`, 3+ digits (e.g. `AIR-012`) | **project-global sequence — unique across all periods, never reused** |

## meta timestamps

Every record (overview, milestone, month, task) carries a `meta` map. All
values are **naive UTC datetimes** — a timezone offset is a validation error.
The server stamps them; agents never write them.

| field | on | rule |
|---|---|---|
| `created_at` | all records | required |
| `updated_at` | all records | required, `>= created_at` |
| `started_at` | tasks | stamped on the first `in_progress` transition |
| `completed_at` | tasks | required iff status is `done` (stamped on `done`, removed when a task leaves `done`) |

## roadmap.yaml

```yaml
key: AIR            # must match the folder name
name: FronyBoard    # optional display name
description: ...    # optional one line — what the project is
repo: owner/name    # optional — where the code lives
status: active      # active | paused | archived (missing = active)
meta: {...}         # stamped by the server (missing on projects created before v0.6)
years:
  "2026":           # 'YYYY' string keys
    overview:       # required per year
      goal: ...     # required — the year in one line
      now: ...      # optional — what is being worked on right now
      target: ...   # optional — what that work is meant to reach
      checklist:    # optional — ordered steps; ticked via set_check or the dashboard
        - {text: ..., done: false}
      meta: {...}
    milestones:     # optional map, Q1-Q4 keys
      Q3:
        goal: ...   # required
        status: planned | active | done
        meta: {...}
```

`status`: `archived` hides the project from `list_projects` unless `include_archived`
is passed, and refuses every mutation except `create_project` and `update_project`
(the only way back to `active`); `paused` only changes the dashboard badge — no other
behavior change. `update_project` requires at least one of `name`, `description`,
`repo`, `status`.

Milestone ↔ file consistency: an `active` or `done` milestone must have its
period file (error); a `planned` one may not be opened yet (warning). A period
file without a matching milestone is an orphan (warning). A `done` milestone
requires the period's `result` field — the retrospective is what closes a
period.

## Period file ({YYYYQ#}.yaml)

```yaml
months:
  - id: M1              # M# — unique within the period
    month: "2026-08"    # 'YYYY-MM', required
    goal: ...           # required
    status: planned | active | done
    meta: {...}
tasks:
  - id: AIR-012         # project-global, never reused
    title: ...          # required
    month: M1           # must reference a month in THIS period
    status: todo | in_progress | done | blocked | cancelled
    week: 3             # optional, integer 1-5 (week of month)
    tags: [frontend]    # optional free-form labels — max 8, 24 chars each, no commas,
                        # trimmed and unique; the vocabulary is a project convention
                        # (see the project's CLAUDE.md), not a schema
    content: ...        # optional markdown — see "Task content" below
    prd: ...            # optional requirement link/excerpt
    branch: feat/AIR-012/short-desc   # optional working branch — week/content/prd/branch/tags
                        # are removed by passing an empty value to update_task (0, "" or []);
                        # title/month cannot be removed this way
    cancel_reason: ...  # required iff status is cancelled
    meta: {...}
result: |               # written by close_period; its presence marks the period
  # 2026Q3 result       # closed (re-closing rewrites it). Markdown: judgment
  ...                   # and reasons only.
```

A period exists once `open_period` creates its file, and it keeps existing after
`close_period` — closing only sets `result` and flips the milestone to `done`; the
months and tasks are untouched and stay queryable (`list_tasks`, `get_status` both
include closed periods). The only way a period is unknown to the tools is if it was
never opened, or the name is wrong: any tool taking `period` other than `open_period`
itself then raises
`project {KEY} has no period {period} (it has: 2026Q3)`, or `(it has: none —
open_period starts one)` when nothing has been opened yet (`service._require_period`).

### Task content

`content` is free markdown, but every task should follow one template so a human can
read it in the dashboard's task panel and an agent can pick it up cold:

```md
## objective
1-3 sentences: why this work exists and what will be observably different once it is
done. For a bug: symptom -> cause. "Out of scope: ..." only if needed.
## action
- implementation-level approach and files to touch (may be empty until work starts)
## criteria
- verifiable completion conditions ("do X, see Y" — not "checked")
```

Title and content are written in English. Keep it under ~25 lines. Decisions go inline
as `(YYYY-MM-DD decided)`. The rationale lives in the task only — commit messages list
what changed and reference the task id. The template is not validated — the server only
checks that `content` is a string — it is carried by the `create_task`/`update_task`
tool descriptions and the server instructions.

Status invariants:

- `cancelled` ⇔ `cancel_reason` present. Cancelled is the soft delete — no
  hard delete exists; the record and its id are kept forever, and queries hide
  it by default. Transitioning a cancelled task to any status restores it
  (the reason is cleared).
- `done` ⇔ `meta.completed_at` present.
- `blocked` means "may resume"; `cancelled` means "will not happen".

Carry-over: a task that outlives its period is not moved — recreate it in the
next period under a new id and note the mapping in the closing `result`.

## Credentials (not plan data, not validated by the gate)

API keys are per device and shared by every Frony service on the machine, so
they live **outside** the FronyBoard data root, in the Frony-wide registry
`%LOCALAPPDATA%\Frony\auth.yaml` (`FRONY_AUTH_FILE` overrides). Managed by
`aira keygen` and the `/api/keys` endpoints; other services only read it:

```yaml
keys:
  - name: pc1
    sha256: <hex digest of the key>
    created_at: 2026-08-18 05:49:35
```

OAuth clients and token hashes for hosted apps sit next to it in
`%LOCALAPPDATA%\Frony\oauth.yaml` (`FRONY_OAUTH_FILE` overrides), also shared:
FronyBoard issues the tokens, any Frony service may verify them (see
[auth.md](auth.md#other-frony-services-behind-the-same-login)).

FronyBoard's own `<data root>/auth.yaml` keeps only the dashboard admin
(`aira admin`). Keys or an `oauth.yaml` found in the data root from before the
shared location existed are moved over the first time the server reads them.

```yaml
admin:
  username: admin
  salt: <hex>
  sha256: <hex digest of salt + password>
  created_at: 2026-08-18 06:02:11
```

A key or password is shown once at creation and cannot be recovered — reissue
instead.

## History

Until v0.1.1 a period was a folder (`objective.yaml` + `tasks.yaml` +
`result.md`) and tasks carried an `epic` reference grouping them under per-
period epics. v0.2.0 merged the folder into the single period file and dropped
epics — months are the only grouping. Old data migrates by concatenating the
two YAMLs, dropping `epic` fields, and moving `result.md` into `result`.
