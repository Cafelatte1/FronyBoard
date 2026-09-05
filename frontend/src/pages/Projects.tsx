import { useEffect, useState } from "react";
import {
  MILESTONE_ST,
  MilestoneChip,
  ProjectStatusChip,
  RepoIcon,
  SORTS,
  StatusChip,
  TASK_ST,
  TagChip,
  countBy,
  currentPeriodName,
  doneRatio,
  fmtServerTime,
  sortTasks,
  useFavorites,
  useIsPhone,
  type SortKey,
} from "../shared";
import { apiSend } from "../api";
import type { BoardData, Overview, PeriodStatus, Roadmap, ServerTimezone, StatusResp, Task } from "../types";

export default function Projects({
  data,
  openKey,
  setOpenKey,
  onOpenTask,
  focus,
  infoOpen,
  onCloseInfo,
}: {
  data: BoardData;
  openKey: string | null;
  setOpenKey: (key: string | null) => void;
  onOpenTask: (key: string, task: Task) => void;
  /** A search pick: land the detail on this period, paged to this task
      (nonce remounts on every pick). */
  focus?: { period: string; taskId?: string; nonce: number } | null;
  /** The phone detail's ⓘ sheet — its button sits in the app header, so App owns the state. */
  infoOpen?: boolean;
  onCloseInfo?: () => void;
}) {
  if (openKey === null) return <ProjectList data={data} onOpen={setOpenKey} />;
  return (
    <ProjectDetail
      key={focus ? `${openKey}:${focus.nonce}` : openKey}
      data={data}
      projectKey={openKey}
      initialPeriod={focus?.period ?? null}
      initialTaskId={focus?.taskId ?? null}
      onBack={() => setOpenKey(null)}
      onOpenTask={(t) => onOpenTask(openKey, t)}
      infoOpen={infoOpen ?? false}
      onCloseInfo={onCloseInfo ?? (() => {})}
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

/** "2026Q3" -> "3분기" — the year is read off the roadmap stepper above the period. */
function quarterLabel(periodId: string): string {
  const m = /Q([1-4])$/.exec(periodId);
  return m ? `${m[1]}분기` : periodId;
}

/** The current year's now / target / checklist, shared by the web roadmap card and the
    phone ⓘ sheet. Ticking an item is optimistic and persisted through the PATCH route
    (= set_check); a failed request flips it back. Overrides reset when fresh data arrives. */
function useFocus(projectKey: string | undefined, year: string | null, overview: Overview | undefined) {
  const [override, setOverride] = useState<Record<string, boolean>>({});
  useEffect(() => setOverride({}), [overview]);
  const items = (overview?.checklist ?? []).map((c, index) => {
    const k = `${year}:${index}`;
    return { index, text: c.text, done: k in override ? override[k] : c.done };
  });
  const done = items.filter((c) => c.done).length;
  const toggle = async (index: number) => {
    if (!projectKey || !year) return;
    const k = `${year}:${index}`;
    const next = !items[index].done;
    setOverride((o) => ({ ...o, [k]: next }));
    try {
      await apiSend(`/api/projects/${projectKey}/years/${year}/checklist/${index}`, "PATCH", { done: next });
    } catch {
      setOverride((o) => ({ ...o, [k]: !next }));
    }
  };
  return {
    now: overview?.now,
    target: overview?.target,
    items,
    done,
    total: items.length,
    pct: items.length ? Math.round((done / items.length) * 100) : 0,
    has: !!(overview?.now || overview?.target || items.length),
    toggle,
  };
}
type Focus = ReturnType<typeof useFocus>;

/** 현재 · 목표 · 체크리스트 — one row on web (1 : 1 : 1.5), stacked in the phone sheet. */
function FocusRow({ focus }: { focus: Focus }) {
  return (
    <div className="focus">
      <div className="focus-block focus-now">
        <span className="focus-label">현재</span>
        <span className="focus-text">{focus.now ?? "—"}</span>
      </div>
      <div className="focus-block focus-target">
        <span className="focus-label">목표</span>
        <span className="focus-text">{focus.target ?? "—"}</span>
      </div>
      <div className="focus-block focus-list">
        <span className="focus-list-head">
          <span className="focus-label">체크리스트</span>
          {focus.total > 0 && (
            <>
              <span className="bar focus-bar">
                <span className="bar-fill" style={{ width: `${focus.pct}%` }} />
              </span>
              <span className="focus-ratio">
                {focus.done}/{focus.total}
              </span>
            </>
          )}
        </span>
        {focus.total > 0 ? (
          <div className="checks">
            {focus.items.map((c) => (
              <button key={c.index} className={`check ${c.done ? "on" : ""}`} onClick={() => focus.toggle(c.index)} aria-pressed={c.done}>
                <span className="check-box">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 10.5 8 14.5 16 6" /></svg>
                </span>
                <span className="check-text">{c.text}</span>
              </button>
            ))}
          </div>
        ) : (
          <span className="focus-text muted">—</span>
        )}
      </div>
    </div>
  );
}

/** Periods of a year, in order: the active one first if any, else the earliest. */
function landingPeriod(year: string, status: StatusResp): string | null {
  const names = Object.keys(status.periods)
    .filter((n) => n.startsWith(year))
    .sort();
  return names.find((n) => status.periods[n].milestone_status === "active") ?? names[0] ?? null;
}

/** The detail screen shows one period at a time: the roadmap picks the year, the
    quarter dots / stepper pick the period, the table below belongs to that period.

    On a phone the screen *is* the task list: the project summary, the roadmap and
    the period chrome move into a sheet behind the header title, so the tasks are
    the first thing on screen instead of the fifth. */
function ProjectDetail({
  data,
  projectKey,
  initialPeriod,
  initialTaskId,
  onBack,
  onOpenTask,
  infoOpen,
  onCloseInfo,
}: {
  data: BoardData;
  projectKey: string;
  initialPeriod?: string | null;
  initialTaskId?: string | null;
  onBack: () => void;
  onOpenTask: (t: Task) => void;
  infoOpen: boolean;
  onCloseInfo: () => void;
}) {
  const isPhone = useIsPhone();
  const status = data.statuses[projectKey];
  const ref = data.projects.find((p) => p.key === projectKey);
  const roadmap = data.roadmaps[projectKey];
  const allTasks = data.tasks[projectKey] ?? [];

  const current = currentPeriodName(status);
  const periodNames = Object.keys(status.periods).sort();
  const years = [...new Set([...Object.keys(roadmap?.years ?? {}), ...periodNames.map((n) => n.slice(0, 4))])].sort();
  const currentYear = current?.slice(0, 4) ?? years[years.length - 1] ?? null;

  const startPeriod = initialPeriod && status.periods[initialPeriod] ? initialPeriod : current;
  const [year, setYear] = useState<string | null>(startPeriod?.slice(0, 4) ?? currentYear);
  const [periodId, setPeriodId] = useState<string | null>(startPeriod);

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

  const pi = periodNames.indexOf(periodId ?? "");
  const older = pi > 0 ? periodNames[pi - 1] : null;
  const newer = pi >= 0 && pi < periodNames.length - 1 ? periodNames[pi + 1] : null;
  const period = periodId ? status.periods[periodId] : null;
  const periodRatio = doneRatio(countBy(allTasks.filter((t) => t.period === periodId)));

  // The desktop keeps the project's own detail inline, above the task table.
  const about = (
    <>
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
        <PeriodChrome
          name={periodId}
          names={periodNames}
          period={status.periods[periodId]}
          tasks={allTasks.filter((t) => t.period === periodId)}
          onPeriod={selectPeriod}
        />
      )}
    </>
  );

  const table =
    periodId && period ? (
      <TaskTable
        key={periodId}
        name={periodId}
        period={period}
        tasks={allTasks.filter((t) => t.period === periodId)}
        tz={data.server.timezone}
        onOpenTask={onOpenTask}
        initialTaskId={initialTaskId ?? undefined}
      />
    ) : null;

  if (isPhone) {
    return (
      <>
        {/* the back button, project identity and the ⓘ info button live in the app
            header (App.tsx); here only the period stepper remains, standalone */}
        {periodId && period && (
          <div className="pdet-qnav">
              <button className="pdet-nav" disabled={!older} onClick={() => older && selectPeriod(older)} title={older ? `${older} 보기` : "이전 분기 없음"} aria-label="이전 분기">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
              </button>
              <span className="pdet-qmid">
                <span className="pdet-period-id">{quarterLabel(periodId)}</span>
                <span className="pdet-qbar">
                  <span className="bar pdet-qbar-track">
                    <span className="bar-fill" style={{ width: `${periodRatio.pct}%` }} />
                  </span>
                  <span className="pdet-qpct">{periodRatio.pct}%</span>
                </span>
              </span>
              <button className="pdet-nav" disabled={!newer} onClick={() => newer && selectPeriod(newer)} title={newer ? `${newer} 보기` : "다음 분기 없음"} aria-label="다음 분기">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
              </button>
          </div>
        )}

        {table ?? <p className="muted">열린 분기가 없어요 — ⓘ 를 눌러 프로젝트 정보를 볼 수 있어요.</p>}

        {infoOpen && (
          <InfoSheet onClose={onCloseInfo}>
            <span className="pdet-desc">
              {ref?.description ?? "설명이 아직 없어요 — update_project로 추가할 수 있어요."}
            </span>

            <div className="pdet-card pdet-facts">
              <Fact label="REPO" mono value={ref?.repo ?? "—"} />
              <Fact label="CREATED_AT" mono value={ref?.meta ? fmtServerTime(ref.meta.created_at, data.server.timezone) : "—"} />
              <Fact
                label="PERIODS"
                mono
                value={`${periodNames.length}개 분기 · ${[...new Set(periodNames.map((n) => n.slice(0, 4)))].sort().join(", ") || "—"}`}
              />
              <Fact label="분기 목표" value={currentInfo?.goal ?? "열린 기간 없음"} />
            </div>

            <PhoneRoadmap
              roadmap={roadmap}
              status={status}
              year={year}
              years={years}
              currentYear={currentYear}
              periodId={periodId}
              onYear={goYear}
              onPeriod={selectPeriod}
            />

            {periodId && period && (
              <div className="pdet-card">
                <span className="pdet-card-title">{periodId} 월 진행</span>
                {(period.months.length > 0 ? period.months : null)?.map((m) => {
                  const r = doneRatio(m.task_counts);
                  return (
                    <span key={m.id} className="pdet-month">
                      <span className="pdet-month-top">
                        <span className="pdet-month-id">{m.month}</span>
                        <span className="pdet-month-goal">{m.goal ?? "—"}</span>
                        <span className="pdet-month-ratio">{r.total ? `${r.done}/${r.total}` : "—"}</span>
                      </span>
                      <span className="bar pdet-month-bar">
                        {r.total > 0 && <span className="bar-fill" style={{ width: `${r.pct}%` }} />}
                      </span>
                    </span>
                  );
                }) ?? <span className="muted">월 계획이 없는 분기</span>}
              </div>
            )}
          </InfoSheet>
        )}
      </>
    );
  }

  return (
    <>
      <button className="back-btn" onClick={onBack}>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12.5 4.5 7 10l5.5 5.5" />
        </svg>
        프로젝트 목록
      </button>

      {about}
      {table}
    </>
  );
}

function Fact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <span className="pdet-fact">
      <span className="pdet-fact-label">{label}</span>
      <span className={`pdet-fact-value ${mono ? "mono" : ""}`}>{value}</span>
    </span>
  );
}

/** Bottom sheet behind the ⓘ button: the project's own detail, on top of the task list. */
function InfoSheet({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="sheet-layer">
      <button className="sheet-scrim" onClick={onClose} aria-label="닫기" />
      <div className="info-sheet" role="dialog" aria-label="프로젝트 정보">
        <span className="sheet-grip" />
        <div className="sheet-head">
          <span className="sheet-title">프로젝트 정보</span>
          <button className="sheet-close" onClick={onClose} title="닫기" aria-label="닫기">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
              <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
            </svg>
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}

/** The roadmap as a phone reads it: a 2x2 grid of quarters instead of the desktop
    timeline, which needs horizontal room for its connecting segments. */
function PhoneRoadmap({
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
  if (!year) {
    return (
      <div className="pdet-card">
        <span className="pdet-card-title">로드맵</span>
        <span className="muted">로드맵이 아직 없어요.</span>
      </div>
    );
  }
  const yd = roadmap?.years[year];
  const yi = years.indexOf(year);
  const prev = yi > 0 ? years[yi - 1] : null;
  const next = yi >= 0 && yi < years.length - 1 ? years[yi + 1] : null;
  const ms = yd?.milestones ?? {};
  const focus = useFocus(roadmap?.key, year, yd?.overview);

  return (
    <div className="pdet-card pdet-road">
      <div className="pdet-road-head">
        <span className="ynav">
          <button className="ynav-btn" disabled={!prev} onClick={() => prev && onYear(prev)} title="이전 연도" aria-label="이전 연도">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
          </button>
          <span className="ynav-year">{year}</span>
          <button className="ynav-btn" disabled={!next} onClick={() => next && onYear(next)} title="다음 연도" aria-label="다음 연도">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
          </button>
        </span>
        <span className="pdet-road-title">
          <span className="pdet-card-title">로드맵</span>
          <span className="pdet-road-goal">{yd?.overview.goal ?? "이 해의 연간 목표가 아직 없어요."}</span>
        </span>
      </div>

      <div className="pdet-q-grid">
        {QUARTERS.map((q) => {
          const pid = `${year}${q}`;
          const hasFile = !!status.periods[pid];
          const st = ms[q]?.status ?? (hasFile ? (status.periods[pid].milestone_status ?? "planned") : "none");
          return (
            <button
              key={q}
              className={`pdet-q q-${st} ${pid === periodId ? "sel" : ""}`}
              disabled={!hasFile}
              onClick={() => onPeriod(pid)}
              title={hasFile ? `${pid} 보기` : `${pid} — 기간 파일 없음`}
            >
              <span className="pdet-q-top">
                <span className="pdet-q-dot" />
                <span className="pdet-q-id">{q}</span>
                <span className="pdet-q-label">{MILESTONE_ST[st] ?? st}</span>
              </span>
              <span className="pdet-q-goal">{ms[q]?.goal ?? status.periods[pid]?.goal ?? "—"}</span>
            </button>
          );
        })}
      </div>

      {yd && year === currentYear && focus.has && <FocusRow focus={focus} />}
    </div>
  );
}

/** The period stepper and the monthly rollup — the part of a period that is not its
    task list. Split out so a phone can move it into the detail sheet. */
function PeriodChrome({
  name,
  names,
  period,
  tasks,
  onPeriod,
}: {
  name: string;
  names: string[];
  period: PeriodStatus;
  tasks: Task[];
  onPeriod: (id: string) => void;
}) {
  const i = names.indexOf(name);
  const older = i > 0 ? names[i - 1] : null;
  const newer = i >= 0 && i < names.length - 1 ? names[i + 1] : null;
  const ratio = doneRatio(countBy(tasks));

  return (
    <>
      <div className="pstep">
        <span className="ynav">
          <button className="ynav-btn lg" disabled={!older} onClick={() => older && onPeriod(older)} title={older ? `${older} 보기` : "이전 분기 없음"} aria-label="이전 분기">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
          </button>
          <span className="pstep-id">{quarterLabel(name)}</span>
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
    </>
  );
}

/** Year stepper + goal → quarter timeline (dots are buttons) → 현재/목표/체크리스트 on the active year. */
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
  const focus = useFocus(roadmap?.key, year, yd?.overview);
  return (
    <div className="card">
      <div className="road-head">
        <span className="ynav">
          <button className="ynav-btn" disabled={!prev} onClick={() => prev && onYear(prev)} title="이전 연도" aria-label="이전 연도">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
          </button>
          <span className="ynav-year">{year}</span>
          <button className="ynav-btn" disabled={!next} onClick={() => next && onYear(next)} title="다음 연도" aria-label="다음 연도">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
          </button>
        </span>
        <span className="card-title">로드맵</span>
        <span className="road-goal">{yd?.overview.goal ?? "이 해의 연간 목표가 아직 없어요."}</span>
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

      {yd && year === currentYear && focus.has && <FocusRow focus={focus} />}
    </div>
  );
}

const ROWS_PER_PAGE = 10;

/** Page numbers to draw: the whole run, or a window of `max` centred on the current page. */
function pageNums(pageNo: number, pageCount: number, max: number): number[] {
  if (pageCount <= max) return Array.from({ length: pageCount }, (_, k) => k + 1);
  const start = Math.min(Math.max(1, pageNo - Math.floor(max / 2)), pageCount - max + 1);
  return Array.from({ length: max }, (_, k) => start + k);
}
const FILTERS = ["all", "in_progress", "todo", "blocked", "done", "cancelled"] as const;
type Filter = (typeof FILTERS)[number];

/** Menu/button colours per filter key — "전체" and "취소됨" are not regular status chips. */
function filterDot(f: Filter): string {
  if (f === "all") return "var(--text-muted)";
  if (f === "cancelled") return "var(--text-disabled)";
  return TASK_ST[f].swatch;
}
function filterLabel(f: Filter): string {
  if (f === "all") return "전체";
  if (f === "cancelled") return "취소됨";
  return TASK_ST[f].label;
}

/** The task table of one period, with its own filter / sort / page state
    (reset whenever the period changes — see key=). */
function TaskTable({
  name,
  period,
  tasks,
  tz,
  onOpenTask,
  initialTaskId,
}: {
  name: string;
  period: PeriodStatus;
  tasks: Task[];
  tz: ServerTimezone | undefined;
  onOpenTask: (t: Task) => void;
  /** Start on the page holding this task (a search pick). */
  initialTaskId?: string;
}) {
  const target = initialTaskId ? tasks.find((t) => t.id === initialTaskId) : undefined;
  const [statuses, setStatuses] = useState<Filter[]>([]);
  const [sort, setSort] = useState<SortKey>("created");
  const [page, setPage] = useState(() => {
    if (!target) return 1;
    const list = sortTasks(tasks, "created", period.months.map((m) => m.id));
    const idx = list.findIndex((t) => t.id === target.id);
    return idx < 0 ? 1 : Math.floor(idx / ROWS_PER_PAGE) + 1;
  });
  const [menu, setMenu] = useState<"filter" | "sort" | null>(null);
  const isPhone = useIsPhone();

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu]);

  const counts = countBy(tasks);
  const visible = tasks.filter((t) => statuses.length === 0 || statuses.includes(t.status as Filter));
  const sorted = sortTasks(visible, sort, period.months.map((m) => m.id));
  const pageCount = Math.max(1, Math.ceil(sorted.length / ROWS_PER_PAGE));
  const pageNo = Math.min(page, pageCount);
  const from = (pageNo - 1) * ROWS_PER_PAGE;
  const rows = sorted.slice(from, from + ROWS_PER_PAGE);
  const sortDef = SORTS.find((s) => s.key === sort)!;
  // Beside the 이전/다음 pills a phone fits five number buttons (168 + 36x5 = 348 of
  // the 361px it has); past that the row would push the pills off the screen.
  const nums = pageNums(pageNo, pageCount, isPhone ? 5 : pageCount);

  const pick = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
    setMenu(null);
  };

  // Multi-select: "전체" clears the selection, and picking every status folds back
  // to 전체. The menu stays open so several statuses can be toggled in one visit.
  const toggleStatus = (f: Filter) => {
    setStatuses((cur) => {
      if (f === "all") return [];
      const next = cur.includes(f) ? cur.filter((k) => k !== f) : [...cur, f];
      return next.length >= FILTERS.length - 1 ? [] : next;
    });
    setPage(1);
  };
  const selFilters = FILTERS.filter((f) => f !== "all" && statuses.includes(f));

  return (
    <>
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
              className={`filter-btn ${statuses.length > 0 ? "on" : ""}`}
              onClick={() => setMenu(menu === "filter" ? null : "filter")}
              title="필터"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M3 5.2h14M5.6 10h8.8M8.2 14.8h3.6" />
              </svg>
              필터
              <span className="dots">
                {(statuses.length > 0 ? selFilters.slice(0, 3) : (["all"] as const)).map((f) => (
                  <span key={f} className="fdot" style={{ background: filterDot(f) }} />
                ))}
                {selFilters.length > 3 && <span className="fmore">+{selFilters.length - 3}</span>}
              </span>
            </button>
            {menu === "filter" && (
              <div className="menu">
                <span className="menu-cap">상태</span>
                {FILTERS.map((f) => (
                  <button
                    key={f}
                    className={`menu-item ${(f === "all" ? statuses.length === 0 : statuses.includes(f)) ? "on" : ""}`}
                    onClick={() => toggleStatus(f)}
                  >
                    <span className="dot" style={{ background: filterDot(f) }} />
                    <span className="grow">{filterLabel(f)}</span>
                    <span className="n">{f === "all" ? tasks.length : (counts[f] ?? 0)}</span>
                  </button>
                ))}
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
                <span className="menu-cap">정렬 기준</span>
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
          {(["ID", "TITLE", "CREATED", "STATUS", "TAGS"] as const).map((col) => (
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
            <span className="c-title">{t.title}</span>
            <span className="c-dim c-created">{fmtServerTime(t.meta.created_at, tz).slice(0, 10)}</span>
            <span className="c-status">
              <StatusChip status={t.status} />
            </span>
            <span className="c-tags">
              {t.tags?.map((tag) => (
                <TagChip key={tag} tag={tag} />
              ))}
            </span>
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
            <button className="pg edge" disabled={pageNo <= 1} onClick={() => setPage(pageNo - 1)} title="이전 페이지" aria-label="이전 페이지">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
              {/* the phone pager spells the edges out — see the mockup */}
              <span className="pg-word">이전</span>
            </button>
            <span className="pg-nums">
              {nums.map((n) => (
                <button key={n} className={`pg num ${n === pageNo ? "on" : ""}`} onClick={() => setPage(n)}>
                  {n}
                </button>
              ))}
            </span>
            <button className="pg edge" disabled={pageNo >= pageCount} onClick={() => setPage(pageNo + 1)} title="다음 페이지" aria-label="다음 페이지">
              <span className="pg-word">다음</span>
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
            </button>
          </div>
        )}
      </div>
    </>
  );
}
