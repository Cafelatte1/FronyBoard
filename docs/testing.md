# Testing

**언제 읽나**: 백엔드/프론트엔드 테스트를 추가·수정하거나 테스트 헬퍼를 건드릴 때
**대상 코드**: `backend/tests/`, `frontend/tests/`

---

## Backend (pytest)

`uv run --directory backend pytest` — `backend/pyproject.toml`의
`[tool.pytest.ini_options] testpaths = ["tests"]`로 `backend/tests/`만 수집한다.
현재 10개 파일, 79개 테스트.

| file | covers |
|---|---|
| `test_store.py` | 파일 IO |
| `test_validation.py` | 스키마·규칙 게이트 |
| `test_service.py` | 오퍼레이션 (24개 — 가장 큼) |
| `test_concurrency.py` | 프로젝트별 락 |
| `test_server.py` | MCP 툴 표면 |
| `test_auth.py` | API 키·세션·락아웃 |
| `test_oauth.py` | OAuth 플로우 — 페이지 문구 대신 상태 코드·`class='result <kind>'` 마커·핸드오프 URL을 단언 |
| `test_oauth_pages.py` | OAuth 페이지(`oauth_pages.py`) 렌더링과 문구 — 이 값들을 단언하는 유일한 파일 |
| `test_web.py` | `/api/*` JSON 라우트 |
| `test_log.py` | `tools.jsonl`/`server.jsonl` |

`test_oauth.py`와 `test_oauth_pages.py`의 분리는 의도된 것이다: 페이지 문구가
바뀌면 `test_oauth_pages.py`만 깨지고, 플로우(상태 코드·리다이렉트·토큰 발급)는
`test_oauth.py`가 별도로 지킨다 (`backend/tests/test_oauth_pages.py:1-6`).

### ASGI 요청 헬퍼

ASGI 앱에 HTTP 요청 하나를 흘려보내는 로직은 `backend/tests/conftest.py`의
`asgi_request(app, method, path, query="", headers=None, json_body=None, form=None, scheme="https") -> (status, headers, body)`
하나로 통일되어 있다 — `test_web.py`, `test_oauth.py`, `test_auth.py`가 모두 이걸
가져다 쓴다 (`from conftest import asgi_request`). 새 ASGI 라우트 테스트를 추가할 때
이 함수를 재사용할 것, 앱별로 다시 만들지 말 것.

같은 파일의 `bootstrap(key="DLY")`는 프로젝트 하나 + 열린 `2026Q3` 기간 +
활성 `M1` 월을 만들어 반환하는 공용 픽스처 헬퍼다.

`data_root` 오토유즈 픽스처가 `AIRA_DATA_DIR`/`FRONY_AUTH_FILE`/`FRONY_OAUTH_FILE`를
`tmp_path` 아래로 돌리고 로그인 락아웃 상태를 매 테스트마다 리셋한다 — 새 테스트
파일에서 데이터 루트를 따로 설정할 필요가 없다.

## Frontend (vitest)

`cd frontend; npm run test` (= `vitest run`) — `frontend/tests/`, 8개 파일,
47개 테스트. 서버를 띄우지 않고 `fetch`는 `vi.stubGlobal`로 모킹한다.

| file | covers |
|---|---|
| `search.test.ts` | `search.ts` 검색 로직 |
| `SearchBar.test.tsx` | `SearchBar.tsx` |
| `api.test.ts` | API 클라이언트 |
| `Dashboard.test.tsx`, `Projects.test.tsx`, `Settings.test.tsx`, `TaskPanel.test.tsx` | 화면 컴포넌트 |
| `markdown.test.ts` | 마크다운 렌더링 |
| `fixtures.ts` | 공용 테스트 데이터 (테스트 파일 아님) |

설정은 `frontend/vite.config.ts`의 `test` 블록: `environment: "jsdom"`,
`setupFiles: "./tests/setup.ts"`, `include: ["tests/**/*.test.{ts,tsx}"]`.
`tests/setup.ts`는 jsdom에 없는 `window.matchMedia`를 데스크톱(`matches: false`)
스텁으로 채워 `useIsPhone`이 동작하게 한다.

`frontend/tsconfig.json`의 `include`는 `["src"]`뿐이라 `npm run build`
(`tsc -b && vite build`)는 `tests/`를 타입체크하지 않는다 — 테스트 코드의
타입 오류는 빌드가 아니라 `npm test` 실행 시점(vitest의 esbuild 변환)에만
드러난다.
