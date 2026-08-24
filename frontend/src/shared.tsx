import { useCallback, useEffect, useState } from "react";
import { Unauthorized, api } from "./api";
import type { BoardData, Roadmap, ServerInfo, StatusResp, Task } from "./types";

// ---------------------------------------------------------------- data hooks

export function useApi<T>(path: string, onAuthFail: () => void) {
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

/** Load everything the shell needs in one go; tiny data set, so no paging. */
export function useBoardData(onAuthFail: () => void) {
  const [data, setData] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const reload = useCallback(() => {
    (async () => {
      const [server, projectsResp] = await Promise.all([
        api<ServerInfo>("/api/server"),
        api<{ projects: BoardData["projects"] }>("/api/projects"),
      ]);
      const projects = projectsResp.projects;
      const statuses: Record<string, StatusResp> = {};
      const tasks: Record<string, Task[]> = {};
      const roadmaps: Record<string, Roadmap> = {};
      await Promise.all(
        projects.map(async (p) => {
          const [s, t, r] = await Promise.all([
            api<StatusResp>(`/api/projects/${p.key}/status`),
            api<{ tasks: Task[] }>(`/api/projects/${p.key}/tasks?include_cancelled=true`),
            api<{ roadmap: Roadmap }>(`/api/projects/${p.key}/roadmap`),
          ]);
          statuses[p.key] = s;
          tasks[p.key] = t.tasks;
          roadmaps[p.key] = r.roadmap;
        }),
      );
      setData({ projects, statuses, tasks, roadmaps, server });
      setFetchedAt(new Date());
      setError(null);
    })().catch((e) => {
      if (e instanceof Unauthorized) onAuthFail();
      else setError(String(e.message ?? e));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(reload, [reload]);
  return { data, error, fetchedAt, reload };
}

// ------------------------------------------------------------ status labels

export const TASK_ST: Record<string, { label: string; swatch: string }> = {
  done: { label: "완료", swatch: "var(--success)" },
  in_progress: { label: "진행중", swatch: "var(--accent)" },
  todo: { label: "대기", swatch: "var(--neutral-subtle)" },
  blocked: { label: "블록", swatch: "var(--danger)" },
  cancelled: { label: "취소", swatch: "var(--neutral-subtle)" },
};

export const MILESTONE_ST: Record<string, string> = {
  active: "진행",
  done: "완료",
  planned: "예정",
};

// ------------------------------------------------------------- computations

export function countBy(tasks: Task[]): Record<string, number> {
  const c: Record<string, number> = {};
  for (const t of tasks) c[t.status] = (c[t.status] ?? 0) + 1;
  return c;
}

export function doneRatio(counts: Record<string, number>): { done: number; total: number; pct: number } {
  const done = counts["done"] ?? 0;
  const total = Object.entries(counts)
    .filter(([s]) => s !== "cancelled")
    .reduce((n, [, c]) => n + c, 0);
  return { done, total, pct: total === 0 ? 0 : Math.round((done / total) * 100) };
}

/** The period a project is "on": the newest active milestone, else the newest period. */
export function currentPeriodName(status: StatusResp): string | null {
  const names = Object.keys(status.periods).sort();
  const active = [...names].reverse().find((n) => status.periods[n].milestone_status === "active");
  return active ?? names[names.length - 1] ?? null;
}

export function donutGradient(counts: Record<string, number>): string {
  const order = ["done", "in_progress", "todo", "blocked"];
  const total = order.reduce((n, k) => n + (counts[k] ?? 0), 0) || 1;
  let acc = 0;
  const stops = order.map((k) => {
    const from = (acc / total) * 100;
    acc += counts[k] ?? 0;
    const to = (acc / total) * 100;
    return `${TASK_ST[k].swatch} ${from.toFixed(2)}% ${to.toFixed(2)}%`;
  });
  return `conic-gradient(from -90deg, ${stops.join(", ")})`;
}

// ------------------------------------------------------------------- dates

/** Server timestamps are naive UTC ("2026-08-18 09:15:00" or ISO). */
export function parseUtc(s: string): Date {
  const iso = s.replace(" ", "T");
  return new Date(iso.endsWith("Z") ? iso : iso + "Z");
}

export function fmtAgo(d: Date, now: Date = new Date()): string {
  const mins = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (mins < 1) return "방금 전";
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

export function fmtUptime(startedAt: string): string {
  const mins = Math.floor((Date.now() - parseUtc(startedAt).getTime()) / 60000);
  if (mins < 60) return `${Math.max(mins, 0)}분`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 ${mins % 60}분`;
  return `${Math.floor(hours / 24)}일 ${hours % 24}시간`;
}

// ------------------------------------------------------------ small pieces

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip st-${status}`}>{TASK_ST[status]?.label ?? status}</span>;
}

export function MilestoneChip({ status }: { status: string | null }) {
  const s = status ?? "planned";
  return <span className={`chip mst-${s}`}>{MILESTONE_ST[s] ?? s}</span>;
}
