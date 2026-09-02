# FronyBoard 로그 파일 스펙 — 템플릿 · 라이브러리

> 다른 Frony 서비스가 같은 방식으로 로그를 남길 때 그대로 가져다 쓰는 레퍼런스.
> 필드·이벤트의 상세 설명과 조회 예시는 [logging.md](logging.md), 구현은 `backend/src/aira/log.py`.
> 로그 위치: `%LOCALAPPDATA%\Frony\FronyBoard\logs` (데이터 루트 옆 `logs/`, `AIRA_LOG_DIR`로 변경).

## 1. 사용 라이브러리

| 라이브러리 | 버전 | 역할 |
|---|---|---|
| **loguru** | 0.7.3 (`>=0.7`) | 유일한 로깅 엔진. 파일 싱크 2개 + (stdio 모드) stderr 에코. `format="{message}"`로 메시지를 그대로 기록 — 메시지 자체가 완성된 JSON 한 줄 |
| stdlib `logging` | — | 직접 쓰지 않음. `InterceptHandler`가 uvicorn / mcp SDK의 stdlib 로그를 가로채 loguru 싱크로 전달 |
| `json` (stdlib) | — | `json.dumps(payload, ensure_ascii=False, default=str)` — 한글 원문 유지, 직렬화 불가 값은 `str()` |
| `zoneinfo` (stdlib) | — | `AIRA_TZ`(예: `Asia/Seoul`) 기준 타임스탬프; 미설정/무효 시 프로세스 로컬 존 |
| `secrets` (stdlib) | — | `token_hex(3)` → 6-hex 상관 id(`req`) |

loguru 싱크 설정 (`log.setup()`):

```python
common = {"format": "{message}", "level": "INFO", "rotation": "00:00",
          "compression": "gz", "encoding": "utf-8"}
logger.add(root / "server.jsonl", retention="30 days",
           filter=lambda r: r["extra"].get("stream") != "tools", **common)
logger.add(root / "tools.jsonl",  retention="180 days",
           filter=lambda r: r["extra"].get("stream") == "tools", **common)
if stderr:   # stdio 모드만 — stdout은 MCP 채널이라 절대 싱크로 쓰지 않음
    logger.add(sys.stderr, format="{message}", level="WARNING",
               filter=lambda r: r["extra"].get("stream") != "tools")
```

- 스트림 분기는 `logger.bind(stream="tools" | "server")`의 extra 필드로만 한다
- 매일 00:00 회전, 이전 날짜는 gzip: `tools.2026-08-26_00-00-00_000000.jsonl.gz`
- `setup()` 전에는 어떤 싱크도 없다(`logger.remove()`) — import·테스트·CLI 서브커맨드는 무음
- uvicorn / uvicorn.error / uvicorn.access 로거는 handlers 교체 + `propagate=False`

## 2. 공통 규칙

- 포맷: **JSON Lines**, 한 줄 = 평면(flat) JSON 객체, 필드 집합 고정. 사람용 산문 없음(독자는 에이전트/쿼리 도구)
- `ts`: ISO 8601 + 오프셋, 밀리초 — `2026-08-26T17:06:15.402+09:00` (데이터 파일의 naive UTC와 다름)
- 절대 기록하지 않는 것: API 키 원문(거절 시 앞 9자 `prefix`만), 비밀번호, 세션 토큰, 계획 산문
- 산문 필드는 **길이만** 기록: `content prd goal now next later result_markdown description` → `<name>_len`
- `null` 인자는 드롭

## 3. tools.jsonl — MCP 툴 호출 1건 = 1줄 (보존 180일)

작성자: `ToolLogMiddleware` (MCP 서버 미들웨어, `tools/call`만 처리)

템플릿:
```json
{"ts":"<ISO>","req":"<6hex>","tool":"<tool name>","caller":"<who>","project":"<KEY>","period":"<YYYYQn>","task":"<KEY-NNN>","args":{...},"ms":<float>,"ok":true,"warnings":<int>}
{"ts":"<ISO>","req":"<6hex>","tool":"<tool name>","caller":"<who>","project":"<KEY>","args":{...},"ms":<float>,"ok":false,"error":"rejected|<ExceptionClass>","msg":"<≤500자>"}
```

예시:
```json
{"ts":"2026-08-26T17:06:15.402+09:00","req":"9f2c1a","tool":"transition_task","caller":"key:frony","project":"AIR","task":"AIR-029","args":{"status":"done"},"ms":14.2,"ok":true,"warnings":0}
{"ts":"2026-08-26T17:07:02.118+09:00","req":"b71e40","tool":"create_task","caller":"key:frony","project":"AIR","period":"2026Q3","args":{"title":"…","month":"M2","content_len":812},"ms":31.0,"ok":true,"warnings":1}
{"ts":"2026-08-26T17:07:40.550+09:00","req":"03aa7d","tool":"update_task","caller":"session:admin","project":"AIR","task":"AIR-031","args":{},"ms":2.9,"ok":false,"error":"rejected","msg":"nothing to update — pass at least one field …"}
```

| 필드 | 항상 | 의미 |
|---|---|---|
| `ts` | ✔ | 호출 시각 |
| `req` | ✔ | 상관 id — 같은 호출의 server.jsonl 후속 줄이 동일 값을 가진다 |
| `tool` | ✔ | MCP 툴 이름 |
| `caller` | ✔ | `key:<API 키 이름>` · `session:<대시보드 사용자>` · `oauth:<client>:<user>` · `stdio`(로컬 `aira` 실행) · `unknown` |
| `project` | 알 때 | `key` 인자, 없으면 `task_id` 접두어 |
| `period` | 전달 시 | `2026Q3` |
| `task` | 전달 시 | `AIR-031` |
| `args` | ✔ | 나머지 인자(`key`/`task_id`/`period`는 상위로 빠짐), 산문은 `_len`, null 드롭 |
| `ms` | ✔ | 벽시계 소요(ms, 소수 1자리) |
| `ok` | ✔ | `false` = 툴이 거절(검증·인자 오류·미존재 id) 또는 예외 |
| `warnings` | ok일 때 | 결과에 동봉된 validation warning 수 |
| `error`, `msg` | !ok일 때 | 거절이면 `"rejected"` + 툴 메시지(SDK 보일러플레이트 제거, 500자 절단); 예외면 클래스명 + `str(e)` |

## 4. server.jsonl — 서버 이벤트 (보존 30일)

작성자: `log.event(level, scope, event, **fields)` / `log.exception(...)`(ERROR + `trace`) / `InterceptHandler`

템플릿 — 고정 헤드 4개 뒤에 이벤트별 필드:
```json
{"ts":"<ISO>","level":"INFO|WARNING|ERROR","scope":"<scope>","event":"<event>", ...fields}
```

예시:
```json
{"ts":"…","level":"INFO","scope":"boot","event":"start","mode":"http","version":"0.20.4","data":"C:\…\data","logs":"C:\…\logs","tz":"Asia/Seoul","host":"0.0.0.0:8642"}
{"ts":"…","level":"INFO","scope":"auth","event":"login_ok","user":"admin","ip":"100.108.65.1"}
{"ts":"…","level":"WARNING","scope":"auth","event":"key_rejected","ip":"100.108.65.1","path":"/mcp","prefix":"aira_347b"}
{"ts":"…","level":"WARNING","scope":"http","event":"response","status":404,"method":"GET","path":"/api/projects/ZZ/status","ip":"100.108.65.1"}
{"ts":"…","level":"WARNING","scope":"tool","event":"rejected","req":"03aa7d","tool":"update_task","msg":"nothing to update — …"}
{"ts":"…","level":"ERROR","scope":"py","event":"log","logger":"uvicorn.error","msg":"Exception in ASGI application","trace":"Traceback (most recent call last): …"}
```

이벤트 카탈로그:

| scope | event | level | 필드 |
|---|---|---|---|
| `boot` | `start` | INFO | `mode`(`http`/`stdio`), `version`, `data`, `logs`, `tz`, `host`(http) |
| `boot` | `shutdown` | INFO | `mode` |
| `auth` | `login_ok` / `login_failed` | INFO / WARNING | `user`, `ip` |
| `auth` | `oauth_login_ok` / `oauth_login_failed` | INFO / WARNING | `user`, `ip` |
| `auth` | `oauth_login_denied` | — | `client` |
| `auth` | `oauth_client_registered` | INFO | `client`, `client_id` |
| `auth` | `key_rejected` | WARNING | `ip`, `path`, `prefix`(키 앞 9자) |
| `auth` | `fauth_unavailable` | ERROR | `ip`, `path` — FronyAuth introspection 불가(503 fail-closed) |
| `auth` | `key_created` / `key_revoked` | INFO | `name`, `ip` |
| `auth` | `keys_migrated` / `oauth_migrated` | INFO | `to` — 1회성 마이그레이션 |
| `http` | `response` | WARNING(<500) / ERROR(≥500) | `status`, `method`, `path`, `ip` — **4xx/5xx만**; 2xx/3xx(대시보드 폴링)와 `GET /mcp` 404/405(SSE 리슨 시도)는 드롭 |
| `tool` | `rejected` | WARNING | `req`, `tool`, `msg` |
| `tool` | `exception` | ERROR | `req`, `tool`, `error`, `msg`, `trace` |
| `py` | `log` | WARNING / ERROR | `logger`, `msg`, `trace`(exc_info 있을 때) — uvicorn/mcp stdlib WARNING+ |

## 5. 다른 서비스에 적용할 때

- 파일 이름·보존 기간·`stream` 값만 서비스에 맞게 바꾸고, 싱크 설정과 `event()`/`tool_call()` 헬퍼 시그니처는 그대로 유지한다 — `req`로 두 파일을 교차 추적하는 방식이 공통 계약
- `TEXT_FIELDS`(길이만 기록할 산문 필드)는 서비스의 자유 텍스트 필드로 교체
- 비밀 정보 마스킹 규칙(키 prefix 9자, 토큰·비밀번호 미기록)은 공통
