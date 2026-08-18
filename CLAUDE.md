# CLAUDE.md

## 프로젝트

AIRA (AI + JIRA): AI 에이전트가 1급 사용자인 프로젝트 트래커 MCP 서버.
계획 데이터는 이 저장소가 아니라 AIRA 서버의 데이터 루트(`~/.aira`, `AIRA_DATA_DIR`)에 저장된다.

## 구조 (모노레포)

- `backend/` — MCP 서버 (uv 프로젝트)
  - `src/aira/store.py` — 파일 IO·데이터 루트
  - `src/aira/validation.py` — 스키마·규칙 게이트 (모든 mutation 전 실행, 오류 시 쓰기 거부)
  - `src/aira/service.py` — 오퍼레이션 (프로젝트별 락 직렬화, 타임스탬프 자동 스탬프)
  - `src/aira/server.py` — MCP 툴 표면 + CLI (stdio / `serve` / `keygen`)
- `frontend/` — FronyBoard 웹 (사람용 조회 대시보드). 빌드 산출물은 backend가 정적 서빙 — 배포 프로세스는 하나.

## 명령 (레포 루트 기준)

- 테스트: `uv run --directory backend pytest`
- 로컬 서버(stdio): `uv run --directory backend aira`
- HTTP 서버: `uv run --directory backend aira serve` (API key 필수 — `aira keygen`)
- 프론트 빌드: `cd frontend; npm run build` — **frontend/dist는 커밋 대상** (홈서버는 pull만 함)

## 배포

홈서버(`laptop`, Tailscale `100.108.65.117:8642`)에서 작업 스케줄러 "AIRA Server"로 상시 실행 중.
홈서버는 **release 태그(vX.Y.Z) 기준으로만 배포**한다 — main에 push해도 영향 없음.
배포 절차: 태그 push 후 서버에서 `git fetch --tags` + `git checkout vX.Y.Z` + `uv sync` + 태스크 재시작 (README의 Deploy 섹션 참조).

## AIRA

This project is tracked by AIRA (project key: AIR).
Manage tasks through the aira MCP tools, following the aira server instructions.
