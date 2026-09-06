# Repository layout for Frony services

**When to read**: when starting a new Frony service repo, adding a top-level folder, or moving tests / scripts / manifests
**Code**: —
**Related**: [README](template_README.md) (docs conventions), [CLAUDE](template_CLAUDE.md) (where the layout is summarised per repo)

---

Every Frony service that has both a server and a UI uses this tree. The point is that an agent moving between repos knows where things are without reading `CLAUDE.md` first. Single-package repos without a UI (FronyAuth) are out of scope.

## Tree

```
<repo>/
├─ CLAUDE.md  AGENTS.md  README.md  .gitignore
├─ docs/                       # per docs/templates/template_README.md
│  └─ archive/                 # optional, frozen
├─ scripts/                    # PowerShell only, run on the server or a dev PC
│  ├─ deploy.ps1               # required: checkout tag → sync deps → restart task
│  ├─ register-task.ps1        # required: create the Task Scheduler task (once per server)
│  ├─ configure_mcp_settings.ps1   # if the service is an MCP server: client-side registration
│  └─ <name>-server.cmd.example    # launcher template; the real .cmd is git-ignored
├─ backend/
│  ├─ <manifest>               # pyproject.toml + uv.lock, or package.json per package
│  ├─ src/ | core/ api/ cli/   # see Variants
│  └─ test/
│     ├─ unit/
│     ├─ integration/
│     ├─ live/                 # optional: hits real external systems, off by default
│     ├─ fixtures/             # sample data files
│     └─ conftest.py | helpers/   # shared setup
├─ frontend/
│  ├─ index.html  package.json  vite.config.ts  tsconfig.json   # or pubspec.yaml for Flutter
│  ├─ src/
│  ├─ test/
│  └─ dist/                    # build output; committed or not is decided per repo
├─ config/                     # optional: committed, non-secret policy files (e.g. policy.toml)
└─ local/                      # optional: git-ignored personal samples and notes
```

## Rules

- **Manifests live in the package folder, never at the repo root**, unless the root is itself a package manager workspace (npm `workspaces`). `backend/` and `frontend/` must each work when checked out alone: `uv run --directory backend …`, `npm --prefix frontend …`.
- **Tests live in `test/` (singular), one per package.** No `tests/`, `__tests__/`, `spec/`, and no test files inside `src/`. `backend/test/` always has `unit/` and `integration/`; `live/` only when a suite needs real external systems and is gated by an env var. `frontend/test/` is flat unless it grows past ~15 files. Shared setup goes in one place: `test/conftest.py` (pytest) or `test/helpers/` (vitest).
- **`scripts/` holds operations, not application code.** Every script is PowerShell, starts with a comment saying where it runs (server / dev PC) and what it needs. Application CLIs belong in the backend package (`backend/cli/`, `[project.scripts]`).
- **Secrets never enter the repo.** Launchers that set keys (`*.cmd`) are git-ignored; commit a `.cmd.example` with placeholder values. Same for `.env`.
- **Build output policy is explicit.** `CLAUDE.md` says whether `frontend/dist/` is committed (server has no toolchain) or built at deploy time. Either is fine; silence is not.
- **`docs/` follows the docs template**; `local/` and `docs/archive/` are the only places where unmaintained material may sit.
- **No other top-level folders** without a line in `CLAUDE.md` Layout explaining why.

## Variants

**Python backend (uv)**

```
backend/
├─ pyproject.toml  uv.lock
├─ src/<pkg>/          # one package; flat modules until a subpackage earns its place
└─ test/
   ├─ conftest.py      # fixtures shared by unit/ and integration/
   ├─ unit/            # no network, no disk outside tmp_path
   ├─ integration/     # ASGI TestClient, real store in tmp_path, fake FronyAuth
   └─ fixtures/
```

`[tool.pytest.ini_options] testpaths = ["test"]`. Run with `uv run --directory backend pytest`.

**TypeScript backend (npm workspaces)**

```
<repo>/package.json            # workspaces: backend/*, frontend; root scripts: build, test, typecheck
tsconfig.base.json  vitest.workspace.ts
backend/
├─ core/   # pure domain logic, no I/O; the others depend on it
├─ app/    # optional: the one package that knows the heavy runtime (browser, DB driver)
├─ api/    # process entry: MCP server, HTTP routes, static serving of frontend/dist
├─ cli/    # operator commands run on the server
└─ test/
   ├─ helpers/  unit/  integration/  live/
```

Dependency direction is `api → app → core`, never reversed; state it in `CLAUDE.md`. Each package has its own `package.json` and `tsconfig.json`; `vitest.workspace.ts` defines one project per test folder so `npm run test:unit` and `test:integration` are separate.

**Frontend**: Vite (React or vanilla TS) or Flutter. The folder contract is the same: `src/`, `test/`, one manifest, build output under `dist/` (Vite) or `build/` (Flutter).

## What CLAUDE.md must state

The `## Layout` section of `CLAUDE.md` lists the top-level folders with one line each, the backend dependency direction if there is more than one package, and the `dist/` commit policy. It does not repeat this document.

## Adopting in an existing repo

1. Move tests into `test/{unit,integration}` with `git mv`; update `testpaths` / `vitest.workspace.ts` / `setupFiles`; run the full suite before and after and compare the pass and fail lists.
2. Move a root `pyproject.toml` into `backend/` and fix every `uv run` invocation (scripts, Task Scheduler action, docs).
3. Add `register-task.ps1` if the task is still created by hand; add `<name>-server.cmd.example` and git-ignore the real one.
4. Update `CLAUDE.md` Layout and `docs/testing.md`, `docs/operations.md`.
5. Leave `local/` and `docs/archive/` alone.
