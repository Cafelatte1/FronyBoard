---
paths:
  - "backend/**"
---
# Backend: store, validation, service, tools
- A document store in SQLite (`fronyboard.db` in the data root): each project's records sit as JSON in two tables, deliberately not normalised — at ~15 projects a relational schema would cost a rewrite of the service layer for no visible gain. Concurrency is the per-project lock (AIR-073)
- `validation.py` runs before every mutation, and an error rejects the write
- ids and timestamps are issued by the server, never invented by an agent — it keeps the record trustworthy
- Soft delete only: tasks are cancelled, projects archived, since history is input to the retrospective
- A task is a title, not a document: agents read titles and status and never a long body, so `content` is one line for the one fact the code cannot give, there are no months, weeks or prd, and `get_status` (overview plus open tasks) is the whole resume; time is `meta.completed_at` (AIR-086)
- A milestone is planning, not a prerequisite: `create_task` opens the current quarter by itself and `open_period` opens any other without a milestone. Only the current quarter opens implicitly, so a typo or a far-off period still takes a deliberate `open_period` (AIR-095)
- No credential is judged here: `BearerAuthMiddleware` hands every key and OAuth token to FronyAuth's `/introspect` (`FRONY_AUTH_URL`, `FRONY_SERVICE_KEY`) and caches the verdict, so a revoked device key dies everywhere at once; only dashboard sessions stay local, and without FronyAuth nothing authenticates (AIR-056)
- `server.py` is the MCP tool surface and the CLI (stdio / `serve`), `web.py` the dashboard's `/api/*` JSON and the static `frontend/dist`; the integration tests drive the ASGI app with a fake FronyAuth
