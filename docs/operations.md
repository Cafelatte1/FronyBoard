# Operations runbook — home server

**When to read**: when deploying, restarting, backing up or diagnosing the home-server instance
**Code**: `scripts/deploy.ps1`, `aira-server.cmd`
**Related**: [auth](auth.md), [logging](logging.md), [http-api](http-api.md)

---

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

On the server, `scripts/deploy.ps1` does the whole sequence (from a dev PC:
`ssh -i ~/.ssh/aira_homeserver flash@100.67.93.87 "powershell -NoProfile -File <path-to-project-aira>\scripts\deploy.ps1 -Tag vX.Y.Z"`).
FronyAuth deploys the same way from its own checkout (`C:\Users\flash\projects\project-auth`,
task "FronyAuth Server", its own `scripts\deploy.ps1`).
Run it as its own ssh command, not combined with anything that also mentions
`aira-server.cmd`: the process cleanup below matches command lines containing
both `aira` and `serve`, so a combined command naming the launcher would match
its own ssh session and kill it mid-deploy.

```powershell
powershell -NoProfile -File scripts\deploy.ps1 -Tag vX.Y.Z
```

It stops the task and any leftover `aira` process, discards the server's
`uv.lock` drift (the server never commits, so this is always safe), `git fetch
--tags` + `git checkout vX.Y.Z` (detached HEAD is expected), `uv sync` in
`backend/`, then starts the task and prints its status. The task is started
again even when checkout or sync fails, so a bad tag leaves the previous
version running rather than nothing. Run it without `-Tag` to only restart.

**Order matters: the task must be stopped before `uv sync`** — while the server
runs, `aira.exe` in the venv is locked and sync fails with `os error 32`
("file in use"), leaving the old version installed. The script handles this;
doing it by hand, stop first.

Verify: `GET /api/server` should report the new version (or open the dashboard
menu drawer — ☰ top-left — and check the version under the logo).

The frontend needs no build step on the server — `frontend/dist` is committed,
and the backend serves it from the checkout.

## After a reboot

The task is registered to start at boot and re-checked every 10 minutes
(a repeating trigger with `MultipleInstances = IgnoreNew`, so it is a no-op
while the server is running). It has no execution time limit and is allowed
on battery. The laptop is set so closing the lid does nothing and it never
sleeps on AC; Fast Startup is off so a power-on counts as a boot. If the
dashboard is still unreachable, check:

```powershell
schtasks /Query /TN "AIRA Server" /FO LIST   # Status should be Running
powershell -NoProfile -File scripts\deploy.ps1   # restart it if not (no -Tag = restart only)
```

A restart (reboot or task restart) clears all dashboard sessions — everyone
signs in again. API keys are unaffected.

## Hosted MCP clients (Tailscale Funnel + OAuth)

The Claude / ChatGPT apps connect from the vendor's servers, so the MCP
endpoint is also reachable from the public internet through Tailscale Funnel.
The OAuth authorization server is **FronyAuth** (project-auth, `:8640`) since
v0.18.0 — aira only advertises FronyAuth's resource metadata on a 401
(`AIRA_PUBLIC_URL` + `AIRA_PUBLIC_MCP_PATH` in `aira-server.cmd`). The public
layout is *root = auth, one prefix per service*:

    https://laptop-windows-hp-dragonflyg3.tailab9579.ts.net/board/mcp  -> http://127.0.0.1:8642/mcp  (FronyBoard)
    https://laptop-windows-hp-dragonflyg3.tailab9579.ts.net/{.well-known,register,authorize,token,revoke,oauth,fonts,favicon.ico}
                                                                       -> http://127.0.0.1:8640/*    (FronyAuth)
    https://laptop-windows-hp-gpu.tailab9579.ts.net/cache/*            -> http://127.0.0.1:9412/*    (FronyHome, its own machine)

Funnel exposes only these path prefixes — the dashboard and `/api` stay
tailnet-only:

| path | purpose |
|---|---|
| `/board/mcp` | the MCP endpoint (bearer: API key or OAuth access token) |
| `/mcp` | the same endpoint at its pre-prefix address — kept for connectors registered before 2026-08-27 |
| `/.well-known` | OAuth discovery (`oauth-authorization-server`, `oauth-protected-resource/board/mcp`) |
| `/register`, `/authorize`, `/token`, `/revoke` | OAuth endpoints (MCP SDK) |
| `/oauth` | the approval page (`/oauth/login`, `/oauth/deny`) — asks for the dashboard login |

Flow: the app finds the metadata, registers itself, sends the browser to
`/oauth/login`, and exchanges the code for tokens. Access tokens last 24 h and
refresh silently for 90 days; after that the app asks for the login again.
Clients and token hashes live in the Frony-wide `Frony\oauth.yaml` (next to the key
registry; `FRONY_OAUTH_FILE` overrides, and the launcher pins it for the SYSTEM
account like `FRONY_AUTH_FILE`) — delete a `grants` entry to sign one app out, or
disconnect the connector in the app. Other Frony services exposed on their own
Funnel path (`--set-path /cache http://127.0.0.1:9412`) verify the same tokens
from that file instead of running OAuth themselves — see
[auth.md](auth.md#other-frony-services-behind-the-same-login). Five failed
logins from one address (all Funnel traffic counts as one address) lock the
login for 15 minutes; the same limit guards `/api/login`.

The Funnel config is stored by tailscaled and survives reboots. Prerequisites
on the admin console (done 2026-08-27): `nodeAttrs` grants `funnel` to
`autogroup:member`, and DNS -> HTTPS Certificates is enabled.

```powershell
$ts = "C:\Program Files\Tailscale\tailscale.exe"
& $ts funnel status
foreach ($p in "/.well-known", "/register", "/authorize", "/token", "/revoke", "/oauth", "/fonts", "/favicon.ico") {
    & $ts funnel --bg --set-path $p "http://127.0.0.1:8640$p"     # FronyAuth (re-)enable
}
& $ts funnel --bg --set-path /board/mcp http://127.0.0.1:8642/mcp   # FronyBoard
& $ts funnel --bg --set-path /mcp http://127.0.0.1:8642/mcp         # pre-prefix address, old connectors
& $ts funnel --https=443 off                                      # close everything
```

Gotcha: the stored funnel config is keyed by the machine's DNS name at the time
it was written — after a machine rename, `--set-path <p> off` reports "handler
does not exist". `tailscale serve reset` and re-add instead.

## API keys

Preferred: the dashboard **Settings** screen (list, issue, revoke) — requires
the dashboard login; API keys themselves cannot manage keys. Since v0.18.0 the
dashboard proxies these to FronyAuth's /keys API. CLI equivalent on the server
(project-auth checkout):

```powershell
uv run fauth keygen <machine-name>   # prints the key once
```

Keys sit in the Frony-wide registry `C:\Users\<user>\AppData\Local\Frony\auth.yaml`,
one level above the FronyBoard data root, so the same key opens every Frony
service on this machine. The scheduled task runs as SYSTEM, whose
`LOCALAPPDATA` is the system profile, so the launcher (`aira-server.cmd`) pins
both `AIRA_DATA_DIR` and `FRONY_AUTH_FILE` explicitly — any other Frony service
started the same way must point at the same file. Revoking a key cuts that
machine off immediately. A key cannot be shown again —
if one is lost, revoke it and issue a new one. Note `aira serve` refuses to
start with zero keys, so the first key always comes from the CLI.

## Dashboard login

Reset (or create) the admin credential on the server (FronyAuth owns it since
v0.18.0 — project-auth checkout):

```powershell
uv run fauth admin <username>        # prompts for the password without echo
```

There is one credential; setting it replaces the previous one.

## Backup

Everything lives in the data root (`C:\Users\<user>\AppData\Local\Frony\FronyBoard\data`,
as set via `AIRA_DATA_DIR` in the launcher script): `projects/` (all plan data) and `auth.yaml`
(admin hash) — plus the Frony-wide files one level up, `Frony\auth.yaml` (API keys) and
`Frony\oauth.yaml` (hosted-app clients/tokens). Copy `Frony\` and the backup is complete — the
repo checkout is reproducible from git and holds no state.

## Known failure modes

| symptom | cause | fix |
|---|---|---|
| `uv sync` fails with `os error 32` | server still running while syncing — `schtasks /End` returns before the python child actually exits | wait until no `aira serve` process remains (`Get-CimInstance Win32_Process` filtered on the command line; force-stop after ~20s), then sync and `/Run`. A `/Run` while the old process lives is silently ignored (`IgnoreNew`), so the old version keeps serving |
| `git checkout vX.Y.Z` refuses ("local changes") | `uv sync` dirtied `backend/uv.lock` | `git checkout -- backend/uv.lock`, then check out the tag |
| everyone logged out of the dashboard | server restarted — sessions are in-memory | sign in again; expected |
| every request answers 503 "auth service unavailable" | FronyAuth down or `FRONY_SERVICE_KEY`/`FRONY_AUTH_URL` wrong in `aira-server.cmd` | check `GET :8640/health`, restart "FronyAuth Server" task, verify the launcher env |
| `fauth serve` exits with "no API keys yet" | fresh registry | `uv run fauth keygen <name>` once, then start |
| task-panel timestamps show `UTC+9` instead of `KST` (or a wrong zone) | the SYSTEM account's locale gives no short zone name / a different zone | set `AIRA_TZ=Asia/Seoul` in the launcher script next to `AIRA_DATA_DIR` |
| server starts with empty data (all projects gone) | task runs as SYSTEM, whose `%LOCALAPPDATA%` is the system profile — the default root resolved elsewhere | set `AIRA_DATA_DIR` to the absolute data path in the launcher script |
| server dead after closing the lid / after ~3 days | laptop slept on lid close, or the task's default 72h execution limit killed it | lid action = do nothing (`powercfg`), `ExecutionTimeLimit 0`, 10-minute watchdog trigger — all applied; re-check with `Get-ScheduledTask` if the task is ever re-created |
| dashboard loads but data errors | version mismatch: old backend serving a newer dist (or vice versa) after a partial deploy | redo the deploy sequence — checkout and sync must both complete |

## Logs

Two JSON Lines files under `%LOCALAPPDATA%\Frony\FronyBoard\logs` (next to the data
root; `AIRA_LOG_DIR` overrides), rotated daily and gzipped:

- `server.jsonl` — boot/shutdown, login and key events, HTTP 4xx/5xx, rejected tool
  calls, unhandled exceptions with `trace`. **Look here first when something is wrong.**
- `tools.jsonl` — one line per MCP tool call (who, what, which record, ms, ok).

Field reference and query recipes: [logging.md](logging.md). A tool line and its
server follow-ups share a `req` id.
