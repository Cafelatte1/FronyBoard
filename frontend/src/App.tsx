import { useEffect, useState } from "react";
import { clearSession, getToken, getUsername, login } from "./api";
import { currentPeriodName, fmtAgo, useBoardData } from "./shared";
import TaskPanel from "./TaskPanel";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import Settings from "./pages/Settings";
import type { Task } from "./types";

type Page = "dashboard" | "projects" | "settings";

const PAGE_TITLES: Record<Page, string> = {
  dashboard: "대시보드",
  projects: "프로젝트",
  settings: "설정",
};

export default function App() {
  const [authed, setAuthed] = useState(getToken() !== null);
  if (!authed) return <LoginGate onDone={() => setAuthed(true)} />;
  return (
    <Board
      onAuthFail={() => {
        clearSession();
        setAuthed(false);
      }}
    />
  );
}

function Board({ onAuthFail }: { onAuthFail: () => void }) {
  const [page, setPage] = useState<Page>("dashboard");
  const [openProject, setOpenProject] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [openTask, setOpenTask] = useState<{ key: string; task: Task } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const { data, error, fetchedAt, reload } = useBoardData(onAuthFail);
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 60000);
    return () => clearInterval(t);
  }, []);

  // Esc closes the topmost layer: task panel first, then the drawer.
  useEffect(() => {
    if (!menuOpen && !openTask) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (openTask) setOpenTask(null);
      else setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen, openTask]);

  const go = (p: Page) => {
    setPage(p);
    setOpenProject(null);
    setMenuOpen(false);
  };
  const openDetail = (key: string) => {
    setPage("projects");
    setOpenProject(key);
  };

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = search.trim().toUpperCase();
    if (!q || !data) return;
    for (const [key, list] of Object.entries(data.tasks)) {
      const hit = list.find((t) => t.id.toUpperCase() === q);
      if (hit) {
        openDetail(key);
        setOpenTask({ key, task: hit });
        setSearch("");
        return;
      }
      if (list.some((t) => t.id.toUpperCase().startsWith(q))) {
        openDetail(key);
        setSearch("");
        return;
      }
    }
  };

  const detailName =
    openProject !== null ? (data?.statuses[openProject]?.name ?? openProject) : null;
  // Only the detail screen gets a path line: "AIR / 2026Q3".
  const crumb =
    page === "projects" && openProject !== null && data
      ? `${openProject} / ${currentPeriodName(data.statuses[openProject]) ?? "—"}`
      : null;

  // Manual sync: the fetch is quick, so keep the spinner up for a beat so the click reads.
  const sync = async () => {
    if (syncing) return;
    setSyncing(true);
    const started = Date.now();
    try {
      await reload();
    } finally {
      const wait = 700 - (Date.now() - started);
      if (wait > 0) await new Promise((r) => setTimeout(r, wait));
      setSyncing(false);
    }
  };
  const title = detailName !== null ? `${detailName} 상세` : PAGE_TITLES[page];
  const version = data?.server.version ?? "…";

  return (
    <div className="stage" data-density="compact">
      <div className="ambient" />
      <div className={`shell ${menuOpen ? "open" : ""}`}>
        <main className="main">
          <header className="head">
            <button className="menu-btn" onClick={() => setMenuOpen(true)} title="메뉴 열기" aria-label="메뉴 열기">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
              </svg>
            </button>
            <div className="head-titles">
              {crumb && <div className="crumb">{crumb}</div>}
              <h1>{title}</h1>
            </div>
            <form className="search" onSubmit={onSearch}>
              <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="9" cy="9" r="5.5" />
                <path d="M13.2 13.2 17 17" strokeLinecap="round" />
              </svg>
              <input placeholder="태스크 ID 검색" value={search} onChange={(e) => setSearch(e.target.value)} />
            </form>
            <button className={`synced ${syncing ? "on" : ""}`} onClick={sync} title={syncing ? "동기화 중" : "지금 동기화"}>
              <svg className={syncing ? "spin" : ""} width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2.6 10a7.4 7.4 0 0 1 12.6-5.2l2.2 2.1M17.4 10a7.4 7.4 0 0 1-12.6 5.2l-2.2-2.1" strokeLinecap="round" />
                <path d="M17.4 2.6v4.5h-4.5M2.6 17.4v-4.5h4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {!syncing && fetchedAt ? `${fmtAgo(fetchedAt)} 동기화` : "동기화 중…"}
            </button>
          </header>

          <div className="content">
            {error && <p className="error">{error}</p>}
            {!data && !error && <p className="muted">불러오는 중…</p>}
            {data && page === "dashboard" && (
              <Dashboard data={data} onOpenProject={openDetail} onOpenTask={(key, task) => setOpenTask({ key, task })} />
            )}
            {data && page === "projects" && (
              <Projects
                data={data}
                openKey={openProject}
                setOpenKey={setOpenProject}
                onOpenTask={(key, task) => setOpenTask({ key, task })}
              />
            )}
            {data && page === "settings" && <Settings data={data} onAuthFail={onAuthFail} />}
          </div>
        </main>

        <TaskPanel
          task={openTask?.task ?? null}
          projectKey={openTask?.key ?? null}
          months={(openTask && data?.statuses[openTask.key]?.periods[openTask.task.period]?.months) ?? []}
          tz={data?.server.timezone}
          onClose={() => setOpenTask(null)}
        />

        <div className="backdrop" onClick={() => setMenuOpen(false)} />
        <aside className="sidebar" aria-hidden={!menuOpen}>
          <div className="drawer-head">
            <span className="logo-mark">F</span>
            <div className="logo-text">
              <div className="logo-name">FronyBoard</div>
              <div className="logo-sub">v{version}</div>
            </div>
            <button className="side-close" onClick={() => setMenuOpen(false)} title="메뉴 닫기" aria-label="메뉴 닫기">
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M5 5l10 10M15 5 5 15" />
              </svg>
            </button>
          </div>

          <div className="nav-label">메뉴</div>
          <NavItem label="대시보드" on={page === "dashboard"} onClick={() => go("dashboard")} icon="grid" />
          <NavItem
            label="프로젝트"
            on={page === "projects"}
            onClick={() => go("projects")}
            icon="folder"
            count={data?.projects.length}
          />
          <NavItem label="설정" on={page === "settings"} onClick={() => go("settings")} icon="gear" />

          <div className="side-foot">
            <span className="foot-state">
              <span className={`dot ${error ? "off" : ""}`} />
              {error ? "서버 연결 안 됨" : "서버 연결됨"} · {getUsername() ?? "?"}
            </span>
            <span className="foot-ver">
              v{version} · {window.location.host}
            </span>
          </div>
        </aside>
      </div>
    </div>
  );
}

function NavItem({
  label,
  on,
  onClick,
  icon,
  count,
}: {
  label: string;
  on: boolean;
  onClick: () => void;
  icon: "grid" | "folder" | "gear";
  count?: number;
}) {
  return (
    <button className={`nav-item ${on ? "on" : ""}`} onClick={onClick}>
      <span className="nav-bar" />
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
        {icon === "grid" && (
          <>
            <rect x="2.5" y="2.5" width="6" height="6" rx="1.6" />
            <rect x="11.5" y="2.5" width="6" height="6" rx="1.6" />
            <rect x="2.5" y="11.5" width="6" height="6" rx="1.6" />
            <rect x="11.5" y="11.5" width="6" height="6" rx="1.6" />
          </>
        )}
        {icon === "folder" && (
          <path d="M2.4 5.4A1.5 1.5 0 0 1 3.9 3.9h3.1l1.7 2.1h7.4a1.5 1.5 0 0 1 1.5 1.5v7.1a1.5 1.5 0 0 1-1.5 1.5H3.9a1.5 1.5 0 0 1-1.5-1.5V5.4Z" />
        )}
        {icon === "gear" && (
          <>
            <circle cx="10" cy="10" r="2.6" />
            <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" strokeLinecap="round" />
          </>
        )}
      </svg>
      <span className="nav-text">{label}</span>
      {count !== undefined && count > 0 && <span className="nav-count">{count}</span>}
    </button>
  );
}

function LoginGate({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="login-wrap" data-density="compact">
      <div className="ambient" />
      <div className="login-card">
        <span className="logo-mark">F</span>
        <div className="login-title">
          <span className="frony">Frony</span>Board
        </div>
        <p className="login-sub">대시보드 로그인으로 전체 프로젝트를 조회합니다</p>
        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!username.trim() || busy) return;
            setBusy(true);
            setError(null);
            login(username.trim(), password)
              .then(onDone)
              .catch((err) => setError(String(err.message ?? err)))
              .finally(() => setBusy(false));
          }}
        >
          <input placeholder="아이디" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          <input
            type="password"
            placeholder="비밀번호"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="cta-btn" type="submit" disabled={busy}>
            {busy ? "…" : "로그인"}
          </button>
        </form>
        {error && <p className="login-error">{error}</p>}
      </div>
    </div>
  );
}
