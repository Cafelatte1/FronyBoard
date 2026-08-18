# CLAUDE.md

이 프로젝트의 AIRA key는 **AIR**다 — task 관리는 aira MCP 툴로 한다 (전역 CLAUDE.md §8 참조).

## 프로젝트

AIRA (AI + JIRA): AI 에이전트가 1급 사용자인 프로젝트 트래커 MCP 서버.
계획 데이터는 이 저장소가 아니라 AIRA 서버의 데이터 루트(`~/.aira`, `AIRA_DATA_DIR`)에 저장된다.

## 구조 (src/aira/)

- `store.py` — 파일 IO·데이터 루트
- `validation.py` — 스키마·규칙 게이트 (모든 mutation 전 실행, 오류 시 쓰기 거부)
- `service.py` — 오퍼레이션 (프로젝트별 락 직렬화, 타임스탬프 자동 스탬프)
- `server.py` — MCP 툴 표면 + CLI (stdio / `serve` / `keygen`)

## 명령

- 테스트: `uv run pytest`
- 로컬 서버(stdio): `uv run aira`
- HTTP 서버: `uv run aira serve` (API key 필수 — `aira keygen`)

## 배포

홈서버(`laptop`, Tailscale `100.108.65.117:8642`)에서 작업 스케줄러 "AIRA Server"로 상시 실행 중.
main에 push해도 홈서버는 자동 갱신되지 않는다 — 서버에서 `git pull` + `uv sync` + 태스크 재시작 필요 (README의 Deploy 섹션 참조).
