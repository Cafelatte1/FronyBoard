# Access channels and how each one authenticates

**When to read**: when changing how a request is authenticated (API key, dashboard session, OAuth) or which access channel serves it
**Code**: `backend/src/fronyboard/auth.py`, `backend/src/fronyboard/fauth.py`
**Related**: [operations](operations.md), [logging](logging.md)

---

Every request that reaches plan data — MCP or the JSON API — carries one
`Authorization: Bearer <token>` header, checked in one place
(`BearerAuthMiddleware`, `backend/src/fronyboard/auth.py`). Since v0.18.0 (AIR-056)
the middleware does not judge keys or OAuth tokens itself: it asks **FronyAuth**
(project-auth repo, same machine, `:8640`) via `POST /introspect` and caches the
verdict briefly (`backend/src/fronyboard/fauth.py`; contract: project-auth's
`docs/introspection.md`). Only dashboard session tokens stay local. Channels
differ only in **how the token is obtained** and **which network path they
arrive on**.

| # | channel | reaches the server via | token | how it is obtained | lifetime |
|---|---|---|---|---|---|
| 1 | Agent CLIs — Claude Code, Codex, any MCP client that can set a header | tailnet, `http://<server>:8642/mcp` | API key `frony_…` | `fauth keygen <machine>` on the server (or dashboard Settings), pasted into the client config once | until revoked |
| 2 | Claude Desktop (local MCP config) | tailnet, through the `mcp-remote` bridge | API key `frony_…` | same key as 1 | until revoked |
| 3 | Dashboard in a browser | tailnet, `http://<server>:8642/` | session `fbsession_…` | `POST /api/login` with the admin id/password | until the server restarts |
| 4 | Hosted apps — Claude app (mobile/web connector), ChatGPT connector | public internet, `https://<funnel-name>/board/mcp` | OAuth access `fbat_…` (+ refresh `fbrt_…`) | one browser login on the approval page; the app manages the tokens afterwards | 24 h, refreshed silently for 90 days |
| 5 | Local `fronyboard` (stdio) | none — same machine, process pipe | — | — | — |

The tailnet itself is the first gate for 1–3: a device that is not enrolled in
Tailscale cannot reach `<server>` at all. Channel 4 is the only one open to the
internet, and only the `/mcp` + OAuth paths are exposed (see
[operations.md](operations.md#hosted-mcp-clients-tailscale-funnel--oauth)).

Whatever the channel, the tool log records who called (`caller` in
`tools.jsonl`): `key:<name>`, `session:<user>`, `oauth:<app>:<user>`, or
`stdio` — see [logging.md](logging.md).

## 1. Agent CLIs (API key)

```
you, on the server           client machine                 server                    FronyAuth (:8640)
─────────────────            ──────────────                 ──────                    ─────────────────
fauth keygen macbook ──key──▶ stored in the MCP config
                             every request:
                             Authorization: Bearer frony_… ──▶ POST /introspect ────▶ sha256(key) ∈ Frony\auth.yaml?
                                                               (verdict cached 60s) ◀─ {active, caller=key:macbook}
```

- Claude Code: `claude mcp add --transport http --scope user FronyBoard http://<server>:8642/mcp --header "Authorization: Bearer <key>"`
- Codex CLI: in `~/.codex/config.toml`
  ```toml
  [mcp_servers.FronyBoard]
  url = "http://<server>:8642/mcp"
  bearer_token_env_var = "FRONY_KEY"          # export FRONY_KEY=frony_…
  ```
- Anything else that speaks MCP streamable HTTP and can add a header works the
  same way. One key per machine; revoke from the dashboard Settings screen or
  `DELETE /api/keys/<name>` — it stops working on the next request.

### The shared key registry

A key is a **device** credential, not a FronyBoard one. FronyAuth owns the
registry (`%LOCALAPPDATA%\Frony\auth.yaml` on its machine) and is the only
process that reads it; every Frony service — FronyBoard included, on any
machine — accepts the same key by asking FronyAuth's `POST /introspect`
(project-auth `docs/introspection.md` is the contract a new service implements).

Issue and revoke with `fauth keygen` or the FronyBoard dashboard Settings
screen (which proxies FronyAuth's /keys API); a revoke is visible to every
service within its verdict-cache TTL (≤60s; FronyBoard's own Settings clears
its cache immediately). Older `aira_…` keys keep working — only the hash is
compared.

## 2. Claude Desktop (API key through a bridge)

Claude Desktop's own "connectors" go through claude.ai (that is channel 4). To
use the tailnet address instead, register a local MCP entry that bridges to the
remote server and adds the header:

```json
{ "mcpServers": { "FronyBoard": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "http://<server>:8642/mcp",
           "--header", "Authorization: Bearer frony_…"]
} } }
```

Same key rules as channel 1.

## 3. Dashboard (session)

```
browser                                  server
───────                                  ──────
POST /api/login {username, password} ──▶ salted sha256 == auth.yaml admin? → fbsession_… (memory only)
every /api request: Bearer fbsession_… ──▶ token in the session table? → ok, caller=session:admin
POST /api/logout                     ──▶ dropped
```

The credential is set on the server with `fauth admin <username>` (FronyAuth
owns it; FronyBoard delegates the check via `POST /admin/verify`, lockout included) (one
credential; setting it replaces the previous one). Sessions are in memory, so a
restart signs everyone out. Five failed logins from one address within 15
minutes lock that address out (`429`) until the window passes. Key management
(`/api/keys`) accepts a session token only — an agent's API key cannot mint or
revoke keys.

## 4. Hosted apps (OAuth 2.1)

The Claude and ChatGPT apps do not connect from your device: the vendor's
servers connect on the app's behalf, so they cannot reach the tailnet and
cannot attach a static key. They use OAuth instead — a way to give the app its
own temporary key without ever handing it your password.

```
app / vendor server                              home server (Funnel)                      you (browser)
───────────────────                              ────────────────────                      ─────────────
① POST /mcp (no token)                       ──▶ 401 + WWW-Authenticate: resource_metadata=…
② GET /.well-known/oauth-authorization-server ──▶ where /authorize, /token, /register are
③ POST /register  "I am Claude, send me back to <redirect_uri>" ──▶ client_id (+ secret) stored in oauth.yaml
④ open browser at /authorize?client_id&code_challenge&state ─────────────────────────────────────────▶
                                                 ⑤ /oauth/login approval page ──────────────────────▶ id/password, approve (or deny)
                                                 ⑥ one-time code, hand the browser back to the app's redirect_uri ─▶
◀─ ⑦ code ──────────────────────────────────────────────────────────────────────────────────────────
⑧ POST /token  code + code_verifier          ──▶ PKCE check → access fbat_ (24 h) + refresh fbrt_ (90 d)
⑨ POST /mcp  Bearer fbat_…                   ──▶ sha256 ∈ oauth.yaml grants, not expired → ok, caller=oauth:Claude:admin
⑩ after 24 h: POST /token  refresh_token     ──▶ both tokens rotated; the old pair stops working
```

What to know:

- The password is typed only on the server's own approval page (⑤). The vendor
  sees nothing but `fbat_…` tokens.
- PKCE (④ `code_challenge` ↔ ⑧ `code_verifier`) means a stolen code cannot be
  turned into tokens by anyone but the app that started the flow.
- Tokens are stored as SHA-256 hashes in the Frony-wide
  `%LOCALAPPDATA%\Frony\oauth.yaml` (`FRONY_OAUTH_FILE` overrides), like API
  keys. To sign one app out, disconnect it in the app or delete its `grants`
  entry; the next request fails and the app asks you to log in again.
- The approval page shares the login lockout with channel 3 (5 failures / 15
  min per address; all Funnel traffic counts as one address, so an attack locks
  the public page, never the tailnet). It counts attempts on the form
  (`(2/5)`), and the fifth strike shows the lockout screen at once.
- Denying (`POST /oauth/deny`) drops the request and sends the app
  `error=access_denied`; nothing is issued. After approve or deny the page shows
  a result screen for a second, then hands the browser back on its own. The
  page is server-rendered by FronyAuth (`oauth_pages.py` in project-auth) with
  no third-party assets — it is public and must render in any in-app browser;
  FronyAuth serves its `/fonts` and `/favicon.ico` itself.
- Setup: FronyAuth runs with `FAUTH_PUBLIC_URL=https://<funnel-name>`; fronyboard
  runs with `FRONYBOARD_PUBLIC_URL`/`FRONYBOARD_PUBLIC_MCP_PATH=/board/mcp` so its 401s
  point at the metadata. Funnel exposes `/board/mcp` (+ legacy `/mcp`) to fronyboard
  and `/.well-known`, `/register`, `/authorize`, `/token`, `/revoke`, `/oauth`,
  `/fonts`, `/favicon.ico` to FronyAuth. In the app, add
  `https://<funnel-name>/board/mcp` as a custom connector. The issuer is the
  root; every service, FronyBoard included, sits under its own prefix.

### Other Frony services behind the same login

FronyAuth is the only authorization server; a sibling service (FronyHome, …)
that wants to be a connector too does not run OAuth itself. It gets its own
Funnel path (on whatever machine it runs) and verifies tokens through
FronyAuth's `POST /introspect` — the same call it already makes for API keys,
so being on a different machine is fine.

```
tailscale funnel --bg --set-path /cache http://127.0.0.1:9412     # https://<funnel-name>/cache/* -> the service
```

The service then needs three things, all on the public prefix it was given
(`PUBLIC_URL=https://<funnel-name>/cache`):

1. `401` on `/mcp` without a valid bearer, carrying
   `WWW-Authenticate: Bearer resource_metadata="<PUBLIC_URL>/.well-known/oauth-protected-resource/mcp"`.
2. That metadata document, pointing at FronyBoard as the issuer:
   ```json
   {"resource": "<PUBLIC_URL>/mcp", "authorization_servers": ["https://<funnel-name>"],
    "bearer_methods_supported": ["header"], "resource_name": "FronyCache"}
   ```
3. For a bearer starting with `fbat_`: `sha256(bearer)` equals some
   `grants[].access_sha256` in `%LOCALAPPDATA%\Frony\oauth.yaml` and
   `access_expires_at` is in the future → accepted; the caller is
   `oauth:<clients[client_id].client_name>:<subject>`. Anything else → `401`
   with the header from step 1. API keys keep working next to this.

The app follows the header to the metadata, finds FronyBoard, registers and
logs in there exactly as in the diagram above, and comes back with a token the
service recognises. One login per app, every Frony service — the token is a
device-style credential like the key, not a per-service one. The
`resource` the app names during authorization is recorded with the code but
not enforced.

## 5. Local stdio

`claude mcp add FronyBoard -- uv run --directory <repo>\backend fronyboard` runs the
server as a child process on the same machine. There is no network and no
token; the log records `caller: stdio`.

## Why three token types instead of one

- API keys fit machines you control: you can paste a header, and revocation is
  one line in a file.
- Sessions fit a browser: the credential is a password, and losing the session
  on restart is acceptable for a read-only dashboard.
- OAuth fits third-party servers: they cannot hold your key or password, so
  they get a scoped, expiring token issued after you approve once.

All three end in the same middleware and the same yaml-hash comparison; there
is no separate identity service to run. Device identity for 1–3 comes from
Tailscale itself.
