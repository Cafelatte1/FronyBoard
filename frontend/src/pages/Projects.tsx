import { useEffect, useState } from "react";
import {
  MilestoneChip,
  ProjectStatusChip,
  RepoIcon,
  SORTS,
  StatusChip,
  TASK_ST,
  countBy,
  currentPeriodName,
  doneRatio,
  fmtServerTime,
  monthOf,
  sortTasks,
  useFavorites,
  weekLabel,
  type SortKey,
} from "../shared";
import type { BoardData, PeriodStatus, Roadmap, ServerTimezone, StatusResp, Task } from "../types";

export default function Projects({
  data,
  openKey,
  setOpenKey,
  onOpenTask,
}: {
  data: BoardData;
  openKey: string | null;
  setOpenKey: (key: string | null) => void;
  onOpenTask: (key: string, task: Task) => void;
}) {
  if (openKey === null) return <ProjectList data={data} onOpen={setOpenKey} />;
  return (
    <ProjectDetail
      key={openKey}
      data={data}
      projectKey={openKey}
      onBack={() => setOpenKey(null)}
      onOpenTask={(t) => onOpenTask(openKey, t)}
    />
  );
}

const COUNT_ORDER = ["done", "in_progress", "todo", "blocked"] as const;

function ProjectList({ data, onOpen }: { data: BoardData; onOpen: (k: string) => void }) {
  const [favs, toggleFav] = useFavorites();
  if (data.projects.length === 0)
    return <p className="muted">프로젝트가 없어요 — MCP로 먼저 등록해 주세요.</p>;
  // Starred first, otherwise the server's key order (sort is stable).
  const ordered = [...data.projects].sort((a, b) => Number(favs.has(b.key)) - Number(favs.has(a.key)));
  return (
    <>
      <span className="hint-text">카드를 누르면 해당 프로젝트의 상세 화면으로 이동합니다.</span>
      <div className="project-grid-2">
        {ordered.map((p) => {
          const fav = favs.has(p.key);
          const onFav = (e: { stopPropagation: () => void; preventDefault: () => void }) => {
            e.stopPropagation();
            e.preventDefault();
            toggleFav(p.key);
          };
          const status = data.statuses[p.key];
          const period = currentPeriodName(status);
          const tasks = (data.tasks[p.key] ?? []).filter((t) => t.period === period);
          const c = countBy(tasks);
          const r = doneRatio(c);
          return (
            <button key={p.key} className="card project-card" onClick={() => onOpen(p.key)}>
              <span className="project-card-head">
                <span className="id-chip">{p.key}</span>
                <span className="project-card-name lg">{status.name ?? p.key}</span>
                <ProjectStatusChip status={p.status} />
                <span className="project-card-period">{period ?? "—"}</span>
              </span>
              <span className="project-card-goal">{p.description ?? "설명이 아직 없어요."}</span>
              <span className={`project-card-repo ${p.repo ? "" : "none"}`}>
                <RepoIcon />
                <span className="repo-name">{p.repo ?? "—"}</span>
                {p.meta && (
                  <span className="since">since {fmtServerTime(p.meta.created_at, data.server.timezone).slice(0, 10)}</span>
                )}
              </span>
              <span className="card-bottom">
                <span className="project-card-meta">
                  <span>진행률</span>
                  <span className="pct">
                    {r.done}/{r.total} · {r.pct}%
                  </span>
                </span>
                <span className="bar">
                  <span className="bar-fill" style={{ width: `${r.pct}%` }} />
                </span>
              </span>
              <span className="count-row">
                {COUNT_ORDER.filter((s) => (c[s] ?? 0) > 0).map((s) => (
                  <span key={s} className={`chip st-${s}`}>
                    {TASK_ST[s].label} {c[s]}
                  </span>
                ))}
                <span className="spacer" />
                {/* a span, not a button: it sits inside the card button */}
                <span
                  role="button"
                  tabIndex={0}
                  className={`fav-btn ${fav ? "on" : ""}`}
                  title={fav ? "즐겨찾기 해제" : "즐겨찾기에 추가"}
                  aria-label={fav ? "즐겨찾기 해제" : "즐겨찾기에 추가"}
                  aria-pressed={fav}
                  onClick={onFav}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") onFav(e);
                  }}
                >
                  <svg viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
                    <path d="M10 2.6l2.28 4.7 5.12.72-3.72 3.63.9 5.1L10 14.35l-4.58 2.4.9-5.1L2.6 8.02l5.12-.72L10 2.6z" />
                  </svg>
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"] as const;
const NNL = ["now", "next", "later"] as const;

/** Periods of a year, in order: the active one first if any, else the earliest. */
function landingPeriod(year: string, status: StatusResp): string | null {
  const names = Object.keys(status.periods)
    .filter((n) => n.startsWith(year))
    .sort();
  return names.find((n) => status.periods[n].milestone_status === "active") ?? names[0] ?? null;
}

/** The detail screen shows one period at a time: the roadmap picks the year, the
    quarter dots / stepper pick the period, the table below belongs to that period. */
function ProjectDetail({
  data,
  projectKey,
  onBack,
  onOpenTask,
}: {
  data: BoardData;
  projectKey: string;
  onBack: () => void;
  onOpenTask: (t: Task) => void;
}) {
  const status = data.statuses[projectKey];
  const ref = data.projects.find((p) => p.key === projectKey);
  const roadmap = data.roadmaps[projectKey];
  const allTasks = data.tasks[projectKey] ?? [];

  const current = currentPeriodName(status);
  const periodNames = Object.keys(status.periods).sort();
  const years = [...new Set([...Object.keys(roadmap?.years ?? {}), ...periodNames.map((n) => n.slice(0, 4))])].sort();
  const currentYear = current?.slice(0, 4) ?? years[years.length - 1] ?? null;

  const [year, setYear] = useState<string | null>(currentYear);
  const [periodId, setPeriodId] = useState<string | null>(current);

  const selectPeriod = (id: string) => {
    setPeriodId(id);
    setYear(id.slice(0, 4));
  };
  const goYear = (y: string) => {
    setYear(y);
    const landing = landingPeriod(y, status);
    if (landing) setPeriodId(landing);
  };

  const currentInfo = current ? status.periods[current] : null;
  const currentRatio = doneRatio(countBy(allTasks.filter((t) => t.period === current)));

  return (
    <>
      <button className="back-btn" onClick={onBack}>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12.5 4.5 7 10l5.5 5.5" />
        </svg>
        프로젝트 목록
      </button>

      {/* Always the active period — the summary does not follow the stepper. */}
      <div className="card summary-card">
        <div className="summary-head">
          <span className="id-chip">{projectKey}</span>
          <span className="summary-name">{status.name ?? projectKey}</span>
          <ProjectStatusChip status={ref?.status} />
          <span className="spacer" />
          <span className="summary-period">{current ?? "—"}</span>
          <span className="summary-ratio">
            {currentRatio.done}/{currentRatio.total} · {currentRatio.pct}%
          </span>
          <span className="bar summary-bar">
            <span className="bar-fill" style={{ width: `${currentRatio.pct}%` }} />
          </span>
        </div>
        <span className="summary-desc">
          {ref?.description ?? "설명이 아직 없어요 — update_project로 추가할 수 있어요."}
        </span>
        <div className="summary-facts">
          <span className="fact">
            <span className="fact-label">repo</span>
            <span className={`fact-value mono repo ${ref?.repo ? "" : "none"}`}>
              <RepoIcon />
              <span className="ellipsis">{ref?.repo ?? "—"}</span>
            </span>
          </span>
          <span className="fact">
            <span className="fact-label">created_at</span>
            <span className="fact-value mono">
              {ref?.meta ? fmtServerTime(ref.meta.created_at, data.server.timezone) : "—"}
            </span>
          </span>
          <span className="fact">
            <span className="fact-label">periods</span>
            <span className="fact-value mono">
              {periodNames.length}개 분기 · {[...new Set(periodNames.map((n) => n.slice(0, 4)))].sort().join(", ") || "—"}
            </span>
          </span>
          <span className="fact">
            <span className="fact-label">분기 목표</span>
            <span className="fact-value muted">{currentInfo?.goal ?? "열린 기간 없음"}</span>
          </span>
        </div>
      </div>

      <RoadmapCard
        roadmap={roadmap}
        status={status}
        year={year}
        years={years}
        currentYear={currentYear}
        periodId={periodId}
        onYear={goYear}
        onPeriod={selectPeriod}
      />

      {periodId && status.periods[periodId] && (
        <PeriodView
          key={periodId}
          name={periodId}
          names={periodNames}
          period={status.periods[periodId]}
          tasks={allTasks.filter((t) => t.period === periodId)}
          tz={data.server.timezone}
          onPeriod={selectPeriod}
          onOpenTask={onOpenTask}
        />
      )}
    </>
  );
}

/** Year goal → quarter timeline (dots are buttons) → NOW/NEXT/LATER on the active year. */
function RoadmapCard({
  roadmap,
  status,
  year,
  years,
  currentYear,
  periodId,
  onYear,
  onPeriod,
}: {
  roadmap: Roadmap | undefined;
  status: StatusResp;
  year: string | null;
  years: string[];
  currentYear: string | null;
  periodId: string | null;
  onYear: (y: string) => void;
  onPeriod: (id: string) => void;
}) {
  const yd = roadmap && year ? roadmap.years[year] : undefined;
  if (!year) {
    return (
      <div className="card">
        <div className="card-title">로드맵</div>
        <p className="muted">로드맵이 아직 없어요.</p>
      </div>
    );
  }
  const yi = years.indexOf(year);
  const prev = yi > 0 ? years[yi - 1] : null;
  const next = yi >= 0 && yi < years.length - 1 ? years[yi + 1] : null;
  const ms = yd?.milestones ?? {};
  const activeIdx = QUARTERS.findIndex((q) => ms[q]?.status === "active");
  const lit = (j: number) => j <= activeIdx;
  return (
    <div className="card">
      <div className="road-head">
        <span className="road-title">
          <span className="card-title">{year} 로드맵</span>
          <span className="road-goal">{yd?.overview.goal ?? "이 해의 연간 목표가 아직 없어요."}</span>
        </span>
        <span className="ynav">
          <button className="ynav-btn" disabled={!prev} onClick={() => prev && onYear(prev)} title="이전 연도" aria-label="이전 연도">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
          </button>
          <span className="ynav-year">{year}</span>
          <button className="ynav-btn" disabled={!next} onClick={() => next && onYear(next)} title="다음 연도" aria-label="다음 연도">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
          </button>
        </span>
      </div>

      <div className="qtl">
        {QUARTERS.map((q, i) => {
          const pid = `${year}${q}`;
          const hasFile = !!status.periods[pid];
          const st = ms[q]?.status ?? (hasFile ? (status.periods[pid].milestone_status ?? "planned") : "none");
          const sel = pid === periodId;
          return (
            <button
              key={q}
              className={`q q-${st} ${sel ? "sel" : ""} ${hasFile ? "" : "nofile"}`}
              disabled={!hasFile}
              onClick={() => onPeriod(pid)}
              title={hasFile ? `${pid} 보기` : `${pid} — 기간 파일 없음`}
            >
              <span className="q-line">
                <span className={`q-seg ${i === 0 ? "hide" : lit(i) ? "lit" : ""}`} />
                <span className={`q-seg ${i === QUARTERS.length - 1 ? "hide" : lit(i + 1) ? "lit" : ""}`} />
                <span className="q-dot" />
              </span>
              <span className="q-id">{q}</span>
              <MilestoneChip status={st} />
              <span className="q-goal">{ms[q]?.goal ?? status.periods[pid]?.goal ?? "—"}</span>
            </button>
          );
        })}
      </div>

      {yd && year === currentYear && (
        <div className="nnl">
          {NNL.map((k, i) => (
            <div key={k} className={`nnl-item nnl-${i}`}>
              <div className="nnl-label">{k}</div>
              <div className="nnl-text">{yd.overview[k]}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const ROWS_PER_PAGE = 10;
const FILTERS = ["all", "in_progress", "todo", "blocked", "done"] as const;
type Filter = (typeof FILTERS)[number];

/** One period: stepper bar, monthly rollup, and the task table with its own
    filter / sort / page state (reset whenever the period changes — see key=). */
function PeriodView({
  name,
  names,
  period,
  tasks,
  tz,
  onPeriod,
  onOpenTask,
}: {
  name: string;
  names: string[];
  period: PeriodStatus;
  tasks: Task[];
  tz: ServerTimezone | undefined;
  onPeriod: (id: string) => void;
  onOpenTask: (t: Task) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [cancelled, setCancelled] = useState(false);
  const [sort, setSort] = useState<SortKey>("created");
  const [page, setPage] = useState(1);
  const [menu, setMenu] = useState<"filter" | "sort" | null>(null);

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu]);

  const i = names.indexOf(name);
  const older = i > 0 ? names[i - 1] : null;
  const newer = i >= 0 && i < names.length - 1 ? names[i + 1] : null;
  const ratio = doneRatio(countBy(tasks));

  const counts = countBy(tasks);
  const visible = tasks.filter(
    (t) => (cancelled || t.status !== "cancelled") && (filter === "all" || t.status === filter),
  );
  const sorted = sortTasks(visible, sort, period.months.map((m) => m.id));
  const pageCount = Math.max(1, Math.ceil(sorted.length / ROWS_PER_PAGE));
  const pageNo = Math.min(page, pageCount);
  const from = (pageNo - 1) * ROWS_PER_PAGE;
  const rows = sorted.slice(from, from + ROWS_PER_PAGE);
  const sortDef = SORTS.find((s) => s.key === sort)!;

  const pick = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
    setMenu(null);
  };

  return (
    <>
      <div className="pstep">
        <span className="ynav">
          <button className="ynav-btn lg" disabled={!older} onClick={() => older && onPeriod(older)} title={older ? `${older} 보기` : "이전 분기 없음"} aria-label="이전 분기">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
          </button>
          <span className="pstep-id">{name}</span>
          <button className="ynav-btn lg" disabled={!newer} onClick={() => newer && onPeriod(newer)} title={newer ? `${newer} 보기` : "다음 분기 없음"} aria-label="다음 분기">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
          </button>
        </span>
        <MilestoneChip status={period.milestone_status} />
        <span className="pstep-goal">{period.goal ?? "—"}</span>
        <span className="pstep-ratio">
          {ratio.done}/{ratio.total} · {ratio.pct}%
        </span>
        <span className="bar pstep-bar">
          <span className="bar-fill" style={{ width: `${ratio.pct}%` }} />
        </span>
      </div>

      {period.months.length > 0 && (
        <div className="card">
          <span className="rollup-cap">월별 진행률</span>
          <div className="rollup">
            {period.months.map((m) => {
              const r = doneRatio(m.task_counts);
              return (
                <div key={m.id} className="rollup-row">
                  <span className="r-id">{m.month}</span>
                  <span className="r-goal">{m.goal ?? "—"}</span>
                  <MilestoneChip status={m.status} />
                  <span className="r-ratio">{r.total ? `${r.done}/${r.total}` : "—"}</span>
                  <span className="bar r-bar">
                    {r.total > 0 && <span className="bar-fill" style={{ width: `${r.pct}%` }} />}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {menu && <div className="menu-overlay" onClick={() => setMenu(null)} />}

      <div className="task-table">
        <div className="table-top">
          <span className="table-title">
            <span className="card-title">태스크</span>
            <span className="table-summary">
              {name} · {sorted.length}건{tasks.length !== sorted.length && ` / 전체 ${tasks.length}건`}
            </span>
          </span>

          <span className="tool">
            <button
              className={`filter-btn ${filter !== "all" || cancelled ? "on" : ""}`}
              onClick={() => setMenu(menu === "filter" ? null : "filter")}
              title="필터"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M3 5.2h14M5.6 10h8.8M8.2 14.8h3.6" />
              </svg>
              필터
              <span className="dots">
                <span className="fdot" style={{ background: filter === "all" ? "var(--text-muted)" : TASK_ST[filter].swatch }} />
                {cancelled && <span className="fdot off" />}
              </span>
            </button>
            {menu === "filter" && (
              <div className="menu">
                <span className="menu-cap">상태</span>
                {FILTERS.map((f) => (
                  <button key={f} className={`menu-item ${filter === f ? "on" : ""}`} onClick={() => pick(setFilter)(f)}>
                    <span className="dot" style={{ background: f === "all" ? "var(--text-muted)" : TASK_ST[f].swatch }} />
                    <span className="grow">{f === "all" ? "전체" : TASK_ST[f].label}</span>
                    <span className="n">{f === "all" ? tasks.length : (counts[f] ?? 0)}</span>
                    <span className="check">✓</span>
                  </button>
                ))}
                <span className="menu-sep" />
                <button className="menu-item" onClick={() => pick(setCancelled)(!cancelled)}>
                  <span className="grow">취소된 태스크 포함</span>
                  <span className={`switch ${cancelled ? "on" : ""}`}>
                    <span className="knob" />
                  </span>
                </button>
              </div>
            )}
          </span>

          <span className="tool">
            <button
              className={`filter-btn ${menu === "sort" ? "open" : ""}`}
              onClick={() => setMenu(menu === "sort" ? null : "sort")}
              title="정렬"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 3.5v13M6 16.5 3.2 13.7M6 3.5 8.8 6.3M14 16.5v-13M14 3.5l2.8 2.8M14 3.5 11.2 6.3" />
              </svg>
              정렬<span className="sort-label">{sortDef.label}</span>
            </button>
            {menu === "sort" && (
              <div className="menu narrow">
                {SORTS.map((s) => (
                  <button key={s.key} className={`menu-item ${sort === s.key ? "on" : ""}`} onClick={() => pick(setSort)(s.key)}>
                    <span className="grow">{s.label}</span>
                    <span className="check">✓</span>
                  </button>
                ))}
              </div>
            )}
          </span>
        </div>

        <div className="task-grid thead">
          {(["ID", "TITLE", "STATUS", "MONTH", "WEEK", "CREATED"] as const).map((col) => (
            <span key={col} className={sortDef.col === col ? "on" : ""}>
              {col}
            </span>
          ))}
        </div>
        {rows.map((t) => (
          <button
            key={t.id}
            className={`task-grid ${t.status === "cancelled" ? "cancelled" : ""}`}
            onClick={() => onOpenTask(t)}
          >
            <span className="c-id">{t.id}</span>
            <span className="c-title">
              <span className="c-title-text">{t.title}</span>
              {t.tags?.map((tag) => (
                <span key={tag} className="tag-chip">
                  {tag}
                </span>
              ))}
            </span>
            <span>
              <StatusChip status={t.status} />
            </span>
            <span className="c-dim">{monthOf(period.months, t.month)}</span>
            <span className="c-dim">{weekLabel(t.week)}</span>
            <span className="c-dim">{fmtServerTime(t.meta.created_at, tz).slice(0, 10)}</span>
          </button>
        ))}
        {sorted.length === 0 && (
          <span className="empty-row">
            {tasks.length === 0 ? "이 분기에는 아직 기간 파일의 태스크가 없어요." : "조건에 맞는 태스크가 없어요."}
          </span>
        )}
        {sorted.length > 0 && (
          <div className="pager">
            <span className="range">
              {from + 1}–{Math.min(from + ROWS_PER_PAGE, sorted.length)} / {sorted.length}
            </span>
            <button className="pg" disabled={pageNo <= 1} onClick={() => setPage(pageNo - 1)} title="이전 페이지" aria-label="이전 페이지">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
            </button>
            {Array.from({ length: pageCount }, (_, k) => k + 1).map((n) => (
              <button key={n} className={`pg num ${n === pageNo ? "on" : ""}`} onClick={() => setPage(n)}>
                {n}
              </button>
            ))}
            <button className="pg" disabled={pageNo >= pageCount} onClick={() => setPage(pageNo + 1)} title="다음 페이지" aria-label="다음 페이지">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
            </button>
          </div>
        )}
      </div>
    </>
  );
}
