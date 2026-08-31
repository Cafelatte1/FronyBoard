# Integrated search (AIR-032)

**언제 읽나**: 헤더 검색바나 검색 매칭 로직을 건드릴 때
**대상 코드**: `frontend/src/search.ts`, `frontend/src/SearchBar.tsx`
**관련 문서**: [http-api.md](http-api.md), [testing.md](testing.md)

---

프론트엔드 전용 기능이다 — 서버에는 검색 API가 없다. 이미 로드된 `BoardData`를
클라이언트에서 훑는다 (`searchTasks(data, query)`, `frontend/src/search.ts:50`).
`/api/*`는 [http-api.md](http-api.md) 문서 그대로이며 이 기능으로 바뀐 게 없다.

## 매칭 규칙

`search.ts:50-84`. 대소문자 무시, 부분 일치.

- 검색 대상: 프로젝트 키, 태스크 id, title, content
- **검색 안 함**: branch, tags (`search.test.ts:24-27`로 고정)
- 범위: 전 프로젝트, 전 기간 — 닫힌 분기와 취소된 태스크도 포함
- 프로젝트 키가 일치하면 그 프로젝트의 모든 태스크가 결과에 포함된다
- 결과는 프로젝트별로 그룹, 그룹 내부는 상태 순(`STATUS_ORDER`: in_progress → blocked → todo → done → cancelled) 후 id 순
- id/title에 매치가 없고 content에만 매치가 있을 때만 30자 안팎의 스니펫(`snippetOf`)을 만든다 — id나 title이 이미 매치를 보여주면 스니펫은 `null`

## SearchBar

`SearchBar.tsx`. 데스크톱은 264px 헤더 인풋 + 드롭다운, 모바일(`useIsPhone`)은
헤더의 돋보기 버튼 → 전체 화면 오버레이(`gs-overlay`).

- `⌘K`/`Ctrl+K`로 어디서든 포커스 (SearchBar.tsx:24-34)
- 그룹당 `PREVIEW_ROWS = 5`행만 먼저 보여주고, "모두 보기"로 인라인 펼침(그룹별 `expanded` 상태, 새 쿼리 입력 시 초기화)
- content-only 매치는 스니펫을 표시
- Enter는 첫 결과를 선택, Escape는 패널을 닫음
- 최근 검색 4개를 localStorage 키 `fb.recentSearches`에 저장(`remember`/`readRecent`, SearchBar.tsx:316-335); 빈 쿼리 상태에서 칩으로 노출

## 결과 클릭 시 동작

`App.tsx`의 `openFromSearch(key, task)` (App.tsx:121-126)가 프로젝트 상세를
열고, 그 태스크의 `period`/`id`를 담은 `detailFocus`를 프로젝트 상세로 넘긴다.
`ProjectDetail`은 `initialPeriod`로 그 분기를 열고, `TaskTable`은
`initialTaskId`로 그 태스크가 있는 페이지에서 시작하며, 대상 태스크가
`cancelled`면 취소 포함 토글을 자동으로 켠다(`cancelled` state 초깃값 =
`target?.status === "cancelled"`, `frontend/src/pages/Projects.tsx:728`).
`onOpenTask`가 이어서 TaskPanel을 즉시 연다.
