import { useState } from "react";
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
  const [burnMode, setBurnMode] = useState<BurnMode>(storedBurnMode);
  const pickBurn = (m: BurnMode) => {
    setBurnMode(m);
    try {
      localStorage.setItem(BURN_KEY, m);
    } catch {
      /* private mode / blocked storage — the tab just does not stick */
    }
  };

  if (data.projects.length === 0)
    return <p className="muted">No projects yet — register one through MCP first.</p>;

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

  // The WIP list is grouped by project, in the server's project order.
  const wipGroups = perProject
    .map((p) => ({
      key: p.ref.key,
      name: p.status.name ?? p.ref.key,
      tasks: p.tasks.filter((t) => t.status === "in_progress"),
    }))
    .filter((g) => g.tasks.length > 0);

  const mainPeriod = perProject.find((p) => p.period)?.period ?? null;
  const burn = completionBuckets(pooled, burnMode, mainPeriod);
  const burnSum = burn.values.reduce((a, b) => a + b, 0);

  return (
    <>
      <div className="stat-grid">
        <Stat
          label="Total tasks"
          value={ratio.total}
          delta={createdThisWeek > 0 ? `+${createdThisWeek}` : ""}
          deltaClass="dim"
          sub={`${mainPeriod ?? ""} · excl. cancelled`}
        />
        <Stat label="In progress" value={counts["in_progress"] ?? 0} delta="WIP" deltaClass="dim" sub={`${withBranch} with a branch`} />
        <Stat
          label="Done this quarter"
          value={ratio.done}
          delta={`${ratio.pct}%`}
          deltaClass="up"
          sub={
            prevDone !== null
              ? `${ratio.done - prevDone >= 0 ? "+" : ""}${ratio.done - prevDone} vs last quarter`
              : "completion rate"
          }
        />
        <Stat
          label="Blocked"
          value={counts["blocked"] ?? 0}
          delta={counts["blocked"] ? "needs a look" : "none"}
          deltaClass={counts["blocked"] ? "warn" : "dim"}
          sub={firstBlocked ? `${firstBlocked.id} ${firstBlocked.title}` : "—"}
        />
      </div>

      <div className="dash-mid">
        <div className="card">
          <div className="card-title">Status this quarter</div>
          <div className="card-sub mono">
            {mainPeriod ?? "—"} · {data.projects.length} projects
          </div>
          <div className="donut-row">
            <div className="donut" style={{ background: donutGradient(counts) }}>
              <div className="donut-hole">
                <span className="donut-pct">{ratio.pct}%</span>
                <span className="donut-cap">done</span>
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
              <div className="card-title">Completion trend</div>
              <div className="card-sub mono">{burn.range}</div>
            </div>
            <div className="burn-tabs">
              <button className={burnMode === "daily" ? "on" : ""} onClick={() => pickBurn("daily")}>
                Daily
              </button>
              <button className={burnMode === "weekly" ? "on" : ""} onClick={() => pickBurn("weekly")}>
                Weekly
              </button>
            </div>
          </div>
          <div className="burn-total">
            <b>{burnSum}</b>
            <span>{burn.sumLabel}</span>
          </div>
          <BurnChart values={burn.values} labels={burn.labels} />
        </div>
      </div>

      <div className="card">
        <div className="list-head">
          <span className="card-title">In progress now</span>
          <span>{withBranch} with a branch</span>
        </div>
        <div className="wip-groups">
          {wipGroups.length === 0 && <p className="muted">Nothing in progress.</p>}
          {wipGroups.map((g) => (
            <div key={g.key} className="wip-group">
              {/* a span, not a button: the rows below it are buttons of their own */}
              <span
                role="button"
                tabIndex={0}
                className="wip-group-head"
                title={`Open ${g.key}`}
                onClick={() => onOpenProject(g.key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onOpenProject(g.key);
                }}
              >
                <span className="id-chip">{g.key}</span>
                <span className="wip-group-name">{g.name}</span>
              </span>
              <div className="rows">
                {g.tasks.map((task) => (
                  <button key={task.id} className="row row-btn" onClick={() => onOpenTask(g.key, task)}>
                    <span className="t-id">{task.id}</span>
                    <span className="t-title">{task.title}</span>
                    <span className="t-branch">{task.branch ?? "—"}</span>
                  </button>
                ))}
              </div>
            </div>
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
type BurnMode = "daily" | "weekly";

const BURN_KEY = "fb.burnMode";

function storedBurnMode(): BurnMode {
  try {
    return localStorage.getItem(BURN_KEY) === "weekly" ? "weekly" : "daily";
  } catch {
    return "daily";
  }
}

const DAY = 86400000;
const KST = 9 * 3600000;

/** Day index (0 = 1970-01-01) of a KST-shifted timestamp. */
const dayOf = (ms: number) => Math.floor(ms / DAY);
/** Day index of that day's Monday. Day 0 was a Thursday, hence the +3. */
const mondayOf = (day: number) => day - ((day + 3) % 7);

/** How many tasks finished in each bucket, oldest bucket first. Buckets are cut on KST
    boundaries: completed_at is stamped in UTC, so cutting there would push anything
    finished before 09:00 KST into the previous day. */
function completionBuckets(tasks: Task[], mode: BurnMode, period: string | null) {
  const done = tasks
    .filter((t) => t.status === "done" && t.meta.completed_at)
    .map((t) => dayOf(parseUtc(t.meta.completed_at!).getTime() + KST));
  const today = dayOf(Date.now() + KST);
  const values = Array(7).fill(0) as number[];

  if (mode === "daily") {
    for (const d of done) {
      const i = 6 - (today - d);
      if (i >= 0 && i < 7) values[i]++;
    }
    const labels = values.map((_, i) => {
      const d = new Date((today - (6 - i)) * DAY);
      return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
    });
    return { values, labels, sumLabel: "done in the last 7 days",
             range: `${labels[0]} – ${labels[6]} · incl. today` };
  }

  const thisMonday = mondayOf(today);
  for (const d of done) {
    const i = 6 - (thisMonday - mondayOf(d)) / 7;
    if (i >= 0 && i < 7) values[i]++;
  }
  const labels = values.map((_, i) => `W${isoWeek(new Date((thisMonday - (6 - i) * 7) * DAY))}`);
  return { values, labels, sumLabel: "done in the last 7 weeks",
           range: `${period ? `${period} · ` : ""}${labels[0]}–${labels[6]} · incl. this week` };
}

function isoWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNum = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const diff = (date.getTime() - firstThursday.getTime()) / 86400000;
  return 1 + Math.round((diff - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
}

function BurnChart({ values, labels }: { values: number[]; labels: string[] }) {
  const max = Math.max(...values, 1);
  const last = values.length - 1;
  return (
    <>
      <div className="burn-bars">
        {values.map((v, i) => (
          <span key={labels[i]} className={`burn-bar ${i === last ? "on" : ""}`}>
            <span className="burn-val">{v}</span>
            <span className="burn-fill" style={{ height: `${Math.max(4, Math.round((v / max) * 112))}px` }} />
          </span>
        ))}
      </div>
      <div className="burn-labels">
        {labels.map((l, i) => (
          <span key={l} className={i === last ? "on" : ""}>
            {l}
          </span>
        ))}
      </div>
    </>
  );
}
