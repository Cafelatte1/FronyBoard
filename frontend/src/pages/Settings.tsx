import { useEffect, useState } from "react";
import { Unauthorized, api, apiSend, getUsername, logout } from "../api";
import { fmtServerTime, fmtUptime } from "../shared";
import type { BoardData, KeyInfo, ServerTimezone } from "../types";

export default function Settings({ data, onAuthFail }: { data: BoardData; onAuthFail: () => void }) {
  const username = getUsername() ?? "?";
  const server = data.server;
  const openPeriods = [...new Set(server.open_periods.map((p) => p.period))];
  const local = server.auth === "local";

  return (
    <div className="settings-col">
      <section className="card">
        <div className="card-title">Account</div>
        <div className="account-row">
          <span className="avatar">{username.charAt(0).toUpperCase()}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="account-name">{username}</div>
            <div className="account-sub">
              {local
                ? "Local mode · loopback only, no login"
                : "Dashboard login · the session lives in server memory, so a restart signs you out"}
            </div>
          </div>
          {!local && (
            <button className="ghost-btn" onClick={() => logout().then(onAuthFail)}>
              Sign out
            </button>
          )}
        </div>
        <div className="note">
          Change the login on the server with <span className="mono">fauth admin &lt;username&gt;</span>.
          Every write goes through the MCP tools — this screen is read-only.
        </div>
      </section>

      {!local && <KeysSection onAuthFail={onAuthFail} tz={server.timezone} />}

      <section className="card">
        <div className="card-title">Server</div>
        <div className="server-grid">
          {(
            [
              ["VERSION", `FronyBoard v${server.version}`],
              ["HOST", window.location.host],
              ["TRANSPORT", "MCP streamable HTTP"],
              ["UPTIME", fmtUptime(server.started_at)],
              ["DATA ROOT", server.data_root],
              ["PROJECTS", `${server.projects}`],
              ["OPEN PERIODS", `${server.open_periods.length} · ${openPeriods.join(", ") || "—"}`],
              ["API KEYS", local ? "Local mode · no auth" : `${server.api_keys ?? "?"} issued`],
            ] as const
          ).map(([label, value]) => (
            <div key={label} className="server-cell">
              <div className="server-cell-label">{label}</div>
              <div className="server-cell-value" title={value}>
                {value}
              </div>
            </div>
          ))}
        </div>
        <div className="hint" style={{ marginTop: 14 }}>
          The server deploys release tags (vX.Y.Z) only — pushing to main changes nothing there.
        </div>
      </section>
    </div>
  );
}

function KeysSection({ onAuthFail, tz }: { onAuthFail: () => void; tz: ServerTimezone | undefined }) {
  const [keys, setKeys] = useState<KeyInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState<{ name: string; key: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const fail = (e: unknown) => {
    if (e instanceof Unauthorized) onAuthFail();
    else setError(String((e as Error).message ?? e));
  };
  const load = () => {
    api<{ keys: KeyInfo[] }>("/api/keys")
      .then((b) => {
        setKeys(b.keys);
        setError(null);
      })
      .catch(fail);
  };
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  const issue = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || busy) return;
    setBusy(true);
    apiSend<{ name: string; key: string }>("/api/keys", "POST", { name })
      .then((b) => {
        setIssued(b);
        setCopied(false);
        setIssuing(false);
        setNewName("");
        setError(null);
        load();
      })
      .catch(fail)
      .finally(() => setBusy(false));
  };

  const revoke = (name: string) => {
    if (!window.confirm(`Revoke '${name}'? That machine loses access immediately.`)) return;
    apiSend(`/api/keys/${encodeURIComponent(name)}`, "DELETE")
      .then(() => {
        if (issued?.name === name) setIssued(null);
        setError(null);
        load();
      })
      .catch(fail);
  };

  return (
    <section className="card">
      <div className="keys-head">
        <div>
          <div className="card-title">API keys</div>
          <div className="card-sub">
            One per client machine · only the hash is stored, and the key is shown once at issue
          </div>
        </div>
        <button className="cta-btn" onClick={() => setIssuing(!issuing)}>
          + New key
        </button>
      </div>

      {issuing && (
        <form className="key-issue" onSubmit={issue}>
          <input
            placeholder="Key name (machine, e.g. pc2)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            autoFocus
          />
          <button className="cta-btn" type="submit" disabled={busy || !newName.trim()}>
            Issue
          </button>
          <button className="ghost-btn" type="button" onClick={() => setIssuing(false)}>
            Cancel
          </button>
        </form>
      )}

      {issued && (
        <div className="key-reveal">
          <div className="key-reveal-label">
            Key '{issued.name}' issued — you cannot see it again. Copy it now.
          </div>
          <div className="key-reveal-row">
            <code>{issued.key}</code>
            <button
              className="ghost-btn"
              onClick={() => {
                navigator.clipboard.writeText(issued.key).then(() => setCopied(true));
              }}
            >
              {copied ? "Copied ✓" : "Copy"}
            </button>
            <button className="ghost-btn" onClick={() => setIssued(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      <div className="key-table">
        <div className="key-grid thead">
          <span>NAME</span>
          <span>FINGERPRINT</span>
          <span>CREATED</span>
          <span></span>
        </div>
        {keys === null && !error && (
          <div className="key-grid">
            <span className="muted">Loading…</span>
          </div>
        )}
        {keys !== null && keys.length === 0 && (
          <div className="key-grid">
            <span className="muted">No keys yet</span>
          </div>
        )}
        {(keys ?? []).map((k) => (
          <div key={k.name} className="key-grid">
            <span className="key-name">
              <span className="dot" />
              {k.name}
            </span>
            <span className="key-fp">{k.fingerprint ?? "—"}</span>
            <span className="key-date">{fmtServerTime(k.created_at, tz).slice(0, 10)}</span>
            <button className="danger-btn" onClick={() => revoke(k.name)}>
              Revoke
            </button>
          </div>
        ))}
      </div>
      <div className="hint">
        Revoking is permanent — that machine loses access immediately. The dashboard login and API
        keys are separate.
      </div>
    </section>
  );
}
