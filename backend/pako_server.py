"""
pako_server.py — Servidor de la plataforma PAKO v4.0

Páginas:
  / → Dashboard
  /automatizaciones → Editor de workflows (n8n-like)
  /conocimiento → Base de conocimiento
  /ajustes → Configuración
  /actividad → Logs y actividad

Seguridad: rate limiting, validación, sanitización, headers.
"""

import sys, json, time, re, threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from collections import defaultdict, deque

sys.path.insert(0, str(Path(__file__).parent))

from pako_memory      import PakoMemory
from pako_brain       import PakoBrain
from pako_web_agent   import PakoWebAgent
from pako_github_agent import PakoGitHubAgent
from pako_file_agent  import PakoFileAgent
from pako_automations import PakoAutomations, TIPOS_NODO

import os
DATA_DIR = Path(os.environ.get("PAKO_DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_REQ  = 65_536
MAX_MSG  = 2_000
RL_RPM   = 80

class _RL:
    def __init__(self, rpm=80):
        self._rpm = rpm; self._h = defaultdict(lambda: deque()); self._l = threading.Lock()
    def ok(self, ip):
        now = time.time()
        with self._l:
            h = self._h[ip]
            while h and h[0] < now - 60: h.popleft()
            if len(h) >= self._rpm: return False
            h.append(now); return True

def _san(t): return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)
def _ok_gh_token(t): return bool(re.match(r"^(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]+)$", t))
def _ok_hash(h): return bool(re.match(r"^[0-9a-f]{8,32}$", h))

# ── Init ──────────────────────────────────────────────────────────
memory       = PakoMemory(data_dir=str(DATA_DIR))
brain        = PakoBrain(memory=memory)
web_agent    = PakoWebAgent(memory=memory)
github_agent = PakoGitHubAgent(memory=memory)
file_agent   = PakoFileAgent(memory=memory)
automations  = PakoAutomations(data_dir=str(DATA_DIR), memory=memory)
rl           = _RL(RL_RPM)

brain.web_agent    = web_agent
brain.github_agent = github_agent
brain.file_agent   = file_agent
brain.automations  = automations
automations.set_brain(brain)

for c in [DATA_DIR/"pako_conocimiento.json", Path("paco_aprendido.json")]:
    if c.exists():
        n = memory.cargar_desde_json_legacy(str(c))
        if n > 0: print(f"✅ {n} entradas cargadas de '{c.name}'"); break

if memory.get_config("github_token",""):
    if github_agent.reconectar():
        print(f"🐙 GitHub: @{github_agent._usuario}")

print(f"🧠 PAKO v4 listo — {memory.stats()['total']} conceptos")


# ══════════════════════════════════════════════════════════════════
# HTML: SHELL MULTIPÁGINA
# ══════════════════════════════════════════════════════════════════

def _platform_html() -> str:
    return r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PAKO Platform</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&family=Sora:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07070d;--bg2:#0d0d18;--s1:#111120;--s2:#16162a;--s3:#1c1c35;
  --bd:#252542;--bd2:#333360;
  --p:#6366f1;--p2:#818cf8;--p3:#a5b4fc;
  --cy:#06b6d4;--gn:#10b981;--am:#f59e0b;--rd:#ef4444;--pk:#ec4899;
  --t1:#f0f0ff;--t2:#9ca3af;--t3:#6b7280;--t4:#4b5563;
  --r:12px;--rs:8px;--rx:5px;
  --sh:0 8px 32px rgba(0,0,0,.6);
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--t1);font-family:'Sora',sans-serif}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px}
*{scrollbar-width:thin;scrollbar-color:var(--bd2) transparent}

/* ══ LAYOUT ══ */
#app{display:flex;height:100vh;overflow:hidden}

/* ══ NAV LATERAL ══ */
#nav{
  width:220px;min-width:220px;
  background:var(--s1);
  border-right:1px solid var(--bd);
  display:flex;flex-direction:column;
  transition:width .3s cubic-bezier(.4,0,.2,1);
  overflow:hidden;
  z-index:10;
}
#nav.mini{width:60px;min-width:60px}

#nav-logo{
  padding:18px 16px;
  border-bottom:1px solid var(--bd);
  display:flex;align-items:center;gap:12px;
  background:linear-gradient(135deg,#0d0d18,#16122a);
  flex-shrink:0;
}
.logo-orb{
  width:36px;height:36px;border-radius:10px;flex-shrink:0;
  background:linear-gradient(135deg,#4f46e5,#7c3aed);
  display:flex;align-items:center;justify-content:center;font-size:18px;
  box-shadow:0 0 20px rgba(99,102,241,.5);
  animation:orb 4s ease-in-out infinite;
}
@keyframes orb{0%,100%{box-shadow:0 0 16px rgba(99,102,241,.4)}50%{box-shadow:0 0 32px rgba(99,102,241,.8)}}
.logo-t{font-size:1.1rem;font-weight:700;letter-spacing:-.01em;white-space:nowrap;overflow:hidden}
.logo-s{font-size:.58rem;color:var(--t3);font-family:'IBM Plex Mono',monospace;white-space:nowrap}

#nav-links{flex:1;padding:10px 8px;overflow-y:auto}
.nav-section{font-size:.55rem;font-weight:600;text-transform:uppercase;letter-spacing:.12em;
  color:var(--t4);padding:10px 8px 4px;font-family:'IBM Plex Mono',monospace;white-space:nowrap;overflow:hidden}
.nav-item{
  display:flex;align-items:center;gap:10px;
  padding:9px 10px;border-radius:var(--rs);cursor:pointer;
  color:var(--t2);font-size:.82rem;font-weight:400;
  transition:all .15s;margin-bottom:2px;white-space:nowrap;overflow:hidden;
  border:1px solid transparent;
}
.nav-item:hover{background:var(--s2);color:var(--t1);border-color:var(--bd)}
.nav-item.active{background:rgba(99,102,241,.15);color:var(--p3);border-color:rgba(99,102,241,.3)}
.nav-item .ni{font-size:16px;flex-shrink:0;width:20px;text-align:center}
.nav-item .nl{flex:1;overflow:hidden;text-overflow:ellipsis}
.nav-badge{
  padding:1px 6px;border-radius:999px;font-size:.58rem;
  font-family:'IBM Plex Mono',monospace;flex-shrink:0;
  background:rgba(99,102,241,.2);color:var(--p3);
}

#nav-footer{padding:10px 8px;border-top:1px solid var(--bd);flex-shrink:0}
.nav-toggle-btn{
  width:100%;padding:7px 10px;background:var(--s2);border:1px solid var(--bd);
  color:var(--t3);border-radius:var(--rs);cursor:pointer;font-size:.72rem;
  font-family:'IBM Plex Mono',monospace;display:flex;align-items:center;gap:8px;
  transition:all .15s;
}
.nav-toggle-btn:hover{border-color:var(--bd2);color:var(--t2)}

/* ══ CONTENIDO PÁGINAS ══ */
#content{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}

.page{display:none;flex:1;flex-direction:column;overflow:hidden;height:100%}
.page.active{display:flex}

/* ── Topbar de página ── */
.page-topbar{
  padding:12px 20px;background:var(--s1);border-bottom:1px solid var(--bd);
  display:flex;align-items:center;gap:10px;flex-shrink:0;
}
.page-title{font-size:.92rem;font-weight:600;color:var(--t2)}
.status-pill{
  display:flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:999px;background:var(--s2);border:1px solid var(--bd);
  font-size:.62rem;font-family:'IBM Plex Mono',monospace;color:var(--t3);
}
.dot{width:6px;height:6px;border-radius:50%;background:var(--gn);animation:dp 2s ease-in-out infinite;flex-shrink:0}
.dot.busy{background:var(--am);animation:dp .5s ease-in-out infinite}
@keyframes dp{0%,100%{opacity:1}50%{opacity:.3}}
.topbar-right{margin-left:auto;display:flex;gap:6px}
.tbtn{
  padding:5px 10px;background:var(--s2);border:1px solid var(--bd);
  color:var(--t3);border-radius:var(--rs);cursor:pointer;font-size:.68rem;
  font-family:'IBM Plex Mono',monospace;transition:all .15s;
}
.tbtn:hover{border-color:var(--bd2);color:var(--t2)}

/* ══════════════════════════════════════════════
   PÁGINA CHAT / DASHBOARD
══════════════════════════════════════════════ */
#page-chat{display:flex}
#chat-sidebar{
  width:260px;min-width:260px;
  background:var(--s1);border-right:1px solid var(--bd);
  display:flex;flex-direction:column;overflow:hidden;
}
#chs-header{padding:14px 16px;border-bottom:1px solid var(--bd);font-size:.75rem;font-weight:600;color:var(--t2)}
#chs-body{flex:1;padding:12px;overflow-y:auto}
.s-label{font-size:.56rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--t4);font-family:'IBM Plex Mono',monospace;margin:12px 0 6px}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:4px}
.sc{background:var(--s2);border:1px solid var(--bd);border-radius:var(--rs);padding:9px 11px}
.sc .n{font-size:1.2rem;font-weight:700;font-family:'IBM Plex Mono',monospace;line-height:1}
.sc .l{font-size:.6rem;color:var(--t3);margin-top:2px}
.tog-row{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--s2);border:1px solid var(--bd);border-radius:var(--rs);margin-bottom:4px;cursor:pointer;transition:border-color .15s}
.tog-row:hover{border-color:var(--bd2)}
.tog-lbl{font-size:.75rem;color:var(--t2);user-select:none}
.sw{width:32px;height:17px;background:var(--bd2);border-radius:9px;position:relative;cursor:pointer;transition:background .2s;flex-shrink:0}
.sw.on{background:var(--p)}
.sw::after{content:'';position:absolute;top:2px;left:2px;width:13px;height:13px;border-radius:50%;background:#fff;transition:transform .2s}
.sw.on::after{transform:translateX(15px)}
.gh-box{background:var(--s2);border:1px solid var(--bd);border-radius:var(--rs);padding:11px}
.gh-box input{width:100%;padding:7px 9px;background:var(--bg);border:1px solid var(--bd);color:var(--t1);border-radius:var(--rx);font-size:.75rem;font-family:'IBM Plex Mono',monospace;outline:none;margin-bottom:6px;transition:border-color .15s}
.gh-box input:focus{border-color:var(--p)}
.gh-box input::placeholder{color:var(--t4)}
.btn-p{width:100%;padding:7px;background:var(--p);color:#fff;border:none;border-radius:var(--rx);cursor:pointer;font-size:.75rem;font-family:'Sora',sans-serif;font-weight:600;transition:all .15s}
.btn-p:hover{background:#4f46e5}
.gh-st{font-size:.65rem;color:var(--t3);text-align:center;margin-top:5px}
.act-item{padding:6px 0;border-bottom:1px solid var(--bd)}
.act-item:last-child{border-bottom:none}
.act-tipo{font-size:.58rem;padding:1px 5px;border-radius:3px;font-family:'IBM Plex Mono',monospace;font-weight:600}
.t-aprendizaje{background:rgba(99,102,241,.2);color:#a5b4fc}
.t-busqueda{background:rgba(6,182,212,.2);color:#67e8f9}
.t-sistema{background:rgba(16,185,129,.2);color:#6ee7b7}
.t-error{background:rgba(239,68,68,.2);color:#fca5a5}
.act-msg{font-size:.68rem;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.act-ts{font-size:.57rem;color:var(--t3);font-family:'IBM Plex Mono',monospace;margin-top:1px}

/* chat principal */
#chat-main{flex:1;display:flex;flex-direction:column;overflow:hidden}
#chat-messages{flex:1;overflow-y:auto;padding:18px 22px;display:flex;flex-direction:column;gap:14px;scroll-behavior:smooth}
.msg{display:flex;gap:9px;animation:mIn .2s ease;max-width:860px}
@keyframes mIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.msg.user{flex-direction:row-reverse;align-self:flex-end}
.msg.pako{align-self:flex-start}
.av{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:.58rem;font-weight:700;flex-shrink:0;font-family:'IBM Plex Mono',monospace}
.msg.user .av{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff}
.msg.pako .av{background:var(--s2);border:1.5px solid var(--p);color:var(--p2)}
.bubble{padding:11px 15px;border-radius:var(--r);font-size:.855rem;line-height:1.75;max-width:680px;word-break:break-word}
.msg.user .bubble{background:linear-gradient(135deg,rgba(79,70,229,.22),rgba(124,58,237,.18));border:1px solid rgba(99,102,241,.35);border-bottom-right-radius:3px;color:#d4d4ff}
.msg.pako .bubble{background:var(--s1);border:1px solid var(--bd);border-bottom-left-radius:3px;color:var(--t1)}
.bubble pre{background:var(--bg2);border:1px solid var(--bd);border-radius:var(--rs);padding:9px 13px;font-family:'IBM Plex Mono',monospace;font-size:.77rem;overflow-x:auto;margin:7px 0}
.bubble code{background:rgba(99,102,241,.15);color:var(--p3);padding:1px 5px;border-radius:3px;font-family:'IBM Plex Mono',monospace;font-size:.82em}
.bubble strong{color:var(--p3);font-weight:600}
.bubble a{color:var(--cy);text-decoration:none}.bubble a:hover{text-decoration:underline}
.bw{display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:rgba(6,182,212,.15);color:#67e8f9;border-radius:3px;font-size:.58rem;font-family:'IBM Plex Mono',monospace;margin-right:3px}
.bg{display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:rgba(16,185,129,.15);color:#6ee7b7;border-radius:3px;font-size:.58rem;font-family:'IBM Plex Mono',monospace;margin-right:3px}
.bm{display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:rgba(99,102,241,.15);color:var(--p3);border-radius:3px;font-size:.58rem;font-family:'IBM Plex Mono',monospace;margin-right:3px}
.msg-meta{font-size:.57rem;color:var(--t4);font-family:'IBM Plex Mono',monospace;align-self:flex-end;flex-shrink:0;padding-bottom:2px}
.typing-b{display:flex;align-items:center;gap:10px;padding:9px 13px;background:var(--s1);border:1px solid var(--bd);border-radius:var(--r);border-bottom-left-radius:3px}
.dots{display:flex;gap:4px}.dots span{width:5px;height:5px;border-radius:50%;background:var(--p2);animation:bounce 1.3s ease-in-out infinite}
.dots span:nth-child(2){animation-delay:.15s}.dots span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-4px)}}
.ty-txt{font-size:.7rem;color:var(--t3);font-family:'IBM Plex Mono',monospace}
#chips{display:flex;flex-wrap:wrap;gap:5px;padding:7px 22px 3px;flex-shrink:0}
.chip{padding:4px 11px;border-radius:999px;border:1px solid var(--bd);background:var(--s2);color:var(--t3);cursor:pointer;font-size:.62rem;font-family:'IBM Plex Mono',monospace;transition:all .15s;white-space:nowrap}
.chip:hover{border-color:var(--p);color:var(--p3);background:rgba(99,102,241,.1)}
#inp-area{display:flex;gap:7px;padding:10px 18px 14px;border-top:1px solid var(--bd);background:var(--s1);flex-shrink:0;align-items:flex-end}
#msg-inp{flex:1;background:var(--bg2);border:1px solid var(--bd);border-radius:var(--r);color:var(--t1);font-family:'Sora',sans-serif;font-size:.855rem;padding:10px 14px;resize:none;min-height:42px;max-height:130px;outline:none;transition:border-color .2s;line-height:1.5}
#msg-inp:focus{border-color:var(--p)}
#msg-inp::placeholder{color:var(--t4)}
#send-btn{width:42px;height:42px;border-radius:var(--r);border:none;background:var(--p);color:#fff;cursor:pointer;font-size:15px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
#send-btn:hover{background:#4f46e5;transform:scale(1.05)}
#send-btn:active{transform:scale(.93)}
#send-btn:disabled{background:var(--bd);cursor:not-allowed;transform:none}

/* ══════════════════════════════════════════════
   PÁGINA AUTOMATIZACIONES
══════════════════════════════════════════════ */
#page-auto .auto-layout{display:flex;flex:1;overflow:hidden}

/* Panel izquierdo: lista de workflows */
#wf-list-panel{
  width:280px;min-width:280px;background:var(--s1);border-right:1px solid var(--bd);
  display:flex;flex-direction:column;
}
#wf-list-header{
  padding:12px 14px;border-bottom:1px solid var(--bd);
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
}
#wf-list-header .ttl{font-size:.82rem;font-weight:600;color:var(--t2)}
.btn-new-wf{
  padding:5px 12px;background:var(--p);color:#fff;border:none;border-radius:var(--rx);
  cursor:pointer;font-size:.72rem;font-family:'Sora',sans-serif;font-weight:600;
  transition:background .15s;
}
.btn-new-wf:hover{background:#4f46e5}
#wf-list{flex:1;overflow-y:auto;padding:8px}
.wf-item{
  padding:10px 12px;border-radius:var(--rs);border:1px solid var(--bd);
  background:var(--s2);cursor:pointer;margin-bottom:6px;
  transition:all .15s;
}
.wf-item:hover{border-color:var(--bd2)}
.wf-item.selected{border-color:var(--p);background:rgba(99,102,241,.08)}
.wf-item-header{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.wf-item-name{font-size:.82rem;font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wf-toggle{width:28px;height:15px;background:var(--bd2);border-radius:8px;position:relative;cursor:pointer;transition:background .2s;flex-shrink:0}
.wf-toggle.on{background:var(--gn)}
.wf-toggle::after{content:'';position:absolute;top:2px;left:2px;width:11px;height:11px;border-radius:50%;background:#fff;transition:transform .2s}
.wf-toggle.on::after{transform:translateX(13px)}
.wf-item-meta{font-size:.62rem;color:var(--t3);font-family:'IBM Plex Mono',monospace;display:flex;gap:8px}
.wf-item-actions{display:flex;gap:4px;margin-top:6px}
.wf-act-btn{padding:3px 8px;border:1px solid var(--bd);background:var(--s1);color:var(--t3);border-radius:4px;cursor:pointer;font-size:.62rem;transition:all .15s}
.wf-act-btn:hover{border-color:var(--bd2);color:var(--t2)}
.wf-act-btn.run{border-color:rgba(16,185,129,.3);color:var(--gn)}
.wf-act-btn.run:hover{background:rgba(16,185,129,.1)}
.wf-act-btn.del{border-color:rgba(239,68,68,.3);color:var(--rd)}
.wf-act-btn.del:hover{background:rgba(239,68,68,.1)}
#wf-empty{text-align:center;color:var(--t4);font-size:.78rem;padding:30px 10px}

/* Editor de workflow */
#wf-editor{flex:1;display:flex;flex-direction:column;overflow:hidden}
#wf-editor-topbar{
  padding:10px 16px;background:var(--s1);border-bottom:1px solid var(--bd);
  display:flex;align-items:center;gap:10px;flex-shrink:0;
}
#wf-editor-name{font-size:.88rem;font-weight:600;color:var(--t1);flex:1}
.editor-btn{padding:5px 12px;border:1px solid var(--bd);background:var(--s2);color:var(--t2);border-radius:var(--rx);cursor:pointer;font-size:.72rem;font-family:'Sora',sans-serif;transition:all .15s}
.editor-btn:hover{border-color:var(--bd2);color:var(--t1)}
.editor-btn.primary{background:var(--p);border-color:var(--p);color:#fff}
.editor-btn.primary:hover{background:#4f46e5}
.editor-btn.success{background:rgba(16,185,129,.2);border-color:rgba(16,185,129,.4);color:var(--gn)}

#wf-editor-canvas{flex:1;overflow:auto;background:var(--bg);position:relative;background-image:radial-gradient(circle,var(--bd) 1px,transparent 1px);background-size:28px 28px}
#canvas-nodes{position:absolute;top:0;left:0;min-width:100%;min-height:100%}

/* Nodos en el canvas */
.canvas-node{
  position:absolute;min-width:160px;
  background:var(--s2);border:1.5px solid var(--bd);
  border-radius:var(--r);cursor:grab;
  box-shadow:0 4px 16px rgba(0,0,0,.4);
  user-select:none;transition:box-shadow .15s;
}
.canvas-node:hover{box-shadow:0 6px 24px rgba(0,0,0,.6)}
.canvas-node.selected{border-color:var(--p);box-shadow:0 0 0 2px rgba(99,102,241,.3)}
.node-header{
  padding:8px 12px;border-radius:var(--r) var(--r) 0 0;
  display:flex;align-items:center;gap:8px;
  background:var(--s3);border-bottom:1px solid var(--bd);
}
.node-ico{font-size:14px;flex-shrink:0}
.node-lbl{font-size:.78rem;font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.node-del{font-size:.7rem;color:var(--t4);cursor:pointer;transition:color .1s;flex-shrink:0}
.node-del:hover{color:var(--rd)}
.node-body{padding:8px 12px;font-size:.68rem;color:var(--t3);font-family:'IBM Plex Mono',monospace}
.node-port-out{
  width:12px;height:12px;border-radius:50%;border:2px solid var(--bd2);
  background:var(--s3);cursor:crosshair;margin:0 auto;
  transition:all .15s;position:relative;
}
.node-port-out:hover{border-color:var(--p);background:var(--p)}
.node-footer{padding:4px 12px 8px;display:flex;justify-content:center}

/* Panel derecho: nodos disponibles + IA chat */
#wf-right-panel{width:260px;min-width:260px;background:var(--s1);border-left:1px solid var(--bd);display:flex;flex-direction:column;overflow:hidden}
#wf-right-tabs{display:flex;border-bottom:1px solid var(--bd);flex-shrink:0}
.wr-tab{flex:1;padding:9px;text-align:center;font-size:.7rem;cursor:pointer;color:var(--t3);border-bottom:2px solid transparent;transition:all .15s;font-family:'IBM Plex Mono',monospace}
.wr-tab.active{color:var(--p3);border-bottom-color:var(--p)}
#wf-right-body{flex:1;overflow-y:auto;padding:10px}

/* Paleta de nodos */
.node-category{font-size:.58rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--t4);margin:10px 0 5px;font-family:'IBM Plex Mono',monospace}
.palette-node{
  display:flex;align-items:center;gap:8px;padding:7px 10px;
  border-radius:var(--rx);border:1px solid var(--bd);background:var(--s2);
  cursor:grab;margin-bottom:4px;font-size:.75rem;transition:all .15s;
}
.palette-node:hover{border-color:var(--bd2);background:var(--s3)}
.palette-node .pn-ico{font-size:13px;flex-shrink:0}
.palette-node .pn-lbl{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* IA assistant en automatizaciones */
#ia-chat-box{display:flex;flex-direction:column;height:100%}
#ia-msgs{flex:1;overflow-y:auto;padding:4px;display:flex;flex-direction:column;gap:8px}
.ia-msg{padding:8px 10px;border-radius:var(--rs);font-size:.75rem;line-height:1.6}
.ia-msg.pako{background:var(--s2);border:1px solid var(--bd);color:var(--t1)}
.ia-msg.user{background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.2);color:var(--p3);text-align:right}
#ia-inp-area{display:flex;gap:5px;padding:6px 0 2px;flex-shrink:0}
#ia-inp{flex:1;background:var(--bg2);border:1px solid var(--bd);border-radius:var(--rx);color:var(--t1);font-family:'Sora',sans-serif;font-size:.75rem;padding:7px 9px;resize:none;height:36px;outline:none;transition:border-color .15s}
#ia-inp:focus{border-color:var(--p)}
#ia-inp::placeholder{color:var(--t4)}
#ia-send{width:34px;height:34px;border-radius:var(--rx);border:none;background:var(--p);color:#fff;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
#ia-send:hover{background:#4f46e5}

/* Ejecución log */
#exec-log{padding:8px;font-size:.68rem;font-family:'IBM Plex Mono',monospace;color:var(--t2)}
.exec-step{padding:5px 7px;border-radius:4px;margin-bottom:3px;background:var(--s2);border:1px solid var(--bd)}
.exec-step.ok{border-color:rgba(16,185,129,.3)}
.exec-step.error{border-color:rgba(239,68,68,.3)}
.exec-step-name{color:var(--t1);font-weight:600;font-size:.7rem}
.exec-step-msg{color:var(--t3);font-size:.65rem}

/* ══════════════════════════════════════════════
   PÁGINA CONOCIMIENTO
══════════════════════════════════════════════ */
#page-conocimiento .kpage{padding:20px 24px;overflow-y:auto;flex:1}
.kpage-header{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.kpage-header h2{font-size:1rem;font-weight:600}
.kpage-search{flex:1;max-width:340px;padding:8px 13px;background:var(--s2);border:1px solid var(--bd);border-radius:var(--rs);color:var(--t1);font-family:'Sora',sans-serif;font-size:.82rem;outline:none;transition:border-color .15s}
.kpage-search:focus{border-color:var(--p)}
.k-table{width:100%;border-collapse:collapse;font-size:.78rem}
.k-table th{padding:9px 12px;text-align:left;font-size:.62rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--t3);border-bottom:1px solid var(--bd);font-family:'IBM Plex Mono',monospace}
.k-table td{padding:8px 12px;border-bottom:1px solid var(--bd);vertical-align:top}
.k-table tr:hover td{background:var(--s2)}
.k-clave{color:var(--p3);font-family:'IBM Plex Mono',monospace;font-size:.72rem}
.k-valor{color:var(--t2);max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.k-fuente{padding:1px 6px;border-radius:3px;font-size:.58rem;font-family:'IBM Plex Mono',monospace}
.f-manual{background:rgba(99,102,241,.2);color:#a5b4fc}
.f-web{background:rgba(6,182,212,.2);color:#67e8f9}
.f-github{background:rgba(16,185,129,.2);color:#6ee7b7}
.f-base{background:rgba(245,158,11,.2);color:#fcd34d}
.f-archivo{background:rgba(236,72,153,.2);color:#f9a8d4}
.k-del{color:var(--t4);cursor:pointer;transition:color .1s}.k-del:hover{color:var(--rd)}

/* ══════════════════════════════════════════════
   PÁGINAS: ACTIVIDAD Y AJUSTES
══════════════════════════════════════════════ */
.generic-page{padding:22px 26px;overflow-y:auto;flex:1}
.gp-title{font-size:1.05rem;font-weight:700;margin-bottom:4px}
.gp-sub{font-size:.8rem;color:var(--t3);margin-bottom:22px}
.card{background:var(--s1);border:1px solid var(--bd);border-radius:var(--r);padding:16px 18px;margin-bottom:12px}
.card-title{font-size:.82rem;font-weight:600;margin-bottom:10px;color:var(--t2)}
.cfg-row{display:flex;align-items:center;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--bd)}
.cfg-row:last-child{border-bottom:none}
.cfg-lbl{font-size:.8rem;color:var(--t2)}
.cfg-sub{font-size:.65rem;color:var(--t3);margin-top:1px}
.cfg-inp{background:var(--bg2);border:1px solid var(--bd);border-radius:var(--rx);color:var(--t1);padding:5px 9px;font-size:.78rem;font-family:'Sora',sans-serif;outline:none;width:180px;transition:border-color .15s}
.cfg-inp:focus{border-color:var(--p)}
.log-line{padding:5px 0;border-bottom:1px solid var(--bd);display:flex;align-items:flex-start;gap:8px;font-size:.72rem}
.log-ts{color:var(--t4);font-family:'IBM Plex Mono',monospace;flex-shrink:0;width:46px}
.log-tipo{flex-shrink:0}
.log-msg{color:var(--t2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ══ TOAST ══ */
#toast{position:fixed;bottom:18px;right:18px;padding:9px 16px;background:var(--s2);border:1px solid var(--bd);border-radius:var(--rs);font-size:.75rem;color:var(--t2);box-shadow:var(--sh);transform:translateY(50px);opacity:0;transition:all .25s;pointer-events:none;z-index:9999}
#toast.show{transform:translateY(0);opacity:1}

/* ══ MODAL ══ */
#modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);display:none;align-items:center;justify-content:center;z-index:1000}
#modal-overlay.show{display:flex}
#modal{background:var(--s1);border:1px solid var(--bd);border-radius:var(--r);padding:24px;min-width:360px;max-width:500px;box-shadow:var(--sh);animation:mIn .2s ease}
.modal-title{font-size:.95rem;font-weight:700;margin-bottom:16px;color:var(--t1)}
.modal-inp{width:100%;padding:9px 12px;background:var(--bg2);border:1px solid var(--bd);border-radius:var(--rs);color:var(--t1);font-family:'Sora',sans-serif;font-size:.82rem;outline:none;margin-bottom:8px;transition:border-color .15s}
.modal-inp:focus{border-color:var(--p)}
.modal-inp::placeholder{color:var(--t4)}
.modal-ta{resize:vertical;min-height:70px}
.modal-btns{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
.modal-btn{padding:7px 16px;border-radius:var(--rx);border:1px solid var(--bd);background:var(--s2);color:var(--t2);cursor:pointer;font-size:.78rem;transition:all .15s}
.modal-btn:hover{border-color:var(--bd2);color:var(--t1)}
.modal-btn.ok{background:var(--p);border-color:var(--p);color:#fff}
.modal-btn.ok:hover{background:#4f46e5}

/* Pending items */
.pi{display:flex;align-items:center;gap:7px;padding:7px 9px;background:var(--s2);border:1px solid var(--bd);border-radius:var(--rx);margin-bottom:4px;font-size:.72rem}
.pi-body{flex:1;overflow:hidden}
.pi-k{color:var(--p3);font-family:'IBM Plex Mono',monospace;font-size:.68rem}
.pi-v{color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pi-ok{padding:2px 7px;background:rgba(16,185,129,.2);color:#6ee7b7;border:none;border-radius:3px;cursor:pointer;font-size:.6rem}
.pi-nk{padding:2px 7px;background:rgba(239,68,68,.2);color:#fca5a5;border:none;border-radius:3px;cursor:pointer;font-size:.6rem}
</style>
</head>
<body>
<div id="app">

<!-- ══ NAV LATERAL ══ -->
<nav id="nav">
  <div id="nav-logo">
    <div class="logo-orb">🧠</div>
    <div>
      <div class="logo-t">PAKO</div>
      <div class="logo-s">PLATFORM v4.0</div>
    </div>
  </div>
  <div id="nav-links">
    <div class="nav-section">Principal</div>
    <div class="nav-item active" data-page="chat" onclick="goPage('chat')">
      <span class="ni">💬</span><span class="nl">Chat / Dashboard</span>
    </div>
    <div class="nav-item" data-page="auto" onclick="goPage('auto')">
      <span class="ni">⚡</span><span class="nl">Automatizaciones</span>
      <span class="nav-badge" id="nb-auto">0</span>
    </div>
    <div class="nav-section">Datos</div>
    <div class="nav-item" data-page="conocimiento" onclick="goPage('conocimiento')">
      <span class="ni">🧠</span><span class="nl">Conocimiento</span>
      <span class="nav-badge" id="nb-conocimiento">0</span>
    </div>
    <div class="nav-item" data-page="actividad" onclick="goPage('actividad')">
      <span class="ni">📋</span><span class="nl">Actividad</span>
    </div>
    <div class="nav-section">Sistema</div>
    <div class="nav-item" data-page="ajustes" onclick="goPage('ajustes')">
      <span class="ni">⚙️</span><span class="nl">Ajustes</span>
    </div>
  </div>
  <div id="nav-footer">
    <button class="nav-toggle-btn" onclick="toggleNav()">
      <span id="nav-toggle-ico">◀</span>
      <span id="nav-toggle-lbl">Contraer</span>
    </button>
  </div>
</nav>

<!-- ══ CONTENIDO ══ -->
<div id="content">

  <!-- ── PÁGINA CHAT ── -->
  <div id="page-chat" class="page active">
    <div class="page-topbar">
      <span class="page-title">💬 Chat con PAKO</span>
      <div class="status-pill">
        <div class="dot" id="s-dot"></div>
        <span id="s-txt">Online</span>
      </div>
      <div class="topbar-right">
        <button class="tbtn" onclick="exportChat()">📥 Exportar</button>
        <button class="tbtn" onclick="clearChat()">🗑️ Limpiar</button>
      </div>
    </div>
    <div style="display:flex;flex:1;overflow:hidden">
      <!-- sidebar chat -->
      <div id="chat-sidebar">
        <div id="chs-header">Panel de control</div>
        <div id="chs-body">
          <div class="s-label">Conocimiento</div>
          <div class="stats-grid">
            <div class="sc"><div class="n" id="st-total">—</div><div class="l">Total</div></div>
            <div class="sc"><div class="n" id="st-pend">—</div><div class="l">Pendientes</div></div>
            <div class="sc"><div class="n" id="st-web">—</div><div class="l">Web</div></div>
            <div class="sc"><div class="n" id="st-gh">—</div><div class="l">GitHub</div></div>
          </div>
          <div class="s-label">Autoaprendizaje</div>
          <div class="tog-row" onclick="tog('autoaprendizaje_web','tw')"><span class="tog-lbl">🌐 Web</span><div class="sw" id="tw"></div></div>
          <div class="tog-row" onclick="tog('autoaprendizaje_github','tg')"><span class="tog-lbl">🐙 GitHub</span><div class="sw" id="tg"></div></div>
          <div class="tog-row" onclick="tog('validacion_manual','tv')"><span class="tog-lbl">✅ Validación manual</span><div class="sw on" id="tv"></div></div>
          <div class="tog-row" onclick="tog('busqueda_web_auto','tb')"><span class="tog-lbl">🔍 Auto-buscar web</span><div class="sw on" id="tb"></div></div>
          <div class="s-label">GitHub</div>
          <div class="gh-box">
            <input type="password" id="gh-tok" placeholder="ghp_xxxx..." autocomplete="off"/>
            <button class="btn-p" onclick="connectGH()">Conectar GitHub</button>
            <div class="gh-st" id="gh-st">Sin conectar</div>
          </div>
          <div class="s-label">Acciones rápidas</div>
          <div style="display:flex;flex-direction:column;gap:4px">
            <button class="nav-toggle-btn" style="justify-content:flex-start" onclick="verPendientes()">⏳ Ver pendientes</button>
            <button class="nav-toggle-btn" style="justify-content:flex-start" onclick="sendChip('estadísticas')">📊 Estadísticas</button>
            <button class="nav-toggle-btn" style="justify-content:flex-start" onclick="goPage('auto')">⚡ Automatizaciones</button>
          </div>
          <div class="s-label">Actividad reciente</div>
          <div id="act-list"></div>
        </div>
      </div>
      <!-- main chat -->
      <div id="chat-main">
        <div id="chat-messages"></div>
        <div id="chips">
          <span class="chip" onclick="sendChip('¿Qué puedes hacer?')">❓ Ayuda</span>
          <span class="chip" onclick="sendChip('busca qué es Docker')">🐳 Docker</span>
          <span class="chip" onclick="sendChip('busca qué es Rust')">🦀 Rust</span>
          <span class="chip" onclick="sendChip('¿cuánto es 1337 × 42?')">🧮 Calc</span>
          <span class="chip" onclick="sendChip('qué es SOLID')">🏗️ SOLID</span>
          <span class="chip" onclick="goPage('auto')">⚡ Automatizaciones</span>
          <span class="chip" onclick="sendChip('cuéntame un chiste')">😄 Chiste</span>
          <span class="chip" onclick="sendChip('dato curioso')">🔍 Curiosidad</span>
        </div>
        <div id="inp-area">
          <textarea id="msg-inp" rows="1" placeholder="Escribe a PAKO... · Enter para enviar · Shift+Enter nueva línea"></textarea>
          <button id="send-btn" onclick="sendMsg()">➤</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ── PÁGINA AUTOMATIZACIONES ── -->
  <div id="page-auto" class="page">
    <div class="page-topbar">
      <span class="page-title">⚡ Automatizaciones</span>
      <div class="status-pill"><div class="dot" id="a-dot"></div><span id="a-txt">Listo</span></div>
      <div class="topbar-right">
        <button class="tbtn" onclick="autoGenWF()">✨ Generar con IA</button>
        <button class="tbtn" onclick="runSelectedWF()" id="btn-run-wf" disabled>▶ Ejecutar</button>
      </div>
    </div>
    <div class="auto-layout" style="flex:1;overflow:hidden">
      <!-- Lista workflows -->
      <div id="wf-list-panel">
        <div id="wf-list-header">
          <span class="ttl">Workflows</span>
          <button class="btn-new-wf" onclick="newWF()">+ Nuevo</button>
        </div>
        <div id="wf-list">
          <div id="wf-empty">No hay workflows aún.<br>Crea uno con el botón "+" o pide a PAKO que genere uno.</div>
        </div>
      </div>
      <!-- Canvas editor -->
      <div id="wf-editor">
        <div id="wf-editor-topbar">
          <div id="wf-editor-name" style="color:var(--t4)">Selecciona o crea un workflow</div>
          <div style="margin-left:auto;display:flex;gap:6px">
            <button class="editor-btn" onclick="addNodeToCanvas()" id="btn-add-node" disabled>+ Nodo</button>
            <button class="editor-btn success" onclick="saveWF()" id="btn-save-wf" disabled>💾 Guardar</button>
          </div>
        </div>
        <div id="wf-editor-canvas">
          <div id="canvas-nodes"></div>
          <svg id="canvas-svg" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:visible">
            <defs><marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="var(--bd2)"/></marker></defs>
          </svg>
          <div id="canvas-placeholder" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--t4);font-size:.85rem;pointer-events:none">
            <div style="font-size:3rem;margin-bottom:12px">⚡</div>
            <div style="font-weight:600;margin-bottom:6px">Selecciona un workflow para editarlo</div>
            <div style="font-size:.75rem">o crea uno nuevo con el botón "+"</div>
          </div>
        </div>
        <div id="exec-log" style="display:none;max-height:180px;overflow-y:auto;border-top:1px solid var(--bd)"></div>
      </div>
      <!-- Panel derecho -->
      <div id="wf-right-panel">
        <div id="wf-right-tabs">
          <div class="wr-tab active" onclick="wrTab('palette')">🧩 Nodos</div>
          <div class="wr-tab" onclick="wrTab('ia')">🤖 IA</div>
          <div class="wr-tab" onclick="wrTab('log')">📋 Log</div>
        </div>
        <div id="wf-right-body">
          <div id="tab-palette"></div>
          <div id="tab-ia" style="display:none;height:calc(100% - 10px)">
            <div id="ia-chat-box">
              <div id="ia-msgs"></div>
              <div id="ia-inp-area">
                <textarea id="ia-inp" placeholder="Pide a PAKO que diseñe un flujo..." rows="1"></textarea>
                <button id="ia-send" onclick="sendIA()">➤</button>
              </div>
            </div>
          </div>
          <div id="tab-log" style="display:none">
            <div id="exec-log-side" style="font-size:.68rem;font-family:'IBM Plex Mono',monospace;color:var(--t2)">Sin ejecuciones aún.</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── PÁGINA CONOCIMIENTO ── -->
  <div id="page-conocimiento" class="page">
    <div class="page-topbar">
      <span class="page-title">🧠 Base de Conocimiento</span>
      <div class="topbar-right">
        <button class="tbtn" onclick="loadConocimiento()">↻ Refrescar</button>
      </div>
    </div>
    <div class="kpage">
      <div class="kpage-header">
        <h2>Conocimiento aprendido</h2>
        <input class="kpage-search" id="k-search" placeholder="Buscar..." oninput="filtrarK()">
        <span id="k-count" style="font-size:.72rem;color:var(--t3);font-family:'IBM Plex Mono',monospace"></span>
      </div>
      <table class="k-table">
        <thead><tr><th>Clave</th><th>Valor</th><th>Fuente</th><th>Conf.</th><th></th></tr></thead>
        <tbody id="k-body"></tbody>
      </table>
      <div id="k-empty" style="display:none;text-align:center;color:var(--t4);font-size:.82rem;padding:30px">Sin entradas.</div>
    </div>
  </div>

  <!-- ── PÁGINA ACTIVIDAD ── -->
  <div id="page-actividad" class="page">
    <div class="page-topbar">
      <span class="page-title">📋 Actividad del sistema</span>
      <div class="topbar-right"><button class="tbtn" onclick="loadActividad()">↻ Refrescar</button></div>
    </div>
    <div class="generic-page">
      <div class="gp-title">Log de actividad</div>
      <div class="gp-sub">Todo lo que PAKO ha hecho: búsquedas, aprendizaje, errores, sistema.</div>
      <div id="log-list"></div>
    </div>
  </div>

  <!-- ── PÁGINA AJUSTES ── -->
  <div id="page-ajustes" class="page">
    <div class="page-topbar"><span class="page-title">⚙️ Ajustes</span></div>
    <div class="generic-page">
      <div class="gp-title">Configuración de PAKO</div>
      <div class="gp-sub">Personaliza tu asistente.</div>
      <div class="card">
        <div class="card-title">Perfil</div>
        <div class="cfg-row">
          <div><div class="cfg-lbl">Tu nombre</div><div class="cfg-sub">PAKO te llamará así</div></div>
          <input class="cfg-inp" id="cfg-nombre" placeholder="Usuario" onchange="saveCfg('nombre_usuario',this.value)">
        </div>
      </div>
      <div class="card">
        <div class="card-title">Comportamiento</div>
        <div class="cfg-row">
          <div><div class="cfg-lbl">Búsqueda web automática</div><div class="cfg-sub">Busca en internet si no sabe</div></div>
          <div class="sw on" id="cfg-bwa" onclick="togCfg('busqueda_web_auto','cfg-bwa')"></div>
        </div>
        <div class="cfg-row">
          <div><div class="cfg-lbl">Validación manual</div><div class="cfg-sub">Revisar antes de guardar conocimiento web</div></div>
          <div class="sw on" id="cfg-vm" onclick="togCfg('validacion_manual','cfg-vm')"></div>
        </div>
        <div class="cfg-row">
          <div><div class="cfg-lbl">Autoaprendizaje web</div><div class="cfg-sub">Guardar automáticamente lo aprendido</div></div>
          <div class="sw" id="cfg-aw" onclick="togCfg('autoaprendizaje_web','cfg-aw')"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">GitHub</div>
        <div class="cfg-row">
          <div><div class="cfg-lbl">Token GitHub</div><div class="cfg-sub">Para leer tus repositorios</div></div>
          <input class="cfg-inp" id="cfg-gh" type="password" placeholder="ghp_xxxx..." onchange="connectGH2(this.value)">
        </div>
      </div>
      <div class="card" id="pendientes-card">
        <div class="card-title">Conocimiento pendiente <span id="pend-count" style="color:var(--am)"></span></div>
        <div id="pendientes-list"></div>
      </div>
    </div>
  </div>

</div><!-- #content -->
</div><!-- #app -->

<div id="toast"></div>
<div id="modal-overlay">
  <div id="modal">
    <div class="modal-title" id="modal-title">Crear workflow</div>
    <input class="modal-inp" id="modal-inp1" placeholder="Nombre del workflow">
    <textarea class="modal-inp modal-ta" id="modal-inp2" placeholder="Descripción (opcional)"></textarea>
    <div class="modal-btns">
      <button class="modal-btn" onclick="closeModal()">Cancelar</button>
      <button class="modal-btn ok" id="modal-ok" onclick="modalOk()">Crear</button>
    </div>
  </div>
</div>

<script>
// ══════════════════════════════════════════════════════════════
// ESTADO GLOBAL
// ══════════════════════════════════════════════════════════════
let esperando  = false;
let navOpen    = true;
let toggStates = { autoaprendizaje_web:false, autoaprendizaje_github:false, validacion_manual:true, busqueda_web_auto:true };
let selectedWF = null;
let wfData     = {};       // id → workflow
let canvasNodes= [];       // nodos en el canvas actual
let canvasConns= [];       // conexiones en el canvas actual
let modalCb    = null;
let wrActiveTab= 'palette';
let allConocimiento = [];  // cache para filtrado

// ══════════════════════════════════════════════════════════════
// NAVEGACIÓN ENTRE PÁGINAS
// ══════════════════════════════════════════════════════════════
function goPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  document.querySelector(`[data-page="${id}"]`)?.classList.add('active');
  if (id === 'auto')         loadWorkflows();
  if (id === 'conocimiento') loadConocimiento();
  if (id === 'actividad')    loadActividad();
  if (id === 'ajustes')      loadAjustes();
}

function toggleNav() {
  navOpen = !navOpen;
  document.getElementById('nav').classList.toggle('mini', !navOpen);
  document.getElementById('nav-toggle-ico').textContent = navOpen ? '◀' : '▶';
  document.getElementById('nav-toggle-lbl').textContent = navOpen ? 'Contraer' : '';
}

// ══════════════════════════════════════════════════════════════
// FORMATEO MARKDOWN
// ══════════════════════════════════════════════════════════════
function fmt(t) {
  let s = t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_,l,c) => `<pre><code>${c.trim()}</code></pre>`);
  s = s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s = s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g,'<em>$1</em>');
  s = s.replace(/_(.+?)_/g,'<em>$1</em>');
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/(^|[\s])(https?:\/\/[^\s<>"]+)/g,'$1<a href="$2" target="_blank">$2</a>');
  s = s.replace(/🌐/g,'<span class="bw">🌐 WEB</span>');
  s = s.replace(/🐙/g,'<span class="bg">🐙 GH</span>');
  s = s.replace(/📚/g,'<span class="bm">📚 MEM</span>');
  s = s.replace(/\n/g,'<br>');
  return s;
}
const esc = t => t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// ══════════════════════════════════════════════════════════════
// CHAT
// ══════════════════════════════════════════════════════════════
const chatEl = () => document.getElementById('chat-messages');
const nowT   = () => new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});

function addMsg(txt, rol, fuente='') {
  const w = document.createElement('div'); w.className='msg '+rol;
  const av= document.createElement('div'); av.className='av'; av.textContent=rol==='user'?'TÚ':'AI';
  const b = document.createElement('div'); b.className='bubble'; b.innerHTML=fmt(txt);
  const m = document.createElement('div'); m.className='msg-meta'; m.textContent=nowT()+(fuente?` · ${fuente}`:'');
  w.appendChild(av); w.appendChild(b); w.appendChild(m);
  chatEl().appendChild(w); chatEl().scrollTop=chatEl().scrollHeight; return w;
}
function showTyping(msg='') {
  const w=document.createElement('div'); w.className='msg pako'; w.id='typing-el';
  const av=document.createElement('div'); av.className='av'; av.textContent='AI';
  const b=document.createElement('div'); b.className='bubble';
  b.innerHTML=`<div class="typing-b"><div class="dots"><span></span><span></span><span></span></div>${msg?`<span class="ty-txt">${msg}</span>`:''}</div>`;
  w.appendChild(av); w.appendChild(b); chatEl().appendChild(w); chatEl().scrollTop=chatEl().scrollHeight;
}
function hideTyping(){ const e=document.getElementById('typing-el'); if(e)e.remove(); }

async function sendChip(t){ if(!esperando){document.getElementById('msg-inp').value=t; sendMsg();} }

async function sendMsg() {
  const inp = document.getElementById('msg-inp');
  const txt = inp.value.trim();
  if (!txt || esperando) return;
  if (txt.length > 2000) { toast('Mensaje muy largo (máx 2000 chars)'); return; }
  esperando=true; document.getElementById('send-btn').disabled=true;
  inp.value=''; autoR();
  addMsg(txt,'user');
  const norm=txt.toLowerCase();
  const isWeb=/^(busca\s|buscar\s|qué\s+es\s|que\s+es\s|cómo\s+funciona\s|como\s+funciona\s|explica\s)/i.test(norm);
  const isGH =/repo|github|aprende\s+de\s+mis/.test(norm);
  document.getElementById('s-dot').className='dot busy';
  document.getElementById('s-txt').textContent=isWeb?'Buscando...':isGH?'GitHub...':'Pensando...';
  showTyping(isWeb?'🌐 Buscando en internet...':isGH?'🐙 Leyendo GitHub...':'');
  try {
    const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mensaje:txt}),signal:AbortSignal.timeout(30000)});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d = await r.json();
    hideTyping();
    addMsg(d.respuesta||'…','pako', d.fuente||'');
    refreshStats(); loadActividad_mini();
  } catch(e) {
    hideTyping();
    addMsg(e.name==='TimeoutError'?'⏱️ La respuesta tardó demasiado. Inténtalo de nuevo.':'❌ Error de conexión con PAKO.','pako');
  } finally {
    esperando=false; document.getElementById('send-btn').disabled=false;
    document.getElementById('s-dot').className='dot';
    document.getElementById('s-txt').textContent='Online';
    inp.focus();
  }
}

const inp=document.getElementById('msg-inp');
inp.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}});
function autoR(){inp.style.height='auto';inp.style.height=Math.min(inp.scrollHeight,130)+'px';}
inp.addEventListener('input',autoR);

function clearChat(){ chatEl().innerHTML=''; toast('Chat limpiado'); bienvenida(); }
function exportChat(){
  const txt=[...chatEl().querySelectorAll('.msg')].map(m=>{
    const r=m.classList.contains('user')?'TÚ':'PAKO';
    return `[${m.querySelector('.msg-meta')?.textContent||''}] ${r}: ${m.querySelector('.bubble')?.innerText||''}`;
  }).join('\n\n');
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([txt],{type:'text/plain'}));
  a.download=`pako_chat_${Date.now()}.txt`; a.click(); toast('💾 Chat exportado');
}

// ══════════════════════════════════════════════════════════════
// STATS / ACTIVIDAD
// ══════════════════════════════════════════════════════════════
async function refreshStats(){
  try{
    const d=await(await fetch('/api/stats')).json();
    document.getElementById('st-total').textContent=d.total??0;
    document.getElementById('st-pend').textContent=d.pendientes??0;
    document.getElementById('st-web').textContent=d.por_fuente?.web??0;
    document.getElementById('st-gh').textContent=d.por_fuente?.github??0;
    document.getElementById('nb-conocimiento').textContent=d.total??0;
    if(d.github_conectado) document.getElementById('gh-st').textContent='✅ @'+(d.github_usuario||'?');
    // Sync toggles
    if(d.config){
      for(const[k,id] of [['autoaprendizaje_web','tw'],['autoaprendizaje_github','tg'],['validacion_manual','tv'],['busqueda_web_auto','tb']]){
        if(d.config[k]!==undefined){toggStates[k]=d.config[k];const el=document.getElementById(id);if(el)el.className='sw'+(d.config[k]?' on':'');}
      }
    }
  }catch(e){}
}

async function loadActividad_mini(){
  try{
    const items=await(await fetch('/api/actividad')).json();
    const el=document.getElementById('act-list');
    if(!items?.length){el.innerHTML='<div style="color:var(--t4);font-size:.68rem;padding:4px 0">Sin actividad aún</div>';return;}
    el.innerHTML=items.slice(0,8).map(a=>{
      const ts=new Date(a.timestamp*1000).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});
      return `<div class="act-item"><div style="display:flex;align-items:center;gap:5px"><span class="act-tipo t-${a.tipo}">${a.tipo}</span><span class="act-msg">${esc(a.mensaje.slice(0,50))}</span></div><div class="act-ts">${ts}</div></div>`;
    }).join('');
  }catch(e){}
}

// ══════════════════════════════════════════════════════════════
// TOGGLES
// ══════════════════════════════════════════════════════════════
async function tog(key,id){
  toggStates[key]=!toggStates[key];
  document.getElementById(id).className='sw'+(toggStates[key]?' on':'');
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,value:toggStates[key]})});
  toast(toggStates[key]?`✅ ${key.replace(/_/g,' ')} ON`:`⏸️ ${key.replace(/_/g,' ')} OFF`);
}
async function togCfg(key,id){
  const el=document.getElementById(id);
  const val=!el.classList.contains('on');
  el.className='sw'+(val?' on':'');
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,value:val})});
  toast(val?'Activado':'Desactivado');
}
async function saveCfg(key,val){
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,value:val})});
  toast('Guardado');
}

// ══════════════════════════════════════════════════════════════
// GITHUB
// ══════════════════════════════════════════════════════════════
async function connectGH(){
  const tok=document.getElementById('gh-tok').value.trim();
  if(!tok){toast('Introduce el token');return;}
  document.getElementById('gh-st').textContent='Conectando...';
  try{
    const d=await(await fetch('/api/github/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:tok})})).json();
    document.getElementById('gh-st').textContent=d.ok?`✅ @${d.usuario}`:`❌ ${d.mensaje}`;
    if(d.ok){document.getElementById('gh-tok').value='';addMsg(`🐙 GitHub conectado como **@${d.usuario}**. Di **"aprende de mis repos"** para empezar.`,'pako');}
  }catch(e){document.getElementById('gh-st').textContent='❌ Error';}
}
async function connectGH2(token){
  if(!token.trim())return;
  try{
    const d=await(await fetch('/api/github/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token.trim()})})).json();
    toast(d.ok?`🐙 Conectado @${d.usuario}`:`❌ ${d.mensaje}`);
  }catch(e){}
}

// ══════════════════════════════════════════════════════════════
// PENDIENTES
// ══════════════════════════════════════════════════════════════
async function verPendientes(){
  const items=await(await fetch('/api/pendientes')).json();
  if(!items?.length){addMsg('✅ No hay conocimiento pendiente de validar.','pako');return;}
  const w=document.createElement('div'); w.className='msg pako';
  const av=document.createElement('div'); av.className='av'; av.textContent='AI';
  const b=document.createElement('div'); b.className='bubble';
  b.innerHTML=`<strong>⏳ ${items.length} pendientes:</strong><br><br>`+
    items.slice(0,8).map(i=>`<div class="pi"><div class="pi-body"><div class="pi-k">${esc(i.clave.slice(0,40))}</div><div class="pi-v">${esc(i.valor.slice(0,70))}</div></div><button class="pi-ok" onclick="aprobar('${i.hash}',this)">✓</button><button class="pi-nk" onclick="rechazar('${i.hash}',this)">✕</button></div>`).join('');
  w.appendChild(av); w.appendChild(b); chatEl().appendChild(w); chatEl().scrollTop=chatEl().scrollHeight;
}
async function aprobar(h,btn){
  await fetch('/api/pendientes/aprobar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hash:h})});
  btn.closest('.pi').style.opacity='.4'; btn.closest('.pi').style.pointerEvents='none'; toast('✅ Aprobado'); refreshStats();
}
async function rechazar(h,btn){
  await fetch('/api/pendientes/rechazar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hash:h})});
  btn.closest('.pi').style.opacity='.4'; btn.closest('.pi').style.pointerEvents='none'; toast('🗑️ Rechazado'); refreshStats();
}

// ══════════════════════════════════════════════════════════════
// AUTOMATIZACIONES
// ══════════════════════════════════════════════════════════════

// -- Lista de workflows --
async function loadWorkflows(){
  try{
    const wfs=await(await fetch('/api/auto/workflows')).json();
    document.getElementById('nb-auto').textContent=wfs.length;
    const el=document.getElementById('wf-list');
    if(!wfs.length){el.innerHTML='<div id="wf-empty">No hay workflows.<br>Crea uno con "+" o usa "✨ Generar con IA".</div>';return;}
    el.innerHTML=wfs.map(wf=>`
      <div class="wf-item${selectedWF===wf.id?' selected':''}" onclick="selectWF('${wf.id}')">
        <div class="wf-item-header">
          <span class="wf-item-name">${esc(wf.nombre)}</span>
          <div class="wf-toggle${wf.activo?' on':''}" onclick="event.stopPropagation();toggleWF('${wf.id}',this)"></div>
        </div>
        <div class="wf-item-meta">
          <span>⚡${wf.nodos} nodos</span>
          <span>▶${wf.ejecuciones}</span>
          <span>${wf.ultima_ejec?new Date(wf.ultima_ejec*1000).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'}):'-'}</span>
        </div>
        <div class="wf-item-actions">
          <button class="wf-act-btn run" onclick="event.stopPropagation();quickRunWF('${wf.id}')">▶ Run</button>
          <button class="wf-act-btn" onclick="event.stopPropagation();dupWF('${wf.id}')">⧉ Dup</button>
          <button class="wf-act-btn del" onclick="event.stopPropagation();delWF('${wf.id}')">🗑</button>
        </div>
      </div>`).join('');
    wfs.forEach(w=>wfData[w.id]=w);
  }catch(e){}
}

function newWF(){
  document.getElementById('modal-title').textContent='Nuevo Workflow';
  document.getElementById('modal-inp1').value='';
  document.getElementById('modal-inp2').value='';
  document.getElementById('modal-ok').textContent='Crear';
  modalCb=async()=>{
    const n=document.getElementById('modal-inp1').value.trim();
    const d=document.getElementById('modal-inp2').value.trim();
    if(!n){toast('Necesito un nombre');return;}
    const r=await(await fetch('/api/auto/workflows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre:n,descripcion:d})})).json();
    if(r.id){closeModal();loadWorkflows();selectWF(r.id);toast('✅ Workflow creado');}
  };
  document.getElementById('modal-overlay').classList.add('show');
  setTimeout(()=>document.getElementById('modal-inp1').focus(),50);
}

async function selectWF(id){
  selectedWF=id;
  document.getElementById('btn-run-wf').disabled=false;
  document.getElementById('btn-add-node').disabled=false;
  document.getElementById('btn-save-wf').disabled=false;
  document.getElementById('canvas-placeholder').style.display='none';
  // Cargar datos del workflow
  try{
    const wf=await(await fetch('/api/auto/workflows/'+id)).json();
    document.getElementById('wf-editor-name').textContent=wf.nombre;
    document.getElementById('wf-editor-name').style.color='var(--t1)';
    canvasNodes=wf.nodos||[];
    canvasConns=wf.conexiones||[];
    renderCanvas();
    // Resaltar en lista
    document.querySelectorAll('.wf-item').forEach(e=>e.classList.remove('selected'));
    document.querySelectorAll('.wf-item').forEach(e=>{if(e.onclick.toString().includes(id))e.classList.add('selected');});
  }catch(e){}
}

async function toggleWF(id,el){
  const r=await(await fetch(`/api/auto/workflows/${id}/toggle`,{method:'POST'})).json();
  if(r.activo!==undefined){el.className='wf-toggle'+(r.activo?' on':'');toast(r.activo?'✅ Workflow activado':'⏸️ Workflow desactivado');}
}

async function delWF(id){
  if(!confirm('¿Eliminar este workflow?'))return;
  await fetch(`/api/auto/workflows/${id}`,{method:'DELETE'});
  if(selectedWF===id){selectedWF=null;document.getElementById('canvas-nodes').innerHTML='';document.getElementById('canvas-placeholder').style.display='flex';document.getElementById('btn-run-wf').disabled=true;}
  loadWorkflows(); toast('🗑️ Eliminado');
}
async function dupWF(id){
  const r=await(await fetch(`/api/auto/workflows/${id}/duplicar`,{method:'POST'})).json();
  if(r.id){loadWorkflows();toast('⧉ Workflow duplicado');}
}

async function quickRunWF(id){
  toast('▶ Ejecutando...');
  try{
    const r=await(await fetch(`/api/auto/workflows/${id}/ejecutar`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})})).json();
    toast(r.estado==='ok'?`✅ OK (${r.log?.length||0} pasos)`:`❌ Error: ${r.error||'?'}`);
    if(selectedWF===id) showExecLog(r);
  }catch(e){toast('❌ Error ejecutando');}
}
async function runSelectedWF(){
  if(!selectedWF)return;
  quickRunWF(selectedWF);
}

function showExecLog(exec){
  const el=document.getElementById('exec-log');
  el.style.display='block';
  el.innerHTML=`<div style="padding:6px 10px;font-weight:600;font-size:.72rem;color:${exec.estado==='ok'?'var(--gn)':'var(--rd)'}">Ejecución ${exec.estado.toUpperCase()} · ${exec.log?.length||0} pasos</div>`+
    (exec.log||[]).map(s=>`<div class="exec-step ${s.estado}"><div class="exec-step-name">${s.nodo_label} <span style="color:var(--t4);font-weight:400">[${s.nodo_tipo}]</span></div><div class="exec-step-msg">${esc(s.mensaje||'')}</div></div>`).join('');
  const side=document.getElementById('exec-log-side');
  side.innerHTML=el.innerHTML;
}

// -- Canvas --
function renderCanvas(){
  const cn=document.getElementById('canvas-nodes');
  cn.innerHTML='';
  const svg=document.getElementById('canvas-svg');
  while(svg.children.length>1) svg.removeChild(svg.lastChild);
  // nodos
  canvasNodes.forEach(n=>cn.appendChild(createNodeEl(n)));
  // conexiones
  canvasConns.forEach(c=>drawConn(c));
}

function createNodeEl(nodo){
  const el=document.createElement('div');
  el.className='canvas-node';
  el.id='cn-'+nodo.id;
  el.style.left=nodo.posicion_x+'px';
  el.style.top=nodo.posicion_y+'px';
  // Buscar info
  const cats={trigger:'var(--am)',accion:'var(--p)',logica:'var(--gn)',ia:'var(--pk)',transform:'var(--cy)'};
  const tinfo={icono:'📦',label:nodo.label,color:'var(--bd2)'};
  for(const[tipo,info] of Object.entries(NODOS_INFO||{})){if(tipo===nodo.tipo){tinfo.icono=info.icono;tinfo.color=info.color;break;}}

  el.innerHTML=`
    <div class="node-header" style="border-bottom-color:${tinfo.color}40">
      <span class="node-ico">${tinfo.icono}</span>
      <span class="node-lbl">${esc(nodo.label)}</span>
      <span class="node-del" onclick="removeNode('${nodo.id}')">✕</span>
    </div>
    <div class="node-body">${nodo.tipo}</div>
    <div class="node-footer"><div class="node-port-out" data-nid="${nodo.id}" onclick="startConn('${nodo.id}')"></div></div>`;

  makeDraggable(el, nodo);
  return el;
}

let connStart=null;
function startConn(nid){
  if(!connStart){connStart=nid;toast('Clic en el puerto de destino para conectar');}
  else{
    if(connStart!==nid){
      const c={id:Math.random().toString(36).slice(2,8),desde_nodo:connStart,hasta_nodo:nid,etiqueta:''};
      canvasConns.push(c); drawConn(c);
    }
    connStart=null;
  }
}

function drawConn(c){
  const fromEl=document.getElementById('cn-'+c.desde_nodo);
  const toEl=document.getElementById('cn-'+c.hasta_nodo);
  if(!fromEl||!toEl)return;
  const fr=fromEl.getBoundingClientRect();
  const tr=toEl.getBoundingClientRect();
  const cvr=document.getElementById('wf-editor-canvas').getBoundingClientRect();
  const x1=fr.left+fr.width/2-cvr.left;
  const y1=fr.bottom-cvr.top;
  const x2=tr.left+tr.width/2-cvr.left;
  const y2=tr.top-cvr.top;
  const svg=document.getElementById('canvas-svg');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  const cp=Math.abs(y2-y1)*0.5;
  path.setAttribute('d',`M${x1},${y1} C${x1},${y1+cp} ${x2},${y2-cp} ${x2},${y2}`);
  path.setAttribute('stroke','var(--bd2)');
  path.setAttribute('stroke-width','2');
  path.setAttribute('fill','none');
  path.setAttribute('marker-end','url(#arrowhead)');
  path.setAttribute('data-conn',c.id);
  svg.appendChild(path);
}

function removeNode(nid){
  canvasNodes=canvasNodes.filter(n=>n.id!==nid);
  canvasConns=canvasConns.filter(c=>c.desde_nodo!==nid&&c.hasta_nodo!==nid);
  renderCanvas(); toast('Nodo eliminado');
}

function makeDraggable(el, nodo){
  let dx=0,dy=0,startX=0,startY=0;
  el.addEventListener('mousedown',e=>{
    if(e.target.classList.contains('node-del')||e.target.classList.contains('node-port-out'))return;
    startX=e.clientX-nodo.posicion_x; startY=e.clientY-nodo.posicion_y;
    const mv=ev=>{nodo.posicion_x=ev.clientX-startX;nodo.posicion_y=ev.clientY-startY;el.style.left=nodo.posicion_x+'px';el.style.top=nodo.posicion_y+'px';
      document.querySelectorAll('[data-conn]').forEach(p=>p.remove()); canvasConns.forEach(c=>drawConn(c));};
    const up=()=>{document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);};
    document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
    e.preventDefault();
  });
}

function addNodeToCanvas(){
  if(!selectedWF){toast('Selecciona un workflow primero');return;}
  // Mostrar paleta en panel derecho
  wrTab('palette');
  toast('Arrastra o haz clic en un nodo de la paleta para añadirlo');
}

async function saveWF(){
  if(!selectedWF)return;
  const r=await fetch(`/api/auto/workflows/${selectedWF}`,{
    method:'PATCH',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({nodos:canvasNodes,conexiones:canvasConns})
  });
  if((await r.json()).ok){toast('💾 Workflow guardado');loadWorkflows();}
}

// Paleta de nodos
const NODOS_INFO={};
async function buildPalette(){
  try{
    const tipos=await(await fetch('/api/auto/tipos-nodo')).json();
    Object.assign(NODOS_INFO,tipos);
    const cats={trigger:'Disparadores',accion:'Acciones',logica:'Lógica',ia:'IA (PAKO)',transform:'Transformación'};
    let html='';
    for(const[cat,label] of Object.entries(cats)){
      const items=Object.entries(tipos).filter(([_,v])=>v.categoria===cat);
      if(!items.length)continue;
      html+=`<div class="node-category">${label}</div>`;
      items.forEach(([tipo,info])=>{
        html+=`<div class="palette-node" onclick="addNodeFromPalette('${tipo}','${info.label}')" title="${info.label}"><span class="pn-ico">${info.icono}</span><span class="pn-lbl">${info.label}</span></div>`;
      });
    }
    document.getElementById('tab-palette').innerHTML=html;
  }catch(e){}
}

function addNodeFromPalette(tipo,label){
  if(!selectedWF){toast('Selecciona un workflow primero');return;}
  const n={id:Math.random().toString(36).slice(2,8),tipo,label,config:{},posicion_x:80+canvasNodes.length*200,posicion_y:180};
  canvasNodes.push(n);
  document.getElementById('canvas-nodes').appendChild(createNodeEl(n));
  toast(`✅ Nodo "${label}" añadido`);
}

// Tabs panel derecho
function wrTab(tab){
  wrActiveTab=tab;
  document.querySelectorAll('.wr-tab').forEach((t,i)=>{
    const tabs=['palette','ia','log'];
    t.classList.toggle('active',tabs[i]===tab);
  });
  document.getElementById('tab-palette').style.display=tab==='palette'?'block':'none';
  document.getElementById('tab-ia').style.display=tab==='ia'?'block':'none';
  document.getElementById('tab-log').style.display=tab==='log'?'block':'none';
}

// IA assistant en automatizaciones
const iaMsgs=()=>document.getElementById('ia-msgs');
function addIAMsg(txt,rol){
  const d=document.createElement('div'); d.className='ia-msg '+rol;
  d.innerHTML=rol==='pako'?fmt(txt):esc(txt);
  iaMsgs().appendChild(d); iaMsgs().scrollTop=iaMsgs().scrollHeight;
}

async function sendIA(){
  const inp=document.getElementById('ia-inp');
  const txt=inp.value.trim(); if(!txt)return;
  inp.value=''; addIAMsg(txt,'user');
  // Primero intentar generar workflow desde descripción
  const triggers=['crea','diseña','genera','quiero','hacer','automatiza','workflow','flujo'];
  const esSolicitudWF=triggers.some(t=>txt.toLowerCase().includes(t));
  if(esSolicitudWF){
    try{
      const r=await(await fetch('/api/auto/generar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({descripcion:txt})})).json();
      if(r.nodos?.length){
        let resp=`✅ He diseñado un flujo con **${r.nodos.length} nodos**:\n\n`;
        r.nodos.forEach((n,i)=>{ resp+=`${i+1}. **${n.label}** (${n.tipo})\n`; });
        resp+='\n¿Quieres que lo cree como workflow? Di **"sí, créalo"**';
        addIAMsg(resp,'pako');
        window._pendingWF=r;
        return;
      }
    }catch(e){}
  }
  // Confirmar creación del workflow pendiente
  if(window._pendingWF&&/^(si|sí|ok|crea|dale|adelante)/i.test(txt)){
    if(!selectedWF){
      toast('Crea un workflow primero con el botón "+"'); return;
    }
    canvasNodes=window._pendingWF.nodos;
    canvasConns=window._pendingWF.conexiones;
    renderCanvas();
    addIAMsg('✅ ¡Nodos añadidos al canvas! Recuerda guardar con 💾','pako');
    window._pendingWF=null;
    return;
  }
  // Chat general con PAKO
  try{
    const r=await(await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mensaje:txt})})).json();
    addIAMsg(r.respuesta||'…','pako');
  }catch(e){addIAMsg('❌ Error contactando con PAKO','pako');}
}
document.getElementById('ia-inp').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendIA();}});

async function autoGenWF(){
  const desc=prompt('Describe qué quieres automatizar:');
  if(!desc)return;
  try{
    const r=await(await fetch('/api/auto/generar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({descripcion:desc})})).json();
    if(!r.nodos?.length){toast('PAKO no pudo generar un flujo. Sé más específico.');return;}
    // Crear workflow con esos nodos
    const wf=await(await fetch('/api/auto/workflows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre:'Auto: '+desc.slice(0,30),descripcion:desc})})).json();
    if(wf.id){
      await fetch(`/api/auto/workflows/${wf.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({nodos:r.nodos,conexiones:r.conexiones})});
      loadWorkflows(); selectWF(wf.id); toast(`✨ Workflow generado con ${r.nodos.length} nodos`);
    }
  }catch(e){toast('❌ Error generando workflow');}
}

// ══════════════════════════════════════════════════════════════
// CONOCIMIENTO
// ══════════════════════════════════════════════════════════════
async function loadConocimiento(){
  try{
    const items=await(await fetch('/api/conocimiento/recientes?n=200')).json();
    allConocimiento=items;
    renderK(items);
  }catch(e){}
}
function renderK(items){
  const body=document.getElementById('k-body');
  document.getElementById('k-count').textContent=items.length+' entradas';
  document.getElementById('k-empty').style.display=items.length?'none':'block';
  const fuenteClass={manual:'f-manual',web:'f-web',github:'f-github',base:'f-base',archivo:'f-archivo'};
  body.innerHTML=items.map(i=>`
    <tr><td class="k-clave">${esc(i.clave.slice(0,50))}</td>
    <td class="k-valor">${esc(i.valor.slice(0,100))}</td>
    <td><span class="k-fuente ${fuenteClass[i.fuente]||''}">${i.fuente}</span></td>
    <td style="font-family:'IBM Plex Mono',monospace;font-size:.68rem;color:var(--t3)">${Math.round((i.confianza||0)*100)}%</td>
    <td class="k-del" onclick="delK('${i.clave}')">🗑</td></tr>`).join('');
}
function filtrarK(){
  const q=document.getElementById('k-search').value.toLowerCase();
  renderK(q?allConocimiento.filter(i=>i.clave.toLowerCase().includes(q)||i.valor.toLowerCase().includes(q)):allConocimiento);
}
async function delK(clave){
  if(!confirm('¿Eliminar este conocimiento?'))return;
  const h=await(await fetch('/api/conocimiento/hash?clave='+encodeURIComponent(clave))).json();
  if(h.hash){await fetch('/api/conocimiento/eliminar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hash:h.hash})});loadConocimiento();refreshStats();toast('🗑️ Eliminado');}
}

// ══════════════════════════════════════════════════════════════
// ACTIVIDAD
// ══════════════════════════════════════════════════════════════
async function loadActividad(){
  try{
    const items=await(await fetch('/api/actividad')).json();
    const el=document.getElementById('log-list');
    el.innerHTML=items.map(a=>{
      const ts=new Date(a.timestamp*1000).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
      return `<div class="log-line"><span class="log-ts">${ts}</span><span class="log-tipo act-tipo t-${a.tipo}">${a.tipo}</span><span class="log-msg">${esc(a.mensaje)}</span></div>`;
    }).join('');
  }catch(e){}
}

// ══════════════════════════════════════════════════════════════
// AJUSTES
// ══════════════════════════════════════════════════════════════
async function loadAjustes(){
  try{
    const d=await(await fetch('/api/stats')).json();
    if(d.config?.nombre_usuario) document.getElementById('cfg-nombre').value=d.config.nombre_usuario;
    const sw={busqueda_web_auto:'cfg-bwa',validacion_manual:'cfg-vm',autoaprendizaje_web:'cfg-aw'};
    for(const[k,id] of Object.entries(sw)){
      const el=document.getElementById(id);
      if(el&&d.config?.[k]!==undefined) el.className='sw'+(d.config[k]?' on':'');
    }
    // Pendientes en ajustes
    const pend=await(await fetch('/api/pendientes')).json();
    document.getElementById('pend-count').textContent=pend.length?`(${pend.length})`:'';
    const pList=document.getElementById('pendientes-list');
    if(!pend.length){pList.innerHTML='<div style="font-size:.78rem;color:var(--t3)">No hay pendientes ✅</div>';return;}
    pList.innerHTML=pend.map(i=>`<div class="pi"><div class="pi-body"><div class="pi-k">${esc(i.clave.slice(0,40))}</div><div class="pi-v">${esc(i.valor.slice(0,70))}</div></div><button class="pi-ok" onclick="aprobar('${i.hash}',this)">✓</button><button class="pi-nk" onclick="rechazar('${i.hash}',this)">✕</button></div>`).join('');
  }catch(e){}
}

// ══════════════════════════════════════════════════════════════
// MODAL
// ══════════════════════════════════════════════════════════════
function closeModal(){document.getElementById('modal-overlay').classList.remove('show');modalCb=null;}
async function modalOk(){if(modalCb)await modalCb();}
document.getElementById('modal-overlay').addEventListener('click',e=>{if(e.target===document.getElementById('modal-overlay'))closeModal();});

// ══════════════════════════════════════════════════════════════
// TOAST
// ══════════════════════════════════════════════════════════════
let toastT;
function toast(msg){
  const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show');
  clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove('show'),3000);
}

// ══════════════════════════════════════════════════════════════
// BIENVENIDA
// ══════════════════════════════════════════════════════════════
function bienvenida(){
  const h=new Date().getHours();
  const s=h<12?'Buenos días':h<20?'Buenas tardes':'Buenas noches';
  addMsg(`${s}! Soy **PAKO**, el motor de IA de esta plataforma. 🧠\n\n`+
    `• 💬 **Chat** — aquí mismo, pregúntame lo que quieras\n`+
    `• ⚡ **Automatizaciones** — crea flujos tipo n8n con IA integrada\n`+
    `• 🧠 **Conocimiento** — todo lo que he aprendido\n`+
    `• 🌐 **Busco en internet** si no sé algo\n\n`+
    `_Y entiendo aunque escribas con errores tipográficos_ 😉`,'pako');
}

// ══════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════
window.addEventListener('load',()=>{
  bienvenida();
  refreshStats();
  loadActividad_mini();
  buildPalette();
  addIAMsg('¡Hola! Soy PAKO, tu asistente de automatizaciones. Puedo:\n• Diseñar flujos a partir de una descripción\n• Explicar cómo funciona cada nodo\n• Configurar nodos IA\n\nDi algo como: **"quiero enviar un email cuando llegue un webhook"**','pako');
  setInterval(refreshStats,12000);
  setInterval(loadActividad_mini,20000);
  document.getElementById('msg-inp').focus();
});
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════
# HANDLER
# ══════════════════════════════════════════════════════════════════

class PakoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _ip(self):
        fwd = self.headers.get("X-Forwarded-For","")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def _sec(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","SAMEORIGIN")
        self.send_header("Referrer-Policy","no-referrer")

    def _json(self, data, st=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(st); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.send_header("Access-Control-Allow-Origin","*")
        self._sec(); self.end_headers(); self.wfile.write(body)

    def _html(self, html, st=200):
        body = html.encode()
        self.send_response(st); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self._sec(); self.end_headers(); self.wfile.write(body)

    def _err(self, msg, st=400): self._json({"error":msg,"ok":False}, st)

    def _body(self):
        try:
            ln = int(self.headers.get("Content-Length",0))
            if ln > MAX_REQ: return {}
            return json.loads(self.rfile.read(ln).decode())
        except: return {}

    def _static(self, path):
        sd = Path(__file__).parent.parent/"frontend"/"dist"
        fp = (sd/path.lstrip("/")).resolve()
        if not str(fp).startswith(str(sd.resolve())): self.send_response(403); self.end_headers(); return
        if fp.exists() and fp.is_file():
            ct = {".js":"application/javascript",".css":"text/css",".png":"image/png",".ico":"image/x-icon",".svg":"image/svg+xml"}.get(fp.suffix.lower(),"application/octet-stream")
            body = fp.read_bytes(); self.send_response(200); self.send_header("Content-Type",ct); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        else: self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Methods","GET,POST,PATCH,DELETE,OPTIONS"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.end_headers()

    def do_GET(self):
        if not rl.ok(self._ip()): self._err("Rate limit exceeded.",429); return
        p = urlparse(self.path).path
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)

        if p in ("/","/index.html"): self._html(_platform_html()); return

        routes = {
            "/api/stats":                    self._g_stats,
            "/api/actividad":                self._g_actividad,
            "/api/pendientes":               self._g_pendientes,
            "/api/conocimiento/recientes":   self._g_recientes,
            "/api/github/info":              self._g_gh_info,
            "/api/github/repos":             self._g_gh_repos,
            "/api/historial":                self._g_historial,
            "/api/config":                   self._g_config,
            "/api/auto/workflows":           self._g_auto_workflows,
            "/api/auto/tipos-nodo":          self._g_auto_tipos,
        }
        if p in routes: routes[p](); return

        # /api/auto/workflows/{id}
        m = re.match(r"^/api/auto/workflows/([a-z0-9]+)$", p)
        if m: self._g_auto_wf(m.group(1)); return

        # /api/conocimiento/hash
        if p == "/api/conocimiento/hash":
            clave = qs.get("clave",[""])[0]
            import hashlib
            h = hashlib.md5(clave.lower().strip().encode()).hexdigest()
            self._json({"hash":h}); return

        self._static(p)

    def do_POST(self):
        if not rl.ok(self._ip()): self._err("Rate limit.",429); return
        p = urlparse(self.path).path; b = self._body()

        routes = {
            "/api/chat":                      self._p_chat,
            "/api/config":                    self._p_config,
            "/api/github/connect":            self._p_gh_connect,
            "/api/pendientes/aprobar":        self._p_aprobar,
            "/api/pendientes/rechazar":       self._p_rechazar,
            "/api/conocimiento/eliminar":     self._p_del_conocimiento,
            "/api/auto/workflows":            self._p_auto_crear,
            "/api/auto/generar":              self._p_auto_generar,
        }
        if p in routes: routes[p](b); return

        m = re.match(r"^/api/auto/workflows/([a-z0-9]+)/toggle$", p)
        if m: self._p_auto_toggle(m.group(1),b); return
        m = re.match(r"^/api/auto/workflows/([a-z0-9]+)/ejecutar$", p)
        if m: self._p_auto_ejecutar(m.group(1),b); return
        m = re.match(r"^/api/auto/workflows/([a-z0-9]+)/duplicar$", p)
        if m: self._p_auto_dup(m.group(1)); return

        self._err("Not found",404)

    def do_PATCH(self):
        if not rl.ok(self._ip()): self._err("Rate limit.",429); return
        p = urlparse(self.path).path; b = self._body()
        m = re.match(r"^/api/auto/workflows/([a-z0-9]+)$", p)
        if m: self._patch_auto_wf(m.group(1),b); return
        self._err("Not found",404)

    def do_DELETE(self):
        if not rl.ok(self._ip()): self._err("Rate limit.",429); return
        p = urlparse(self.path).path
        m = re.match(r"^/api/auto/workflows/([a-z0-9]+)$", p)
        if m:
            ok = automations.eliminar_workflow(m.group(1))
            self._json({"ok":ok}); return
        self._err("Not found",404)

    # ── GET handlers ─────────────────────────────────────────────
    def _g_stats(self):
        s=memory.stats(); s.update(brain.stats())
        cfg={k:v for k,v in memory.config.items() if k!="github_token"}
        s["config"]=cfg; s["github_usuario"]=github_agent._usuario if github_agent.conectado else ""; self._json(s)
    def _g_actividad(self): self._json(memory.get_actividad(50))
    def _g_pendientes(self): self._json(memory.get_pendientes())
    def _g_recientes(self):
        from urllib.parse import parse_qs
        qs=parse_qs(urlparse(self.path).query)
        n=int(qs.get("n",["50"])[0]); self._json(memory.get_recientes(min(n,500)))
    def _g_gh_info(self): info=github_agent.info(); self._json({k:v for k,v in info.items() if k!="token"})
    def _g_gh_repos(self): self._json(github_agent.listar_repos())
    def _g_historial(self): self._json(memory.get_historial(50))
    def _g_config(self): self._json({k:v for k,v in memory.config.items() if k!="github_token"})
    def _g_auto_workflows(self): self._json(automations.listar_workflows())
    def _g_auto_tipos(self): self._json(TIPOS_NODO)
    def _g_auto_wf(self,wf_id): wf=automations.get_workflow(wf_id); self._json(wf if wf else {"error":"not found"},200 if wf else 404)

    # ── POST handlers ─────────────────────────────────────────────
    def _p_chat(self,b):
        msg=_san(str(b.get("mensaje","")).strip())[:MAX_MSG]
        if not msg: self._json({"respuesta":"Mensaje vacío.","fuente":""}); return
        memory.agregar_mensaje("user",msg)
        try: resp,fuente=brain.responder(msg)
        except Exception as ex: memory.log("error",str(ex)); resp="Error interno."; fuente="error"
        self._json({"respuesta":resp,"fuente":fuente})

    def _p_config(self,b):
        key=str(b.get("key",""))
        val=b.get("value")
        allowed={"autoaprendizaje_web","autoaprendizaje_github","validacion_manual","busqueda_web_auto","nombre_usuario","max_historial"}
        if key not in allowed: self._err("Clave no permitida"); return
        if val is None: self._err("value requerido"); return
        memory.set_config(key,val); self._json({"ok":True})

    def _p_gh_connect(self,b):
        tok=str(b.get("token","")).strip()
        if not tok: self._json({"ok":False,"mensaje":"Token vacío"}); return
        if not _ok_gh_token(tok): self._json({"ok":False,"mensaje":"Formato inválido. Debe empezar por ghp_ o github_pat_"}); return
        ok,msg=github_agent.conectar(tok)
        self._json({"ok":ok,"mensaje":msg,"usuario":github_agent._usuario if ok else ""})

    def _p_aprobar(self,b):
        h=str(b.get("hash",""))
        if not _ok_hash(h): self._err("Hash inválido"); return
        self._json({"ok":memory.aprobar_pendiente(h)})

    def _p_rechazar(self,b):
        h=str(b.get("hash",""))
        if not _ok_hash(h): self._err("Hash inválido"); return
        self._json({"ok":memory.rechazar_pendiente(h)})

    def _p_del_conocimiento(self,b):
        h=str(b.get("hash",""))
        if not _ok_hash(h): self._err("Hash inválido"); return
        self._json({"ok":memory.eliminar_conocimiento(h)})

    def _p_auto_crear(self,b):
        nombre=_san(str(b.get("nombre","")).strip())[:100]
        desc=_san(str(b.get("descripcion","")).strip())[:500]
        if not nombre: self._err("nombre requerido"); return
        wf=automations.crear_workflow(nombre,desc)
        self._json({"ok":True,"id":wf.id,"nombre":wf.nombre})

    def _p_auto_generar(self,b):
        desc=_san(str(b.get("descripcion","")).strip())[:500]
        if not desc: self._err("descripcion requerida"); return
        result=automations.generar_workflow_desde_descripcion(desc)
        self._json(result)

    def _p_auto_toggle(self,wf_id,b):
        r=automations.toggle_activo(wf_id)
        if r is None: self._err("Workflow no encontrado",404); return
        self._json({"ok":True,"activo":r})

    def _p_auto_ejecutar(self,wf_id,b):
        log=automations.ejecutar_workflow(wf_id, b)
        self._json(log.to_dict())

    def _p_auto_dup(self,wf_id):
        wf=automations.duplicar_workflow(wf_id)
        if not wf: self._err("Workflow no encontrado",404); return
        self._json({"ok":True,"id":wf.id,"nombre":wf.nombre})

    def _patch_auto_wf(self,wf_id,b):
        ok=automations.actualizar_workflow(wf_id,b)
        self._json({"ok":ok})


def iniciar(host="localhost", port=8765):
    server = HTTPServer((host, port), PakoHandler)
    print(f"\n{'═'*52}")
    print(f"  🧠 PAKO Platform v4.0")
    print(f"  🌐 http://{host}:{port}")
    print(f"  📚 Conocimiento: {memory.stats()['total']} entradas")
    print(f"  ⚡ Workflows: {automations.stats()['total_workflows']}")
    print(f"  🔒 Rate limit: {RL_RPM} req/min")
    print(f"{'═'*52}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Guardando y cerrando...")
        memory.guardar_historial(); memory._guardar_actividad()
        print("✅ ¡Hasta pronto!"); server.shutdown()

if __name__ == "__main__":
    iniciar()
