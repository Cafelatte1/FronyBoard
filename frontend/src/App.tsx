import { useEffect, useState } from "react";
import { clearSession, getToken, getUsername, login } from "./api";
import { fmtAgo, useBoardData } from "./shared";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import Settings from "./pages/Settings";

type Page = "dashboard" | "projects" | "settings";

const PAGE_TITLES: Record<Page, string> = {
  dashboard: "전체 진행 상황",
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
  const [rail, setRail] = useState(false);
  const [openProject, setOpenProject] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const { data, error, fetchedAt, reload } = useBoardData(onAuthFail);
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 60000);
    return () => clearInterval(t);
  }, []);

  const go = (p: Page) => {
    setPage(p);
    setOpenProject(null);
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
      if (list.some((t) => t.id.toUpperCase() === q || t.id.toUpperCase().startsWith(q))) {
        openDetail(key);
        setSearch("");
        return;
      }
    }
  };

  const detailName =
    openProject !== null ? (data?.statuses[openProject]?.name ?? openProject) : null;
  const crumb =
    page === "projects" && openProject !== null
      ? `FronyBoard / projects / ${openProject}`
      : `FronyBoard / ${page}`;
  const title = detailName !== null ? `${detailName} 상세` : PAGE_TITLES[page];

  return (
    <div className={`shell ${rail ? "rail" : ""}`} data-density="compact">
      <div className="ambient" />
      <aside className="sidebar">
        <button
          className="side-toggle"
          onClick={() => setRail((v) => !v)}
          title={rail ? "사이드바 펼치기" : "사이드바 접기"}
          aria-label={rail ? "사이드바 펼치기" : "사이드바 접기"}
        >
          <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
            <path d={rail ? "M7.5 4.5 13 10l-5.5 5.5" : "M12.5 4.5 7 10l5.5 5.5"} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <div className="logo">
          <span className="logo-mark">F</span>
          <div className="logo-text">
            <div className="logo-name">FronyBoard</div>
            <div className="logo-sub">v{data?.server.version ?? "…"}</div>
          </div>
        </div>

        <nav className="nav">
          <div className="nav-label">메뉴</div>
          <NavItem label="대시보드" on={page === "dashboard"} onClick={() => go("dashboard")} icon="grid" />
          <NavItem label="프로젝트" on={page === "projects"} onClick={() => go("projects")} icon="folder" />
          <NavItem label="설정" on={page === "settings"} onClick={() => go("settings")} icon="gear" />
        </nav>

        <div className="side-foot">
          <div className="server-card">
            <div className="server-state">
              <span className={`dot ${error ? "off" : ""}`} />
              {error ? "서버 연결 안 됨" : "서버 연결됨"}
            </div>
            <div className="server-host">{window.location.host}</div>
            <div className="server-sub">aira v{data?.server.version ?? "…"} · MCP HTTP</div>
          </div>
          <div className="user-row">
            <span className="avatar">{(getUsername() ?? "?").charAt(0).toUpperCase()}</span>
            <div className="user-text">
              <div className="user-name">{getUsername() ?? "?"}</div>
              <div className="user-role">viewer · 조회 전용</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="head">
          <div className="head-titles">
            <div className="crumb">{crumb}</div>
            <h1>{title}</h1>
          </div>
          <form className="search" onSubmit={onSearch}>
            <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
              <circle cx="9" cy="9" r="5.5" />
              <path d="M13.2 13.2 17 17" />
            </svg>
            <input
              placeholder="태스크 ID 검색 (예: AIR-011)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </form>
          <button className="synced" onClick={reload} title="다시 불러오기">
            <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M16.5 10a6.5 6.5 0 1 1-2-4.7M17 3v3.5h-3.5" />
            </svg>
            {fetchedAt ? `${fmtAgo(fetchedAt)} 동기화` : "동기화 중…"}
          </button>
        </header>

        <div className="content">
          {error && <p className="error">{error}</p>}
          {!data && !error && <p className="muted">불러오는 중…</p>}
          {data && page === "dashboard" && <Dashboard data={data} onOpenProject={openDetail} />}
          {data && page === "projects" && (
            <Projects data={data} openKey={openProject} setOpenKey={setOpenProject} />
          )}
          {data && page === "settings" && <Settings data={data} onAuthFail={onAuthFail} />}
        </div>
      </main>
    </div>
  );
}

function NavItem({
  label,
  on,
  onClick,
  icon,
}: {
  label: string;
  on: boolean;
  onClick: () => void;
  icon: "grid" | "folder" | "gear";
}) {
  return (
    <button className={`nav-item ${on ? "on" : ""}`} onClick={onClick} title={label}>
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
          <path d="M2.5 5.5a1.5 1.5 0 0 1 1.5-1.5h3l1.6 2h6.9a1.5 1.5 0 0 1 1.5 1.5v7a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5v-9Z" />
        )}
        {icon === "gear" && (
          <>
            <circle cx="10" cy="10" r="2.6" />
            <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" />
          </>
        )}
      </svg>
      <span className="nav-text">{label}</span>
    </button>
  );
}

function LoginGate({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="login-wrap">
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
          <input
            placeholder="아이디"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
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
