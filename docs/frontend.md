# Frontend

**When to read**: when changing a dashboard page, the data loading, or a UI-only feature such as the header search
**Code**: `frontend/src/`
**Related**: [http-api](http-api.md), [architecture](architecture.md), [testing](testing.md)

---

## Stack and build

React 18 + Vite + TypeScript, no router library; `App.tsx` switches pages by state. `npm run build` runs `tsc -b` then `vite build` into `frontend/dist`, which is **committed** and served by the backend at `/` (see [architecture](architecture.md)). `npm run dev` proxies `/api` to a local `fronyboard serve`; override the target with `AIRA_API=http://<server>:8642`. Tests: `npm test` (vitest, see [testing](testing.md)).

## Layout

| File | Role |
|---|---|
| `App.tsx` | Login screen, header (project switcher, search bar, info button), page switch, `openFromSearch` |
| `pages/Dashboard.tsx` | All-projects overview: cards with progress, favorites, latest update |
| `pages/Projects.tsx` | One project: roadmap card (`goal / now / target / checklist`, year stepper), period stepper, task table with filter/sort menus, phone layout and info sheet |
| `pages/Settings.tsx` | Server info, API key list (issue / revoke through `/api/keys`) |
| `TaskPanel.tsx` | Task detail side panel: markdown content, branch, timestamps |
| `SearchBar.tsx` | Header search input and result dropdown / phone overlay |
| `search.ts` | Client-side matching (`searchTasks`, `snippetOf`) |
| `shared.tsx` | `useBoardData`, `useApi`, `useIsPhone`, `useFavorites`, status tables, sort helpers, time formatting, chips |
| `api.ts` | Session token storage, `login` / `logout`, `api` (GET) and `apiSend` (POST / DELETE / PATCH) |
| `types.ts` | Response shapes: `BoardData`, `Task`, `Roadmap`, `Overview`, `ServerInfo`, … |
| `markdown.ts` | Minimal markdown parser for task content |
| `styles.css` | All styling; phone breakpoints via media queries |

## Data loading and state

`useBoardData` fetches the whole board in one call to `/api/board` (server facts, projects, and per project status / roadmap / tasks with content) after login and on the one-minute refresh, and holds it in memory; pages filter that object rather than fetching per view. The first load is two calls: `/api/board?content=0` paints the board without task content, then the full board replaces it (TaskPanel and the header search need content). A `401` clears the session and returns to the login screen. Server time and timezone come from the `server` part of that response.

Load cost (AIR-072, measured from a dev PC over Tailscale, 7 active projects, 351 tasks): before, 23 requests totalling 130 KB, about 2.1 s when run in sequence; the first `/api/board` (v0.26.0) still took 1.6 s. Two server-side costs made up most of it: a fresh `httpx.AsyncClient` per FronyAuth call, about 200 ms each (v0.26.1 keeps one per event loop), and the board reaching every project's state five times through the per-project reads plus a WAL switch and schema pass on every SQLite connection (v0.27.1: `service.board()` loads each project once, `store.connect()` prepares a database once per process). After: the light board answers in about 170 ms and the full board (190 KB gzipped) in about 270 ms. Task content stays in the full payload on purpose: the header search matches on it client-side.

The only write the dashboard performs is the checklist toggle: `PATCH /api/projects/{key}/years/{year}/checklist/{index}` with `{done}`, applied optimistically in `useFocus` (`pages/Projects.tsx`).

localStorage keys: `fb.favorites` (starred projects), `fb.recentSearches` (last 4 queries). Both are per-browser conveniences; nothing else is persisted client-side.

## Header search (AIR-032)

A frontend-only feature. There is no search API; `searchTasks(data, query)` in `search.ts` scans the already-loaded `BoardData`. The MCP tool `search_tasks` mirrors these rules server-side for agents.

Matching:

- Case-insensitive substring match on project key, task id, title and content. Branch and tags are **not** searched (pinned by `test/search.test.ts`).
- Scope is every project and every period, including closed periods and cancelled tasks.
- A matching project key includes all of that project's tasks.
- Results are grouped by project; inside a group, status order (`in_progress → blocked → todo → done → cancelled`) then id.
- A ~30-character snippet (`snippetOf`) is built only when the hit is in content alone. If id or title already shows the match, snippet is `null`.

SearchBar behaviour:

- Desktop: 264px header input with a dropdown. Phone (`useIsPhone`): magnifier button opens a full-screen overlay.
- `⌘K` / `Ctrl+K` focuses the input from anywhere.
- Each group shows `PREVIEW_ROWS = 5` rows; "모두 보기" expands the group inline. Expansion resets on a new query.
- Enter picks the first result, Escape closes the panel. Recent queries appear as chips when the input is empty.

Selecting a result: `openFromSearch(key, task)` in `App.tsx` opens the project detail with a `detailFocus` carrying the task's `period` and `id`. `ProjectDetail` opens that period, `TaskTable` starts on the page containing the task and turns on the include-cancelled toggle when the task is `cancelled`, then `onOpenTask` opens the TaskPanel.
