# Access channels and how each one authenticates

Every request that reaches plan data — MCP or the JSON API — carries one
`Authorization: Bearer <token>` header, checked in one place
(`BearerAuthMiddleware`, `backend/src/aira/auth.py`). Channels differ only in
**how the token is obtained** and **which network path they arrive on**.

| # | channel | reaches the server via | token | how it is obtained | lifetime |
|---|---|---|---|---|---|
| 1 | Agent CLIs — Claude Code, Codex, any MCP client that can set a header | tailnet, `http://<server>:8642/mcp` | API key `frony_…` | `aira keygen <machine>` on the server, pasted into the client config once | until revoked |
| 2 | Claude Desktop (local MCP config) | tailnet, through the `mcp-remote` bridge | API key `frony_…` | same key as 1 | until revoked |
| 3 | Dashboard in a browser | tailnet, `http://<server>:8642/` | session `fbsession_…` | `POST /api/login` with the admin id/password | until the server restarts |
| 4 | Hosted apps — Claude app (mobile/web connector), ChatGPT connector | public internet, `https://<funnel-name>/mcp` | OAuth access `fbat_…` (+ refresh `fbrt_…`) | one browser login on the approval page; the app manages the tokens afterwards | 24 h, refreshed silently for 90 days |
| 5 | Local `aira` (stdio) | none — same machine, process pipe | — | — | — |

The tailnet itself is the first gate for 1–3: a device that is not enrolled in
Tailscale cannot reach `<server>` at all. Channel 4 is the only one open to the
internet, and only the `/mcp` + OAuth paths are exposed (see
[operations.md](operations.md#hosted-mcp-clients-tailscale-funnel--oauth)).

Whatever the channel, the tool log records who called (`caller` in
`tools.jsonl`): `key:<name>`, `session:<user>`, `oauth:<app>:<user>`, or
`stdio` — see [logging.md](logging.md).

## 1. Agent CLIs (API key)

```
you, on the server          client machine                 server
─────────────────           ──────────────                 ──────
aira keygen macbook ──key──▶ stored in the MCP config
                             every request:
                             Authorization: Bearer frony_… ──▶ sha256(key) ∈ Frony\auth.yaml? → ok, caller=key:macbook
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

A key is a **device** credential, not a FronyBoard one: it is stored in the
Frony-wide file `%LOCALAPPDATA%\Frony\auth.yaml` (`FRONY_AUTH_FILE`
overrides) and any Frony service on the same machine accepts it by doing the
same check. To add a service, read the file per request and compare
`sha256(bearer)` against the list — no shared code needed:

```yaml
keys:
- name: frony-pc            # label = the device
  sha256: <hex digest>      # of the full "frony_…" string
  created_at: 2026-08-18 05:49:35
```

Issue and revoke through FronyBoard (`aira keygen`, dashboard Settings); the
change is visible to every service on the next request. Older `aira_…` keys
keep working — only the hash is compared.

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

The credential is set on the server with `aira admin <username>` (one
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
                                                 ⑤ /oauth/login approval page ──────────────────────▶ id/password, approve
                                                 ⑥ one-time code, redirect to the app's redirect_uri ─▶
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
- Tokens are stored as SHA-256 hashes in `<data root>/oauth.yaml`, like API
  keys. To sign one app out, disconnect it in the app or delete its `grants`
  entry; the next request fails and the app asks you to log in again.
- The approval page shares the login lockout with channel 3 (5 failures / 15
  min per address; all Funnel traffic counts as one address, so an attack locks
  the public page, never the tailnet).
- Setup: `AIRA_PUBLIC_URL=https://<funnel-name>` on the server (or
  `aira serve --public-url`), Funnel exposing `/mcp`, `/.well-known`,
  `/register`, `/authorize`, `/token`, `/revoke`, `/oauth`. In the app, add
  `https://<funnel-name>/mcp` as a custom connector.

## 5. Local stdio

`claude mcp add FronyBoard -- uv run --directory <repo>\backend aira` runs the
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
