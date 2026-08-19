# Operations runbook — home server

Day-2 operations for the always-on Windows server. First-time install lives in
the README ("Deploy — Windows home server"); this page is what you need after
that. The server runs as the Task Scheduler task **"AIRA Server"** and deploys
**release tags only** — pushing to main changes nothing on the server.

## Deploying a release

On a dev PC:

```powershell
# bump version in backend/pyproject.toml, commit, then:
git tag -a vX.Y.Z -m "..."
git push origin main vX.Y.Z
```

On the server — **order matters: stop the task before `uv sync`**. While the
server runs, `aira.exe` in the venv is locked and sync fails with
`os error 32` ("file in use"), leaving the old version installed:

```powershell
schtasks /End /TN "AIRA Server"
cd <path-to-project-aira>
git checkout -- backend/uv.lock   # uv sync may have dirtied it; a dirty tree blocks checkout
git fetch --tags
git checkout vX.Y.Z          # detached HEAD is expected
cd backend
uv sync
schtasks /Run /TN "AIRA Server"
```

The server never commits, so discarding its local `uv.lock` drift is always
safe.

Verify: `GET /api/server` should report the new version (or check the version
under the logo in the dashboard sidebar).

The frontend needs no build step on the server — `frontend/dist` is committed,
and the backend serves it from the checkout.

## After a reboot

The task is registered to start at boot; nothing to do. If the dashboard is
unreachable, check:

```powershell
schtasks /Query /TN "AIRA Server" /FO LIST   # Status should be Running
schtasks /Run /TN "AIRA Server"              # start it if not
```

A restart (reboot or task restart) clears all dashboard sessions — everyone
signs in again. API keys are unaffected.

## API keys

Preferred: the dashboard **Settings** screen (list, issue, revoke) — requires
the dashboard login; API keys themselves cannot manage keys. CLI equivalent on
the server:

```powershell
uv run aira keygen <machine-name>    # prints the key once
```

Revoking a key cuts that machine off immediately. A key cannot be shown again —
if one is lost, revoke it and issue a new one. Note `aira serve` refuses to
start with zero keys, so the first key always comes from the CLI.

## Dashboard login

Reset (or create) the admin credential on the server:

```powershell
uv run aira admin <username>         # prompts for the password without echo
```

There is one credential; setting it replaces the previous one.

## Backup

Everything lives in the data root (`C:\Users\<user>\AppData\Local\Frony\FronyBoard\data`,
as set via `AIRA_DATA_DIR` in the launcher script): `projects/` (all plan data) and `auth.yaml`
(key/admin hashes). Copy that directory and the backup is complete — the repo
checkout is reproducible from git and holds no state.

## Known failure modes

| symptom | cause | fix |
|---|---|---|
| `uv sync` fails with `os error 32` | server still running while syncing | `schtasks /End` first (see above), re-run sync, restart |
| `git checkout vX.Y.Z` refuses ("local changes") | `uv sync` dirtied `backend/uv.lock` | `git checkout -- backend/uv.lock`, then check out the tag |
| everyone logged out of the dashboard | server restarted — sessions are in-memory | sign in again; expected |
| `aira serve` exits with "no API keys yet" | fresh data root | `uv run aira keygen <name>` once, then start |
| server starts with empty data (all projects gone) | task runs as SYSTEM, whose `%LOCALAPPDATA%` is the system profile — the default root resolved elsewhere | set `AIRA_DATA_DIR` to the absolute data path in the launcher script |
| dashboard loads but data errors | version mismatch: old backend serving a newer dist (or vice versa) after a partial deploy | redo the deploy sequence — checkout and sync must both complete |
