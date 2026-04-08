"""
server.py — Servidor web de Paco.
Expone una API REST + sirve la interfaz HTML.
"""

import sys
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Añadir el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))
from paco_brain import Paco

# Instancia global de Paco
paco = Paco()

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paco — IA Propia</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #111118;
    --border: #1e1e2e;
    --accent: #7c3aed;
    --accent2: #a78bfa;
    --accent3: #38bdf8;
    --text: #e2e8f0;
    --muted: #64748b;
    --user-bg: #1e1b4b;
    --paco-bg: #0f172a;
    --green: #4ade80;
    --radius: 12px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    flex-shrink: 0;
  }

  .logo-ring {
    width: 44px; height: 44px;
    border-radius: 50%;
    border: 2px solid var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    background: linear-gradient(135deg, #1e1b4b, #0f172a);
    box-shadow: 0 0 20px rgba(124,58,237,0.3);
    animation: pulse-ring 3s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes pulse-ring {
    0%,100% { box-shadow: 0 0 16px rgba(124,58,237,0.3); }
    50%      { box-shadow: 0 0 32px rgba(124,58,237,0.6); }
  }

  .header-info h1 {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 1.2rem;
    letter-spacing: 0.05em;
    background: linear-gradient(90deg, var(--accent2), var(--accent3));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .header-info p {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    color: var(--muted);
    margin-top: 2px;
  }

  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--green);
    margin-left: auto;
    box-shadow: 0 0 8px var(--green);
    animation: blink 2s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.4} }

  .stats-bar {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem;
    color: var(--muted);
    margin-right: 12px;
    text-align: right;
    line-height: 1.6;
  }

  /* ── Chat ── */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    scroll-behavior: smooth;
  }
  #chat::-webkit-scrollbar { width: 4px; }
  #chat::-webkit-scrollbar-track { background: transparent; }
  #chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .msg {
    display: flex;
    gap: 12px;
    animation: fadein 0.25s ease;
    max-width: 820px;
  }
  @keyframes fadein { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }

  .msg.user { flex-direction: row-reverse; align-self: flex-end; }
  .msg.paco  { align-self: flex-start; }

  .avatar {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; flex-shrink: 0;
    font-weight: 700;
  }
  .msg.user .avatar {
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    color: #fff;
  }
  .msg.paco .avatar {
    background: linear-gradient(135deg, #0f172a, #1e1b4b);
    border: 1px solid var(--accent);
    color: var(--accent2);
    font-family: 'Space Mono', monospace;
    font-size: 10px;
  }

  .bubble {
    padding: 12px 16px;
    border-radius: var(--radius);
    font-size: 0.9rem;
    line-height: 1.65;
    max-width: 680px;
    word-break: break-word;
    white-space: pre-wrap;
  }
  .msg.user .bubble {
    background: var(--user-bg);
    border: 1px solid #312e81;
    border-bottom-right-radius: 4px;
    color: #c7d2fe;
  }
  .msg.paco .bubble {
    background: var(--paco-bg);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
    color: var(--text);
  }

  .msg-time {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem;
    color: var(--muted);
    align-self: flex-end;
    flex-shrink: 0;
    padding-bottom: 4px;
  }

  /* Highlight **texto** */
  .bubble b { color: var(--accent2); font-weight: 700; }

  /* ── Chips de sugerencias ── */
  #chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 20px 8px;
    flex-shrink: 0;
  }
  .chip {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    padding: 5px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .chip:hover {
    border-color: var(--accent);
    color: var(--accent2);
    background: #1e1b4b;
  }

  /* ── Input ── */
  #input-area {
    display: flex;
    gap: 10px;
    padding: 14px 20px 18px;
    border-top: 1px solid var(--border);
    background: var(--surface);
    flex-shrink: 0;
    align-items: flex-end;
  }

  #msg-input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    font-size: 0.9rem;
    padding: 12px 16px;
    resize: none;
    min-height: 46px;
    max-height: 140px;
    outline: none;
    transition: border-color 0.2s;
    line-height: 1.5;
  }
  #msg-input:focus { border-color: var(--accent); }
  #msg-input::placeholder { color: var(--muted); }

  #send-btn {
    width: 46px; height: 46px;
    border-radius: var(--radius);
    border: none;
    background: var(--accent);
    color: #fff;
    cursor: pointer;
    font-size: 18px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: background 0.2s, transform 0.1s;
  }
  #send-btn:hover { background: #6d28d9; }
  #send-btn:active { transform: scale(0.94); }

  /* ── Typing indicator ── */
  .typing { display: flex; gap: 5px; align-items: center; padding: 4px 0; }
  .typing span {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent2);
    animation: bounce 1.2s ease-in-out infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

  /* ── Scrollbar global ── */
  * { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
</style>
</head>
<body>

<header>
  <div class="logo-ring">🧠</div>
  <div class="header-info">
    <h1>PACO</h1>
    <p>Pacogerte a todas horas con ideas </p>
  </div>
  <div class="stats-bar" id="stats-bar">cargando...</div>
  <div class="status-dot" title="Online"></div>
</header>

<div id="chat"></div>

<div id="chips">
  <span class="chip" onclick="enviar('¿Qué puedes hacer?')">¿Qué puedes hacer?</span>
  <span class="chip" onclick="enviar('¿Cuánto es 347 * 28?')">347 × 28</span>
  <span class="chip" onclick="enviar('¿Qué hora es?')">¿Qué hora es?</span>
  <span class="chip" onclick="enviar('Cuéntame un chiste')">Chiste</span>
  <span class="chip" onclick="enviar('Dato curioso')">Dato curioso</span>
  <span class="chip" onclick="enviar('Número aleatorio entre 1 y 100')">Nº aleatorio</span>
  <span class="chip" onclick="enviar('Analiza estos datos: 12, 45, 7, 89, 34, 56, 23')">Analizar datos</span>
</div>

<div id="input-area">
  <textarea id="msg-input" rows="1" placeholder="Escríbele a Paco..." autocomplete="off"></textarea>
  <button id="send-btn" onclick="enviarInput()" title="Enviar">➤</button>
</div>

<script>
const chat  = document.getElementById('chat');
const input = document.getElementById('msg-input');
let esperando = false;

function ahora() {
  const d = new Date();
  return d.toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'});
}

function parsearBold(text) {
  return text.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}

function agregarMensaje(texto, rol) {
  const div  = document.createElement('div');
  div.className = 'msg ' + rol;

  const av   = document.createElement('div');
  av.className = 'avatar';
  av.textContent = rol === 'user' ? 'TÚ' : 'P';

  const bub  = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = parsearBold(texto.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\*\*(.+?)\*\*/g,'<b>$1</b>'));
  // re-apply after escaping
  bub.innerHTML = parsearBold(
    texto.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  ).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');

  const t    = document.createElement('div');
  t.className = 'msg-time';
  t.textContent = ahora();

  div.appendChild(av);
  div.appendChild(bub);
  div.appendChild(t);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function mostrarTyping() {
  const div = document.createElement('div');
  div.className = 'msg paco';
  div.id = 'typing-indicator';
  const av = document.createElement('div');
  av.className = 'avatar'; av.textContent = 'P';
  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  div.appendChild(av); div.appendChild(bub);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function quitarTyping() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

async function actualizarStats() {
  try {
    const r = await fetch('/stats');
    const d = await r.json();
    document.getElementById('stats-bar').innerHTML =
      `mensajes: ${d.mensajes_totales}<br>aprendido: ${d.cosas_aprendidas} cosas<br>vocab: ${d.vocabulario} palabras`;
  } catch(e) {}
}

async function enviar(texto) {
  if (!texto.trim() || esperando) return;
  esperando = true;
  input.value = '';
  autoResize();

  agregarMensaje(texto, 'user');
  mostrarTyping();

  // Simular latencia mínima de pensamiento
  await new Promise(r => setTimeout(r, 300 + Math.random()*400));

  try {
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mensaje: texto})
    });
    const data = await resp.json();
    quitarTyping();
    agregarMensaje(data.respuesta, 'paco');
    await actualizarStats();
  } catch(e) {
    quitarTyping();
    agregarMensaje('Error de conexión con Paco. ¿Está el servidor activo?', 'paco');
  }
  esperando = false;
}

function enviarInput() {
  enviar(input.value.trim());
}

// Enter para enviar, Shift+Enter para salto de línea
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    enviarInput();
  }
});

function autoResize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
}
input.addEventListener('input', autoResize);

// Mensaje de bienvenida
window.addEventListener('load', () => {
  agregarMensaje(
    '¡Hola! Soy Paco, tu IA personal construida desde cero.\n\n' +
    'Puedo calcular, analizar datos, responder preguntas y aprender lo que me enseñes.\n\n' +
    'Prueba a decirme:\n• "aprende que Python es un lenguaje de programación"\n• "¿cuánto es 1234 * 56?"\n• "analiza estos datos: 10, 20, 30, 40, 50"',
    'paco'
  );
  actualizarStats();
  input.focus();
});
</script>
</body>
</html>
"""


class PacoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silenciar logs de requests

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_html(HTML)
        elif path == "/stats":
            self._send_json(paco.stats())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/chat":
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            try:
                data    = json.loads(raw.decode("utf-8"))
                mensaje = data.get("mensaje", "").strip()
                if not mensaje:
                    self._send_json({"respuesta": "No he recibido ningún mensaje."})
                    return
                respuesta = paco.responder(mensaje)
                self._send_json({"respuesta": respuesta})
            except Exception as e:
                self._send_json({"respuesta": f"Error interno: {e}"}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def iniciar(host: str = "localhost", port: int = 8765):
    server = HTTPServer((host, port), PacoHandler)
    print(f"""
╔══════════════════════════════════════════╗
║         PACO — IA Propia activa          ║
╠══════════════════════════════════════════╣
║  URL:  https://{host}:{port}             ║
║  Ctrl+C para detener                     ║
╚══════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Paco desconectado. ¡Hasta pronto!")
        server.shutdown()


if __name__ == "__main__":
    iniciar()
