---
paths:
  - "frontend/src/**"
  - "frontend/test/**"
  - "frontend/public/**"
  - "frontend/index.html"
  - "frontend/vite.config.ts"
---
# Dashboard
- UI mocks live in the Claude Design project "FronyBoard" as `FronyBoard_YYYYMMDD.dc.html`, the latest date winning. Read them with the DesignSync tool and projectId `2290d769-da3c-4fcb-846e-25d0045d8c88` (`list_files` / `get_file`) — `list_projects` shows only the design-system project, and `/design-login` must be approved once per session
- `frontend/dist` is committed and served by the backend, since the home server only pulls: a frontend change ships only with `npm run build` and the rebuilt `dist`
- Tests are vitest, in `frontend/test/`
