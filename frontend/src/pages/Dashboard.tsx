import { TASK_ST, countBy, currentPeriodName, doneRatio, donutGradient, parseUtc } from "../shared";
import type { BoardData, Task } from "../types";

export default function Dashboard({
  data,
  onOpenProject,
  onOpenTask,
}: {
  data: BoardData;
  onOpenProject: (key: string) => void;
  onOpenTask: (key: string, task: Task) => void;
}) {
  if (data.projects.length === 0)
    return <p className="muted">프로젝트가 없어요 — MCP로 먼저 등록해 주세요.</p>;

  // Every project's "current" period tasks, pooled for the top widgets.
  const perProject = data.projects.map((p) => {
    const status = data.statuses[p.key];
    const period = currentPeriodName(status);
    const tasks = (data.tasks[p.key] ?? []).filter((t) => t.period === period);
    return { ref: p, status, period, tasks };
  });
  const pooled = perProject.flatMap((p) => p.tasks);
  const counts = countBy(pooled);
  const ratio = doneRatio(counts);

  const weekAgo = Date.now() - 7 * 86400000;
  const createdThisWeek = pooled.filter((t) => parseUtc(t.meta.created_at).getTime() >= weekAgo).length;
  const withBranch = pooled.filter((t) => t.status === "in_progress" && t.branch).length;
  const firstBlocked = pooled.find((t) => t.status === "blocked");

  // Done delta vs the period right before each project's current one.
  let prevDone: number | null = null;
  for (const p of perProject) {
    const names = Object.keys(p.status.periods).sort();
    const idx = p.period ? names.indexOf(p.period) : -1;
    if (idx > 0) {
      const prev = names[idx - 1];
      prevDone =
        (prevDone ?? 0) +
        (data.tasks[p.ref.key] ?? []).filter((t) => t.period === prev && t.status === "done").length;
    }
  }

  const wip = perProject.flatMap((p) =>
    p.tasks.filter((t) => t.status === "in_progress").map((t) => ({ key: p.ref.key, task: t })),
  );

  const mainPeriod = perProject.find((p) => p.period)?.period ?? null;
  const burn = mainPeriod ? burnup(pooled, mainPeriod) : null;

  return (
    <>
      <div className="stat-grid">
        <Stat
          label="전체 태스크"
          value={ratio.total}
          delta={createdThisWeek > 0 ? `+${createdThisWeek}` : ""}
          deltaClass="dim"
          sub={`${mainPeriod ?? ""} · 취소 제외`}
        />
        <Stat label="진행 중" value={counts["in_progress"] ?? 0} delta="WIP" deltaClass="dim" sub={`브랜치 연결 ${withBranch}건`} />
        <Stat
          label="이번 분기 완료"
          value={ratio.done}
          delta={`${ratio.pct}%`}
          deltaClass="up"
          sub={
            prevDone !== null
              ? `지난 분기 대비 ${ratio.done - prevDone >= 0 ? "+" : ""}${ratio.done - prevDone}`
              : "완료율"
          }
        />
        <Stat
          label="블록됨"
          value={counts["blocked"] ?? 0}
          delta={counts["blocked"] ? "확인 필요" : "없음"}
          deltaClass={counts["blocked"] ? "warn" : "dim"}
          sub={firstBlocked ? `${firstBlocked.id} ${firstBlocked.title}` : "—"}
        />
      </div>

      <div className="dash-mid">
        <div className="card">
          <div className="card-title">이번 분기 상태 분포</div>
          <div className="card-sub mono">
            {mainPeriod ?? "—"} · {data.projects.length} projects
          </div>
          <div className="donut-row">
            <div className="donut" style={{ background: donutGradient(counts) }}>
              <div className="donut-hole">
                <span className="donut-pct">{ratio.pct}%</span>
                <span className="donut-cap">완료</span>
              </div>
            </div>
            <div className="legend">
              {(["done", "in_progress", "todo", "blocked"] as const).map((s) => (
                <div key={s} className="legend-row">
                  <span className="legend-swatch" style={{ background: TASK_ST[s].swatch }} />
                  <span style={{ flex: 1 }}>{TASK_ST[s].label}</span>
                  <span className="legend-n">{counts[s] ?? 0}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card burn-card">
          <div className="burn-head">
            <div>
              <div className="card-title">주별 완료 추이 (누적)</div>
              <div className="card-sub mono">
                {mainPeriod ?? "—"}
                {burn && burn.weeks.length > 1 && ` · ${burn.weeks[0]}–${burn.weeks[burn.weeks.length - 1]}`}
              </div>
            </div>
            <div className="burn-total">
              <b>{burn ? burn.values[burn.values.length - 1] : 0}</b>
              <span>누적 완료</span>
            </div>
          </div>
          {burn && burn.values.length >= 3 ? (
            <>
              <BurnChart values={burn.values} />
              <div className="burn-weeks">
                {burn.weeks.map((w) => (
                  <span key={w}>{w}</span>
                ))}
              </div>
            </>
          ) : (
            <div className="burn-empty">데이터 없음</div>
          )}
        </div>
      </div>

      <div className="project-grid-3">
        {perProject.map(({ ref, status, period, tasks }) => {
          const r = doneRatio(countBy(tasks));
          const periodInfo = period ? status.periods[period] : null;
          return (
            <button key={ref.key} className="card project-card" onClick={() => onOpenProject(ref.key)}>
              <span className="project-card-head">
                <span className="id-chip">{ref.key}</span>
                <span className="project-card-name">{status.name ?? ref.key}</span>
              </span>
              <span className="project-card-goal">{periodInfo?.goal ?? "열린 기간 없음"}</span>
              <span>
                <span className="project-card-meta">
                  <span className="mono">{period ?? "—"}</span>
                  <span className="pct">
                    {r.done}/{r.total} · {r.pct}%
                  </span>
                </span>
                <span className="bar">
                  <span className="bar-fill" style={{ width: `${r.pct}%` }} />
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="card">
        <div className="list-head">
          <span className="card-title">지금 진행 중인 태스크</span>
          <span>브랜치 연결 {withBranch}건</span>
        </div>
        <div className="rows">
          {wip.length === 0 && <p className="muted">진행 중인 태스크가 없어요.</p>}
          {wip.map(({ key, task }) => (
            <button key={task.id} className="row row-btn" onClick={() => onOpenTask(key, task)}>
              <span className="t-id">{task.id}</span>
              <span className="t-title">{task.title}</span>
              <span className="t-branch">{task.branch ?? "—"}</span>
            </button>
          ))}
        </div>
      </div>

    </>
  );
}

function Stat({
  label,
  value,
  delta,
  deltaClass = "",
  sub,
}: {
  label: string;
  value: number;
  delta: string;
  deltaClass?: string;
  sub: string;
}) {
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className="stat-line">
        <span className="stat-value">{value}</span>
        {delta && <span className={`stat-delta ${deltaClass}`}>{delta}</span>}
      </div>
      <div className="stat-sub" title={sub}>
        {sub}
      </div>
    </div>
  );
}

/** Cumulative done counts per ISO week of the quarter, up to today.
    completed_at only accumulates from v0.2.0 on — older done tasks land in week 1. */
function burnup(tasks: Task[], period: string): { weeks: string[]; values: number[] } | null {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (!m) return null;
  const year = Number(m[1]);
  const startMonth = (Number(m[2]) - 1) * 3;
  const qStart = new Date(Date.UTC(year, startMonth, 1));
  const qEnd = new Date(Date.UTC(year, startMonth + 3, 1));
  const end = new Date(Math.min(Date.now(), qEnd.getTime()));
  if (end <= qStart) return null;

  const weekEnds: Date[] = [];
  const cur = new Date(qStart);
  cur.setUTCDate(cur.getUTCDate() + ((7 - ((cur.getUTCDay() + 6) % 7)) % 7 || 7)); // next Monday
  while (cur <= end) {
    weekEnds.push(new Date(cur));
    cur.setUTCDate(cur.getUTCDate() + 7);
  }
  weekEnds.push(new Date(end.getTime() + 1));

  const doneAt = tasks
    .filter((t) => t.status === "done")
    .map((t) => (t.meta.completed_at ? parseUtc(t.meta.completed_at).getTime() : qStart.getTime()));
  const values = weekEnds.map((w) => doneAt.filter((d) => d < w.getTime()).length);
  const weeks = weekEnds.map((w) => `W${isoWeek(new Date(w.getTime() - 86400000))}`);
  return { weeks, values };
}

function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNum = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const diff = (date.getTime() - firstThursday.getTime()) / 86400000;
  return 1 + Math.round((diff - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
}

function BurnChart({ values }: { values: number[] }) {
  const W = 640;
  const H = 168;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => {
    const x = values.length === 1 ? W : (i / (values.length - 1)) * W;
    const y = H - 12 - (v / max) * (H - 26);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="burn-svg">
      <defs>
        <linearGradient id="fbline" x1="0" y1="0" x2={W} y2="0" gradientUnits="userSpaceOnUse">
          <stop style={{ stopColor: "var(--brand-1)" }} />
          <stop offset="1" style={{ stopColor: "var(--brand-2)" }} />
        </linearGradient>
        <linearGradient id="fbarea" x1="0" y1="0" x2="0" y2={H} gradientUnits="userSpaceOnUse">
          <stop style={{ stopColor: "var(--accent)", stopOpacity: 0.34 }} />
          <stop offset="1" style={{ stopColor: "var(--accent)", stopOpacity: 0 }} />
        </linearGradient>
      </defs>
      <path d={`M0 42H${W}M0 84H${W}M0 126H${W}`} stroke="var(--border)" strokeWidth="1" />
      <path d={`M0,${H - 12} L${pts.join(" L")} L${W},${H - 12} Z`} fill="url(#fbarea)" />
      <polyline points={pts.join(" ")} fill="none" stroke="url(#fbline)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
