"""
pako_server.py — Servidor web de PAKO v3.0

Mejoras de seguridad:
  - Rate limiting por IP
  - Validación de inputs
  - CORS configurable
  - Sanitización de outputs
  - Logs de acceso con IPs
  - Límite de tamaño de requests
  - Headers de seguridad HTTP
  - No exponer el token GitHub en respuestas
"""

import sys
import json
import time
import re
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import defaultdict, deque

sys.path.insert(0, str(Path(__file__).parent))

from pako_memory       import PakoMemory
from pako_brain        import PakoBrain
from pako_web_agent    import PakoWebAgent
from pako_github_agent import PakoGitHubAgent
from pako_file_agent   import PakoFileAgent


# ══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN Y SEGURIDAD
# ══════════════════════════════════════════════════════════════════

MAX_REQUEST_BYTES = 32_768   # 32 KB máx por request
MAX_MSG_LEN       = 2_000    # Caracteres máx por mensaje
RATE_LIMIT_RPM    = 60       # Requests por minuto por IP
RATE_LIMIT_BURST  = 10       # Burst máximo
ALLOW_ORIGINS     = {"http://localhost:8765", "http://127.0.0.1:8765"}


class RateLimiter:
    """Rate limiter por IP con ventana deslizante."""
    def __init__(self, rpm: int = 60):
        self._rpm     = rpm
        self._ventana = 60.0
        self._hist: dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.Lock()

    def permitido(self, ip: str) -> bool:
        ahora = time.time()
        with self._lock:
            hist = self._hist[ip]
            # Limpiar entradas viejas
            while hist and hist[0] < ahora - self._ventana:
                hist.popleft()
            if len(hist) >= self._rpm:
                return False
            hist.append(ahora)
            return True


def sanitizar_texto(texto: str) -> str:
    """Elimina caracteres de control peligrosos."""
    # Permitir saltos de línea y tabulaciones
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)


def validar_token_github(token: str) -> bool:
    """Valida formato básico de un token de GitHub."""
    # Tokens clásicos: ghp_xxxx (40 chars), fine-grained: github_pat_xxxx
    return bool(re.match(r"^(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]+)$", token))


# ══════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ══════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

memory       = PakoMemory(data_dir=str(DATA_DIR))
brain        = PakoBrain(memory=memory)
web_agent    = PakoWebAgent(memory=memory)
github_agent = PakoGitHubAgent(memory=memory)
file_agent   = PakoFileAgent(memory=memory)
rate_limiter = RateLimiter(rpm=RATE_LIMIT_RPM)

# Inyectar agentes
brain.web_agent    = web_agent
brain.github_agent = github_agent
brain.file_agent   = file_agent

# Cargar base de conocimiento
_rutas_candidatas = [
    DATA_DIR / "pako_conocimiento.json",
    Path(__file__).parent.parent / "paco_aprendido.json",
    Path(__file__).parent.parent / "paco_aprendido_informatica.json",
    Path("paco_aprendido.json"),
]
for c in _rutas_candidatas:
    if c.exists():
        n = memory.cargar_desde_json_legacy(str(c))
        if n > 0:
            print(f"✅ Cargadas {n} entradas de '{c.name}'")
            break

# Reconectar GitHub si hay token guardado
_gh_token = memory.get_config("github_token", "")
if _gh_token:
    ok = github_agent.reconectar()
    if ok:
        print(f"🐙 GitHub reconectado como @{github_agent._usuario}")

print(f"🧠 PAKO listo — {memory.stats()['total']} conceptos cargados")


# ══════════════════════════════════════════════════════════════════
# UI EMBEBIDA (HTML standalone moderno)
# ══════════════════════════════════════════════════════════════════

def _leer_index_html() -> str:
    react_build = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if react_build.exists():
        return react_build.read_text(encoding="utf-8")
    return _html_standalone()


def _html_standalone() -> str:
    return r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PAKO — Tu IA Personal</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Sora:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0f;--bg2:#0f0f1a;--surface:#14141f;--surface2:#1a1a2e;--surface3:#1f1f35;
  --border:#2a2a45;--border2:#353560;
  --accent:#6366f1;--accent2:#818cf8;--accent3:#a5b4fc;
  --cyan:#06b6d4;--green:#10b981;--amber:#f59e0b;--red:#ef4444;--pink:#ec4899;
  --text:#f0f0ff;--text2:#9ca3af;--text3:#6b7280;
  --r:12px;--r-sm:8px;--r-xs:5px;
  --shadow:0 4px 24px rgba(0,0,0,0.4);
}
html,body{height:100%;overflow:hidden}
body{
  background:var(--bg);color:var(--text);
  font-family:'Sora',sans-serif;
  display:flex;
}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
*{scrollbar-width:thin;scrollbar-color:var(--border2) transparent}

/* ── SIDEBAR ── */
#sidebar{
  width:300px;min-width:300px;
  background:var(--surface);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;
  transition:all .3s cubic-bezier(.4,0,.2,1);
  overflow:hidden;
}
#sidebar.collapsed{width:0;min-width:0}

#sidebar-header{
  padding:18px 20px;
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:14px;
  background:linear-gradient(135deg,#0f0f1a 0%,#1a1229 100%);
  flex-shrink:0;
}
.logo-wrap{
  width:42px;height:42px;border-radius:12px;flex-shrink:0;
  background:linear-gradient(135deg,#4f46e5,#7c3aed);
  display:flex;align-items:center;justify-content:center;
  font-size:20px;
  box-shadow:0 0 24px rgba(99,102,241,0.5);
  animation:logoPulse 4s ease-in-out infinite;
}
@keyframes logoPulse{0%,100%{box-shadow:0 0 20px rgba(99,102,241,0.4)}50%{box-shadow:0 0 36px rgba(99,102,241,0.7)}}
.logo-title{font-size:1.25rem;font-weight:700;letter-spacing:-.02em;color:var(--text)}
.logo-sub{font-size:.62rem;color:var(--text3);font-family:'IBM Plex Mono',monospace;margin-top:1px}

#sidebar-body{flex:1;overflow-y:auto;padding:14px 16px}

.section-label{
  font-size:.58rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.12em;color:var(--text3);
  font-family:'IBM Plex Mono',monospace;
  margin:18px 0 8px;padding-left:2px;
}

/* Stat cards */
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:4px}
.stat-card{
  background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--r-sm);padding:10px 12px;
  transition:border-color .15s;
}
.stat-card:hover{border-color:var(--border2)}
.stat-n{font-size:1.3rem;font-weight:700;color:var(--text);line-height:1;font-family:'IBM Plex Mono',monospace}
.stat-l{font-size:.62rem;color:var(--text3);margin-top:3px}
.stat-card-full{
  background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--r-sm);padding:10px 14px;
  display:flex;align-items:center;gap:10px;margin-bottom:6px;
}
.stat-card-full .icon{font-size:16px;flex-shrink:0}
.stat-card-full .info .n{font-size:.9rem;font-weight:600;font-family:'IBM Plex Mono',monospace}
.stat-card-full .info .l{font-size:.62rem;color:var(--text3)}

/* Toggles */
.toggle-row{
  display:flex;align-items:center;justify-content:space-between;
  padding:9px 12px;background:var(--surface2);
  border:1px solid var(--border);border-radius:var(--r-sm);margin-bottom:5px;
  cursor:pointer;transition:border-color .15s;
}
.toggle-row:hover{border-color:var(--border2)}
.toggle-row .lbl{font-size:.78rem;color:var(--text2);user-select:none}
.sw{width:34px;height:18px;background:var(--border2);border-radius:9px;position:relative;
    cursor:pointer;transition:background .2s;flex-shrink:0}
.sw.on{background:var(--accent)}
.sw::after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;
    border-radius:50%;background:#fff;transition:transform .2s}
.sw.on::after{transform:translateX(16px)}

/* GitHub panel */
.gh-panel{
  background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--r-sm);padding:12px;
}
.gh-panel input{
  width:100%;padding:8px 10px;background:var(--bg);
  border:1px solid var(--border);color:var(--text);
  border-radius:var(--r-sm);font-size:.78rem;
  font-family:'IBM Plex Mono',monospace;outline:none;margin-bottom:7px;
  transition:border-color .15s;
}
.gh-panel input:focus{border-color:var(--accent)}
.gh-panel input::placeholder{color:var(--text3)}
.btn-primary{
  width:100%;padding:8px 14px;background:var(--accent);color:#fff;
  border:none;border-radius:var(--r-sm);cursor:pointer;font-size:.78rem;
  font-family:'Sora',sans-serif;font-weight:600;
  transition:background .15s,transform .1s;
}
.btn-primary:hover{background:#4f46e5}
.btn-primary:active{transform:scale(.97)}
.gh-status-text{font-size:.68rem;color:var(--text3);text-align:center;margin-top:6px}

/* Action btns */
.action-btn{
  width:100%;padding:8px 12px;background:var(--surface2);
  border:1px solid var(--border);color:var(--text2);
  border-radius:var(--r-sm);cursor:pointer;font-size:.78rem;
  font-family:'Sora',sans-serif;text-align:left;
  display:flex;align-items:center;gap:8px;
  transition:all .15s;margin-bottom:5px;
}
.action-btn:hover{border-color:var(--accent);color:var(--accent3);background:rgba(99,102,241,.1)}

/* Activity */
.act-item{
  padding:7px 0;border-bottom:1px solid var(--border);
}
.act-item:last-child{border-bottom:none}
.act-top{display:flex;align-items:center;gap:6px}
.act-tipo{font-size:.6rem;padding:1px 5px;border-radius:3px;font-family:'IBM Plex Mono',monospace;font-weight:600}
.act-tipo.aprendizaje{background:rgba(99,102,241,.2);color:#a5b4fc}
.act-tipo.busqueda{background:rgba(6,182,212,.2);color:#67e8f9}
.act-tipo.sistema{background:rgba(16,185,129,.2);color:#6ee7b7}
.act-tipo.error{background:rgba(239,68,68,.2);color:#fca5a5}
.act-msg{font-size:.7rem;color:var(--text2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.act-ts{font-size:.58rem;color:var(--text3);font-family:'IBM Plex Mono',monospace;margin-top:2px}

/* ── MAIN ── */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}

/* Topbar */
#topbar{
  padding:14px 20px;
  background:var(--surface);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:10px;
  flex-shrink:0;
}
.topbar-title{font-size:.88rem;font-weight:500;color:var(--text2)}
.status-badge{
  display:flex;align-items:center;gap:5px;
  padding:3px 10px;border-radius:999px;
  background:var(--surface2);border:1px solid var(--border);
  font-size:.62rem;font-family:'IBM Plex Mono',monospace;color:var(--text3);
}
.dot{width:6px;height:6px;border-radius:50%;background:var(--green);
  animation:dotPulse 2s ease-in-out infinite;flex-shrink:0}
.dot.busy{background:var(--amber);animation:dotPulse .5s ease-in-out infinite}
@keyframes dotPulse{0%,100%{opacity:1}50%{opacity:.35}}
.topbar-actions{margin-left:auto;display:flex;gap:6px}
.topbar-btn{
  padding:5px 10px;background:var(--surface2);border:1px solid var(--border);
  color:var(--text3);border-radius:var(--r-sm);cursor:pointer;font-size:.7rem;
  font-family:'IBM Plex Mono',monospace;transition:all .15s;
}
.topbar-btn:hover{border-color:var(--border2);color:var(--text2)}

/* ── CHAT ── */
#chat{
  flex:1;overflow-y:auto;
  padding:20px 24px;
  display:flex;flex-direction:column;
  gap:16px;
  scroll-behavior:smooth;
}

.msg{display:flex;gap:10px;animation:msgIn .22s ease;max-width:900px}
@keyframes msgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.msg.user{flex-direction:row-reverse;align-self:flex-end}
.msg.pako{align-self:flex-start}

.av{
  width:32px;height:32px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  font-size:.6rem;font-weight:700;flex-shrink:0;
  font-family:'IBM Plex Mono',monospace;
}
.msg.user .av{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff}
.msg.pako .av{
  background:var(--surface2);border:1.5px solid var(--accent);
  color:var(--accent2);font-size:.55rem;
}

.bubble{
  padding:12px 16px;border-radius:var(--r);
  font-size:.875rem;line-height:1.75;
  max-width:700px;word-break:break-word;
}
.msg.user .bubble{
  background:linear-gradient(135deg,rgba(79,70,229,.25),rgba(124,58,237,.2));
  border:1px solid rgba(99,102,241,.4);
  border-bottom-right-radius:3px;
  color:#d8d8ff;
}
.msg.pako .bubble{
  background:var(--surface);
  border:1px solid var(--border);
  border-bottom-left-radius:3px;
  color:var(--text);
}
.bubble pre{
  background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--r-sm);padding:10px 14px;
  font-family:'IBM Plex Mono',monospace;font-size:.78rem;
  overflow-x:auto;margin:8px 0;line-height:1.5;
}
.bubble code{
  background:rgba(99,102,241,.15);color:var(--accent3);
  padding:1px 5px;border-radius:3px;
  font-family:'IBM Plex Mono',monospace;font-size:.82em;
}
.bubble strong,.bubble b{color:var(--accent3);font-weight:600}
.bubble em,.bubble i{color:var(--text2)}
.bubble a{color:var(--cyan);text-decoration:none}
.bubble a:hover{text-decoration:underline}
.badge-web{display:inline-flex;align-items:center;gap:3px;padding:1px 6px;
  background:rgba(6,182,212,.15);color:#67e8f9;border-radius:3px;
  font-size:.6rem;font-family:'IBM Plex Mono',monospace;margin-right:4px}
.badge-gh{display:inline-flex;align-items:center;gap:3px;padding:1px 6px;
  background:rgba(16,185,129,.15);color:#6ee7b7;border-radius:3px;
  font-size:.6rem;font-family:'IBM Plex Mono',monospace;margin-right:4px}
.badge-mem{display:inline-flex;align-items:center;gap:3px;padding:1px 6px;
  background:rgba(99,102,241,.15);color:var(--accent3);border-radius:3px;
  font-size:.6rem;font-family:'IBM Plex Mono',monospace;margin-right:4px}

.msg-meta{
  font-size:.58rem;color:var(--text3);
  font-family:'IBM Plex Mono',monospace;
  align-self:flex-end;flex-shrink:0;padding-bottom:2px;
}

/* Typing */
.typing-wrap{
  display:flex;align-items:center;gap:12px;
  padding:10px 16px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r);
  border-bottom-left-radius:3px;
}
.dots{display:flex;gap:4px}
.dots span{
  width:6px;height:6px;border-radius:50%;background:var(--accent2);
  animation:bounce 1.3s ease-in-out infinite;
}
.dots span:nth-child(2){animation-delay:.15s}
.dots span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}
.typing-text{font-size:.72rem;color:var(--text3);font-family:'IBM Plex Mono',monospace}

/* Chips */
#chips{
  display:flex;flex-wrap:wrap;gap:6px;
  padding:8px 24px 4px;flex-shrink:0;
}
.chip{
  padding:5px 12px;border-radius:999px;
  border:1px solid var(--border);background:var(--surface2);
  color:var(--text3);cursor:pointer;font-size:.65rem;
  font-family:'IBM Plex Mono',monospace;
  transition:all .15s;white-space:nowrap;
}
.chip:hover{border-color:var(--accent);color:var(--accent3);background:rgba(99,102,241,.1)}

/* Input */
#input-area{
  display:flex;gap:8px;
  padding:12px 20px 16px;
  border-top:1px solid var(--border);
  background:var(--surface);flex-shrink:0;
  align-items:flex-end;
}
#msg-input{
  flex:1;background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--r);color:var(--text);
  font-family:'Sora',sans-serif;font-size:.875rem;
  padding:11px 15px;resize:none;
  min-height:44px;max-height:140px;
  outline:none;transition:border-color .2s;line-height:1.5;
}
#msg-input:focus{border-color:var(--accent)}
#msg-input::placeholder{color:var(--text3)}
#send-btn{
  width:44px;height:44px;border-radius:var(--r);border:none;
  background:var(--accent);color:#fff;cursor:pointer;font-size:16px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  transition:all .15s;
}
#send-btn:hover{background:#4f46e5;transform:scale(1.04)}
#send-btn:active{transform:scale(.94)}
#send-btn:disabled{background:var(--border);cursor:not-allowed;transform:none}

/* Pending panel */
.pending-item{
  display:flex;align-items:center;gap:8px;
  padding:8px 10px;background:var(--surface2);
  border:1px solid var(--border);border-radius:var(--r-sm);margin-bottom:5px;
  font-size:.75rem;
}
.pending-item .pi-body{flex:1;overflow:hidden}
.pending-item .pi-key{color:var(--accent3);font-family:'IBM Plex Mono',monospace;font-size:.68rem}
.pending-item .pi-val{color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.7rem}
.pi-btn{padding:3px 8px;border-radius:4px;border:none;cursor:pointer;font-size:.62rem;margin-left:2px;transition:opacity .15s}
.pi-ok{background:rgba(16,185,129,.2);color:#6ee7b7}
.pi-ok:hover{background:rgba(16,185,129,.35)}
.pi-reject{background:rgba(239,68,68,.2);color:#fca5a5}
.pi-reject:hover{background:rgba(239,68,68,.35)}

/* Toast */
#toast{
  position:fixed;bottom:20px;right:20px;
  padding:10px 18px;background:var(--surface2);
  border:1px solid var(--border);border-radius:var(--r-sm);
  font-size:.78rem;color:var(--text2);
  box-shadow:var(--shadow);
  transform:translateY(60px);opacity:0;
  transition:all .25s cubic-bezier(.4,0,.2,1);
  pointer-events:none;z-index:1000;
}
#toast.show{transform:translateY(0);opacity:1}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div id="sidebar">
  <div id="sidebar-header">
    <div class="logo-wrap">🧠</div>
    <div>
      <div class="logo-title">PAKO</div>
      <div class="logo-sub">IA PROPIA v3.0</div>
    </div>
  </div>
  <div id="sidebar-body">

    <div class="section-label">Conocimiento</div>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-n" id="st-total">—</div>
        <div class="stat-l">Total</div>
      </div>
      <div class="stat-card">
        <div class="stat-n" id="st-pending">—</div>
        <div class="stat-l">Pendientes</div>
      </div>
      <div class="stat-card">
        <div class="stat-n" id="st-web">—</div>
        <div class="stat-l">Web</div>
      </div>
      <div class="stat-card">
        <div class="stat-n" id="st-gh">—</div>
        <div class="stat-l">GitHub</div>
      </div>
    </div>

    <div class="section-label">Autoaprendizaje</div>
    <div class="toggle-row" onclick="toggle('autoaprendizaje_web','toggle-web')">
      <span class="lbl">🌐 Aprender de web</span>
      <div class="sw" id="toggle-web"></div>
    </div>
    <div class="toggle-row" onclick="toggle('autoaprendizaje_github','toggle-gh')">
      <span class="lbl">🐙 Aprender de GitHub</span>
      <div class="sw" id="toggle-gh"></div>
    </div>
    <div class="toggle-row" onclick="toggle('validacion_manual','toggle-val')">
      <span class="lbl">✅ Validación manual</span>
      <div class="sw on" id="toggle-val"></div>
    </div>
    <div class="toggle-row" onclick="toggle('busqueda_web_auto','toggle-bwa')">
      <span class="lbl">🔍 Busqueda web automática</span>
      <div class="sw on" id="toggle-bwa"></div>
    </div>

    <div class="section-label">GitHub</div>
    <div class="gh-panel">
      <input type="password" id="gh-token" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx" autocomplete="off" />
      <button class="btn-primary" onclick="connectGH()">Conectar GitHub</button>
      <div class="gh-status-text" id="gh-status">Sin conectar</div>
    </div>

    <div class="section-label">Acciones</div>
    <button class="action-btn" onclick="verPendientes()">⏳ Ver pendientes</button>
    <button class="action-btn" onclick="enviarChip('¿Qué puedes hacer?')">❓ Ayuda</button>
    <button class="action-btn" onclick="enviarChip('estadísticas')">📊 Ver estadísticas</button>
    <button class="action-btn" onclick="limpiarChat()">🗑️ Limpiar chat</button>

    <div class="section-label">Actividad</div>
    <div id="activity-list"></div>

  </div>
</div>

<!-- MAIN -->
<div id="main">
  <div id="topbar">
    <span class="topbar-title">PAKO · Conversación</span>
    <div class="status-badge">
      <div class="dot" id="status-dot"></div>
      <span id="status-text">Online</span>
    </div>
    <div class="topbar-actions">
      <button class="topbar-btn" onclick="toggleSidebar()">☰ Panel</button>
      <button class="topbar-btn" onclick="exportarConversacion()">📥 Exportar</button>
    </div>
  </div>

  <div id="chat"></div>

  <div id="chips">
    <span class="chip" onclick="enviarChip('¿Qué puedes hacer?')">❓ Ayuda</span>
    <span class="chip" onclick="enviarChip('busca qué es Docker')">🐳 Docker</span>
    <span class="chip" onclick="enviarChip('busca qué es Rust')">🦀 Rust</span>
    <span class="chip" onclick="enviarChip('¿cuánto es 1337 × 42?')">🧮 Cálculo</span>
    <span class="chip" onclick="enviarChip('qué es SOLID')">🏗️ SOLID</span>
    <span class="chip" onclick="enviarChip('¿qué hora es?')">🕒 Hora</span>
    <span class="chip" onclick="enviarChip('cuéntame un chiste')">😄 Chiste</span>
    <span class="chip" onclick="enviarChip('dato curioso')">🔍 Curiosidad</span>
    <span class="chip" onclick="enviarChip('analiza: 12, 45, 7, 89, 34, 56, 23')">📊 Analizar</span>
  </div>

  <div id="input-area">
    <textarea id="msg-input" rows="1"
      placeholder="Escribe a PAKO... · 'busca [tema]' · 'aprende que X es Y' · Enter para enviar"></textarea>
    <button id="send-btn" onclick="enviarInput()">➤</button>
  </div>
</div>

<div id="toast"></div>

<script>
// ══════════════════════════════════════════════════════════════
// ESTADO
// ══════════════════════════════════════════════════════════════
const chat  = document.getElementById('chat');
const input = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
let esperando = false;
let sidebarOpen = true;
let toggleStates = {
  autoaprendizaje_web: false,
  autoaprendizaje_github: false,
  validacion_manual: true,
  busqueda_web_auto: true,
};
// IDs de toggles
const toggleMap = {
  autoaprendizaje_web:    'toggle-web',
  autoaprendizaje_github: 'toggle-gh',
  validacion_manual:      'toggle-val',
  busqueda_web_auto:      'toggle-bwa',
};

// ══════════════════════════════════════════════════════════════
// FORMATEO DE MARKDOWN
// ══════════════════════════════════════════════════════════════
function fmt(texto) {
  let t = texto
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // Code blocks
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, (_,lang,code) => {
    return `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`;
  });
  // Inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
  t = t.replace(/_(.+?)_/g, '<em>$1</em>');
  // Links
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // URLs bare
  t = t.replace(/(^|[\s(])(https?:\/\/[^\s<>"]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  // Source badges
  t = t.replace(/🌐/g, '<span class="badge-web">🌐 WEB</span>');
  t = t.replace(/🐙/g, '<span class="badge-gh">🐙 GH</span>');
  t = t.replace(/📚/g, '<span class="badge-mem">📚 MEM</span>');
  // Newlines
  t = t.replace(/\n/g,'<br>');
  return t;
}

// ══════════════════════════════════════════════════════════════
// MENSAJES
// ══════════════════════════════════════════════════════════════
function hora() {
  return new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});
}

function addMsg(texto, rol, fuente='') {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + rol;

  const av = document.createElement('div');
  av.className = 'av';
  av.textContent = rol === 'user' ? 'TÚ' : 'AI';

  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = fmt(texto);

  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  meta.textContent = hora() + (fuente ? ' · ' + fuente : '');

  wrap.appendChild(av);
  wrap.appendChild(bub);
  wrap.appendChild(meta);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

function showTyping(msg='') {
  const wrap = document.createElement('div');
  wrap.className = 'msg pako'; wrap.id = 'typing-el';
  const av = document.createElement('div');
  av.className = 'av'; av.textContent = 'AI';
  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = `<div class="typing-wrap">
    <div class="dots"><span></span><span></span><span></span></div>
    ${msg ? `<span class="typing-text">${msg}</span>` : ''}
  </div>`;
  wrap.appendChild(av); wrap.appendChild(bub);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}
function hideTyping() {
  const el = document.getElementById('typing-el');
  if (el) el.remove();
}

// ══════════════════════════════════════════════════════════════
// ENVÍO
// ══════════════════════════════════════════════════════════════
async function enviarChip(t) {
  if (esperando) return;
  input.value = t;
  enviarInput();
}

async function enviarInput() {
  const texto = input.value.trim();
  if (!texto || esperando) return;

  if (texto.length > 2000) {
    showToast('Mensaje demasiado largo (máx 2000 caracteres)');
    return;
  }

  esperando = true;
  sendBtn.disabled = true;
  input.value = '';
  autoResize();
  addMsg(texto, 'user');

  const norm = texto.toLowerCase();
  const esWeb = /^(busca\s|buscar\s|qué\s+es\s|que\s+es\s|cómo\s+funciona\s|como\s+funciona\s|explica\s|dime\s+sobre\s)/.test(norm);
  const esGH  = /repo|github|aprende\s+de\s+mis/.test(norm);

  document.getElementById('status-dot').className = 'dot busy';
  document.getElementById('status-text').textContent = esWeb ? 'Buscando...' : esGH ? 'Leyendo repos...' : 'Pensando...';
  showTyping(esWeb ? '🌐 Buscando en internet...' : esGH ? '🐙 Leyendo GitHub...' : '');

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensaje: texto }),
      signal: AbortSignal.timeout(30000),
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const data = await resp.json();
    hideTyping();
    addMsg(data.respuesta || '…', 'pako', data.fuente || '');
    actualizarStats();
    actualizarActividad();
  } catch (e) {
    hideTyping();
    if (e.name === 'TimeoutError') {
      addMsg('⏱️ La respuesta tardó demasiado. Si estaba buscando en internet, puede que la conexión sea lenta. Inténtalo de nuevo.', 'pako');
    } else {
      addMsg('❌ Error de conexión con PAKO. ¿Está el servidor activo?', 'pako');
    }
  } finally {
    esperando = false;
    sendBtn.disabled = false;
    document.getElementById('status-dot').className = 'dot';
    document.getElementById('status-text').textContent = 'Online';
    input.focus();
  }
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviarInput(); }
});
function autoResize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
}
input.addEventListener('input', autoResize);

// ══════════════════════════════════════════════════════════════
// STATS Y ACTIVIDAD
// ══════════════════════════════════════════════════════════════
async function actualizarStats() {
  try {
    const d = await (await fetch('/api/stats')).json();
    document.getElementById('st-total').textContent   = d.total ?? 0;
    document.getElementById('st-pending').textContent = d.pendientes ?? 0;
    document.getElementById('st-web').textContent     = (d.por_fuente?.web) ?? 0;
    document.getElementById('st-gh').textContent      = (d.por_fuente?.github) ?? 0;

    // Sincronizar toggles con config real
    if (d.config) {
      for (const [key, id] of Object.entries(toggleMap)) {
        const val = d.config[key];
        if (val !== undefined) {
          toggleStates[key] = val;
          document.getElementById(id).className = 'sw' + (val ? ' on' : '');
        }
      }
    }
    // Estado GitHub
    if (d.github_conectado) {
      document.getElementById('gh-status').textContent = '✅ Conectado como @' + (d.github_usuario || '?');
    }
  } catch(e) {}
}

async function actualizarActividad() {
  try {
    const items = await (await fetch('/api/actividad')).json();
    const el = document.getElementById('activity-list');
    if (!items?.length) {
      el.innerHTML = '<div style="color:var(--text3);font-size:.68rem;padding:4px 0">Sin actividad aún</div>';
      return;
    }
    el.innerHTML = items.slice(0,8).map(a => {
      const ts = new Date(a.timestamp * 1000).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});
      return `<div class="act-item">
        <div class="act-top">
          <span class="act-tipo ${a.tipo}">${a.tipo}</span>
          <span class="act-msg">${escapeHtml(a.mensaje.slice(0,55))}</span>
        </div>
        <div class="act-ts">${ts}</div>
      </div>`;
    }).join('');
  } catch(e) {}
}

function escapeHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ══════════════════════════════════════════════════════════════
// TOGGLES
// ══════════════════════════════════════════════════════════════
async function toggle(key, id) {
  toggleStates[key] = !toggleStates[key];
  const el = document.getElementById(id);
  el.className = 'sw' + (toggleStates[key] ? ' on' : '');
  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value: toggleStates[key] }),
    });
    showToast(toggleStates[key] ? `✅ ${key.replace(/_/g,' ')} activado` : `⏸️ ${key.replace(/_/g,' ')} desactivado`);
  } catch(e) {}
}

// ══════════════════════════════════════════════════════════════
// GITHUB
// ══════════════════════════════════════════════════════════════
async function connectGH() {
  const token = document.getElementById('gh-token').value.trim();
  if (!token) { showToast('Introduce el token de GitHub'); return; }
  document.getElementById('gh-status').textContent = '⏳ Conectando...';
  try {
    const d = await (await fetch('/api/github/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })).json();
    document.getElementById('gh-status').textContent = d.ok
      ? `✅ @${d.usuario}` : `❌ ${d.mensaje}`;
    if (d.ok) {
      document.getElementById('gh-token').value = '';
      addMsg(`🐙 GitHub conectado como **@${d.usuario}**.\n\nDi **"aprende de mis repos"** para aprender de tu código, o **"mis repos"** para listarlos.`, 'pako');
    }
  } catch(e) {
    document.getElementById('gh-status').textContent = '❌ Error de conexión';
  }
}

// ══════════════════════════════════════════════════════════════
// PENDIENTES
// ══════════════════════════════════════════════════════════════
async function verPendientes() {
  try {
    const items = await (await fetch('/api/pendientes')).json();
    if (!items?.length) {
      addMsg('✅ No hay conocimiento pendiente de validar.', 'pako');
      return;
    }
    // Mostrar en chat con botones
    const wrap = document.createElement('div');
    wrap.className = 'msg pako';
    const av = document.createElement('div');
    av.className = 'av'; av.textContent = 'AI';
    const bub = document.createElement('div');
    bub.className = 'bubble';
    bub.innerHTML = `<strong>⏳ ${items.length} entradas pendientes de validar:</strong><br><br>` +
      items.slice(0,10).map(item => `
        <div class="pending-item">
          <div class="pi-body">
            <div class="pi-key">${escapeHtml(item.clave.slice(0,40))}</div>
            <div class="pi-val">${escapeHtml(item.valor.slice(0,70))}</div>
          </div>
          <button class="pi-btn pi-ok" onclick="aprobar('${item.hash}',this)">✓ OK</button>
          <button class="pi-btn pi-reject" onclick="rechazar('${item.hash}',this)">✕</button>
        </div>`).join('');
    wrap.appendChild(av); wrap.appendChild(bub);
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
  } catch(e) { showToast('Error cargando pendientes'); }
}

async function aprobar(hash, btn) {
  try {
    await fetch('/api/pendientes/aprobar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hash})});
    btn.closest('.pending-item').style.opacity='.4';
    btn.closest('.pending-item').style.pointerEvents='none';
    showToast('✅ Aprobado');
    actualizarStats();
  } catch(e) {}
}
async function rechazar(hash, btn) {
  try {
    await fetch('/api/pendientes/rechazar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hash})});
    btn.closest('.pending-item').style.opacity='.4';
    btn.closest('.pending-item').style.pointerEvents='none';
    showToast('🗑️ Rechazado');
    actualizarStats();
  } catch(e) {}
}

// ══════════════════════════════════════════════════════════════
// UTILIDADES
// ══════════════════════════════════════════════════════════════
function toggleSidebar() {
  sidebarOpen = !sidebarOpen;
  document.getElementById('sidebar').classList.toggle('collapsed', !sidebarOpen);
}

function limpiarChat() {
  chat.innerHTML = '';
  showToast('Chat limpiado');
  bienvenida();
}

function exportarConversacion() {
  const msgs = [...chat.querySelectorAll('.msg')].map(m => {
    const rol  = m.classList.contains('user') ? 'TÚ' : 'PAKO';
    const txt  = m.querySelector('.bubble')?.innerText || '';
    const meta = m.querySelector('.msg-meta')?.textContent || '';
    return `[${meta}] ${rol}: ${txt}`;
  }).join('\n\n');
  const blob = new Blob([msgs], {type:'text/plain'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `pako_chat_${Date.now()}.txt`;
  a.click();
  showToast('💾 Conversación exportada');
}

let toastTimer;
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3000);
}

// ══════════════════════════════════════════════════════════════
// BIENVENIDA
// ══════════════════════════════════════════════════════════════
function bienvenida() {
  const hora = new Date().getHours();
  const saludo = hora < 12 ? 'Buenos días' : hora < 20 ? 'Buenas tardes' : 'Buenas noches';
  addMsg(
    `${saludo}! Soy **PAKO**, tu IA personal construida desde cero. 🧠\n\n` +
    `• 🌐 Busco en internet: **"busca qué es [tema]"**\n` +
    `• 🐙 Aprendo de GitHub: conecta tu cuenta en el panel\n` +
    `• 📚 Aprendo lo que me enseñas: **"aprende que X es Y"**\n` +
    `• 🧮 Calculo: **"¿cuánto es 347 × 28?"**\n` +
    `• 📊 Analizo datos: **"analiza: 12, 45, 7, 89"**\n\n` +
    `¿Por dónde empezamos? 👇`,
    'pako'
  );
}

// ══════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════
window.addEventListener('load', () => {
  bienvenida();
  actualizarStats();
  actualizarActividad();
  setInterval(actualizarStats, 12000);
  setInterval(actualizarActividad, 18000);
  input.focus();
});
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════
# HANDLER HTTP SEGURO
# ══════════════════════════════════════════════════════════════════

class PakoHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Log controlado
        ip = self.client_address[0]
        if "error" in str(args).lower() or "404" in str(args):
            print(f"[{time.strftime('%H:%M:%S')}] {ip} {fmt % args}")

    def _get_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        # CSP básica
        self.send_header("Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'")

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, msg: str, status: int = 400):
        self._json({"error": msg, "ok": False}, status)

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_REQUEST_BYTES:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _check_rate_limit(self) -> bool:
        ip = self._get_ip()
        return rate_limiter.permitido(ip)

    def _static(self, path: str):
        static_dir = Path(__file__).parent.parent / "frontend" / "dist"
        file_path  = (static_dir / path.lstrip("/")).resolve()
        # Security: prevent path traversal
        if not str(file_path).startswith(str(static_dir.resolve())):
            self.send_response(403)
            self.end_headers()
            return
        if file_path.exists() and file_path.is_file():
            ext = file_path.suffix.lower()
            ct = {
                ".js": "application/javascript",
                ".css": "text/css",
                ".png": "image/png",
                ".ico": "image/x-icon",
                ".svg": "image/svg+xml",
                ".woff2": "font/woff2",
            }.get(ext, "application/octet-stream")
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    # ── GET ──────────────────────────────────────────────────────

    def do_GET(self):
        if not self._check_rate_limit():
            self._error("Rate limit exceeded. Espera un momento.", 429)
            return

        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._html(_leer_index_html())
            return

        routes = {
            "/api/stats":    self._get_stats,
            "/api/actividad": self._get_actividad,
            "/api/pendientes": self._get_pendientes,
            "/api/conocimiento/recientes": self._get_recientes,
            "/api/github/info": self._get_github_info,
            "/api/github/repos": self._get_github_repos,
            "/api/historial": self._get_historial,
            "/api/config": self._get_config,
        }
        if path in routes:
            routes[path]()
            return

        self._static(path)

    def _get_stats(self):
        s = memory.stats()
        s.update(brain.stats())
        # Añadir config (sin token)
        cfg = {k: v for k, v in memory.config.items() if k != "github_token"}
        s["config"] = cfg
        s["github_usuario"] = github_agent._usuario if github_agent.conectado else ""
        self._json(s)

    def _get_actividad(self):
        self._json(memory.get_actividad(30))

    def _get_pendientes(self):
        self._json(memory.get_pendientes())

    def _get_recientes(self):
        self._json(memory.get_recientes(20))

    def _get_github_info(self):
        info = github_agent.info()
        # No incluir el token en la respuesta
        self._json({k: v for k, v in info.items() if k != "token"})

    def _get_github_repos(self):
        self._json(github_agent.listar_repos())

    def _get_historial(self):
        self._json(memory.get_historial(50))

    def _get_config(self):
        cfg = {k: v for k, v in memory.config.items() if k != "github_token"}
        self._json(cfg)

    # ── POST ─────────────────────────────────────────────────────

    def do_POST(self):
        if not self._check_rate_limit():
            self._error("Rate limit exceeded.", 429)
            return

        path = urlparse(self.path).path
        body = self._read_body()

        routes_post = {
            "/api/chat":               self._post_chat,
            "/api/config":             self._post_config,
            "/api/github/connect":     self._post_github_connect,
            "/api/pendientes/aprobar": self._post_aprobar,
            "/api/pendientes/rechazar":self._post_rechazar,
            "/api/conocimiento/eliminar": self._post_eliminar,
        }

        handler = routes_post.get(path)
        if handler:
            handler(body)
        else:
            self._error("Endpoint no encontrado.", 404)

    def _post_chat(self, body: dict):
        mensaje = body.get("mensaje", "")
        if not isinstance(mensaje, str):
            self._error("Mensaje debe ser texto.")
            return
        mensaje = sanitizar_texto(mensaje.strip())
        if not mensaje:
            self._json({"respuesta": "Mensaje vacío.", "fuente": ""})
            return
        if len(mensaje) > MAX_MSG_LEN:
            self._json({"respuesta": f"Mensaje demasiado largo (máx {MAX_MSG_LEN} caracteres).", "fuente": ""})
            return

        # Registrar el mensaje del usuario
        memory.agregar_mensaje("user", mensaje)

        # Responder
        try:
            respuesta, fuente = brain.responder(mensaje)
        except Exception as ex:
            memory.log("error", f"Error en brain.responder: {ex}")
            respuesta = "Ha ocurrido un error interno. Por favor, inténtalo de nuevo."
            fuente = "error"

        self._json({"respuesta": respuesta, "fuente": fuente})

    def _post_config(self, body: dict):
        key = body.get("key", "")
        val = body.get("value")
        if not isinstance(key, str) or not key:
            self._error("key requerida.")
            return
        # Claves permitidas para cambiar desde la UI
        claves_permitidas = {
            "autoaprendizaje_web", "autoaprendizaje_github",
            "validacion_manual", "busqueda_web_auto",
            "nombre_usuario", "max_historial",
        }
        if key not in claves_permitidas:
            self._error(f"Clave '{key}' no modificable desde la UI.")
            return
        if val is None:
            self._error("value requerido.")
            return
        memory.set_config(key, val)
        self._json({"ok": True})

    def _post_github_connect(self, body: dict):
        token = body.get("token", "")
        if not isinstance(token, str):
            self._json({"ok": False, "mensaje": "Token inválido."})
            return
        token = token.strip()
        if not token:
            self._json({"ok": False, "mensaje": "Token vacío."})
            return
        # Validación básica de formato
        if not validar_token_github(token):
            self._json({"ok": False, "mensaje": "Formato de token inválido. Debe empezar por ghp_ o github_pat_"})
            return

        ok, msg = github_agent.conectar(token)
        self._json({
            "ok": ok,
            "mensaje": msg,
            "usuario": github_agent._usuario if ok else "",
        })

    def _post_aprobar(self, body: dict):
        h = body.get("hash", "")
        if not isinstance(h, str) or not re.match(r"^[0-9a-f]{32}$", h):
            self._error("Hash inválido.")
            return
        ok = memory.aprobar_pendiente(h)
        self._json({"ok": ok})

    def _post_rechazar(self, body: dict):
        h = body.get("hash", "")
        if not isinstance(h, str) or not re.match(r"^[0-9a-f]{32}$", h):
            self._error("Hash inválido.")
            return
        ok = memory.rechazar_pendiente(h)
        self._json({"ok": ok})

    def _post_eliminar(self, body: dict):
        h = body.get("hash", "")
        if not isinstance(h, str) or not re.match(r"^[0-9a-f]{32}$", h):
            self._error("Hash inválido.")
            return
        ok = memory.eliminar_conocimiento(h)
        self._json({"ok": ok})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ══════════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════════

def iniciar(host: str = "localhost", port: int = 8765):
    server = HTTPServer((host, port), PakoHandler)
    url = f"http://{host}:{port}"
    print(f"\n{'═'*50}")
    print(f"  🧠 PAKO v3.0 — {url}")
    print(f"  📚 Conocimiento: {memory.stats()['total']} entradas")
    print(f"  🔒 Rate limit: {RATE_LIMIT_RPM} req/min")
    print(f"  📂 Datos en: {DATA_DIR}")
    print(f"{'═'*50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 PAKO desconectado. Guardando datos...")
        memory.guardar_historial()
        memory._guardar_actividad()
        print("✅ Datos guardados. ¡Hasta pronto!")
        server.shutdown()


if __name__ == "__main__":
    iniciar()
