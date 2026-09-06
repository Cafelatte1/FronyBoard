import { useCallback, useEffect, useRef, useState } from "react";
import { Unauthorized, api } from "./api";
import type { BoardData, MonthInfo, ProjectRef, ServerTimezone, StatusResp, Task } from "./types";

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
const REFRESH_MS = 60_000;

export function useBoardData(onAuthFail: () => void) {
  const [data, setData] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const reload = useCallback(() => {
    return (async () => {
      // One round trip for the whole board (AIR-072): the server assembles what used to
      // be 2 + 3n requests, and the SPA keeps it in memory as before.
      const board = await api<BoardData>("/api/board");
      setData(board);
      setFetchedAt(new Date());
      setError(null);
    })().catch((e) => {
      if (e instanceof Unauthorized) onAuthFail();
      else setError(String(e.message ?? e));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Auto refresh: every minute while the tab is visible, and right away when the
  // tab comes back after being stale — agents write through MCP, the board follows.
  const fetchedRef = useRef<Date | null>(null);
  fetchedRef.current = fetchedAt;
  useEffect(() => {
    const stale = () => !fetchedRef.current || Date.now() - fetchedRef.current.getTime() >= REFRESH_MS;
    const t = setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible" && stale()) reload();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [reload]);

  return { data, error, fetchedAt, reload };
}

// ------------------------------------------------------------ status labels

/** Phones get a different shell, not a squeezed one: bottom tabs instead of the drawer,
    and the comfortable density so touch targets clear 44px. Width decides, not the
    user agent — a narrowed desktop window is the same layout problem. */
const PHONE = "(max-width: 760px)";

export function useIsPhone(): boolean {
  const [phone, setPhone] = useState(() => window.matchMedia(PHONE).matches);
  useEffect(() => {
    const mq = window.matchMedia(PHONE);
    const onChange = () => setPhone(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return phone;
}

export const TASK_ST: Record<string, { label: string; swatch: string }> = {
  done: { label: "완료", swatch: "var(--success)" },
  in_progress: { label: "진행중", swatch: "var(--accent)" },
  todo: { label: "대기", swatch: "var(--border-strong)" },
  blocked: { label: "블록", swatch: "var(--danger)" },
  cancelled: { label: "취소", swatch: "var(--neutral-subtle)" },
};

export const MILESTONE_ST: Record<string, string> = {
  active: "진행",
  done: "완료",
  planned: "예정",
  none: "없음", // a roadmap quarter with no period file
};

// ------------------------------------------------------------------ sorting

export type SortKey = "id" | "created" | "status" | "month";

export const SORTS: { key: SortKey; label: string; col: string }[] = [
  { key: "id", label: "ID 순", col: "ID" },
  { key: "created", label: "최근 생성 순", col: "CREATED" },
  { key: "status", label: "상태 순", col: "STATUS" },
  { key: "month", label: "월 · 주차 순", col: "MONTH" },
];

const STATUS_ORDER = ["in_progress", "blocked", "todo", "done", "cancelled"];

/** Stable sort by the chosen key; ties fall back to id. `monthOrder` is the period's month ids. */
export function sortTasks(tasks: Task[], key: SortKey, monthOrder: string[]): Task[] {
  const byId = (a: Task, b: Task) => a.id.localeCompare(b.id);
  const cmp: Record<SortKey, (a: Task, b: Task) => number> = {
    id: byId,
    created: (a, b) => b.meta.created_at.localeCompare(a.meta.created_at) || byId(a, b),
    status: (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || byId(a, b),
    month: (a, b) =>
      monthOrder.indexOf(a.month) - monthOrder.indexOf(b.month) || (a.week ?? 9) - (b.week ?? 9) || byId(a, b),
  };
  return [...tasks].sort(cmp[key]);
}

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

// ---------------------------------------------------------------- favorites

const FAV_KEY = "fronyboard_favorites";

function readFavorites(): string[] {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return []; // storage blocked or corrupt — behave as "no favorites"
  }
}

/** Starred project keys, kept per browser in localStorage (the board is read-only
    and single-user, so this never touches the server). */
export function useFavorites(): [Set<string>, (key: string) => void] {
  const [favs, setFavs] = useState<string[]>(readFavorites);
  const toggle = useCallback((key: string) => {
    setFavs((cur) => {
      const next = cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key];
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify(next));
      } catch {
        // keep the in-memory value for this page view
      }
      return next;
    });
  }, []);
  return [new Set(favs), toggle];
}

/** Newest `meta.updated_at` across a project's record and its tasks ("" when unknown). */
export function latestUpdate(ref: ProjectRef, tasks: Task[]): string {
  let latest = ref.meta?.updated_at ?? "";
  for (const t of tasks) if (t.meta.updated_at > latest) latest = t.meta.updated_at;
  return latest;
}

/** The period a project is "on": the newest active milestone, else the newest period. */
export function currentPeriodName(status: StatusResp): string | null {
  const names = Object.keys(status.periods).sort();
  const active = [...names].reverse().find((n) => status.periods[n].milestone_status === "active");
  return active ?? names[names.length - 1] ?? null;
}

/** The month a task sits in, as its calendar month ("2026-07"); falls back to the id. */
export function monthOf(months: MonthInfo[], monthId: string): string {
  return months.find((m) => m.id === monthId)?.month ?? monthId;
}

export function weekLabel(week: number | undefined): string {
  return week ? `${week}주차` : "—";
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

/** "KST (UTC+9)" / "UTC+9" / "UTC" — the label for timestamps shifted by `tz`. */
export function tzLabel(tz: ServerTimezone | undefined): string {
  if (!tz) return "UTC";
  const m = tz.offset_minutes;
  const sign = m < 0 ? "-" : "+";
  const h = Math.floor(Math.abs(m) / 60);
  const mm = Math.abs(m) % 60;
  const utc = m === 0 ? "UTC" : `UTC${sign}${h}${mm ? ":" + String(mm).padStart(2, "0") : ""}`;
  return tz.name && tz.name !== utc ? `${tz.name} (${utc})` : utc;
}

/** A stored naive-UTC timestamp rendered in the server's zone: "2026-08-24 23:08:12". */
export function fmtServerTime(s: string, tz: ServerTimezone | undefined): string {
  const t = new Date(parseUtc(s).getTime() + (tz?.offset_minutes ?? 0) * 60000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())} ${p(t.getUTCHours())}:${p(t.getUTCMinutes())}:${p(t.getUTCSeconds())}`;
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

/** Tags name a category, not a state: the colour comes from the tag's own text, so the
    same tag looks the same everywhere and no tag outranks another. Eight hues, wrapping. */
export function TagChip({ tag }: { tag: string }) {
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) >>> 0;
  return (
    <span className={`tag-chip cat-${(h % 8) + 1}`}>
      <span className="tag-dot" />
      {tag}
    </span>
  );
}

export const PROJECT_ST: Record<string, string> = { active: "운영 중", paused: "보류", archived: "보관" };

export function ProjectStatusChip({ status }: { status: string | undefined }) {
  const s = status ?? "active";
  return <span className={`chip pst-${s}`}>{PROJECT_ST[s] ?? s}</span>;
}

/** Small "where the code lives" glyph used next to a repo name. */
export function RepoIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="5.5" cy="4.5" r="2" />
      <circle cx="5.5" cy="15.5" r="2" />
      <circle cx="14.5" cy="7" r="2" />
      <path d="M5.5 6.5v7M14.5 9c0 3.5-9 2-9 4.5" />
    </svg>
  );
}

export function MilestoneChip({ status }: { status: string | null }) {
  const s = status ?? "planned";
  return <span className={`chip mst-${s}`}>{MILESTONE_ST[s] ?? s}</span>;
}
