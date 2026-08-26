import { useState } from "react";
import {
  MilestoneChip,
  ProjectStatusChip,
  RepoIcon,
  StatusChip,
  TASK_ST,
  countBy,
  currentPeriodName,
  doneRatio,
  fmtServerTime,
  monthOf,
  weekLabel,
} from "../shared";
import type { BoardData, MonthInfo, PeriodStatus, Roadmap, ServerTimezone, Task } from "../types";

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
      data={data}
      projectKey={openKey}
      onBack={() => setOpenKey(null)}
      onOpenTask={(t) => onOpenTask(openKey, t)}
    />
  );
}

const COUNT_ORDER = ["done", "in_progress", "todo", "blocked"] as const;

function ProjectList({ data, onOpen }: { data: BoardData; onOpen: (k: string) => void }) {
  if (data.projects.length === 0)
    return <p className="muted">프로젝트가 없어요 — MCP로 먼저 등록해 주세요.</p>;
  return (
    <>
      <span className="hint-text">카드를 누르면 해당 프로젝트의 상세 화면으로 이동합니다.</span>
      <div className="project-grid-2">
        {data.projects.map((p) => {
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
              <span>
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
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}

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
  const [filter, setFilter] = useState<TaskFilter>({ status: [], month: [], cancelled: false, open: null });
  const status = data.statuses[projectKey];
  const ref = data.projects.find((p) => p.key === projectKey);
  const allTasks = data.tasks[projectKey] ?? [];

  const current = currentPeriodName(status);
  const periodNames = Object.keys(status.periods).sort((a, b) => b.localeCompare(a));
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
        roadmap={data.roadmaps[projectKey]}
        projectKey={projectKey}
        current={current}
        months={currentInfo?.months ?? []}
      />

      {periodNames.map((name) => (
        <PeriodBlock
          key={name}
          name={name}
          isCurrent={name === current}
          period={status.periods[name]}
          tasks={allTasks.filter((t) => t.period === name)}
          filter={filter}
          setFilter={setFilter}
          tz={data.server.timezone}
          onOpenTask={onOpenTask}
        />
      ))}
    </>
  );
}

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"] as const;
const NNL = ["now", "next", "later"] as const;

/** Year goal → quarter timeline → current-period month ticks → NOW/NEXT/LATER. */
function RoadmapCard({
  roadmap,
  projectKey,
  current,
  months,
}: {
  roadmap: Roadmap | undefined;
  projectKey: string;
  current: string | null;
  months: MonthInfo[];
}) {
  const year = roadmap ? Object.keys(roadmap.years ?? {}).sort((a, b) => b.localeCompare(a))[0] : undefined;
  const yd = roadmap && year ? roadmap.years[year] : null;
  if (!yd) {
    return (
      <div className="card">
        <div className="card-title">로드맵</div>
        <p className="muted">로드맵이 아직 없어요.</p>
      </div>
    );
  }
  const ms = yd.milestones ?? {};
  const activeIdx = QUARTERS.findIndex((q) => ms[q]?.status === "active");
  const lit = (j: number) => j <= activeIdx;
  return (
    <div className="card">
      <div className="road-head">
        <span className="card-title">{year} 로드맵</span>
        <span className="mono">{projectKey} · 연간</span>
      </div>
      <span className="road-goal">{yd.overview.goal}</span>

      <div className="qtl">
        {QUARTERS.map((q, i) => {
          const st = ms[q]?.status ?? "planned";
          return (
            <div key={q} className={`q q-${st}`}>
              <span className="q-line">
                <span className={`q-seg ${i === 0 ? "hide" : lit(i) ? "lit" : ""}`} />
                <span className={`q-seg ${i === QUARTERS.length - 1 ? "hide" : lit(i + 1) ? "lit" : ""}`} />
                <span className="q-dot" />
              </span>
              <span className="q-id">{q}</span>
              <MilestoneChip status={st} />
              <span className="q-goal">{ms[q]?.goal ?? "—"}</span>
            </div>
          );
        })}
      </div>

      {current && months.length > 0 && (
        <div className="ticks">
          <span className="ticks-period">{current}</span>
          {months.map((m) => {
            const r = doneRatio(m.task_counts);
            return (
              <span key={m.id} className={`tick ${m.status === "planned" ? "planned" : ""}`}>
                <span className="tick-head">
                  <span className="tick-month">{m.month}</span>
                  <span className="tick-ratio">{r.total ? `${r.done}/${r.total}` : "—"}</span>
                </span>
                <span className="bar tick-bar">
                  {r.total > 0 && <span className="bar-fill" style={{ width: `${r.pct}%` }} />}
                </span>
              </span>
            );
          })}
        </div>
      )}

      <div className="nnl">
        {NNL.map((k, i) => (
          <div key={k} className={`nnl-item nnl-${i}`}>
            <div className="nnl-label">{k}</div>
            <div className="nnl-text">{yd.overview[k]}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Table filters live on the detail screen so they apply to every period block. */
interface TaskFilter {
  status: string[];
  month: string[];
  cancelled: boolean;
  open: "status" | "month" | null;
}

const STATUS_OPTIONS = ["done", "in_progress", "todo", "blocked"] as const;
const EYE_ON = "M2.2 10S5.2 4.6 10 4.6 17.8 10 17.8 10 14.8 15.4 10 15.4 2.2 10 2.2 10Zm7.8 2.3a2.3 2.3 0 1 0 0-4.6 2.3 2.3 0 0 0 0 4.6Z";
const EYE_OFF = "M4 4l12 12M2.2 10S5.2 4.6 10 4.6c1.5 0 2.8.5 3.9 1.2M17.8 10s-3 5.4-7.8 5.4c-1.4 0-2.7-.4-3.8-1.1";

function toggle(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

function PeriodBlock({
  name,
  isCurrent,
  period,
  tasks,
  filter,
  setFilter,
  tz,
  onOpenTask,
}: {
  name: string;
  isCurrent: boolean;
  period: PeriodStatus;
  tasks: Task[];
  filter: TaskFilter;
  setFilter: (f: TaskFilter) => void;
  tz: ServerTimezone | undefined;
  onOpenTask: (t: Task) => void;
}) {
  const shown = tasks.filter(
    (t) =>
      (filter.cancelled || t.status !== "cancelled") &&
      (filter.status.length === 0 || filter.status.includes(t.status)) &&
      (filter.month.length === 0 || filter.month.includes(t.month)),
  );
  const ratio = doneRatio(countBy(tasks));
  const openPicker = (which: "status" | "month") =>
    setFilter({ ...filter, open: filter.open === which ? null : which });
  return (
    <>
      {/* The current period is described by the summary card; older ones get a caption. */}
      {!isCurrent && (
        <div className="period-cap">
          <span className="p-name">{name}</span>
          <MilestoneChip status={period.milestone_status} />
          <span>{period.goal ?? ""}</span>
          <span className="mono" style={{ marginLeft: "auto" }}>
            {ratio.done}/{ratio.total} · {ratio.pct}%
          </span>
        </div>
      )}

      {period.months.length > 0 && (
        <div className="month-grid">
          {period.months.map((m) => (
            <div key={m.id} className={`month-card ${m.status === "active" ? "on" : ""}`}>
              <div className="month-head">
                <span className="m-id">{m.month}</span>
                <MilestoneChip status={m.status} />
              </div>
              <div className="month-goal">{m.goal ?? "—"}</div>
            </div>
          ))}
        </div>
      )}

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

      <div className="table-head">
        <span className="count">
          태스크{" "}
          <b>
            {shown.length}/{tasks.length}
          </b>
        </span>
        <button
          className={`filter-btn ${filter.status.length > 0 ? "on" : ""}`}
          onClick={() => openPicker("status")}
          title="상태 필터"
        >
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M3 5.2h14M5.6 10h8.8M8.2 14.8h3.6" />
          </svg>
          상태{filter.status.length > 0 && ` · ${filter.status.length}`}
        </button>
        {period.months.length > 0 && (
          <button
            className={`filter-btn ${filter.month.length > 0 ? "on" : ""}`}
            onClick={() => openPicker("month")}
            title="월 필터"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <rect x="3" y="4.5" width="14" height="12" rx="1.8" />
              <path d="M3 8h14M7 3v3M13 3v3" />
            </svg>
            월{filter.month.length > 0 && ` · ${filter.month.length}`}
          </button>
        )}
        <button
          className={`filter-btn ${filter.cancelled ? "on" : ""}`}
          onClick={() => setFilter({ ...filter, cancelled: !filter.cancelled })}
          title="취소된 태스크 표시"
        >
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d={filter.cancelled ? EYE_ON : EYE_OFF} />
          </svg>
          취소된 태스크
        </button>
      </div>

      {filter.open === "status" && (
        <div className="filter-row">
          <span className="cap">상태</span>
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              className={`fchip ${filter.status.includes(s) ? "on" : ""}`}
              onClick={() => setFilter({ ...filter, status: toggle(filter.status, s) })}
            >
              {TASK_ST[s].label}
            </button>
          ))}
          {filter.status.length > 0 && (
            <button className="fchip clear" onClick={() => setFilter({ ...filter, status: [] })}>
              전체
            </button>
          )}
        </div>
      )}
      {filter.open === "month" && (
        <div className="filter-row">
          <span className="cap">월</span>
          {period.months.map((m) => (
            <button
              key={m.id}
              className={`fchip ${filter.month.includes(m.id) ? "on" : ""}`}
              onClick={() => setFilter({ ...filter, month: toggle(filter.month, m.id) })}
            >
              {m.month}
            </button>
          ))}
          {filter.month.length > 0 && (
            <button className="fchip clear" onClick={() => setFilter({ ...filter, month: [] })}>
              전체
            </button>
          )}
        </div>
      )}
      <div className="task-table">
        <div className="task-grid thead">
          <span>ID</span>
          <span>TITLE</span>
          <span>STATUS</span>
          <span>MONTH</span>
          <span>WEEK</span>
          <span>CREATED</span>
        </div>
        {shown.map((t) => (
          <button
            key={t.id}
            className={`task-grid ${t.status === "cancelled" ? "cancelled" : ""}`}
            onClick={() => onOpenTask(t)}
          >
            <span className="c-id">{t.id}</span>
            <span className="c-title">{t.title}</span>
            <span>
              <StatusChip status={t.status} />
            </span>
            <span className="c-dim">{monthOf(period.months, t.month)}</span>
            <span className="c-dim">{weekLabel(t.week)}</span>
            <span className="c-dim">{fmtServerTime(t.meta.created_at, tz).slice(0, 10)}</span>
          </button>
        ))}
        {shown.length === 0 && (
          <div className="task-grid">
            <span className="muted" style={{ gridColumn: "1 / -1" }}>
              {tasks.length === 0 ? "태스크가 없어요." : "필터에 맞는 태스크가 없어요."}
            </span>
          </div>
        )}
      </div>
    </>
  );
}
