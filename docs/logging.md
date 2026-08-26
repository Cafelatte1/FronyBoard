# Logging

FronyBoard writes JSON Lines, not prose: the reader is an agent (or a query tool),
so every line is a flat object with a fixed field set. Nothing is logged to stdout —
in stdio mode that channel carries MCP.

| | `tools.jsonl` | `server.jsonl` |
|---|---|---|
| one line per | MCP tool call | server event |
| purpose | usage analysis, activity per agent, transition history | error tracking |
| kept | 180 days | 30 days |

Location: `%LOCALAPPDATA%\Frony\FronyBoard\logs` (the `logs` folder next to the data
root); `AIRA_LOG_DIR` overrides. Rotated at midnight, older days gzipped
(`tools.2026-08-26_00-00-00_000000.jsonl.gz`). Timestamps are ISO 8601 in the server's
zone (`AIRA_TZ`, else local) with offset — unlike the data files, which store naive UTC.

Not logged, ever: API keys (only the first 9 characters on a rejection), passwords,
session tokens, and the planning prose (`content`, `prd`, `goal`, `now`, `next`,
`later`, `result_markdown`, `description` appear as `<field>_len`).

## tools.jsonl

```json
{"ts":"2026-08-26T17:06:15.402+09:00","req":"9f2c1a","tool":"transition_task","caller":"key:frony","project":"AIR","task":"AIR-029","args":{"status":"done"},"ms":14.2,"ok":true,"warnings":0}
{"ts":"2026-08-26T17:07:02.118+09:00","req":"b71e40","tool":"create_task","caller":"key:frony","project":"AIR","period":"2026Q3","args":{"title":"…","month":"M2","content_len":812},"ms":31.0,"ok":true,"warnings":1}
{"ts":"2026-08-26T17:07:40.550+09:00","req":"03aa7d","tool":"update_task","caller":"session:admin","project":"AIR","task":"AIR-031","args":{},"ms":2.9,"ok":false,"error":"rejected","msg":"nothing to update — pass at least one field …"}
```

| field | always | meaning |
|---|---|---|
| `ts` | yes | call time, ISO 8601 with offset |
| `req` | yes | 6-hex correlation id; `server.jsonl` follow-ups carry the same value |
| `tool` | yes | MCP tool name |
| `caller` | yes | `key:<api key name>` · `session:<dashboard user>` · `stdio` (local `aira` run) |
| `project` | when known | from `key`, or the prefix of `task_id` |
| `period` | when passed | `2026Q3` |
| `task` | when passed | `AIR-031` |
| `args` | yes | remaining arguments; prose fields replaced by `<name>_len`; `null`s dropped |
| `ms` | yes | wall time of the call |
| `ok` | yes | `false` when the tool rejected the call (validation, bad argument, unknown id) |
| `warnings` | ok only | number of validation warnings returned with the result |
| `error`, `msg` | !ok only | `rejected` + the tool's message; an unexpected exception uses its class name |

## server.jsonl

```json
{"ts":"…","level":"INFO","scope":"boot","event":"start","mode":"http","version":"0.6.2","data":"C:\\…\\data","logs":"C:\\…\\logs","tz":"Asia/Seoul","host":"0.0.0.0:8642"}
{"ts":"…","level":"INFO","scope":"auth","event":"login_ok","user":"admin","ip":"100.108.65.1"}
{"ts":"…","level":"WARNING","scope":"auth","event":"key_rejected","ip":"100.108.65.1","path":"/mcp","prefix":"aira_347b"}
{"ts":"…","level":"WARNING","scope":"http","event":"response","status":404,"method":"GET","path":"/api/projects/ZZ/status","ip":"100.108.65.1"}
{"ts":"…","level":"WARNING","scope":"tool","event":"rejected","req":"03aa7d","tool":"update_task","msg":"nothing to update — …"}
{"ts":"…","level":"ERROR","scope":"py","event":"log","logger":"uvicorn.error","msg":"Exception in ASGI application","trace":"Traceback (most recent call last): …"}
```

Fixed head `ts level scope event`, then per-event fields:

| scope | event | fields |
|---|---|---|
| `boot` | `start` | `mode` (`http`/`stdio`), `version`, `data`, `logs`, `tz`, `host` (http) |
| `boot` | `shutdown` | `mode` |
| `auth` | `login_ok` / `login_failed` | `user`, `ip` |
| `auth` | `key_rejected` | `ip`, `path`, `prefix` |
| `auth` | `key_created` / `key_revoked` | `name`, `ip` |
| `http` | `response` | `status` (≥ 400 only — 2xx/3xx, i.e. the dashboard's minute polling, is not recorded; `GET /mcp` 404/405, a client opening the optional SSE stream, is dropped too), `method`, `path`, `ip` |
| `tool` | `rejected` | `req`, `tool`, `msg` |
| `tool` | `exception` | `req`, `tool`, `error`, `msg`, `trace` |
| `py` | `log` | `logger`, `msg`, `trace` (stdlib WARNING+ from uvicorn/mcp) |

## Reading it

```sh
# calls per tool
jq -r .tool logs/tools.jsonl | sort | uniq -c | sort -rn
# rejected calls with their message
jq -c 'select(.ok==false) | {ts,tool,caller,msg}' logs/tools.jsonl
# what did one agent do today
jq -c 'select(.caller=="key:frony") | {ts,tool,task,args}' logs/tools.jsonl
# transition history of a task
jq -c 'select(.task=="AIR-029" and .tool=="transition_task") | {ts,args}' logs/tools.jsonl
# everything that went wrong, newest first
jq -c 'select(.level!="INFO")' logs/server.jsonl | tail -20
# follow one request across both files
grep 03aa7d logs/tools.jsonl logs/server.jsonl
```

With DuckDB: `select tool, count(*), quantile_cont(ms, .95) from read_json_auto('logs/tools*.jsonl*') group by 1`.
