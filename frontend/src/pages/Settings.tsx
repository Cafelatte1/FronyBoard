import { useEffect, useState } from "react";
import { Unauthorized, api, apiSend, getUsername, logout } from "../api";
import { fmtServerTime, fmtUptime } from "../shared";
import type { BoardData, KeyInfo, ServerTimezone } from "../types";

export default function Settings({ data, onAuthFail }: { data: BoardData; onAuthFail: () => void }) {
  const username = getUsername() ?? "?";
  const server = data.server;
  const openPeriods = [...new Set(server.open_periods.map((p) => p.period))];

  return (
    <div className="settings-col">
      <section className="card">
        <div className="card-title">계정</div>
        <div className="account-row">
          <span className="avatar">{username.charAt(0).toUpperCase()}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="account-name">{username}</div>
            <div className="account-sub">대시보드 로그인 · 세션은 서버 메모리에 있어 재시작하면 로그아웃됩니다</div>
          </div>
          <button className="ghost-btn" onClick={() => logout().then(onAuthFail)}>
            로그아웃
          </button>
        </div>
        <div className="note">
          로그인 계정은 서버에서 <span className="mono">aira admin &lt;username&gt;</span> 으로
          변경합니다. 모든 쓰기는 MCP 툴을 통해서만 이루어집니다 — 이 화면은 조회 전용입니다.
        </div>
      </section>

      <KeysSection onAuthFail={onAuthFail} tz={server.timezone} />

      <section className="card">
        <div className="card-title">서버 정보</div>
        <div className="server-grid">
          {(
            [
              ["VERSION", `aira v${server.version}`],
              ["HOST", window.location.host],
              ["TRANSPORT", "MCP streamable HTTP"],
              ["UPTIME", fmtUptime(server.started_at)],
              ["DATA ROOT", server.data_root],
              ["PROJECTS", `${server.projects}개`],
              ["OPEN PERIODS", `${server.open_periods.length} · ${openPeriods.join(", ") || "—"}`],
              ["API KEYS", `${server.api_keys}개 발급`],
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
          홈서버는 release 태그(vX.Y.Z) 기준으로만 배포합니다 — main에 push해도 서버에는 반영되지
          않습니다.
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
    if (!window.confirm(`'${name}' 키를 삭제할까요? 해당 PC는 즉시 연결이 끊깁니다.`)) return;
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
          <div className="card-title">API 키</div>
          <div className="card-sub">
            클라이언트 PC 1대당 1개 · 해시만 저장되며 발급 시 한 번만 표시됩니다
          </div>
        </div>
        <button className="cta-btn" onClick={() => setIssuing(!issuing)}>
          ＋ 키 발급
        </button>
      </div>

      {issuing && (
        <form className="key-issue" onSubmit={issue}>
          <input
            placeholder="키 이름 (기기명, 예: pc2)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            autoFocus
          />
          <button className="cta-btn" type="submit" disabled={busy || !newName.trim()}>
            발급
          </button>
          <button className="ghost-btn" type="button" onClick={() => setIssuing(false)}>
            취소
          </button>
        </form>
      )}

      {issued && (
        <div className="key-reveal">
          <div className="key-reveal-label">
            '{issued.name}' 키가 발급되었어요 — 이 키는 다시 볼 수 없어요. 지금 복사해 두세요.
          </div>
          <div className="key-reveal-row">
            <code>{issued.key}</code>
            <button
              className="ghost-btn"
              onClick={() => {
                navigator.clipboard.writeText(issued.key).then(() => setCopied(true));
              }}
            >
              {copied ? "복사됨 ✓" : "복사"}
            </button>
            <button className="ghost-btn" onClick={() => setIssued(null)}>
              닫기
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
            <span className="muted">불러오는 중…</span>
          </div>
        )}
        {keys !== null && keys.length === 0 && (
          <div className="key-grid">
            <span className="muted">발급된 키가 없어요</span>
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
              삭제
            </button>
          </div>
        ))}
      </div>
      <div className="hint">
        키 삭제는 되돌릴 수 없습니다 — 해당 PC는 즉시 연결이 끊깁니다. 대시보드 로그인과 API 키는
        서로 별개입니다.
      </div>
    </section>
  );
}
