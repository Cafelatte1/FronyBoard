# Docs template for Frony service repos

**When to read**: when setting up or auditing the `docs/` folder of a Frony service repo (project-aira, project-shop, project-wallet, project-file)
**Code**: —
**Related**: [INDEX](template_INDEX.md), [CLAUDE](template_CLAUDE.md), [logging-spec](template_logging-spec.md)

---

## Why

Agents read docs by task, not cover to cover. Each file answers one question ("how is a request authenticated?") and says up front when it is worth opening. English only: cheaper in tokens, and it matches the code.

## Layout

| File | Every repo | Holds |
|---|---|---|
| `CLAUDE.md` (repo root) | yes | The 30-second brief: what, where, commands, deploy, FronyBoard key. Links to `docs/INDEX.md`. The same text works as `AGENTS.md`. |
| `docs/INDEX.md` | yes | One row per doc: name + when to read. |
| `docs/architecture.md` | yes | Components, request/data flow, where things live, decisions not obvious from the code. |
| `docs/testing.md` | yes | How to run, layout, fixtures, known failures. |
| `docs/data-model.md` | if it stores data | Storage layout, schemas, invariants, validation rules. |
| `docs/tool-surface.md` | if it is an MCP server | Tools by group, `instructions=` policy, what belongs in a docstring. |
| `docs/http-api.md` | if it serves HTTP | Routes, auth per route, payload shapes, error shape. |
| `docs/auth.md` | if it authenticates | Credentials, channels, verification path (FronyAuth introspection). |
| `docs/operations.md` | if it is deployed | Host, launcher, deploy / restart / backup, incident notes. |
| `docs/logging.md` | if it logs | Files, fields, events, query recipes. Start from [logging-spec](template_logging-spec.md). |
| `docs/frontend.md` | if it has a UI | Pages, data loading, UI-only features, build. |
| `docs/archive/` | optional | Superseded docs kept for reference. Not maintained, not indexed, not linked from live docs. |

Add a domain doc only when a topic outgrows the file it lives in. Name files by topic, never by ticket.

## Archive

`docs/archive/` is where a doc goes when it stops being true but is still worth keeping. Rules:

- Nothing in `archive/` is maintained: no translation, no header block, no link fixing, no content updates.
- `INDEX.md` does not list its files. It carries one line: "Superseded docs live in `archive/`; they are not maintained."
- Live docs never link into `archive/`. If a fact there is still needed, move the fact into a live doc.
- To retire a doc, move it with `git mv` and add one line at the top: `> Archived YYYY-MM-DD: superseded by [x](../x.md)`. Change nothing else.

## Header convention

Every doc starts with this block. `When to read` is copied verbatim into `INDEX.md`, so keep it to one line.

```markdown
# Title

**When to read**: <the change or question that makes this doc worth opening>
**Code**: `<main source files>` (or `—`)
**Related**: [name](file.md), [name](file.md)

---
```

## Writing rules

- Describe current behavior. History lives in git and FronyBoard; add a dated note only when a decision needs its context.
- Reference code as `path/file.py` or `path/file.py:func`. No line numbers, they rot.
- UI strings stay in their original language, quoted. Everything else is English.
- Under ~200 lines per file. Split by topic when it grows.
- Change the doc in the same branch as the code it describes.

## Adopting in a repo

1. Copy `template_CLAUDE.md` to the repo root as `CLAUDE.md` and fill the `<...>` slots (name it `AGENTS.md` for tools that read that name).
2. Copy `template_INDEX.md` and the skeletons that apply into `docs/`, dropping the `template_` prefix.
3. Move existing notes into the matching file, translate to English, add the header block.
4. Delete sections and slots you did not fill. An empty heading is worse than none.
5. Leave `docs/archive/` as it is. Only add the one-line pointer to `INDEX.md`.
