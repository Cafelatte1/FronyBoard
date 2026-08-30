# AGENTS.md

## 프로젝트

<프로젝트명>: <무엇을 하는 소프트웨어인지 한두 문장>
<코드 밖에 저장되는 데이터가 있으면 그 위치와 환경변수를 여기 적는다. 없으면 이 줄 삭제>

## 디렉토리 구조

- `<디렉토리>/` — <역할> (<빌드 도구·언어>)
  - `<주요 파일 경로>` — <이 파일이 책임지는 것>
  - `<주요 파일 경로>` — <이 파일이 책임지는 것>
- `<디렉토리>/` — <역할>. <다른 디렉토리와의 관계나 산출물 처리 방식>

## 주요 명령 (레포 루트 기준)

- 테스트: `<명령>`
- <실행/개발 서버>: `<명령>`
- <빌드>: `<명령>` — <커밋 대상 여부 등 주의사항이 있으면 함께>

## 배포 방식

<어디서 어떤 방식으로 돌고 있는지 (호스트·프로세스 관리 방식)>
<무엇을 기준으로 배포되는지 — 브랜치인지 태그인지, 배포되지 않는 조건>
배포 절차: <단계 나열 또는 참조할 문서 위치>
<배포 대상이 아닌 프로젝트면 이 섹션 전체를 삭제>

## FronyBoard

This project is tracked by FronyBoard (project key: <KEY>).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: <작업이 놓이는 영역 — 예: frontend / backend / infra / docs>, plus
<작업의 성격 — 예: design / test / bug> for what kind it is. Reuse these rather than
coining a synonym.
