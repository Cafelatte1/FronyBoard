/** Client-side task search over what the shell already holds (BoardData) — no server API.
    Axes: project key, task id, title, content (decided 2026-08-31; branch and tags are
    deliberately not searched). Case-insensitive substring match, all projects, all
    periods — closed ones included. */

import type { BoardData, Task } from "./types";

export type Hit = { pre: string; hit: string; post: string };

export interface SearchRow {
  task: Task;
  projectKey: string;
  id: Hit;
  title: Hit;
  /** Context around a content-only match; null when the id/title/key already shows why. */
  snippet: Hit | null;
}

export interface SearchGroup {
  key: string;
  name: string;
  /** "2026Q3", or "2026Q4 +1" when the matches span quarters. */
  period: string;
  rows: SearchRow[];
  total: number;
}

const STATUS_ORDER = ["in_progress", "blocked", "todo", "done", "cancelled"];
const SNIPPET_AROUND = 30;

function cut(text: string, q: string): Hit {
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return { pre: text, hit: "", post: "" };
  return { pre: text.slice(0, i), hit: text.slice(i, i + q.length), post: text.slice(i + q.length) };
}

function snippetOf(content: string, q: string): Hit | null {
  const flat = content.replace(/\s+/g, " ");
  const i = flat.toLowerCase().indexOf(q);
  if (i < 0) return null;
  const from = Math.max(0, i - SNIPPET_AROUND);
  const to = Math.min(flat.length, i + q.length + SNIPPET_AROUND);
  return {
    pre: (from > 0 ? "…" : "") + flat.slice(from, i),
    hit: flat.slice(i, i + q.length),
    post: flat.slice(i + q.length, to) + (to < flat.length ? "…" : ""),
  };
}

export function searchTasks(data: BoardData, query: string): SearchGroup[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return data.projects
    .map((p) => {
      const keyHit = p.key.toLowerCase().includes(q);
      const rows = (data.tasks[p.key] ?? [])
        .filter(
          (t) =>
            keyHit ||
            t.id.toLowerCase().includes(q) ||
            t.title.toLowerCase().includes(q) ||
            (t.content ?? "").toLowerCase().includes(q),
        )
        .sort(
          (a, b) =>
            STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.id.localeCompare(b.id),
        )
        .map((t): SearchRow => {
          const id = cut(t.id, q);
          const title = cut(t.title, q);
          const shown = keyHit || !!id.hit || !!title.hit;
          return { task: t, projectKey: p.key, id, title, snippet: shown ? null : snippetOf(t.content ?? "", q) };
        });
      const quarters = [...new Set(rows.map((r) => r.task.period))].sort().reverse();
      return {
        key: p.key,
        name: data.statuses[p.key]?.name ?? p.key,
        period: quarters.length > 1 ? `${quarters[0]} +${quarters.length - 1}` : (quarters[0] ?? ""),
        rows,
        total: rows.length,
      };
    })
    .filter((g) => g.total > 0);
}
