import { useEffect, useState } from "react";
import { Unauthorized, api, clearKey, getKey, setKey } from "./api";
import type { EpicInfo, PeriodStatus, ProjectRef, Roadmap, StatusResp, Task } from "./types";

type View = { page: "list" } | { page: "project"; projectKey: string };

export default function App() {
  const [authed, setAuthed] = useState(getKey() !== null);
  const [view, setView] = useState<View>({ page: "list" });

  const onAuthFail = () => {
    clearKey();
    setAuthed(false);
  };

  if (!authed) return <KeyGate onDone={() => setAuthed(true)} />;
  return (
    <div className="shell">
      <header className="topbar">
        <h1 className="brand" onClick={() => setView({ page: "list" })}>
          Frony<span>Board</span>
        </h1>
        <button className="ghost" onClick={onAuthFail}>
          sign out
        </button>
      </header>
      {view.page === "list" ? (
        <ProjectList onOpen={(k) => setView({ page: "project", projectKey: k })} onAuthFail={onAuthFail} />
      ) : (
        <ProjectView projectKey={view.projectKey} onBack={() => setView({ page: "list" })} onAuthFail={onAuthFail} />
      )}
    </div>
  );
}

function KeyGate({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="keygate">
      <h1 className="brand">
        Frony<span>Board</span>
      </h1>
      <p>Paste an AIRA API key to view your boards.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!value.trim()) return;
          setKey(value.trim());
          onDone();
        }}
      >
        <input
          type="password"
          placeholder="aira_…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
        />
        <button type="submit">Open</button>
      </form>
    </div>
  );
}

function useApi<T>(path: string, onAuthFail: () => void) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api<T>(path)
      .then((d) => live && setData(d))
      .catch((e) => {
        if (!live) return;
        if (e instanceof Unauthorized) onAuthFail();
        else setError(String(e.message ?? e));
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  return { data, error };
}

function ProjectList({ onOpen, onAuthFail }: { onOpen: (k: string) => void; onAuthFail: () => void }) {
  const { data, error } = useApi<{ projects: ProjectRef[] }>("/api/projects", onAuthFail);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  if (data.projects.length === 0) return <p className="muted">No projects yet — create one over MCP.</p>;
  return (
    <div className="cards">
      {data.projects.map((p) => (
        <button key={p.key} className="card project-card" onClick={() => onOpen(p.key)}>
          <span className="project-key">{p.key}</span>
          <span className="project-name">{p.name ?? "—"}</span>
        </button>
      ))}
    </div>
  );
}

function ProjectView({
  projectKey,
  onBack,
  onAuthFail,
}: {
  projectKey: string;
  onBack: () => void;
  onAuthFail: () => void;
}) {
  const roadmap = useApi<{ roadmap: Roadmap }>(`/api/projects/${projectKey}/roadmap`, onAuthFail);
  const status = useApi<StatusResp>(`/api/projects/${projectKey}/status`, onAuthFail);
  const tasks = useApi<{ tasks: Task[] }>(
    `/api/projects/${projectKey}/tasks?include_cancelled=true`,
    onAuthFail,
  );
  const [showCancelled, setShowCancelled] = useState(false);

  const error = roadmap.error ?? status.error ?? tasks.error;
  if (error) return <p className="error">{error}</p>;
  if (!roadmap.data || !status.data || !tasks.data) return <p className="muted">Loading…</p>;

  const years = Object.entries(roadmap.data.roadmap.years ?? {}).sort((a, b) => b[0].localeCompare(a[0]));
  const periods = Object.entries(status.data.periods).sort((a, b) => b[0].localeCompare(a[0]));

  return (
    <div className="project">
      <nav>
        <button className="ghost" onClick={onBack}>
          ← projects
        </button>
        <h2>
          {status.data.name ?? projectKey} <span className="muted">({projectKey})</span>
        </h2>
      </nav>

      {years.map(([year, y]) => (
        <section key={year} className="card">
          <h3>
            {year} <span className="muted">— {y.overview.goal}</span>
          </h3>
          <div className="nnl">
            <div>
              <span className="nnl-label">Now</span> {y.overview.now}
            </div>
            <div>
              <span className="nnl-label">Next</span> {y.overview.next}
            </div>
            <div>
              <span className="nnl-label">Later</span> {y.overview.later}
            </div>
          </div>
          {y.milestones && (
            <div className="chips">
              {Object.entries(y.milestones).map(([q, m]) => (
                <span key={q} className={`chip status-${m.status}`}>
                  {q} · {m.goal}
                </span>
              ))}
            </div>
          )}
        </section>
      ))}

      {periods.map(([name, p]) => (
        <PeriodSection
          key={name}
          name={name}
          period={p}
          tasks={tasks.data!.tasks.filter(
            (t) => t.period === name && (showCancelled || t.status !== "cancelled"),
          )}
          showCancelled={showCancelled}
          setShowCancelled={setShowCancelled}
        />
      ))}
    </div>
  );
}

function doneRatio(counts: Record<string, number>): { done: number; total: number } {
  const done = counts["done"] ?? 0;
  const total = Object.entries(counts)
    .filter(([s]) => s !== "cancelled")
    .reduce((n, [, c]) => n + c, 0);
  return { done, total };
}

function ProgressBar({ counts }: { counts: Record<string, number> }) {
  const { done, total } = doneRatio(counts);
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div className="progress" title={`${done}/${total} done`}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
      <span className="progress-text">
        {done}/{total} · {pct}%
      </span>
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
  return (
    <section className="card">
      <div className="period-head">
        <h3>
          {name} <span className={`chip status-${period.milestone_status}`}>{period.milestone_status}</span>
        </h3>
        <ProgressBar counts={period.task_counts} />
      </div>
      {period.goal && <p className="muted">{period.goal}</p>}

      <div className="chips">
        {period.months.map((m) => (
          <span key={m.id} className={`chip status-${m.status}`}>
            {m.id} · {m.month} · {m.goal ?? ""}
          </span>
        ))}
      </div>

      {period.epics.length > 0 && (
        <div className="epics">
          {period.epics.map((e) => (
            <EpicRow key={e.id} epic={e} />
          ))}
        </div>
      )}

      <div className="table-head">
        <h4>Tasks</h4>
        <label className="toggle">
          <input
            type="checkbox"
            checked={showCancelled}
            onChange={(e) => setShowCancelled(e.target.checked)}
          />
          show cancelled
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>title</th>
              <th>epic</th>
              <th>month</th>
              <th>status</th>
              <th>branch</th>
              <th>done</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id} className={t.status === "cancelled" ? "row-cancelled" : ""}>
                <td className="mono">{t.id}</td>
                <td title={t.cancel_reason ?? t.content ?? ""}>{t.title}</td>
                <td className="mono">{t.epic}</td>
                <td className="mono">{t.month}</td>
                <td>
                  <span className={`chip status-${t.status}`}>{t.status}</span>
                </td>
                <td className="mono branch">{t.branch ?? ""}</td>
                <td className="mono">{t.meta.completed_at?.slice(0, 10) ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EpicRow({ epic }: { epic: EpicInfo }) {
  return (
    <div className="epic-row">
      <span className="mono epic-id">{epic.id}</span>
      <span className="epic-goal">{epic.goal}</span>
      <ProgressBar counts={epic.task_counts} />
    </div>
  );
}
