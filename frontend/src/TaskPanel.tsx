import { type ReactNode } from "react";
import { StatusChip, TagChip, TASK_ST, fmtServerTime, tzLabel } from "./shared";
import type { ServerTimezone, Task } from "./types";

/** Right-hand slide-over with the full task record. Stays mounted so the
    close transition can play; `task` null just means closed. */
export default function TaskPanel({
  task,
  projectKey,
  tz,
  onClose,
}: {
  task: Task | null;
  projectKey: string | null;
  tz: ServerTimezone | undefined;
  onClose: () => void;
}) {
  const open = task !== null;

  return (
    <>
      <div className={`panel-backdrop ${open ? "open" : ""}`} onClick={onClose} />
      <aside className={`task-panel ${open ? "open" : ""}`} aria-hidden={!open}>
        {task && (
          <>
            <div className="panel-head">
              <div className="panel-titles">
                <div className="panel-badges">
                  <span className="id-chip">{task.id}</span>
                  <StatusChip status={task.status} />
                </div>
                <div className="panel-title">{task.title}</div>
              </div>
              <button className="panel-close" onClick={onClose} title="Close" aria-label="Close">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" />
                </svg>
              </button>
            </div>

            <div className="panel-body">
              <div className="panel-tags-row">
                <span className="panel-cap">tags</span>
              </div>
              {task.tags && task.tags.length > 0 && (
                <div className="panel-tags">
                  {task.tags.map((tag) => (
                    <TagChip key={tag} tag={tag} />
                  ))}
                </div>
              )}
              <div className="field-grid">
                <Field label="status" value={TASK_ST[task.status]?.label ?? task.status} tone="accent" />
                <Field label="branch" value={task.branch ?? "—"} tone={task.branch ? undefined : "dim"} />
                <Field label="project" value={projectKey ?? "—"} />
              </div>

              {task.cancel_reason && (
                <div className="cancel-box">
                  <span className="panel-cap">cancel_reason</span>
                  <p>{task.cancel_reason}</p>
                </div>
              )}

              <div className="panel-section">
                <span className="panel-cap">content</span>
                {task.content
                  ? <p className="panel-note"><InlineMd text={task.content} /></p>
                  : <p className="panel-note dim">—</p>}
              </div>

              <div className="panel-section sep">
                <span className="panel-cap">meta · {tzLabel(tz)}</span>
                {metaRows(task).map(([label, value]) => (
                  <div key={label} className="meta-row">
                    <span>{label}</span>
                    <span>{fmtServerTime(value, tz)}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
}

function metaRows(task: Task): [string, string][] {
  const m = task.meta;
  const rows: [string, string | undefined][] = [
    ["created_at", m.created_at],
    ["updated_at", m.updated_at],
    ["started_at", m.started_at],
    ["completed_at", m.completed_at],
  ];
  return rows.filter((r): r is [string, string] => Boolean(r[1]));
}

function Field({ label, value, tone }: { label: string; value: string; tone?: "accent" | "dim" }) {
  return (
    <span className="field">
      <span className="field-label">{label}</span>
      <span className={`field-value ${tone ?? ""}`} title={value}>
        {value}
      </span>
    </span>
  );
}

/** Inline markdown for the one-line task `content`: `code`, **bold**, _italic_.
    Block markdown is gone with the 25-line body (v0.33.0) — content is one short line now. */
function InlineMd({ text }: { text: string }) {
  const re = /(`[^`]+`|\*\*[^*]+\*\*|_[^_]+_)/g;
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("`")) out.push(<code key={out.length}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={out.length}>{tok.slice(2, -2)}</strong>);
    else out.push(<em key={out.length}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}
