import { useState } from "react";
import {
  GradientBar,
  MilestoneChip,
  StatusChip,
  countBy,
  currentPeriodName,
  doneRatio,
  donutGradient,
} from "../shared";
import type { BoardData, PeriodStatus, Task } from "../types";

export default function Projects({
  data,
  openKey,
  setOpenKey,
}: {
  data: BoardData;
  openKey: string | null;
  setOpenKey: (key: string | null) => void;
}) {
  if (openKey === null) return <ProjectList data={data} onOpen={setOpenKey} />;
  return <ProjectDetail data={data} projectKey={openKey} onBack={() => setOpenKey(null)} />;
}

function ProjectList({ data, onOpen }: { data: BoardData; onOpen: (k: string) => void }) {
  if (data.projects.length === 0)
    return <p className="muted">프로젝트가 없어요 — MCP로 먼저 등록해 주세요.</p>;
  return (
    <div className="project-grid">
      {data.projects.map((p) => {
        const status = data.statuses[p.key];
        const period = currentPeriodName(status);
        const tasks = (data.tasks[p.key] ?? []).filter((t) => t.period === period);
        const c = countBy(tasks);
        return (
          <button key={p.key} className="card project-card" onClick={() => onOpen(p.key)}>
            <div className="project-card-head">
              <span className="id-chip">{p.key}</span>
              <span className="project-card-name" style={{ fontSize: 16 }}>
                {status.name ?? p.key}
              </span>
              <span className="muted">→</span>
            </div>
            <div className="project-card-goal">
              {(period && status.periods[period]?.goal) ?? "열린 기간 없음"}
            </div>
            <div className="mini-grid">
              {(
                [
                  ["완료", c["done"] ?? 0, "var(--lav-light)"],
                  ["진행중", c["in_progress"] ?? 0, "var(--ink)"],
                  ["대기", c["todo"] ?? 0, "var(--muted)"],
                  ["블록", c["blocked"] ?? 0, "var(--red-soft)"],
                ] as const
              ).map(([label, n, color]) => (
                <div key={label}>
                  <div className="mini-n" style={{ color }}>
                    {n}
                  </div>
                  <div className="mini-label">{label}</div>
                </div>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function ProjectDetail({
  data,
  projectKey,
  onBack,
}: {
  data: BoardData;
  projectKey: string;
  onBack: () => void;
}) {
  const [showCancelled, setShowCancelled] = useState(false);
  const status = data.statuses[projectKey];
  const roadmap = data.roadmaps[projectKey];
  const allTasks = data.tasks[projectKey] ?? [];

  const periodNames = Object.keys(status.periods).sort((a, b) => b.localeCompare(a));
  const current = currentPeriodName(status);
  const currentTasks = allTasks.filter((t) => t.period === current);
  const currentRatio = doneRatio(countBy(currentTasks));

  const latestYear = Object.keys(roadmap.years ?? {}).sort((a, b) => b.localeCompare(a))[0];
  const overview = latestYear ? roadmap.years[latestYear].overview : null;

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="detail-bar">
        <button className="back-btn" onClick={onBack}>
          ← 프로젝트 목록
        </button>
        <div style={{ flex: 1 }} />
        {periodNames.map((n) => (
          <span key={n} className={`period-chip ${n === current ? "on" : ""}`}>
            {n}
          </span>
        ))}
      </div>

      <div className="card" style={{ padding: "22px 24px" }}>
        <div className="detail-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="detail-name">
              {status.name ?? projectKey}
              <span className="id-chip">{projectKey}</span>
            </div>
            {overview && <div className="detail-goal">{overview.goal}</div>}
            {overview && (
              <div className="detail-nnl">
                {(
                  [
                    ["Now", overview.now],
                    ["Next", overview.next],
                    ["Later", overview.later],
                  ] as const
                ).map(([label, text]) => (
                  <div key={label} className="nnl-item">
                    <div className="nnl-label">{label}</div>
                    <div className="nnl-text">{text}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="detail-donut">
            <div
              className="donut"
              style={{ width: 118, height: 118, margin: "0 auto", background: donutGradient(countBy(currentTasks)) }}
            >
              <div className="donut-hole" style={{ inset: 13 }}>
                <span className="donut-pct" style={{ fontSize: 22 }}>
                  {currentRatio.pct}%
                </span>
                <span className="donut-cap mono">
                  {currentRatio.done}/{currentRatio.total}
                </span>
              </div>
            </div>
            <div className="detail-donut-cap">{current ?? "—"} 진행률</div>
          </div>
        </div>
      </div>

      {periodNames.map((name) => (
        <PeriodSection
          key={name}
          name={name}
          period={status.periods[name]}
          tasks={allTasks.filter((t) => t.period === name)}
          showCancelled={showCancelled}
          setShowCancelled={setShowCancelled}
        />
      ))}
    </div>
  );
}

function PeriodSection({
  name,
  period,
  tasks,
  showCancelled,
  setShowCancelled,
}: {
  name: string;
  period: PeriodStatus;
  tasks: Task[];
  showCancelled: boolean;
  setShowCancelled: (v: boolean) => void;
}) {
  const ratio = doneRatio(countBy(tasks));
  const shown = tasks.filter((t) => showCancelled || t.status !== "cancelled");
  return (
    <section className="card" style={{ padding: "22px 24px" }}>
      <div className="period-title">
        <span className="p-name">{name}</span>
        <MilestoneChip status={period.milestone_status} />
        <span className="p-goal">{period.goal ?? ""}</span>
        <span className="p-ratio">
          {ratio.done}/{ratio.total} · {ratio.pct}%
        </span>
        <GradientBar pct={ratio.pct} />
      </div>

      {period.months.length > 0 && (
        <div className="month-grid">
          {period.months.map((m) => {
            const r = doneRatio(m.task_counts);
            return (
              <div key={m.id} className={`month-card ${m.status === "active" ? "on" : ""}`}>
                <div className="month-head">
                  <span className="m-id">{m.id}</span>
                  <span className="m-month">{m.month}</span>
                  <MilestoneChip status={m.status} />
                </div>
                <div className="month-goal">{m.goal ?? "—"}</div>
                <div className="month-progress">
                  <GradientBar pct={r.pct} />
                  <span className="m-ratio">
                    {r.done}/{r.total}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="table-head">
        <span className="count">
          태스크 <b>{shown.length}/{tasks.length}</b>
        </span>
        <button className={`toggle-btn ${showCancelled ? "on" : ""}`} onClick={() => setShowCancelled(!showCancelled)}>
          취소된 태스크 표시
        </button>
      </div>
      <div className="task-table">
        <div className="task-grid thead">
          <span>ID</span>
          <span>TITLE</span>
          <span>MONTH</span>
          <span>STATUS</span>
          <span>BRANCH</span>
          <span>DONE</span>
        </div>
        {shown.map((t) => (
          <div key={t.id} className={`task-grid ${t.status === "cancelled" ? "cancelled" : ""}`}>
            <span className="c-id">{t.id}</span>
            <span className="c-title" title={t.cancel_reason ?? t.content ?? ""}>
              {t.title}
            </span>
            <span className="c-dim">{t.month}</span>
            <span>
              <StatusChip status={t.status} />
            </span>
            <span className="c-branch">{t.branch ?? "—"}</span>
            <span className="c-date">{t.meta.completed_at?.slice(0, 10) ?? "—"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
