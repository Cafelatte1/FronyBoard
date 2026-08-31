# CLAUDE.md

## 프로젝트

FronyBoard: AI 에이전트가 1급 사용자인 프로젝트 트래커 MCP 서버.
계획 데이터는 이 저장소가 아니라 FronyBoard 서버의 데이터 루트(`%LOCALAPPDATA%\Frony\FronyBoard\data`, `AIRA_DATA_DIR`로 변경 가능)에 저장된다.

## 디렉토리 구조

- `backend/` — MCP 서버 (uv 프로젝트)
  - `src/aira/store.py` — 파일 IO·데이터 루트
  - `src/aira/validation.py` — 스키마·규칙 게이트 (모든 mutation 전 실행, 오류 시 쓰기 거부)
  - `src/aira/service.py` — 오퍼레이션 (프로젝트별 락 직렬화, 타임스탬프 자동 스탬프)
  - `src/aira/server.py` — MCP 툴 표면 + CLI (stdio / `serve` / `keygen`)
- `frontend/` — FronyBoard 웹 (사람용 조회 대시보드). 빌드 산출물은 backend가 정적 서빙 — 배포 프로세스는 하나.

## 주요 명령 (레포 루트 기준)

- 테스트: `uv run --directory backend pytest`
- 로컬 서버(stdio): `uv run --directory backend aira`
- HTTP 서버: `uv run --directory backend aira serve` (API key 필수 — `aira keygen`)
- 프론트 빌드: `cd frontend; npm run build` — **frontend/dist는 커밋 대상** (홈서버는 pull만 함)

## 배포 방식

홈서버(드래곤플라이 G3, Tailscale `100.67.93.87:8642`)에서 작업 스케줄러 "AIRA Server"로 상시 실행 중.
같은 머신의 "FronyAuth Server"(`:8640`, project-auth 레포)가 인증을 담당한다 — aira는 모든 bearer 검증을
FronyAuth introspection에 위임하므로(v0.18.0+, `FRONY_AUTH_URL`/`FRONY_SERVICE_KEY`) FronyAuth 없이는 인증이 안 된다.
홈서버는 **release 태그(vX.Y.Z) 기준으로만 배포**한다 — main에 push해도 영향 없음.
배포 절차: 태그 push 후 서버에서 `scripts\deploy.ps1 -Tag vX.Y.Z` (README의 Deploy 섹션 참조).
키 발급은 `fauth keygen`(또는 대시보드 Settings) — `aira keygen`은 제거됨.

## 디자인 시안

UI 목업은 Claude Design의 "FronyBoard" 프로젝트에 있다 — 아트보드 파일은 `FronyBoard_YYYYMMDD.dc.html`, 최신 날짜가 기준.
Claude Code에서는 DesignSync 툴로 읽는다: projectId `2290d769-da3c-4fcb-846e-25d0045d8c88`에 `list_files` / `get_file`.
`list_projects`에는 design-system 프로젝트만 나오므로 이 projectId를 직접 써야 하고, 세션 최초 1회 `/design-login` 승인이 필요하다.

## FronyBoard

This project is tracked by FronyBoard (project key: AIR).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: `frontend` / `backend` / `infra` / `docs` for where the work lands, plus
`design` or `test` for what kind it is. Reuse these rather than coining a synonym.
