---
paths:
  - "scripts/**"
  - ".github/**"
  - "server.json"
  - "backend/pyproject.toml"
---
# Server scripts and release
- `scripts/` is the server-side PowerShell — `deploy.ps1`, `register-task.ps1`, `bootstrap-server.ps1`, `configure_mcp_settings.ps1` — and `fronyboard-server.cmd.example`, whose real launcher is git-ignored
- A change to the deploy or the server setup updates `docs/self-hosting.md` and `docs/operations.md`, the home-server runbook, in the same branch
- `.github/workflows/publish.yml` publishes to PyPI and the MCP Registry only when the tag matches `backend/pyproject.toml` and `server.json`, then creates the GitHub release that Glama's Auto-Release rebuilds the listing from
- Server keys come from `fauth keygen` or the dashboard Settings page
