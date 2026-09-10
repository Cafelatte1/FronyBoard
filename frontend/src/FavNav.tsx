import { useEffect, useRef, useState } from "react";
import { countBy, currentPeriodName, doneRatio, latestUpdate } from "./shared";
import type { BoardData } from "./types";

/** Header shortcut to the starred projects (AIR-082): a dropdown left of the search
    box, most recently touched project first. Favorites live in localStorage and the
    board is read-only, so this only navigates. */
export default function FavNav({
  data,
  favs,
  onOpen,
}: {
  data: BoardData;
  favs: Set<string>;
  onOpen: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const rows = data.projects
    .filter((p) => favs.has(p.key))
    .map((p) => {
      const status = data.statuses[p.key];
      const tasks = data.tasks[p.key] ?? [];
      const period = currentPeriodName(status);
      const r = doneRatio(countBy(tasks.filter((t) => t.period === period)));
      const updated = latestUpdate(p, tasks);
      return { key: p.key, name: status?.name ?? p.key, pct: r.pct, updated };
    })
    .sort((a, b) => b.updated.localeCompare(a.updated));

  return (
    <div className="fav-nav" ref={wrapRef}>
      <button
        className={`fav-nav-btn ${open ? "open" : ""}`}
        disabled={rows.length === 0}
        aria-expanded={open}
        aria-haspopup="menu"
        title="Favorites"
        onClick={() => setOpen((v) => !v)}
      >
        <svg className={`fav-nav-star ${rows.length > 0 ? "on" : ""}`} viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" fill="none">
          <path d="M10 2.6l2.28 4.7 5.12.72-3.72 3.63.9 5.1L10 14.35l-4.58 2.4.9-5.1L2.6 8.02l5.12-.72L10 2.6z" />
        </svg>
        <span className="fav-nav-count">{rows.length}</span>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5.5 8l4.5 4.5L14.5 8" />
        </svg>
      </button>
      {open && (
        <div className="fav-menu" role="menu">
          {rows.map((row) => (
            <button
              key={row.key}
              className="fav-row"
              role="menuitem"
              onClick={() => {
                onOpen(row.key);
                setOpen(false);
              }}
            >
              <span className="fav-row-top">
                <span className="id-chip">{row.key}</span>
                <span className="fav-row-name">{row.name}</span>
                <span className="fav-row-pct">{row.pct}%</span>
              </span>
              <span className="fav-row-bottom">
                <span className="bar">
                  <span className="bar-fill" style={{ width: `${row.pct}%` }} />
                </span>
                <span className="fav-row-since">updated {row.updated ? row.updated.slice(5, 10) : "—"}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
