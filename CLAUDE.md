# CLAUDE.md

## Project

FronyBoard: a project-tracker MCP server whose first-class user is an AI agent, with a web dashboard for humans.
Plan data is not in this repo. It lives in the server's data root (`%LOCALAPPDATA%\Frony\FronyBoard\data`, moved with `AIRA_DATA_DIR`).

## Layout

- `backend/` — MCP server (uv project, Python)
  - `src/aira/store.py` — file IO, data root
  - `src/aira/validation.py` — schema and rule gate; runs before every mutation, an error rejects the write
  - `src/aira/service.py` — operations; per-project lock, timestamps stamped by the server
  - `src/aira/server.py` — MCP tool surface + CLI (stdio / `serve`)
  - `src/aira/web.py` — `/api/*` JSON for the dashboard, static serving of `frontend/dist`
  - `test/unit/`, `test/integration/` — pytest; integration drives the ASGI app with a fake FronyAuth
- `frontend/` — FronyBoard dashboard (React + Vite). Build output is served by the backend, so there is one deploy. `test/` is vitest.
- `scripts/` — server-side PowerShell: `deploy.ps1`, `register-task.ps1`, `aira-server.cmd.example` (the real launcher is git-ignored), `bootstrap-server.ps1`, `configure_mcp_settings.ps1`
- Folder rules for every Frony repo: `docs/templates/template_LAYOUT.md`.

## Commands (from the repo root)

- Test: `uv run --directory backend pytest` · `cd frontend; npm test`
- Local server (stdio): `uv run --directory backend aira`
- HTTP server: `uv run --directory backend aira serve` (needs FronyAuth, see Deploy)
- Frontend build: `cd frontend; npm run build` — **`frontend/dist` is committed** (the home server only pulls)

## Deploy

Runs on the home server (Tailscale `100.67.93.87:8642`) as the Task Scheduler task "AIRA Server". "FronyAuth Server" (`:8640`, the project-auth repo) on the same machine does all bearer verification through introspection (`FRONY_AUTH_URL` / `FRONY_SERVICE_KEY`, v0.18.0+); without it nothing authenticates.
The server deploys **release tags only** (`vX.Y.Z`); pushing to main changes nothing.
Procedure: push the tag, then on the server run `scripts\deploy.ps1 -Tag vX.Y.Z` (README, Deploy section). Keys come from `fauth keygen` or the dashboard Settings page.

## Docs

`docs/INDEX.md` lists every doc with when to read it. Read the matching doc before changing auth, schema, tools, routes or deploy, and update it in the same branch. `docs/templates/` holds the docs conventions shared with the other Frony repos.

## Design mocks

UI mocks live in the Claude Design project "FronyBoard"; artboard files are `FronyBoard_YYYYMMDD.dc.html`, latest date wins.
Read them with the DesignSync tool: projectId `2290d769-da3c-4fcb-846e-25d0045d8c88`, `list_files` / `get_file`.
`list_projects` only shows the design-system project, so use this projectId directly; `/design-login` must be approved once per session.

## FronyBoard

This project is tracked by FronyBoard (project key: AIR).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: `frontend` / `backend` / `infra` / `docs` for where the work lands, plus
`design` or `test` for what kind it is. Reuse these rather than coining a synonym.
