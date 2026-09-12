# CLAUDE.md

## Project

FronyBoard: a project-tracker MCP server whose first-class user is an AI agent, with a web dashboard for humans.
Plan data is not in this repo. It lives in the server's data root (`%LOCALAPPDATA%\Frony\FronyBoard\data`, moved with `AIRA_DATA_DIR`).

## Layout

- `backend/` — MCP server (uv project, Python)
  - `src/fronyboard/store.py` — SQLite store (`fronyboard.db`), data root, YAML migration
  - `src/fronyboard/validation.py` — schema and rule gate; runs before every mutation, an error rejects the write
  - `src/fronyboard/service.py` — operations; per-project lock, timestamps stamped by the server
  - `src/fronyboard/server.py` — MCP tool surface + CLI (stdio / `serve`)
  - `src/fronyboard/web.py` — `/api/*` JSON for the dashboard, static serving of `frontend/dist`
  - `test/unit/`, `test/integration/` — pytest; integration drives the ASGI app with a fake FronyAuth
- `frontend/` — FronyBoard dashboard (React + Vite). Build output is served by the backend, so there is one deploy. `test/` is vitest.
- `scripts/` — server-side PowerShell: `deploy.ps1`, `register-task.ps1`, `fronyboard-server.cmd.example` (the real launcher is git-ignored), `bootstrap-server.ps1`, `configure_mcp_settings.ps1`

## Commands (from the repo root)

- Test: `uv run --directory backend pytest` · `cd frontend; npm test`
- Local server (stdio): `uv run --directory backend fronyboard`
- HTTP server: `uv run --directory backend fronyboard serve` (needs FronyAuth, see Deploy)
- Local dashboard, no auth: `uv run --directory backend fronyboard serve --local` (loopback only)
- Frontend build: `cd frontend; npm run build` — **`frontend/dist` is committed** (the home server only pulls)

## Deploy

Runs on the home server (Tailscale, port 8642; the address is in `~/HomeServerInfo.md`) as the Task Scheduler task "FronyBoard Server". "FronyAuth Server" (`:8640`, the project-auth repo) on the same machine does all bearer verification through introspection (`FRONY_AUTH_URL` / `FRONY_SERVICE_KEY`, v0.18.0+); without it nothing authenticates.
The server deploys **release tags only** (`vX.Y.Z`); pushing to main changes nothing. Pushing a tag also runs `.github/workflows/publish.yml`, which publishes the package to PyPI and the MCP Registry after checking the tag against `backend/pyproject.toml` and `server.json`.
Procedure: push the tag, then on the server run `scripts\deploy.ps1 -Tag vX.Y.Z` (`docs/self-hosting.md`, `docs/operations.md`). Keys come from `fauth keygen` or the dashboard Settings page.

## Decisions

- **A document store in SQLite** (v0.25.0, AIR-073). Until v0.24 each project was a YAML tree; the same records now sit as JSON in two tables, so the service and validation layers were untouched while writes became atomic and backup became one file. Not normalised on purpose: at ~15 projects a relational schema would cost a rewrite of the service layer for no visible gain. Concurrency is still the per-project lock.
- **Server-issued ids and timestamps.** Agents must not invent either; it keeps the record trustworthy.
- **Soft delete only.** Tasks are cancelled, projects archived. History is input to the retrospective.
- **No credential is judged here** (v0.18.0, AIR-056). `BearerAuthMiddleware` hands every key and OAuth token to FronyAuth's `/introspect` and caches the verdict; only dashboard sessions stay local. One registry serves every Frony service, so a revoked device key dies everywhere at once.

## Docs

`docs/` holds only what the code cannot answer — running this on real machines: `self-hosting.md` and `operations.md` (home-server runbook). Update them in the same branch when deploy or the server setup changes.
Docs that only described the codebase were deleted — read the code instead. Do not write new ones.
Authentication is not documented here: FronyAuth (project-auth) is its single owner.

## Design mocks

UI mocks live in the Claude Design project "FronyBoard"; artboard files are `FronyBoard_YYYYMMDD.dc.html`, latest date wins.
Read them with the DesignSync tool: projectId `2290d769-da3c-4fcb-846e-25d0045d8c88`, `list_files` / `get_file`.
`list_projects` only shows the design-system project, so use this projectId directly; `/design-login` must be approved once per session.

## FronyBoard

This project is tracked by FronyBoard (project key: AIR).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: `frontend` / `backend` / `infra` / `docs` for where the work lands, plus
`design` or `test` for what kind it is. Reuse these rather than coining a synonym.
