import { useState } from "react";
import { clearSession, getToken, login } from "./api";
import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import Settings from "./pages/Settings";

type Page = "dashboard" | "projects" | "settings";

const TABS: [Page, string][] = [
  ["dashboard", "Dashboard"],
  ["projects", "Projects"],
  ["settings", "Settings"],
];

export default function App() {
  const [authed, setAuthed] = useState(getToken() !== null);
  const [page, setPage] = useState<Page>("dashboard");
  const [openProject, setOpenProject] = useState<string | null>(null);

  const onAuthFail = () => {
    clearSession();
    setAuthed(false);
  };

  if (!authed) return <LoginGate onDone={() => setAuthed(true)} />;
  return (
    <div className="shell">
      <header className="topbar">
        <h1 className="brand" onClick={() => setPage("dashboard")}>
          Frony<span>Board</span>
        </h1>
        <nav className="tabs">
          {TABS.map(([p, label]) => (
            <button
              key={p}
              className={`tab ${page === p ? "tab-active" : ""}`}
              onClick={() => {
                setPage(p);
                if (p === "projects") setOpenProject(null);
              }}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      {page === "dashboard" && (
        <Dashboard
          onOpenProject={(k) => {
            setOpenProject(k);
            setPage("projects");
          }}
          onAuthFail={onAuthFail}
        />
      )}
      {page === "projects" && (
        <Projects openKey={openProject} setOpenKey={setOpenProject} onAuthFail={onAuthFail} />
      )}
      {page === "settings" && <Settings onAuthFail={onAuthFail} />}
    </div>
  );
}

function LoginGate({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="keygate">
      <h1 className="brand">
        Frony<span>Board</span>
      </h1>
      <p>Sign in to view your boards.</p>
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
          placeholder="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        <input
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit" disabled={busy}>
          {busy ? "…" : "Sign in"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
