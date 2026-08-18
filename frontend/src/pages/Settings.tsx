import { getUsername, logout } from "../api";
import { useApi } from "../shared";
import type { ProjectRef } from "../types";

export default function Settings({ onAuthFail }: { onAuthFail: () => void }) {
  const { data } = useApi<{ projects: ProjectRef[]; data_root: string }>("/api/projects", onAuthFail);

  return (
    <div className="settings">
      <section className="card">
        <h3>Account</h3>
        <p>
          Signed in as <span className="mono">{getUsername() ?? "?"}</span>. Change the login on the
          server with <span className="mono">aira admin &lt;username&gt;</span>.
        </p>
        <button onClick={() => logout().then(onAuthFail)}>Sign out</button>
      </section>

      <section className="card">
        <h3>Server</h3>
        <p>
          Data root: <span className="mono">{data?.data_root ?? "…"}</span>
        </p>
        <p>
          Projects: <span className="mono">{data ? data.projects.length : "…"}</span>
        </p>
        <p className="muted">
          API keys (<span className="mono">aira keygen</span>) authenticate agents over MCP and are
          separate from this login. Account signup and project registration from this page arrive
          with Phase 4.
        </p>
      </section>
    </div>
  );
}
