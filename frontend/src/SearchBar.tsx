import { useEffect, useMemo, useRef, useState } from "react";
import { searchTasks, type Hit, type SearchGroup, type SearchRow } from "./search";
import { TASK_ST, useIsPhone, weekLabel } from "./shared";
import type { BoardData, Task } from "./types";

/** Header search (AIR-032): a 264px input with a result dropdown on desktop, a
    full-screen overlay behind a magnifier button on the phone. Search itself is
    client-side over BoardData — see search.ts. */
export default function SearchBar({
  data,
  onPick,
}: {
  data: BoardData;
  onPick: (key: string, task: Task) => void;
}) {
  const isPhone = useIsPhone();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const groups = useMemo(() => searchTasks(data, q), [data, q]);

  // ⌘K / Ctrl+K focuses (and opens) the search from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setOpen(true);
        requestAnimationFrame(() => inputRef.current?.focus());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const setQuery = (v: string) => {
    setQ(v);
    setExpanded([]); // a new query folds every "모두 보기" back to 4 rows
  };
  const close = () => {
    setOpen(false);
    setExpanded([]);
  };
  const pick = (key: string, task: Task) => {
    remember(q);
    close();
    setQ("");
    onPick(key, task);
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") close();
    else if (e.key === "Enter") {
      const g = groups[0];
      if (g && g.rows[0]) pick(g.key, g.rows[0].task);
    }
  };

  const panel = (
    <Panel
      q={q}
      groups={groups}
      expanded={expanded}
      onExpand={(key) => setExpanded([...expanded, key])}
      onRecent={(r) => {
        setQuery(r);
        inputRef.current?.focus();
      }}
      onPick={pick}
      phone={isPhone}
    />
  );

  if (isPhone)
    return (
      <>
        <button className="gs-icon-btn" onClick={() => setOpen(true)} title="태스크 검색" aria-label="태스크 검색">
          <MagnifierIcon />
        </button>
        {open && (
          <div className="gs-overlay">
            <div className="gs-overlay-bar">
              <button className="gs-back" onClick={close} title="검색 닫기" aria-label="검색 닫기">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11.5 4.5 6 10l5.5 5.5" />
                </svg>
              </button>
              <div className="gs-field">
                <input
                  ref={inputRef}
                  autoFocus
                  value={q}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder="태스크 · ID · 내용 검색"
                  aria-label="태스크 검색"
                />
                {q && <ClearButton onClick={() => setQuery("")} />}
              </div>
            </div>
            <div className="gs-body">{panel}</div>
          </div>
        )}
      </>
    );

  return (
    <>
      {open && <div className="menu-overlay" onClick={close} />}
      <div className={`gsearch ${open ? "open" : ""}`}>
        <MagnifierIcon className="gs-icon" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="태스크 · ID · 내용 검색"
          aria-label="태스크 검색"
        />
        {q ? (
          <ClearButton
            onClick={() => {
              setQuery("");
              inputRef.current?.focus();
            }}
          />
        ) : (
          <span className="gs-kbd">{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl+K"}</span>
        )}
        {open && <div className="gs-pop">{panel}</div>}
      </div>
    </>
  );
}

function Panel({
  q,
  groups,
  expanded,
  onExpand,
  onRecent,
  onPick,
  phone,
}: {
  q: string;
  groups: SearchGroup[];
  expanded: string[];
  onExpand: (key: string) => void;
  onRecent: (r: string) => void;
  onPick: (key: string, task: Task) => void;
  phone: boolean;
}) {
  if (!q.trim()) {
    const recent = readRecent();
    return (
      <div className="gs-blank">
        {recent.length > 0 && (
          <>
            <span className="gs-cap">최근 검색</span>
            <div className="gs-chips">
              {recent.map((r) => (
                <button key={r} className="gs-chip" onClick={() => onRecent(r)}>
                  {r}
                </button>
              ))}
            </div>
          </>
        )}
        <span className="gs-guide">
          프로젝트 키 · 태스크 ID · 제목 · 내용을 함께 찾습니다. 결과는 프로젝트별로 묶여 나옵니다.
        </span>
      </div>
    );
  }

  if (groups.length === 0)
    return (
      <div className="gs-none">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <path d="m15.4 15.4 4.1 4.1M8 8l5 5M13 8l-5 5" />
        </svg>
        <span className="gs-none-title">‘{q.trim()}’와 일치하는 태스크가 없습니다</span>
        <span className="gs-none-sub">태스크 ID(AIR-050)나 내용에 있는 단어로도 찾을 수 있습니다.</span>
      </div>
    );

  const hits = groups.reduce((n, g) => n + g.total, 0);
  return (
    <div className="gs-results">
      <div className="gs-countbar">
        <b>태스크 {hits}건</b>
        <i />
        <span>프로젝트 {groups.length}개</span>
        {!phone && <span className="gs-countbar-right">project · quarter</span>}
      </div>
      <div className="gs-list">
        {groups.map((g) => {
          const rows = expanded.includes(g.key) ? g.rows : g.rows.slice(0, 4);
          return (
            <div key={g.key}>
              <div className="gs-ghead">
                <span className="id-chip">{g.key}</span>
                <span className="gs-gname">{g.name}</span>
                <span className="gs-gperiod">{g.period}</span>
                <span className="gs-gcount">{g.total}건</span>
              </div>
              {rows.map((r) => (
                <Row key={r.task.id} r={r} phone={phone} onOpen={() => onPick(g.key, r.task)} />
              ))}
              {g.total > rows.length && (
                <button className="gs-more" onClick={() => onExpand(g.key)}>
                  {g.name} 결과 {g.total}건 모두 보기
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Row({ r, phone, onOpen }: { r: SearchRow; phone: boolean; onOpen: () => void }) {
  const st = r.task.status;
  const meta = `${r.task.month}${r.task.week ? ` · ${weekLabel(r.task.week)}` : ""}`;
  if (phone)
    return (
      <button className="gs-row ph" onClick={onOpen}>
        <span className="gs-row-top">
          <span className="gs-dot" style={{ background: stDot(st) }} />
          <span className="gs-id">
            <HitText h={r.id} />
          </span>
          <span className="gs-grow" />
          <span className="gs-meta">{meta}</span>
          <span className="gs-st" style={{ color: stColor(st) }}>
            {TASK_ST[st]?.label ?? st}
          </span>
        </span>
        <span className="gs-title-ph">
          <HitText h={r.title} />
        </span>
        {r.snippet && (
          <span className="gs-via ph">
            <HitText h={r.snippet} />
          </span>
        )}
      </button>
    );
  return (
    <button className="gs-row" onClick={onOpen}>
      <span className="gs-dot" style={{ background: stDot(st) }} />
      <span className="gs-id">
        <HitText h={r.id} />
      </span>
      <span className="gs-title">
        <HitText h={r.title} />
      </span>
      {r.snippet && (
        <span className="gs-via">
          <HitText h={r.snippet} />
        </span>
      )}
      <span className="gs-meta">{meta}</span>
      <span className="gs-st" style={{ color: stColor(st) }}>
        {TASK_ST[st]?.label ?? st}
      </span>
    </button>
  );
}

function HitText({ h }: { h: Hit }) {
  return (
    <>
      {h.pre}
      {h.hit && <mark className="gs-mark">{h.hit}</mark>}
      {h.post}
    </>
  );
}

/** Status swatches double as dot colors, except cancelled whose swatch is a surface tone. */
function stDot(status: string): string {
  return TASK_ST[status]?.swatch ?? "var(--text-disabled)";
}
function stColor(status: string): string {
  return status === "cancelled" ? "var(--text-disabled)" : (TASK_ST[status]?.swatch ?? "var(--text-muted)");
}

function MagnifierIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <circle cx="8.8" cy="8.8" r="5.4" />
      <path d="m12.9 12.9 3.6 3.6" />
    </svg>
  );
}

function ClearButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="gs-clear" onClick={onClick} title="검색어 지우기" aria-label="검색어 지우기">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M5 5l10 10M15 5 5 15" />
      </svg>
    </button>
  );
}

const RECENT_KEY = "fb.recentSearches";

function readRecent(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string").slice(0, 4) : [];
  } catch {
    return [];
  }
}

function remember(q: string) {
  const v = q.trim();
  if (!v) return;
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([v, ...readRecent().filter((r) => r !== v)].slice(0, 4)));
  } catch {
    // storage blocked — recents just don't stick
  }
}
