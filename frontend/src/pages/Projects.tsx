import { useState } from "react";
import { MilestoneChip, StatusChip, TASK_ST, countBy, currentPeriodName, doneRatio } from "../shared";
import type { BoardData, PeriodStatus, Task } from "../types";

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
                <span className="project-card-period">{period ?? "—"}</span>
              </span>
              <span className="project-card-goal">
                {(period && status.periods[period]?.goal) ?? "열린 기간 없음"}
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
  const [showCancelled, setShowCancelled] = useState(false);
  const status = data.statuses[projectKey];
  const allTasks = data.tasks[projectKey] ?? [];

  const current = currentPeriodName(status);
  const periodNames = Object.keys(status.periods).sort((a, b) => b.localeCompare(a));
  const currentInfo = current ? status.periods[current] : null;
  const currentRatio = doneRatio(countBy(allTasks.filter((t) => t.period === current)));

  return (
    <>
      <button className="back-btn" onClick={onBack}>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12.5 4.5 7 10l5.5 5.5" />
        </svg>
        프로젝트 목록
      </button>

      <div className="card summary-card">
        <span className="id-chip">{projectKey}</span>
        <span className="summary-name">{status.name ?? projectKey}</span>
        <span className="summary-goal">{currentInfo?.goal ?? "열린 기간 없음"}</span>
        <span className="summary-period">{current ?? "—"}</span>
        <span className="summary-ratio">
          {currentRatio.done}/{currentRatio.total} · {currentRatio.pct}%
        </span>
        <span className="bar summary-bar">
          <span className="bar-fill" style={{ width: `${currentRatio.pct}%` }} />
        </span>
      </div>

      {periodNames.map((name) => (
        <PeriodBlock
          key={name}
          name={name}
          isCurrent={name === current}
          period={status.periods[name]}
          tasks={allTasks.filter((t) => t.period === name)}
          showCancelled={showCancelled}
          setShowCancelled={setShowCancelled}
          onOpenTask={onOpenTask}
        />
      ))}
    </>
  );
}

function PeriodBlock({
  name,
  isCurrent,
  period,
  tasks,
  showCancelled,
  setShowCancelled,
  onOpenTask,
}: {
  name: string;
  isCurrent: boolean;
  period: PeriodStatus;
  tasks: Task[];
  showCancelled: boolean;
  setShowCancelled: (v: boolean) => void;
  onOpenTask: (t: Task) => void;
}) {
  const shown = tasks.filter((t) => showCancelled || t.status !== "cancelled");
  const ratio = doneRatio(countBy(tasks));
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
                <span className="m-id">{m.id}</span>
                <span className="m-month">{m.month}</span>
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
                  <span className="r-id">{m.id}</span>
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
        <button className={`toggle-btn ${showCancelled ? "on" : ""}`} onClick={() => setShowCancelled(!showCancelled)}>
          취소된 태스크 표시
        </button>
      </div>
      <div className="task-table">
        <div className="task-grid thead">
          <span>ID</span>
          <span>TITLE</span>
          <span>STATUS</span>
          <span>M</span>
          <span>W</span>
          <span>BRANCH</span>
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
            <span className="c-dim">{t.month}</span>
            <span className="c-dim">{t.week ? `W${t.week}` : "—"}</span>
            <span className="c-branch">{t.branch ?? "—"}</span>
          </button>
        ))}
        {shown.length === 0 && (
          <div className="task-grid">
            <span className="muted" style={{ gridColumn: "1 / -1" }}>
              태스크가 없어요.
            </span>
          </div>
        )}
      </div>
    </>
  );
}
