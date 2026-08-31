import { useEffect, useId, useRef, useState } from "react";
import { clearSession, getToken, login } from "./api";
import SearchBar from "./SearchBar";
import { currentPeriodName, fmtAgo, useBoardData, useIsPhone } from "./shared";
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

/** The project detail is the one screen that gets its own history entry, so back
    returns to the project list instead of leaving the dashboard. Everything else
    stays state-only: back from a top-level menu leaves the site, as before. */
const DETAIL_HASH = /^#\/p\/([A-Z]{2,5})$/;

function detailKeyFromHash(): string | null {
  return DETAIL_HASH.exec(window.location.hash)?.[1] ?? null;
}


/** The brand glyph, shared by the drawer head and the phone header. */
function FronyMark() {
  // The mark can appear twice on one screen (header + drawer); a shared gradient id
  // would leave one path pointing at a def that unmounts with the other instance.
  const id = useId();
  return (
    <svg className="logo-mark" viewBox="18 10 22 22" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="19.09" y1="20.95" x2="39" y2="20.95" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--brand-1)" />
          <stop offset="1" stopColor="var(--brand-2)" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${id})`}
        d="M26.107 14.448C26.705 12.698 29.123 12.645 29.832 14.289L29.892 14.449L30.699 16.809C30.8839 17.3502 31.1828 17.8455 31.5754 18.2614C31.968 18.6773 32.4453 19.0042 32.975 19.22L33.192 19.301L35.552 20.107C37.302 20.705 37.355 23.123 35.712 23.832L35.552 23.892L33.192 24.699C32.6506 24.8838 32.1551 25.1826 31.739 25.5753C31.3229 25.9679 30.9959 26.4452 30.78 26.975L30.699 27.191L29.893 29.552C29.295 31.302 26.877 31.355 26.169 29.712L26.107 29.552L25.301 27.192C25.1162 26.6506 24.8174 26.1551 24.4247 25.739C24.0321 25.3229 23.5548 24.9959 23.025 24.78L22.809 24.699L20.449 23.893C18.698 23.295 18.645 20.877 20.289 20.169L20.449 20.107L22.809 19.301C23.3502 19.1161 23.8455 18.8172 24.2614 18.4246C24.6773 18.0319 25.0042 17.5547 25.22 17.025L25.301 16.809L26.107 14.448Z"
      />
      <path
        fill={`url(#${id})`}
        d="M36 11C36.1871 11 36.3704 11.0525 36.5291 11.1515C36.6879 11.2505 36.8157 11.392 36.898 11.56L36.946 11.677L37.296 12.703L38.323 13.053C38.5105 13.1167 38.6748 13.2346 38.7952 13.3918C38.9156 13.549 38.9866 13.7384 38.9993 13.936C39.0119 14.1336 38.9656 14.3305 38.8662 14.5018C38.7668 14.673 38.6188 14.8109 38.441 14.898L38.323 14.946L37.297 15.296L36.947 16.323C36.8832 16.5104 36.7652 16.6747 36.6079 16.795C36.4506 16.9153 36.2612 16.9862 36.0636 16.9987C35.866 17.0113 35.6692 16.9648 35.498 16.8654C35.3268 16.7659 35.189 16.6179 35.102 16.44L35.054 16.323L34.704 15.297L33.677 14.947C33.4895 14.8833 33.3251 14.7654 33.2048 14.6082C33.0844 14.451 33.0133 14.2616 33.0007 14.064C32.9881 13.8664 33.0344 13.6695 33.1338 13.4982C33.2332 13.327 33.3811 13.1891 33.559 13.102L33.677 13.054L34.703 12.704L35.053 11.677C35.1204 11.4794 35.248 11.3079 35.4178 11.1865C35.5876 11.0651 35.7912 10.9999 36 11Z"
      />
    </svg>
  );
}
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
  const [page, setPage] = useState<Page>(detailKeyFromHash() ? "projects" : "dashboard");
  const [openProject, setOpenProject] = useState<string | null>(detailKeyFromHash);
  const pushedDetail = useRef(false);
  const closingInApp = useRef(false);
  const isPhone = useIsPhone();
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

  // Back/forward moves in and out of the project detail; the hash is the source of truth.
  useEffect(() => {
    const onPop = () => {
      const key = detailKeyFromHash();
      pushedDetail.current = key !== null;
      setOpenProject(key);
      // Back out of a detail always lands on the project list.
      if (closingInApp.current) closingInApp.current = false;   // the caller picked the screen
      else setPage("projects");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const openDetail = (key: string) => {
    setPage("projects");
    setOpenProject(key);
    setDetailFocus(null);
    if (detailKeyFromHash() !== key) {
      window.history.pushState(null, "", `#/p/${key}`);
      pushedDetail.current = true;
    }
  };
  // A search pick lands on the task's own quarter — table paged to the task — and
  // opens its panel right away.
  const [detailFocus, setDetailFocus] = useState<{ period: string; taskId: string; nonce: number } | null>(null);
  const focusNonce = useRef(0);
  const openFromSearch = (key: string, task: Task) => {
    openDetail(key);
    focusNonce.current += 1;
    setDetailFocus({ period: task.period, taskId: task.id, nonce: focusNonce.current });
    setOpenTask({ key, task });
  };
  const closeDetail = () => {
    setOpenProject(null);
    if (!detailKeyFromHash()) return;
    if (pushedDetail.current) {
      pushedDetail.current = false;
      closingInApp.current = true;
      window.history.back();          // drop the entry we pushed
    } else {
      // Opened straight from a bookmark: there is nothing of ours to go back to.
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  };
  // A hand-edited hash can name a project that does not exist — drop it once data is in.
  useEffect(() => {
    if (data && openProject !== null && !data.statuses[openProject]) closeDetail();
  }, [data, openProject]);

  const go = (p: Page) => {
    setPage(p);
    closeDetail();
    setMenuOpen(false);
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
  // The phone detail screen owns its whole chrome: no app header, no tab bar.
  const phoneDetail = isPhone && openProject !== null;
  const version = data?.server.version ?? "…";

  return (
    <div className="stage" data-density={isPhone ? "comfortable" : "compact"}>
      <div className="ambient" />
      <div className={`shell ${menuOpen ? "open" : ""}`}>
        <main className="main">
          {/* The phone's project detail draws its own two-row header (project + period
              stepper), so the app header steps aside entirely on that one screen. */}
          {!phoneDetail && (
          <header className="head">
            {isPhone ? (
              <div className="head-brand">
                <FronyMark />
                <span className="logo-text">
                  <span className="logo-frony">FRONY</span>
                  <span className="logo-name">Board</span>
                </span>
              </div>
            ) : (
              <button className="menu-btn" onClick={() => setMenuOpen(true)} title="메뉴 열기" aria-label="메뉴 열기">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
                </svg>
              </button>
            )}
            {isPhone ? (
              <span className="head-spacer" />
            ) : (
              <div className="head-titles">
                <div className="head-meta">
                  <span className="head-lockup">
                    <FronyMark />
                    <span className="logo-inline">
                      <span className="logo-frony">FRONY</span>
                      <span className="logo-sep" />
                      <span className="logo-name">Board</span>
                    </span>
                  </span>
                  {crumb && <div className="crumb">{crumb}</div>}
                </div>
                <h1>{title}</h1>
              </div>
            )}
            {data && <SearchBar data={data} onPick={openFromSearch} />}
            <button className={`synced ${syncing ? "on" : ""}`} onClick={sync} title={syncing ? "동기화 중" : "지금 동기화"}>
              <svg className={syncing ? "spin" : ""} width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2.6 10a7.4 7.4 0 0 1 12.6-5.2l2.2 2.1M17.4 10a7.4 7.4 0 0 1-12.6 5.2l-2.2-2.1" strokeLinecap="round" />
                <path d="M17.4 2.6v4.5h-4.5M2.6 17.4v-4.5h4.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {!syncing && fetchedAt ? `${fmtAgo(fetchedAt)} 동기화` : "동기화 중…"}
            </button>
          </header>
          )}

          <div className={`content ${phoneDetail ? "detail" : ""}`}>
            {isPhone && !phoneDetail && <h1 className="page-title">{title}</h1>}
            {error && <p className="error">{error}</p>}
            {!data && !error && <p className="muted">불러오는 중…</p>}
            {data && page === "dashboard" && (
              <Dashboard data={data} onOpenProject={openDetail} onOpenTask={(key, task) => setOpenTask({ key, task })} />
            )}
            {data && page === "projects" && (
              <Projects
                data={data}
                openKey={openProject}
                setOpenKey={(key) => (key === null ? closeDetail() : openDetail(key))}
                onOpenTask={(key, task) => setOpenTask({ key, task })}
                focus={detailFocus}
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

        {isPhone ? (
          !phoneDetail && (
          <nav className="tabbar">
            <TabItem label="대시보드" on={page === "dashboard"} onClick={() => go("dashboard")} icon="grid" />
            <TabItem label="프로젝트" on={page === "projects"} onClick={() => go("projects")} icon="folder" />
            <TabItem label="설정" on={page === "settings"} onClick={() => go("settings")} icon="gear" />
          </nav>
          )
        ) : (
          <>
          <div className="backdrop" onClick={() => setMenuOpen(false)} />
          <aside className="sidebar" aria-hidden={!menuOpen}>
            <button className="side-close" onClick={() => setMenuOpen(false)} title="메뉴 닫기" aria-label="메뉴 닫기">
              <span className="side-close-grip" />
            </button>
            <div className="drawer-head">
              <FronyMark />
              <div className="logo-text">
                <span className="logo-frony">FRONY</span>
                <span className="logo-name">Board</span>
              </div>
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
              <span
                className={`dot ${error ? "off" : ""}`}
                title={error ? "서버 연결 안 됨" : "서버 연결됨"}
              />
              <span className="foot-ver">
                v{version} · {window.location.host}
              </span>
            </div>
          </aside>
          </>
        )}
      </div>
    </div>
  );
}

type NavIconName = "grid" | "folder" | "gear";

function NavIcon({ icon }: { icon: NavIconName }) {
  return (
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
  );
}

/** Phone navigation: the drawer's three destinations as a fixed bottom bar. */
function TabItem({ label, on, onClick, icon }: { label: string; on: boolean; onClick: () => void; icon: NavIconName }) {
  return (
    <button className={`tab-item ${on ? "on" : ""}`} onClick={onClick}>
      <NavIcon icon={icon} />
      <span>{label}</span>
    </button>
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
  icon: NavIconName;
  count?: number;
}) {
  return (
    <button className={`nav-item ${on ? "on" : ""}`} onClick={onClick}>
      <span className="nav-bar" />
      <NavIcon icon={icon} />
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
        <span className="login-lockup">
          <FronyMark />
          <span className="logo-inline">
            <span className="logo-frony">FRONY</span>
            <span className="logo-sep" />
            <span className="logo-name">Board</span>
          </span>
        </span>
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
            {busy && <span className="cta-spin" />}
            {busy ? "로그인 중…" : "로그인"}
          </button>
        </form>
        {error && (
          <p className="login-error">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
              <circle cx="10" cy="10" r="7.4" />
              <path d="M10 6.3v4.4M10 13.4h.01" />
            </svg>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
