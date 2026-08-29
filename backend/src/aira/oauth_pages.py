"""The pages of the OAuth browser leg (/oauth/login, /oauth/deny).

Server-rendered and self-contained — no build step, nothing from a third party:
this is a public page behind the Funnel and must work from any in-app browser.
Styling follows the dashboard's dark design tokens (frontend/src/styles.css) and
the same two webfonts it serves from /fonts.
"""

from __future__ import annotations

import html
from urllib.parse import urlsplit

from starlette.responses import HTMLResponse

_CSS = """
@font-face{font-family:'Pretendard';font-style:normal;font-weight:400;font-display:swap;
src:url('/fonts/Pretendard-Regular.woff2') format('woff2')}
@font-face{font-family:'Pretendard';font-style:normal;font-weight:600;font-display:swap;
src:url('/fonts/Pretendard-SemiBold.woff2') format('woff2')}
@font-face{font-family:'Pretendard';font-style:normal;font-weight:700;font-display:swap;
src:url('/fonts/Pretendard-Bold.woff2') format('woff2')}
@font-face{font-family:'JetBrains Mono';font-style:normal;font-weight:400;font-display:swap;
src:url('/fonts/JetBrainsMono-Regular.woff2') format('woff2')}
@font-face{font-family:'JetBrains Mono';font-style:normal;font-weight:600;font-display:swap;
src:url('/fonts/JetBrainsMono-SemiBold.woff2') format('woff2')}
:root{--bg:#1b1b22;--surface:#23232b;--surface-raised:#2c2c36;--border:#34343f;--border-strong:#43424f;
--text:#f2f0f7;--text-muted:#b4b4be;--text-disabled:#8a8a94;--accent:#a18cd1;--on-accent-subtle:#b9a6e4;
--gradient:linear-gradient(90deg,#a18cd1,#fbc2eb);--gradient-diag:linear-gradient(135deg,#a18cd1,#fbc2eb);
--gradient-cta:linear-gradient(90deg,#a18cd1,#e9a8d4);--on-gradient:#2a2530;
--success:#6fbf8b;--success-subtle:#24402f;--on-success-subtle:#8fd6a6;--warning-subtle:#453820;--on-warning-subtle:#e5b87e;
--danger:#b0505c;--danger-subtle:#4e2f3a;--on-danger-subtle:#de9099;--neutral-subtle:#383843;--on-neutral-subtle:#b4b4be;
--font:'Pretendard',-apple-system,'Segoe UI','Noto Sans KR',sans-serif;--mono:'JetBrains Mono',ui-monospace,'SF Mono',Consolas,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px 24px;
background:#15151a;color:var(--text);font-family:var(--font);font-size:15px;line-height:1.55;position:relative;overflow-x:hidden}
body::before,body::after{content:'';position:absolute;border-radius:50%;pointer-events:none;z-index:0}
body::before{top:-320px;left:50%;margin-left:-420px;width:840px;height:760px;
background:radial-gradient(closest-side,rgba(161,140,209,.2),rgba(161,140,209,0))}
body::after{bottom:-380px;right:-140px;width:760px;height:700px;
background:radial-gradient(closest-side,rgba(251,194,235,.09),rgba(251,194,235,0))}
main{position:relative;z-index:1;width:760px;max-width:100%;display:grid;grid-template-columns:330px minmax(0,1fr);
background:var(--surface);border:1px solid var(--border);border-radius:18px;box-shadow:0 24px 60px rgba(0,0,0,.55);overflow:hidden}
aside{background:var(--bg);border-right:1px solid var(--border);padding:26px 24px;display:flex;flex-direction:column;gap:20px}
.brand{display:flex;align-items:center;gap:9px;font-size:14px;font-weight:700;letter-spacing:.08em}
.brand img{width:22px;height:22px;flex:none;display:block}
h1{margin:0;font-size:19px;font-weight:700;letter-spacing:-.01em;line-height:1.35}
aside p{margin:6px 0 0;font-size:13px;color:var(--text-muted)}
section{padding:26px 28px;display:flex;flex-direction:column;gap:16px}
h2{margin:0;font-size:16px;font-weight:600}
form{display:flex;flex-direction:column;gap:14px}
label{display:flex;flex-direction:column;gap:6px}
.lbl{display:flex;justify-content:space-between;align-items:center;font-size:12px;font-weight:600;color:var(--text-muted)}
.lbl button{font:inherit;background:none;border:0;padding:0;color:var(--text-muted);cursor:pointer}
.lbl button:hover{color:var(--on-accent-subtle)}
input{font:inherit;width:100%;height:38px;padding:0 14px;border:1px solid var(--border-strong);border-radius:10px;
background:var(--surface-raised);color:var(--text);outline:none}
input:focus{border-color:var(--accent)}
.err{display:flex;gap:8px;align-items:flex-start;padding:9px 11px;border-radius:10px;background:var(--danger-subtle);
color:var(--on-danger-subtle);font-size:13px}
.err svg{width:14px;height:14px;flex:none;margin-top:2px}
.btn{font:inherit;display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:38px;border-radius:10px;
border:1px solid var(--border-strong);background:transparent;color:var(--text);font-size:13px;font-weight:600;cursor:pointer;text-decoration:none}
.btn:hover{border-color:var(--accent);color:var(--on-accent-subtle)}
.btn.deny{color:var(--text-muted);margin-top:-5px}
.btn.deny:hover{border-color:var(--danger);color:var(--on-danger-subtle)}
.btn.primary{height:42px;border:0;background:var(--gradient-cta);color:var(--on-gradient);font-size:15px;font-weight:700;
box-shadow:0 4px 14px rgba(161,140,209,.35);margin-top:4px}
.btn.primary:hover{filter:brightness(1.06)}
.btn.primary:disabled{opacity:.75;cursor:default}
.btn.primary svg{width:15px;height:15px;display:none;animation:spin .8s linear infinite}
.btn.primary:disabled svg{display:block}
@keyframes spin{to{transform:rotate(360deg)}}
.result{display:flex;flex-direction:column;align-items:center;gap:14px;text-align:center;padding-top:12px}
.result .icon{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.result .icon svg{width:22px;height:22px}
.result h2{font-size:17px;font-weight:700;letter-spacing:-.01em}
.result p{margin:6px 0 0;font-size:13px;color:var(--text-muted)}
.done .icon{background:var(--success-subtle);color:var(--on-success-subtle)}
.denied .icon{background:var(--neutral-subtle);color:var(--on-neutral-subtle)}
.expired .icon{background:var(--warning-subtle);color:var(--on-warning-subtle)}
.locked .icon{background:var(--danger-subtle);color:var(--on-danger-subtle)}
.mono{font-family:var(--mono);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.detail{width:100%;padding:9px 12px;border-radius:10px;background:var(--bg);border:1px solid var(--border);color:var(--text-muted)}
@media(max-width:720px){body{padding:16px 12px;align-items:flex-start}main{grid-template-columns:1fr}
aside{border-right:0;border-bottom:1px solid var(--border);padding:20px}section{padding:20px}}
"""

_ALERT = ("<svg viewBox='0 0 16 16' fill='none' stroke='currentColor' stroke-width='1.5'>"
          "<circle cx='8' cy='8' r='6.2'/><path d='M8 5v4.2M8 11.2v.2' stroke-linecap='round'/></svg>")
_SPINNER = ("<svg viewBox='0 0 20 20' fill='none' stroke='currentColor' stroke-width='2'>"
            "<path d='M10 2.6a7.4 7.4 0 1 1-7.3 6.1' stroke-linecap='round'/></svg>")
_ICONS = {
    "done": "M5 12.5 9.5 17 19 7",
    "denied": "M7 7l10 10M17 7 7 17",
    "expired": "M12 7v5l3 2M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Z",
    "locked": "M6 10.5h12v9H6zM9 10.5V7.5a3 3 0 0 1 6 0v3",
}

_JS = """
var pw=document.getElementById('pw'),sh=document.getElementById('show');
sh.onclick=function(){var t=pw.type==='password';pw.type=t?'text':'password';sh.textContent=t?'숨기기':'보기'};
document.getElementById('f').onsubmit=function(){var b=document.getElementById('go');
b.disabled=true;b.lastElementChild.textContent='승인 처리 중…'};
"""


def _jong(name: str) -> int | None:
    """Final consonant index of the last Hangul syllable (0 = none), None if not Hangul."""
    code = ord(name[-1]) if name else 0
    return (code - 0xAC00) % 28 if 0xAC00 <= code <= 0xD7A3 else None


def _ga(name: str) -> str:
    return "이" if _jong(name) else "가"


def ro(name: str) -> str:
    return "으로" if _jong(name) not in (None, 0, 8) else "로"


def _shell(client_name: str, body: str, status: int, head: str = "") -> HTMLResponse:
    name = html.escape(client_name)
    return HTMLResponse(
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Frony 연결 승인</title>{head}<style>{_CSS}</style></head><body><main>"
        f"<aside><div class='brand'><img src='/favicon.ico' alt=''>FRONY</div><div><h1>{name}{_ga(client_name)}<br>Frony 연결을 요청합니다</h1>"
        "<p>승인하면 이 앱에 전용 토큰이 발급됩니다.</p></div></aside>"
        f"<section>{body}</section>"
        "</main></body></html>", status_code=status, headers={"Cache-Control": "no-store"})


def form_page(txn: str, client_name: str, error: str | None = None) -> HTMLResponse:
    err = f"<div class='err'>{_ALERT}<span>{html.escape(error)}</span></div>" if error else ""
    body = (
        "<h2>Frony 계정으로 로그인</h2>"
        f"<form method='post' action='/oauth/login' id='f'><input type='hidden' name='txn' value='{html.escape(txn)}'>"
        "<label><span class='lbl'>아이디</span><input name='username' autocomplete='username' required autofocus></label>"
        "<label><span class='lbl'>비밀번호<button type='button' id='show'>보기</button></span>"
        "<input name='password' type='password' id='pw' autocomplete='current-password' required></label>"
        f"{err}<button type='submit' class='btn primary' id='go'>{_SPINNER}<span>승인하고 연결</span></button></form>"
        f"<form method='post' action='/oauth/deny'><input type='hidden' name='txn' value='{html.escape(txn)}'>"
        "<button type='submit' class='btn deny'>거부</button></form>"
        f"<script>{_JS}</script>")
    return _shell(client_name, body, 200)


def result_page(kind: str, client_name: str | None, title: str, text: str, detail: str,
                status: int = 200, redirect: str | None = None) -> HTMLResponse:
    """A terminal screen: done / denied (both hand the browser back to the app
    after a second), expired, locked."""
    head = f"<meta http-equiv='refresh' content='1;url={html.escape(redirect, quote=True)}'>" if redirect else ""
    body = (
        f"<div class='result {kind}'><span class='icon'><svg viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.8'><path d='{_ICONS[kind]}' stroke-linecap='round' stroke-linejoin='round'/></svg></span>"
        f"<div><h2>{html.escape(title)}</h2><p>{html.escape(text)}</p></div>"
        f"<span class='detail mono'>{html.escape(detail)}</span></div>")
    return _shell(client_name or "앱", body, status, head)


def redirect_detail(url: str) -> str:
    """`→ claude.ai/api/mcp/auth_callback?code=…` — where the app is taken, without the secret."""
    u = urlsplit(url)
    key = "code" if "code=" in u.query else "error"
    value = "…" if key == "code" else "access_denied"
    return f"→ {u.netloc}{u.path}?{key}={value}"
