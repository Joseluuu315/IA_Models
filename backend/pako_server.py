"""
pako_server.py - Servidor web de PAKO.

API REST completa + sirve la app React compilada (o HTML standalone).
"""

import sys
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))

from pako_memory     import PakoMemory
from pako_brain      import PakoBrain
from pako_web_agent  import PakoWebAgent
from pako_github_agent import PakoGitHubAgent
from pako_file_agent import PakoFileAgent

# ===================================================================
# INICIALIZACION DEL SISTEMA
# ===================================================================

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

memory        = PakoMemory(data_dir=str(DATA_DIR))
brain         = PakoBrain(memory=memory)
web_agent     = PakoWebAgent(memory=memory)
github_agent  = PakoGitHubAgent(memory=memory)
file_agent    = PakoFileAgent(memory=memory)

# Inyectar agentes en el cerebro
brain.web_agent    = web_agent
brain.github_agent = github_agent
brain.file_agent   = file_agent

# Importar base de conocimiento de informática si existe
for candidate in [
    DATA_DIR / "pako_conocimiento.json",
    Path(__file__).parent.parent / "paco_aprendido_informatica.json",
    Path(__file__).parent / "paco_aprendido_informatica.json",
    Path("paco_aprendido_informatica.json"),
    Path("../data/paco_aprendido.json"),
]:
    if candidate.exists():
        n = memory.cargar_desde_json_legacy(str(candidate))
        if n > 0:
            print(f"Cargadas {n} entradas de {candidate.name}")
            break

# Reconectar GitHub si hay token guardado
if memory.get_config("github_token", ""):
    ok = github_agent.reconectar()
    if ok:
        print(f"GitHub reconectado como @{github_agent._usuario}")


# ===================================================================
# HTML STANDALONE (fallback si no hay React compilado)
# ===================================================================

def _leer_index_html() -> str:
    """Lee el index.html compilado por React, o devuelve el HTML embebido."""
    react_build = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if react_build.exists():
        return react_build.read_text(encoding="utf-8")
    return _html_standalone()

def _html_standalone() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PAKO - IA Propia</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#09090b;--surface:#18181b;--surface2:#27272a;--border:#3f3f46;
  --accent:#8b5cf6;--accent2:#a78bfa;--accent3:#06b6d4;
  --green:#22c55e;--amber:#f59e0b;--red:#ef4444;
  --text:#fafafa;--text2:#a1a1aa;--text3:#71717a;
  --radius:14px;--radius-sm:8px;
}
body{background:var(--bg);color:var(--text);font-family:'Outfit',sans-serif;
  height:100vh;display:flex;overflow:hidden}

/* Sidebar */
#sidebar{
  width:280px;min-width:280px;background:var(--surface);
  border-right:1px solid var(--border);display:flex;flex-direction:column;
  transition:transform .3s;
}
#sidebar-header{
  padding:20px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:12px;
}
.logo-glow{
  width:40px;height:40px;border-radius:50%;
  background:linear-gradient(135deg,#4c1d95,#1e1b4b);
  border:2px solid var(--accent);
  display:flex;align-items:center;justify-content:center;
  font-size:18px;
  box-shadow:0 0 20px rgba(139,92,246,0.4);
  animation:glow 3s ease-in-out infinite;
  flex-shrink:0;
}
@keyframes glow{0%,100%{box-shadow:0 0 16px rgba(139,92,246,0.4)}
  50%{box-shadow:0 0 32px rgba(139,92,246,0.7)}}
.logo-text{font-size:1.3rem;font-weight:700;
  background:linear-gradient(90deg,var(--accent2),var(--accent3));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo-sub{font-size:.65rem;color:var(--text3);font-family:'JetBrains Mono',monospace;margin-top:2px}

#sidebar-body{flex:1;overflow-y:auto;padding:16px}

.section-title{
  font-size:.65rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.1em;color:var(--text3);margin:16px 0 8px;
  font-family:'JetBrains Mono',monospace;
}

.stat-card{
  background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:12px;margin-bottom:8px;
  display:flex;align-items:center;gap:10px;
}
.stat-icon{font-size:18px;flex-shrink:0}
.stat-info{flex:1}
.stat-label{font-size:.7rem;color:var(--text3);font-family:'JetBrains Mono',monospace}
.stat-value{font-size:.95rem;font-weight:600;color:var(--text)}

.toggle-row{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 12px;background:var(--surface2);
  border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;
}
.toggle-label{font-size:.8rem;color:var(--text2)}
.toggle{
  position:relative;width:36px;height:20px;
  background:var(--border);border-radius:10px;
  cursor:pointer;transition:background .2s;flex-shrink:0;
}
.toggle.on{background:var(--accent)}
.toggle::after{
  content:'';position:absolute;top:2px;left:2px;
  width:16px;height:16px;border-radius:50%;background:#fff;
  transition:transform .2s;
}
.toggle.on::after{transform:translateX(16px)}

.action-btn{
  width:100%;padding:9px 14px;border:1px solid var(--border);
  background:var(--surface2);color:var(--text2);
  border-radius:var(--radius-sm);cursor:pointer;font-size:.8rem;
  font-family:'Outfit',sans-serif;text-align:left;
  display:flex;align-items:center;gap:8px;
  transition:all .15s;margin-bottom:6px;
}
.action-btn:hover{border-color:var(--accent);color:var(--accent2);background:#1e1b4b}

.activity-item{
  padding:8px 0;border-bottom:1px solid var(--border);
  font-size:.72rem;font-family:'JetBrains Mono',monospace;
}
.activity-tipo{color:var(--accent2);margin-right:6px}
.activity-msg{color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.activity-ts{color:var(--text3);font-size:.6rem;margin-top:2px}

.badge{
  display:inline-block;padding:2px 7px;border-radius:999px;
  font-size:.6rem;font-weight:600;font-family:'JetBrains Mono',monospace;
}
.badge-purple{background:#4c1d95;color:#c4b5fd}
.badge-green{background:#14532d;color:#86efac}
.badge-amber{background:#451a03;color:#fde68a}

/* GitHub panel */
#gh-panel{
  padding:12px;background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--radius-sm);margin-top:6px;
}
#gh-panel input{
  width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--border);
  color:var(--text);border-radius:var(--radius-sm);font-size:.8rem;
  font-family:'JetBrains Mono',monospace;outline:none;margin-bottom:6px;
}
#gh-panel input:focus{border-color:var(--accent)}
#gh-panel input::placeholder{color:var(--text3)}
#gh-connect-btn{
  width:100%;padding:8px;background:var(--accent);color:#fff;
  border:none;border-radius:var(--radius-sm);cursor:pointer;font-size:.8rem;
  font-family:'Outfit',sans-serif;font-weight:600;
}
#gh-connect-btn:hover{background:#7c3aed}
#gh-status{font-size:.7rem;color:var(--text3);margin-top:6px;text-align:center}

/* Main chat */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}

#topbar{
  padding:14px 20px;background:var(--surface);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:10px;flex-shrink:0;
}
#topbar-title{font-size:.95rem;font-weight:600;color:var(--text2)}
.status-pill{
  display:flex;align-items:center;gap:5px;
  padding:3px 10px;border-radius:999px;border:1px solid var(--border);
  font-size:.65rem;font-family:'JetBrains Mono',monospace;color:var(--text3);
  background:var(--surface2);
}
.status-dot{width:6px;height:6px;border-radius:50%;background:var(--green);
  animation:pulse 2s ease-in-out infinite;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.status-dot.searching{background:var(--amber);animation:pulse .6s ease-in-out infinite}
#toggle-sidebar-btn{
  margin-left:auto;padding:5px 10px;background:var(--surface2);border:1px solid var(--border);
  color:var(--text3);border-radius:var(--radius-sm);cursor:pointer;font-size:.75rem;
  font-family:'JetBrains Mono',monospace;
}

#chat{
  flex:1;overflow-y:auto;padding:20px;
  display:flex;flex-direction:column;gap:14px;scroll-behavior:smooth;
}
#chat::-webkit-scrollbar{width:3px}
#chat::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

.msg{display:flex;gap:10px;animation:fadein .2s ease;max-width:860px}
@keyframes fadein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.msg.user{flex-direction:row-reverse;align-self:flex-end}
.msg.pako{align-self:flex-start}

.av{
  width:30px;height:30px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:.65rem;font-weight:700;flex-shrink:0;
  font-family:'JetBrains Mono',monospace;
}
.msg.user .av{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff}
.msg.pako .av{
  background:linear-gradient(135deg,#09090b,#1e1b4b);
  border:1.5px solid var(--accent);color:var(--accent2);font-size:.6rem;
}

.bubble{
  padding:11px 15px;border-radius:var(--radius);font-size:.88rem;line-height:1.7;
  max-width:680px;word-break:break-word;white-space:pre-wrap;
}
.msg.user .bubble{
  background:linear-gradient(135deg,#1e1b4b,#312e81);
  border:1px solid #4338ca;border-bottom-right-radius:4px;color:#c7d2fe;
}
.msg.pako .bubble{
  background:var(--surface);border:1px solid var(--border);
  border-bottom-left-radius:4px;color:var(--text);
}
.bubble b{color:var(--accent2);font-weight:600}
.bubble .web-tag{
  display:inline-block;padding:1px 6px;background:#0c4a6e;color:#7dd3fc;
  border-radius:4px;font-size:.65rem;font-family:'JetBrains Mono',monospace;
  margin-right:4px;
}
.bubble .gh-tag{
  display:inline-block;padding:1px 6px;background:#14532d;color:#86efac;
  border-radius:4px;font-size:.65rem;font-family:'JetBrains Mono',monospace;
  margin-right:4px;
}

.msg-meta{
  font-size:.58rem;color:var(--text3);
  font-family:'JetBrains Mono',monospace;
  align-self:flex-end;flex-shrink:0;padding-bottom:3px;
}

/* Chips */
#chips{
  display:flex;flex-wrap:wrap;gap:6px;padding:6px 20px 4px;flex-shrink:0;
}
.chip{
  padding:4px 11px;border-radius:999px;border:1px solid var(--border);
  background:var(--surface2);color:var(--text3);cursor:pointer;
  font-size:.65rem;font-family:'JetBrains Mono',monospace;
  transition:all .15s;white-space:nowrap;
}
.chip:hover{border-color:var(--accent);color:var(--accent2);background:#1e1b4b}

/* Input */
#input-area{
  display:flex;gap:8px;padding:12px 20px 16px;
  border-top:1px solid var(--border);background:var(--surface);flex-shrink:0;
  align-items:flex-end;
}
#msg-input{
  flex:1;background:var(--bg);border:1px solid var(--border);
  border-radius:var(--radius);color:var(--text);
  font-family:'Outfit',sans-serif;font-size:.88rem;
  padding:11px 15px;resize:none;min-height:44px;max-height:130px;
  outline:none;transition:border-color .2s;line-height:1.5;
}
#msg-input:focus{border-color:var(--accent)}
#msg-input::placeholder{color:var(--text3)}
#send-btn{
  width:44px;height:44px;border-radius:var(--radius);border:none;
  background:var(--accent);color:#fff;cursor:pointer;font-size:16px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  transition:background .2s,transform .1s;
}
#send-btn:hover{background:#7c3aed}
#send-btn:active{transform:scale(.93)}

.typing{display:flex;gap:4px;align-items:center;padding:3px 0}
.typing span{
  width:6px;height:6px;border-radius:50%;background:var(--accent2);
  animation:bounce 1.2s ease-in-out infinite;
}
.typing span:nth-child(2){animation-delay:.2s}
.typing span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}

/* Pending */
.pending-item{
  display:flex;align-items:center;gap:8px;padding:8px 10px;
  background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--radius-sm);margin-bottom:6px;font-size:.75rem;
}
.pending-item .pi-text{flex:1;overflow:hidden}
.pending-item .pi-key{color:var(--accent2);font-family:'JetBrains Mono',monospace;font-size:.7rem}
.pending-item .pi-val{color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pi-btn{padding:3px 8px;border-radius:4px;border:none;cursor:pointer;font-size:.65rem;margin-left:2px}
.pi-ok{background:#14532d;color:#86efac}
.pi-reject{background:#450a0a;color:#fca5a5}

*{scrollbar-width:thin;scrollbar-color:var(--border) transparent}
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sidebar">
  <div id="sidebar-header">
    <div class="logo-glow">🧠</div>
    <div>
      <div class="logo-text">PAKO</div>
      <div class="logo-sub">IA propia - sin modelos externos</div>
    </div>
  </div>
  <div id="sidebar-body">

    <div class="section-title">Estado del sistema</div>
    <div class="stat-card">
      <span class="stat-icon">📚</span>
      <div class="stat-info">
        <div class="stat-label">Conocimiento total</div>
        <div class="stat-value" id="st-total">-</div>
      </div>
    </div>
    <div class="stat-card">
      <span class="stat-icon">🌐</span>
      <div class="stat-info">
        <div class="stat-label">Aprendido de la web</div>
        <div class="stat-value" id="st-web">-</div>
      </div>
    </div>
    <div class="stat-card">
      <span class="stat-icon">🐙</span>
      <div class="stat-info">
        <div class="stat-label">Aprendido de GitHub</div>
        <div class="stat-value" id="st-github">-</div>
      </div>
    </div>
    <div class="stat-card">
      <span class="stat-icon">⏳</span>
      <div class="stat-info">
        <div class="stat-label">Pendientes de validar</div>
        <div class="stat-value" id="st-pending">-</div>
      </div>
    </div>

    <div class="section-title">Autoaprendizaje</div>
    <div class="toggle-row">
      <span class="toggle-label">🌐 Aprender de la web</span>
      <div class="toggle" id="toggle-web" onclick="toggleWeb()"></div>
    </div>
    <div class="toggle-row">
      <span class="toggle-label">🐙 Aprender de GitHub</span>
      <div class="toggle" id="toggle-gh" onclick="toggleGh()"></div>
    </div>
    <div class="toggle-row">
      <span class="toggle-label">✅ Validacion manual</span>
      <div class="toggle on" id="toggle-val" onclick="toggleVal()"></div>
    </div>

    <div class="section-title">GitHub</div>
    <div id="gh-panel">
      <input type="password" id="gh-token" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx" />
      <button id="gh-connect-btn" onclick="connectGH()">Conectar GitHub</button>
      <div id="gh-status">Sin conectar</div>
    </div>

    <div class="section-title">Acciones</div>
    <button class="action-btn" onclick="verPendientes()">⏳ Ver pendientes de validar</button>
    <button class="action-btn" onclick="enviarChip('¿Qué puedes hacer?')">❓ ¿Qué puedes hacer?</button>

    <div class="section-title">Actividad reciente</div>
    <div id="activity-list">-</div>

  </div>
</div>

<!-- Main -->
<div id="main">
  <div id="topbar">
    <span id="topbar-title">Conversacion con PAKO</span>
    <div class="status-pill">
      <div class="status-dot" id="status-dot"></div>
      <span id="status-text">Online</span>
    </div>
    <button id="toggle-sidebar-btn" onclick="toggleSidebar()">☰ Panel</button>
  </div>

  <div id="chat"></div>

  <div id="chips">
    <span class="chip" onclick="enviarChip('¿Qué puedes hacer?')">¿Qué puedes hacer?</span>
    <span class="chip" onclick="enviarChip('busca qué es Docker')">Buscar Docker</span>
    <span class="chip" onclick="enviarChip('¿Cuánto es 1337 * 42?')">1337 x 42</span>
    <span class="chip" onclick="enviarChip('¿Qué hora es?')">¿Qué hora?</span>
    <span class="chip" onclick="enviarChip('qué es SOLID')">SOLID</span>
    <span class="chip" onclick="enviarChip('busca qué es Kubernetes')">Kubernetes</span>
    <span class="chip" onclick="enviarChip('Cuéntame un chiste')">Chiste 😄</span>
    <span class="chip" onclick="enviarChip('analiza: 12, 45, 7, 89, 34, 56')">Analizar datos</span>
  </div>

  <div id="input-area">
    <textarea id="msg-input" rows="1"
      placeholder="Escribe a PAKO... o di 'busca [tema]' para buscar en internet"></textarea>
    <button id="send-btn" onclick="enviarInput()">➤</button>
  </div>
</div>

<script>
// -- Estado --
const chat  = document.getElementById('chat');
const input = document.getElementById('msg-input');
let esperando   = false;
let sidebarOpen = true;
let configLocal = { web: false, gh: false, val: true };

// -- Utilidades --
const ahora = () => new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});

function parsearFormato(texto) {
  let t = texto
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\\*\\*(.+?)\\*\\*/g,'<b>$1</b>')
    .replace(/🌐/g,'<span class="web-tag">🌐 WEB</span>')
    .replace(/🐙/g,'<span class="gh-tag">🐙 GITHUB</span>');
  return t;
}

function agregarMensaje(texto, rol, extra='') {
  const div = document.createElement('div');
  div.className = 'msg ' + rol;

  const av = document.createElement('div');
  av.className = 'avatar av';
  av.textContent = rol === 'user' ? 'TU' : 'AI';

  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = parsearFormato(texto);

  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  meta.textContent = ahora() + (extra ? ' · ' + extra : '');

  div.appendChild(av); div.appendChild(bub); div.appendChild(meta);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function mostrarTyping(texto='') {
  const div = document.createElement('div');
  div.className = 'msg pako'; div.id = 'typing-el';
  const av = document.createElement('div');
  av.className = 'avatar av'; av.textContent = 'AI';
  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = texto
    ? `<span style="font-size:.75rem;color:var(--text3)">${texto}</span>`
    : '<div class="typing"><span></span><span></span><span></span></div>';
  div.appendChild(av); div.appendChild(bub);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}
function quitarTyping() {
  const el = document.getElementById('typing-el');
  if (el) el.remove();
}

// -- Envio de mensajes --
async function enviarChip(t) { if (!esperando) input.value = t; enviarInput(); }

async function enviarInput() {
  const texto = input.value.trim();
  if (!texto || esperando) return;
  esperando = true;
  input.value = '';
  autoResize();
  agregarMensaje(texto, 'user');

  // Detectar si va a buscar en web
  const esWeb = /^(busca |buscar |qué es |que es |cómo funciona |como funciona |explica |dime sobre )/i.test(texto);
  mostrarTyping(esWeb ? '🌐 Buscando en internet...' : '');

  await new Promise(r => setTimeout(r, esWeb ? 200 : 100));

  try {
    const resp = await fetch('/api/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mensaje: texto})
    });
    const data = await resp.json();
    quitarTyping();
    const fuente = data.fuente || '';
    agregarMensaje(data.respuesta, 'pako', fuente ? `via ${fuente}` : '');
    actualizarStats();
    actualizarActividad();
  } catch(e) {
    quitarTyping();
    agregarMensaje('Error de conexion con PAKO. ¿Esta el servidor activo?', 'pako');
  }
  esperando = false;
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviarInput(); }
});

function autoResize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 130) + 'px';
}
input.addEventListener('input', autoResize);

// -- Stats y actividad --
async function actualizarStats() {
  try {
    const r = await fetch('/api/stats');
    const d = await r.json();
    document.getElementById('st-total').textContent   = d.total || 0;
    document.getElementById('st-web').textContent     = (d.por_fuente && d.por_fuente.web) || 0;
    document.getElementById('st-github').textContent  = (d.por_fuente && d.por_fuente.github) || 0;
    document.getElementById('st-pending').textContent = d.pendientes || 0;
  } catch(e) {}
}

async function actualizarActividad() {
  try {
    const r  = await fetch('/api/actividad');
    const ds = await r.json();
    const list = document.getElementById('activity-list');
    if (!ds.length) { list.innerHTML = '<div style="color:var(--text3);font-size:.7rem">Sin actividad aun</div>'; return; }
    list.innerHTML = ds.slice(0,8).map(a => {
      const ts = new Date(a.timestamp * 1000).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});
      return `<div class="activity-item">
        <span class="activity-tipo">[${a.tipo}]</span>
        <span class="activity-msg">${a.mensaje.slice(0,60)}</span>
        <div class="activity-ts">${ts}</div>
      </div>`;
    }).join('');
  } catch(e) {}
}

// -- Toggles --
async function toggleWeb() {
  configLocal.web = !configLocal.web;
  document.getElementById('toggle-web').className = 'toggle' + (configLocal.web ? ' on' : '');
  await fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:'autoaprendizaje_web', value: configLocal.web})});
}
async function toggleGh() {
  configLocal.gh = !configLocal.gh;
  document.getElementById('toggle-gh').className = 'toggle' + (configLocal.gh ? ' on' : '');
  await fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:'autoaprendizaje_github', value: configLocal.gh})});
}
async function toggleVal() {
  configLocal.val = !configLocal.val;
  document.getElementById('toggle-val').className = 'toggle' + (configLocal.val ? ' on' : '');
  await fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:'validacion_manual', value: configLocal.val})});
}

// -- GitHub --
async function connectGH() {
  const token = document.getElementById('gh-token').value.trim();
  if (!token) return;
  document.getElementById('gh-status').textContent = 'Conectando...';
  try {
    const r = await fetch('/api/github/connect', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({token})});
    const d = await r.json();
    document.getElementById('gh-status').textContent = d.mensaje;
    if (d.ok) {
      document.getElementById('gh-token').value = '';
      agregarMensaje(`🐙 GitHub conectado como **@${d.usuario}**. Puedo aprender de tus repos. Di 'aprende de mis repos' para empezar.`, 'pako');
    }
  } catch(e) {
    document.getElementById('gh-status').textContent = 'Error de conexion';
  }
}

// -- Pendientes --
async function verPendientes() {
  const r = await fetch('/api/pendientes');
  const items = await r.json();
  if (!items.length) {
    agregarMensaje('No hay conocimiento pendiente de validar. ✅', 'pako');
    return;
  }
  let html = `⏳ **${items.length} entradas pendientes de validacion:**\\n\\n`;
  items.slice(0,5).forEach((item,i) => {
    html += `${i+1}. **${item.clave}** -> ${item.valor.slice(0,80)}...\\n   Fuente: ${item.fuente} | Confianza: ${Math.round(item.confianza*100)}%\\n\\n`;
  });
  html += 'Para aprobar/rechazar usa los botones en el panel lateral.';
  agregarMensaje(html, 'pako');
}

// -- Sidebar toggle --
function toggleSidebar() {
  sidebarOpen = !sidebarOpen;
  document.getElementById('sidebar').style.transform =
    sidebarOpen ? '' : 'translateX(-100%)';
  document.getElementById('sidebar').style.minWidth =
    sidebarOpen ? '280px' : '0';
}

// -- Bienvenida --
window.addEventListener('load', () => {
  agregarMensaje(
    '¡Hola! Soy **PAKO**, tu IA personal construida desde cero.\\n\\n' +
    '🧠 Tengo 212+ conceptos de informática ya cargados.\\n' +
    '🌐 Puedo buscar en internet: di **"busca qué es [tema]"**\\n' +
    '🐙 Puedo aprender de tu GitHub: conecta tu cuenta en el panel izquierdo.\\n' +
    '📚 Puedo aprender lo que me enseñes: **"aprende que X es Y"**\\n\\n' +
    '¿Por dónde empezamos?',
    'pako'
  );
  actualizarStats();
  actualizarActividad();
  setInterval(actualizarStats, 10000);
  setInterval(actualizarActividad, 15000);
  input.focus();
});
</script>
</body>
</html>"""


# ===================================================================
# HANDLER HTTP
# ===================================================================

class PakoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silenciar logs de acceso

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str):
        """Sirve archivos estaticos del build de React."""
        static_dir = Path(__file__).parent.parent / "frontend" / "dist"
        file_path  = static_dir / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            ext = file_path.suffix.lower()
            ct  = {
                ".js": "application/javascript",
                ".css": "text/css",
                ".png": "image/png",
                ".ico": "image/x-icon",
                ".svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # -- GET -----------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._html(_leer_index_html()); return

        # API endpoints
        if path == "/api/stats":
            stats = memory.stats()
            stats.update(brain.stats())
            self._json(stats); return

        if path == "/api/actividad":
            self._json(memory.get_actividad(30)); return

        if path == "/api/pendientes":
            self._json(memory.get_pendientes()); return

        if path == "/api/conocimiento/recientes":
            self._json(memory.get_recientes(20)); return

        if path == "/api/github/info":
            self._json(github_agent.info()); return

        if path.startswith("/api/github/repos"):
            self._json(github_agent.listar_repos()); return

        # Archivos estaticos del build React
        self._static(path)

    # -- POST ----------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        # -- Chat ----------------------------------------------
        if path == "/api/chat":
            mensaje = body.get("mensaje", "").strip()
            if not mensaje:
                self._json({"respuesta": "Mensaje vacio."}); return

            # Comandos especiales de GitHub
            norm = mensaje.lower()
            if "aprende de mis repos" in norm or "aprende de todos mis repos" in norm:
                if not github_agent.conectado:
                    self._json({"respuesta": "No estoy conectado a GitHub. Usa el panel lateral para conectarte.", "fuente": "sistema"}); return
                n, msg = github_agent.aprender_de_todos_los_repos()
                self._json({"respuesta": f"🐙 {msg}", "fuente": "github"}); return

            import re as _re
            m_repo = _re.search(r"aprende del? repo(?:sitorio)?\\s+(.+)", norm)
            if m_repo:
                repo_n = m_repo.group(1).strip()
                if not github_agent.conectado:
                    self._json({"respuesta": "No conectado a GitHub.", "fuente": "sistema"}); return
                n, msg = github_agent.aprender_de_repo(repo_n)
                self._json({"respuesta": f"🐙 {msg}", "fuente": "github"}); return

            # Comando: leer URL
            m_url = _re.search(r"(?:lee|aprende de|extrae de)\\s+(https?://\\S+)", norm)
            if m_url:
                url_target = m_url.group(1)
                n, msg = web_agent.aprender_de_url(url_target)
                self._json({"respuesta": f"🌐 {msg}", "fuente": "web"}); return

            # Respuesta normal del cerebro
            respuesta = brain.responder(mensaje)
            # Determinar fuente para la UI
            fuente = ""
            if respuesta.startswith("🌐"):
                fuente = "web"
            elif respuesta.startswith("🐙"):
                fuente = "github"
            elif respuesta.startswith("📚"):
                fuente = "memoria"
            self._json({"respuesta": respuesta, "fuente": fuente}); return

        # -- Config --------------------------------------------
        if path == "/api/config":
            key = body.get("key","")
            val = body.get("value")
            if key and val is not None:
                memory.set_config(key, val)
                # Propagar a agentes
                if key == "autoaprendizaje_web":
                    web_agent.activo = True  # siempre activo, el autoaprendizaje es solo guardar auto
                self._json({"ok": True}); return
            self._json({"ok": False, "error": "key/value requeridos"}, 400); return

        # -- GitHub connect ------------------------------------
        if path == "/api/github/connect":
            token = body.get("token","").strip()
            if not token:
                self._json({"ok": False, "mensaje": "Token vacio."}); return
            ok, msg = github_agent.conectar(token)
            self._json({
                "ok": ok,
                "mensaje": msg,
                "usuario": github_agent._usuario if ok else ""
            }); return

        # -- Aprobar/rechazar pendiente -------------------------
        if path == "/api/pendientes/aprobar":
            h = body.get("hash","")
            ok = memory.aprobar_pendiente(h)
            self._json({"ok": ok}); return

        if path == "/api/pendientes/rechazar":
            h = body.get("hash","")
            ok = memory.rechazar_pendiente(h)
            self._json({"ok": ok}); return

        self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def iniciar(host: str = "localhost", port: int = 8765):
    server = HTTPServer((host, port), PakoHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\n👋 PAKO desconectado. ¡Hasta pronto!")
        server.shutdown()


if __name__ == "__main__":
    iniciar()
