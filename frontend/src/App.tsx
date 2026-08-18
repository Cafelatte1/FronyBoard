import { useState } from "react";
import { clearKey, getKey, setKey } from "./api";
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
  const [authed, setAuthed] = useState(getKey() !== null);
  const [page, setPage] = useState<Page>("dashboard");
  const [openProject, setOpenProject] = useState<string | null>(null);

  const onAuthFail = () => {
    clearKey();
    setAuthed(false);
  };

  if (!authed) return <KeyGate onDone={() => setAuthed(true)} />;
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

function KeyGate({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="keygate">
      <h1 className="brand">
        Frony<span>Board</span>
      </h1>
      <p>Paste an AIRA API key to view your boards.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!value.trim()) return;
          setKey(value.trim());
          onDone();
        }}
      >
        <input
          type="password"
          placeholder="aira_…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
        />
        <button type="submit">Open</button>
      </form>
    </div>
  );
}
