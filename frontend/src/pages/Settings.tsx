import { getKey } from "../api";
import { useApi } from "../shared";
import type { ProjectRef } from "../types";

export default function Settings({ onAuthFail }: { onAuthFail: () => void }) {
  const { data } = useApi<{ projects: ProjectRef[]; data_root: string }>("/api/projects", onAuthFail);
  const key = getKey();
  const masked = key ? `${key.slice(0, 10)}…${key.slice(-4)}` : "—";

  return (
    <div className="settings">
      <section className="card">
        <h3>Access</h3>
        <p>
          API key <span className="mono">{masked}</span> is stored in this browser and sent with
          every request. All keys see every project — a key is a device pass, not a project scope.
        </p>
        <button onClick={onAuthFail}>Replace key / sign out</button>
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
          Keys are issued on the server with <span className="mono">aira keygen</span>; revoke one by
          removing its entry from <span className="mono">auth.yaml</span>. Key issuing and project
          registration from this page arrive with the account system (Phase 4).
        </p>
      </section>
    </div>
  );
}
