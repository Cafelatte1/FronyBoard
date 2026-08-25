import { parseMd, type Span } from "./markdown";
import { StatusChip, TASK_ST, fmtServerTime, monthOf, tzLabel, weekLabel } from "./shared";
import type { MonthInfo, ServerTimezone, Task } from "./types";

/** Right-hand slide-over with the full task record. Stays mounted so the
    close transition can play; `task` null just means closed. */
export default function TaskPanel({
  task,
  projectKey,
  months,
  tz,
  onClose,
}: {
  task: Task | null;
  projectKey: string | null;
  months: MonthInfo[];
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
              <button className="panel-close" onClick={onClose} title="닫기" aria-label="닫기">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" />
                </svg>
              </button>
            </div>

            <div className="panel-body">
              <div className="field-grid">
                <Field label="status" value={TASK_ST[task.status]?.label ?? task.status} tone="accent" />
                <Field
                  label="month"
                  value={task.week ? `${monthOf(months, task.month)} · ${weekLabel(task.week)}` : monthOf(months, task.month)}
                />
                <Field label="branch" value={task.branch ?? "—"} tone={task.branch ? undefined : "dim"} />
                <Field label="project" value={projectKey ?? "—"} />
              </div>

              {task.cancel_reason && (
                <div className="cancel-box">
                  <span className="panel-cap">취소 사유 · cancel_reason</span>
                  <p>{task.cancel_reason}</p>
                </div>
              )}

              <div className="panel-section">
                <span className="panel-cap">content · markdown</span>
                <Markdown
                  src={
                    task.content ??
                    "이 태스크에는 아직 `content`가 없습니다.\n\n에이전트가 `update_task`로 상세를 채우면 이 자리에 표시됩니다."
                  }
                />
              </div>

              {task.prd && (
                <div className="panel-section sep">
                  <span className="panel-cap">prd</span>
                  <div className="panel-prd">{task.prd}</div>
                </div>
              )}

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

function Markdown({ src }: { src: string }) {
  return (
    <div className="md">
      {parseMd(src).map((b, i) =>
        b.kind === "code" ? (
          <pre key={i} className="md-code">
            {b.text}
          </pre>
        ) : (
          <div key={i} className={`md-${b.kind}`}>
            <Spans spans={b.spans} />
          </div>
        ),
      )}
    </div>
  );
}

function Spans({ spans }: { spans: Span[] }) {
  return (
    <>
      {spans.map((s, i) =>
        s.kind === "code" ? (
          <code key={i}>{s.text}</code>
        ) : s.kind === "strong" ? (
          <strong key={i}>{s.text}</strong>
        ) : s.kind === "em" ? (
          <em key={i}>{s.text}</em>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}
