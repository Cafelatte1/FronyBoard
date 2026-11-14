# CLAUDE.md
FronyBoard: a project-tracker MCP server whose first-class user is an AI agent, with a web dashboard for humans, published to PyPI, the MCP Registry and Glama. Plan data is not in this repo: it lives in the server's data root (`%LOCALAPPDATA%\Frony\FronyBoard\data`, moved with `AIRA_DATA_DIR`).
Stack: `backend/`, a Python uv project (MCP server, SQLite store, ASGI web API), serves the build of `frontend/` (React + Vite), so there is one deploy.
## Commands
- Test: `uv run --directory backend pytest` · `cd frontend; npm test`
- Servers: `uv run --directory backend fronyboard` (stdio); `… fronyboard serve` (HTTP, needs FronyAuth); `… fronyboard serve --local` (loopback dashboard, no auth)
- Frontend build: `cd frontend; npm run build` — `frontend/dist` is committed, the home server only pulls
- Deploy: release tags only, pushing to main changes nothing. Push `vX.Y.Z` (publish.yml releases it to PyPI, the MCP Registry and GitHub), then run `scripts\deploy.ps1 -Tag vX.Y.Z` on the home server (Task Scheduler "FronyBoard Server", port 8642; address in HomeServerInfo)
## Rules
- `docs/` holds only what the code cannot answer, the home-server runbook (`self-hosting.md`, `operations.md`); docs that described the code were deleted — do not write new ones
- Authentication is not documented here: FronyAuth (project-auth) is its single owner
## FronyBoard
This project is tracked by FronyBoard (project key: AIR); manage tasks through its MCP tools. Tags: `frontend` / `backend` / `infra` / `docs`, plus `design` or `test`.
