import { ProgressBar, useApi } from "../shared";
import type { ProjectRef, StatusResp } from "../types";

export default function Dashboard({
  onOpenProject,
  onAuthFail,
}: {
  onOpenProject: (key: string) => void;
  onAuthFail: () => void;
}) {
  const { data, error } = useApi<{ projects: ProjectRef[] }>("/api/projects", onAuthFail);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  if (data.projects.length === 0) return <p className="muted">No projects yet — create one over MCP.</p>;
  return (
    <div className="cards-col">
      {data.projects.map((p) => (
        <ProjectSummary key={p.key} project={p} onOpen={() => onOpenProject(p.key)} onAuthFail={onAuthFail} />
      ))}
    </div>
  );
}

function ProjectSummary({
  project,
  onOpen,
  onAuthFail,
}: {
  project: ProjectRef;
  onOpen: () => void;
  onAuthFail: () => void;
}) {
  const { data, error } = useApi<StatusResp>(`/api/projects/${project.key}/status`, onAuthFail);
  if (error)
    return (
      <div className="card">
        <p className="error">
          {project.key}: {error}
        </p>
      </div>
    );
  if (!data) return <div className="card muted">Loading {project.key}…</div>;

  const periods = Object.entries(data.periods).sort((a, b) => a[0].localeCompare(b[0]));
  const current =
    [...periods].reverse().find(([, p]) => p.milestone_status === "active") ??
    periods[periods.length - 1];
  const activeMonth = current?.[1].months.find((m) => m.status === "active");

  return (
    <div className="card summary" onClick={onOpen} role="button" tabIndex={0}>
      <div className="summary-head">
        <h3>
          <span className="project-key">{project.key}</span>{" "}
          {data.name ?? ""}
        </h3>
        {current && <ProgressBar counts={current[1].task_counts} />}
      </div>
      {current ? (
        <>
          <p className="muted">
            <span className="mono">{current[0]}</span> — {current[1].goal ?? "no milestone goal"}
          </p>
          {activeMonth && (
            <p className="muted">
              This month (<span className="mono">{activeMonth.month}</span>): {activeMonth.goal ?? "—"}
            </p>
          )}
          {current[1].in_progress.length > 0 && (
            <div className="chips">
              {current[1].in_progress.map((id) => (
                <span key={id} className="chip status-in_progress">
                  {id}
                </span>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="muted">No open period.</p>
      )}
    </div>
  );
}
