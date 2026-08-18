# Data model

Field-level reference for the files under the data root (`~/.aira`, override
with `AIRA_DATA_DIR`). The conceptual overview lives in the README ("Model");
this page documents what the validation gate (`validation.py`) actually
enforces. Validation runs before every mutation — errors block the write —
and is also exposed as the `validate` MCP tool.

The schema is **frozen**: field additions wait for real-usage feedback.

## File layout

```
<data root>/
├── auth.yaml               API keys + dashboard admin (hashes only — see below)
└── projects/
    └── {KEY}/              project folder, named by its key
        ├── roadmap.yaml
        └── {YYYY}{Q#}/     one folder per opened period (e.g. 2026Q3)
            ├── objective.yaml
            ├── tasks.yaml
            └── result.md   written once, when the period is closed
```

## Identifiers

| id | format | scope |
|---|---|---|
| project key | `[A-Z]{2,5}` (e.g. `AIR`) | global; folder name must match `roadmap.yaml key` |
| period | `YYYYQ#` (e.g. `2026Q3`) | folder name; must match a roadmap milestone `{year}{quarter}` |
| month | `M1`, `M2`, … | per period |
| epic | `E1`, `E2`, … | per period |
| task | `{KEY}-NNN`, 3+ digits (e.g. `AIR-012`) | **project-global sequence — unique across all periods, never reused** |

## meta timestamps

Every record (overview, milestone, month, epic, task) carries a `meta` map.
All values are **naive UTC datetimes** — a timezone offset is a validation
error. The server stamps them; agents never write them.

| field | on | rule |
|---|---|---|
| `created_at` | all records | required |
| `updated_at` | all records | required, `>= created_at` |
| `started_at` | tasks | stamped on the first `in_progress` transition |
| `completed_at` | tasks | required iff status is `done` (stamped on `done`, removed when a task leaves `done`) |

## roadmap.yaml

```yaml
key: AIR            # must match the folder name
name: AIRA          # optional display name
years:
  "2026":           # 'YYYY' string keys
    overview:       # required per year
      goal: ...     # all four fields required
      now: ...
      next: ...
      later: ...
      meta: {...}
    milestones:     # optional map, Q1-Q4 keys
      Q3:
        goal: ...   # required
        status: planned | active | done
        meta: {...}
```

Milestone ↔ folder consistency: an `active` or `done` milestone must have its
period folder (error); a `planned` one may not be opened yet (warning). A
period folder without a matching milestone is an orphan (warning). A `done`
milestone requires `result.md` in the folder — result.md is what closes a
period.

## objective.yaml

```yaml
months:
  - id: M1              # M# — unique within the period
    month: "2026-08"    # 'YYYY-MM', required
    goal: ...           # required
    status: planned | active | done
    meta: {...}
```

## tasks.yaml

```yaml
epics:
  - id: E1              # E# — unique within the period
    goal: ...           # required
    meta: {...}
tasks:
  - id: AIR-012         # project-global, never reused
    title: ...          # required
    epic: E1            # must reference an epic in THIS period
    month: M1           # must reference a month in THIS period
    status: todo | in_progress | done | blocked | cancelled
    week: 3             # optional, integer 1-5 (week of month)
    content: ...        # optional markdown — enough to pick the task up cold
    prd: ...            # optional requirement link/excerpt
    branch: feat/AIR-012/short-desc   # optional working branch
    cancel_reason: ...  # required iff status is cancelled
    meta: {...}
```

Status invariants:

- `cancelled` ⇔ `cancel_reason` present. Cancelled is the soft delete — no
  hard delete exists; the record and its id are kept forever, and queries hide
  it by default. Transitioning a cancelled task to any status restores it
  (the reason is cleared).
- `done` ⇔ `meta.completed_at` present.
- `blocked` means "may resume"; `cancelled` means "will not happen".

Carry-over: a task that outlives its period is not moved — recreate it in the
next period under a new id and note the mapping in `result.md`.

## auth.yaml

Not plan data and not validated by the gate; managed by `aira keygen` /
`aira admin` and the `/api/keys` endpoints. Stores only hashes:

```yaml
keys:
  - name: pc1
    sha256: <hex digest of the key>
    created_at: 2026-08-18 05:49:35
admin:
  username: admin
  salt: <hex>
  sha256: <hex digest of salt + password>
  created_at: 2026-08-18 06:02:11
```

A key or password is shown once at creation and cannot be recovered — reissue
instead.
