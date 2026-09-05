# Logging spec — line templates and library setup

**When to read**: when a Frony service adopts the shared JSON Lines logging (tools.jsonl / server.jsonl) or changes its sink configuration
**Code**: `backend/src/aira/log.py`
**Related**: [logging](../logging.md) (field meanings, query recipes)

---
## 1. Libraries used

| Library | Version | Role |
|---|---|---|
| **loguru** | 0.7.3 (`>=0.7`) | The only logging engine. Two file sinks + (stdio mode) a stderr echo. `format="{message}"` writes the message verbatim — the message itself is one finished JSON line |
| stdlib `logging` | — | Never used directly. `InterceptHandler` intercepts the stdlib logs of uvicorn / the mcp SDK and hands them to the loguru sinks |
| `json` (stdlib) | — | `json.dumps(payload, ensure_ascii=False, default=str)` — keeps Korean text as written, unserializable values fall back to `str()` |
| `zoneinfo` (stdlib) | — | Timestamps in `AIRA_TZ` (e.g. `Asia/Seoul`); the process-local zone when unset or invalid |
| `secrets` (stdlib) | — | `token_hex(3)` → 6-hex correlation id (`req`) |

loguru sink configuration (`log.setup()`) — `root` is `%LOCALAPPDATA%\Frony\FronyBoard\logs`, the `logs/` beside the data root, changed with `AIRA_LOG_DIR`:

```python
common = {"format": "{message}", "level": "INFO", "rotation": "00:00",
          "compression": "gz", "encoding": "utf-8"}
logger.add(root / "server.jsonl", retention="30 days",
           filter=lambda r: r["extra"].get("stream") != "tools", **common)
logger.add(root / "tools.jsonl",  retention="180 days",
           filter=lambda r: r["extra"].get("stream") == "tools", **common)
if stderr:   # stdio mode only — stdout is the MCP channel, never a sink
    logger.add(sys.stderr, format="{message}", level="WARNING",
               filter=lambda r: r["extra"].get("stream") != "tools")
```

- Stream routing is done solely through the extra field of `logger.bind(stream="tools" | "server")`
- Rotation every day at 00:00, earlier dates gzipped: `tools.2026-08-26_00-00-00_000000.jsonl.gz`
- Before `setup()` there is no sink at all (`logger.remove()`) — imports, tests and CLI subcommands stay silent
- The uvicorn / uvicorn.error / uvicorn.access loggers get their handlers replaced plus `propagate=False`

## 2. Common rules

- Format: **JSON Lines**, one line = one flat JSON object, fixed field set. No human prose (the readers are agents and query tools)
- `ts`: ISO 8601 + offset, milliseconds — `2026-08-26T17:06:15.402+09:00` (unlike the naive UTC in the data files)
- Never written: raw API keys (on rejection only the first 9 chars as `prefix`), passwords, session tokens, plan prose
- Prose fields are recorded by **length only**: `content prd goal now next later result_markdown description` → `<name>_len`; `null` arguments are dropped

## 3. tools.jsonl — one MCP tool call = one line (180-day retention)

Writer: `ToolLogMiddleware` (MCP server middleware, handles `tools/call` only)

Template:
```json
{"ts":"<ISO>","req":"<6hex>","tool":"<tool name>","caller":"<who>","project":"<KEY>","period":"<YYYYQn>","task":"<KEY-NNN>","args":{...},"ms":<float>,"ok":true,"warnings":<int>}
{"ts":"<ISO>","req":"<6hex>","tool":"<tool name>","caller":"<who>","project":"<KEY>","args":{...},"ms":<float>,"ok":false,"error":"rejected|<ExceptionClass>","msg":"<≤500 chars>"}
```

Examples:
```json
{"ts":"2026-08-26T17:06:15.402+09:00","req":"9f2c1a","tool":"transition_task","caller":"key:frony","project":"AIR","task":"AIR-029","args":{"status":"done"},"ms":14.2,"ok":true,"warnings":0}
{"ts":"2026-08-26T17:07:02.118+09:00","req":"b71e40","tool":"create_task","caller":"key:frony","project":"AIR","period":"2026Q3","args":{"title":"…","month":"M2","content_len":812},"ms":31.0,"ok":true,"warnings":1}
{"ts":"2026-08-26T17:07:40.550+09:00","req":"03aa7d","tool":"update_task","caller":"session:admin","project":"AIR","task":"AIR-031","args":{},"ms":2.9,"ok":false,"error":"rejected","msg":"nothing to update — pass at least one field …"}
```

| Field | Always | Meaning |
|---|---|---|
| `ts` | ✔ | Time of the call |
| `req` | ✔ | Correlation id — the server.jsonl lines that follow for the same call carry the same value |
| `tool` | ✔ | MCP tool name |
| `caller` | ✔ | `key:<API key name>` · `session:<dashboard user>` · `oauth:<client>:<user>` · `stdio` (local `aira` run) · `unknown` |
| `project` | when known | The `key` argument, or else the `task_id` prefix |
| `period` | when passed | `2026Q3` |
| `task` | when passed | `AIR-031` |
| `args` | ✔ | The remaining arguments (`key`/`task_id`/`period` are hoisted out), prose as `_len`, nulls dropped |
| `ms` | ✔ | Wall-clock duration (ms, one decimal) |
| `ok` | ✔ | `false` = the tool rejected the call (validation, bad argument, unknown id) or raised |
| `warnings` | when ok | Number of validation warnings enclosed with the result |
| `error`, `msg` | when !ok | On a rejection `"rejected"` + the tool message (SDK boilerplate stripped, truncated at 500 chars); on an exception the class name + `str(e)` |

## 4. server.jsonl — server events (30-day retention)

Writers: `log.event(level, scope, event, **fields)` / `log.exception(...)` (ERROR + `trace`) / `InterceptHandler`

Template — the four fixed head fields, then the per-event fields:
```json
{"ts":"<ISO>","level":"INFO|WARNING|ERROR","scope":"<scope>","event":"<event>", ...fields}
```

Examples:
```json
{"ts":"…","level":"INFO","scope":"boot","event":"start","mode":"http","version":"0.20.4","data":"C:\…\data","logs":"C:\…\logs","tz":"Asia/Seoul","host":"0.0.0.0:8642"}
{"ts":"…","level":"INFO","scope":"auth","event":"login_ok","user":"admin","ip":"100.108.65.1"}
{"ts":"…","level":"WARNING","scope":"auth","event":"key_rejected","ip":"100.108.65.1","path":"/mcp","prefix":"aira_347b"}
{"ts":"…","level":"WARNING","scope":"http","event":"response","status":404,"method":"GET","path":"/api/projects/ZZ/status","ip":"100.108.65.1"}
{"ts":"…","level":"WARNING","scope":"tool","event":"rejected","req":"03aa7d","tool":"update_task","msg":"nothing to update — …"}
{"ts":"…","level":"ERROR","scope":"py","event":"log","logger":"uvicorn.error","msg":"Exception in ASGI application","trace":"Traceback (most recent call last): …"}
```

Event catalogue:

| scope | event | level | Fields |
|---|---|---|---|
| `boot` | `start` | INFO | `mode` (`http`/`stdio`), `version`, `data`, `logs`, `tz`, `host` (http) |
| `boot` | `shutdown` | INFO | `mode` |
| `auth` | `login_ok` / `login_failed` | INFO / WARNING | `user`, `ip` |
| `auth` | `oauth_login_ok` / `oauth_login_failed` | INFO / WARNING | `user`, `ip` |
| `auth` | `oauth_login_denied` | — | `client` |
| `auth` | `oauth_client_registered` | INFO | `client`, `client_id` |
| `auth` | `key_rejected` | WARNING | `ip`, `path`, `prefix` (first 9 chars of the key) |
| `auth` | `fauth_unavailable` | ERROR | `ip`, `path` — FronyAuth introspection unavailable (503, fail-closed) |
| `auth` | `key_created` / `key_revoked` | INFO | `name`, `ip` |
| `auth` | `keys_migrated` / `oauth_migrated` | INFO | `to` — one-off migration |
| `http` | `response` | WARNING(<500) / ERROR(≥500) | `status`, `method`, `path`, `ip` — **4xx/5xx only**; 2xx/3xx (dashboard polling) and `GET /mcp` 404/405 (SSE listen attempts) are dropped |
| `tool` | `rejected` | WARNING | `req`, `tool`, `msg` |
| `tool` | `exception` | ERROR | `req`, `tool`, `error`, `msg`, `trace` |
| `py` | `log` | WARNING / ERROR | `logger`, `msg`, `trace` (when exc_info is present) — uvicorn/mcp stdlib WARNING+ |

## 5. Adopting it in another service

- Change only the file names, retention periods and `stream` values to fit the service, and keep the sink configuration and the `event()` / `tool_call()` helper signatures as they are — cross-tracing the two files by `req` is the shared contract
- Replace `TEXT_FIELDS` (the prose fields recorded by length only) with the service's own free-text fields
- The secret-masking rules (9-char key prefix, tokens and passwords never written) are shared
