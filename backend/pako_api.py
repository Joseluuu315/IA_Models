"""
pako_api.py — API externa de PAKO v4.0
=======================================

Expone PAKO como modelo de lenguaje consumible desde cualquier cliente externo.

ENDPOINTS IMPLEMENTADOS:
  OpenAI-compatible (funciona con Onyx, Open WebUI, LM Studio clients, etc.):
    GET  /v1/models                     → lista de modelos disponibles
    POST /v1/chat/completions           → chat estilo OpenAI (streaming + no-streaming)
    POST /v1/completions                → completions clásico
    GET  /v1/models/{model}             → info de un modelo

  API nativa PAKO:
    POST /api/chat                      → chat directo (formato PAKO)
    POST /api/learn                     → enseñar conocimiento
    POST /api/search                    → buscar en la memoria
    GET  /api/memory                    → consultar memoria
    GET  /api/stats                     → estadísticas del sistema
    POST /api/embed                     → "embedding" aproximado (vectores bag-of-words)
    GET  /health                        → health check
    GET  /api/docs                      → documentación interactiva

  Seguridad:
    - API Key opcional (configurable en pako_config.json)
    - Rate limiting por IP y por API key
    - CORS configurable
    - Todos los inputs validados y sanitizados

USO RÁPIDO:
  python pako_api.py                    → puerto 11434 (mismo que Ollama)
  python pako_api.py --port 8000
  python pako_api.py --key mi-api-key  → activa autenticación

EJEMPLO (compatible con cliente OpenAI):
  from openai import OpenAI
  client = OpenAI(base_url="http://localhost:11434/v1", api_key="pako")
  resp = client.chat.completions.create(
      model="pako",
      messages=[{"role": "user", "content": "qué es Docker?"}]
  )
  print(resp.choices[0].message.content)

EJEMPLO con requests:
  import requests
  r = requests.post("http://localhost:11434/api/chat",
      json={"mensaje": "qué es Python"})
  print(r.json()["respuesta"])
"""

import sys, json, time, re, uuid, hashlib, threading, os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import defaultdict, deque
from typing import Optional

# ── Path setup ───────────────────────────────────────────────────
ROOT    = Path(__file__).parent.parent
BACKEND = Path(__file__).parent
sys.path.insert(0, str(BACKEND))

from pako_memory      import PakoMemory
from pako_brain       import PakoBrain
from pako_web_agent   import PakoWebAgent
from pako_github_agent import PakoGitHubAgent
from pako_file_agent  import PakoFileAgent
from pako_fuzzy       import fuzzy as _fuzzy

# ══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════

API_VERSION      = "4.0.0"
MODEL_ID         = "pako"
MODEL_FULL_ID    = "pako-4.0"
CONTEXT_WINDOW   = 4096
MAX_TOKENS_DEF   = 1024
MAX_REQ_BYTES    = 65_536   # 64 KB
MAX_MSG_LEN      = 4_000
RL_RPM_IP        = 120      # req/min por IP
RL_RPM_KEY       = 300      # req/min por API key

CREATED_TS = int(time.time())

# ══════════════════════════════════════════════════════════════════
# RATE LIMITER
# ══════════════════════════════════════════════════════════════════

class RateLimiter:
    def __init__(self, rpm: int):
        self._rpm  = rpm
        self._hist = defaultdict(lambda: deque())
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            h = self._hist[key]
            while h and h[0] < now - 60: h.popleft()
            if len(h) >= self._rpm: return False
            h.append(now); return True

rl_ip  = RateLimiter(RL_RPM_IP)
rl_key = RateLimiter(RL_RPM_KEY)

# ══════════════════════════════════════════════════════════════════
# INICIALIZACIÓN DEL MOTOR PAKO
# ══════════════════════════════════════════════════════════════════

DATA_DIR = Path(os.environ.get("PAKO_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

memory       = PakoMemory(data_dir=str(DATA_DIR))
brain        = PakoBrain(memory=memory)
web_agent    = PakoWebAgent(memory=memory)
github_agent = PakoGitHubAgent(memory=memory)
file_agent   = PakoFileAgent(memory=memory)

brain.web_agent    = web_agent
brain.github_agent = github_agent
brain.file_agent   = file_agent

# Cargar base de conocimiento
for c in [DATA_DIR/"pako_conocimiento.json", ROOT/"paco_aprendido.json"]:
    if c.exists():
        n = memory.cargar_desde_json_legacy(str(c))
        if n > 0: print(f"✅ {n} entradas cargadas"); break

if memory.get_config("github_token",""):
    if github_agent.reconectar():
        print(f"🐙 GitHub: @{github_agent._usuario}")

# API key (None = sin autenticación)
_API_KEY: Optional[str] = None

def set_api_key(key: str):
    global _API_KEY
    _API_KEY = key.strip() if key and key.strip() else None

# Cargar API key desde config si existe
_stored_key = memory.get_config("api_key", "")
if _stored_key:
    set_api_key(_stored_key)


# ══════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════

def _san(t: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(t))

def _now_ms() -> int:
    return int(time.time() * 1000)

def _tok_count(text: str) -> int:
    """Estimación de tokens (≈ palabras / 0.75)"""
    return max(1, len(text.split()) * 4 // 3)

def _completion_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex[:20]

def _extract_messages_text(messages: list) -> str:
    """
    Extrae el texto útil de una lista de mensajes OpenAI.
    Devuelve el último mensaje de usuario, con contexto de los anteriores.
    """
    if not messages:
        return ""
    parts = []
    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Formato multi-modal → extraer solo texto
            content = " ".join(
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        content = str(content).strip()
        if not content:
            continue
        if role == "system":
            parts.append(f"[SISTEMA: {content}]")
        elif role == "assistant":
            parts.append(f"[PAKO: {content[:300]}]")
        elif role == "user":
            parts.append(content)
    return " ".join(parts[-6:]) if parts else ""   # últimos 6 turnos

def _build_openai_response(
    content:     str,
    model:       str = MODEL_FULL_ID,
    finish:      str = "stop",
    prompt_toks: int = 0,
    comp_toks:   int = 0,
) -> dict:
    return {
        "id":      _completion_id(),
        "object":  "chat.completion",
        "created": int(time.time()),
        "model":   model,
        "choices": [{
            "index":         0,
            "message":       {"role": "assistant", "content": content},
            "finish_reason": finish,
        }],
        "usage": {
            "prompt_tokens":     prompt_toks or _tok_count(content),
            "completion_tokens": comp_toks   or _tok_count(content),
            "total_tokens":      (prompt_toks or 0) + (comp_toks or _tok_count(content)),
        },
    }

def _build_stream_chunk(
    content: str,
    model:   str  = MODEL_FULL_ID,
    finish:  Optional[str] = None,
    cid:     str  = "",
) -> str:
    chunk = {
        "id":      cid or _completion_id(),
        "object":  "chat.completion.chunk",
        "created": int(time.time()),
        "model":   model,
        "choices": [{
            "index": 0,
            "delta": {"content": content} if content else {},
            "finish_reason": finish,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


# ══════════════════════════════════════════════════════════════════
# HTML: DOCUMENTACIÓN INTERACTIVA
# ══════════════════════════════════════════════════════════════════

def _docs_html() -> str:
    stats  = memory.stats()
    key_status = f"<span style='color:#ef4444'>Activada</span>" if _API_KEY else "<span style='color:#10b981'>Sin clave (acceso libre)</span>"
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PAKO API — Documentación</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#08080f;--s1:#0f0f1a;--s2:#161628;--bd:#252545;--bd2:#353565;--p:#6366f1;--p2:#818cf8;--p3:#a5b4fc;--cy:#06b6d4;--gn:#10b981;--am:#f59e0b;--rd:#ef4444;--t1:#f0f0ff;--t2:#9ca3af;--t3:#6b7280}}
body{{background:var(--bg);color:var(--t1);font-family:'Sora',sans-serif;line-height:1.6;padding:0}}
::-webkit-scrollbar{{width:5px}}::-webkit-scrollbar-thumb{{background:var(--bd2);border-radius:3px}}
.hero{{background:linear-gradient(135deg,#0d0d20,#1a1235);border-bottom:1px solid var(--bd);padding:40px 48px}}
.hero h1{{font-size:2rem;font-weight:700;letter-spacing:-.03em;margin-bottom:6px}}
.hero h1 span{{color:var(--p2)}}
.hero p{{color:var(--t2);font-size:.95rem;margin-bottom:20px}}
.badges{{display:flex;gap:8px;flex-wrap:wrap}}
.badge{{padding:3px 10px;border-radius:999px;font-size:.65rem;font-family:'IBM Plex Mono',monospace;font-weight:600}}
.bg{{background:rgba(16,185,129,.15);color:#6ee7b7;border:1px solid rgba(16,185,129,.3)}}
.bp{{background:rgba(99,102,241,.15);color:#a5b4fc;border:1px solid rgba(99,102,241,.3)}}
.bc{{background:rgba(6,182,212,.15);color:#67e8f9;border:1px solid rgba(6,182,212,.3)}}
.ba{{background:rgba(245,158,11,.15);color:#fcd34d;border:1px solid rgba(245,158,11,.3)}}
.container{{max-width:960px;margin:0 auto;padding:36px 24px}}
.section{{margin-bottom:40px}}
.section h2{{font-size:1.05rem;font-weight:700;color:var(--p3);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--bd);display:flex;align-items:center;gap:8px}}
.endpoint{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;margin-bottom:12px;overflow:hidden}}
.ep-header{{padding:12px 16px;display:flex;align-items:center;gap:10px;cursor:pointer;transition:background .15s}}
.ep-header:hover{{background:var(--s2)}}
.method{{padding:2px 9px;border-radius:5px;font-size:.68rem;font-weight:700;font-family:'IBM Plex Mono',monospace;flex-shrink:0}}
.GET{{background:rgba(16,185,129,.2);color:#6ee7b7}}.POST{{background:rgba(99,102,241,.2);color:#a5b4fc}}
.ep-path{{font-family:'IBM Plex Mono',monospace;font-size:.82rem;flex:1}}
.ep-desc{{font-size:.75rem;color:var(--t2);flex:1;text-align:right}}
.ep-body{{padding:14px 18px;border-top:1px solid var(--bd);display:none;background:var(--bg)}}
.ep-body.open{{display:block}}
pre{{background:var(--s2);border:1px solid var(--bd);border-radius:7px;padding:13px 16px;font-family:'IBM Plex Mono',monospace;font-size:.77rem;overflow-x:auto;margin:8px 0;color:var(--t1)}}
.label{{font-size:.7rem;color:var(--t3);font-family:'IBM Plex Mono',monospace;margin-top:10px;margin-bottom:4px}}
.try-btn{{padding:6px 14px;background:var(--p);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:.75rem;font-family:'Sora',sans-serif;font-weight:600;margin-top:8px;transition:background .15s}}
.try-btn:hover{{background:#4f46e5}}
.try-out{{margin-top:10px;background:var(--s1);border:1px solid var(--bd));border-radius:7px;padding:12px;font-family:'IBM Plex Mono',monospace;font-size:.75rem;display:none;color:var(--gn)}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:16px}}
.stat{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px 16px}}
.stat .n{{font-size:1.4rem;font-weight:700;font-family:'IBM Plex Mono',monospace;color:var(--p2)}}
.stat .l{{font-size:.65rem;color:var(--t3);margin-top:2px}}
.info-box{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:14px 18px;font-size:.82rem;color:var(--t2);line-height:1.7}}
.info-box strong{{color:var(--t1)}}
</style>
</head>
<body>
<div class="hero">
  <h1>🧠 <span>PAKO</span> API</h1>
  <p>Motor de IA local · Compatible con OpenAI · Sin dependencias externas</p>
  <div class="badges">
    <span class="badge bg">Online</span>
    <span class="badge bp">v{API_VERSION}</span>
    <span class="badge bc">OpenAI Compatible</span>
    <span class="badge ba">Onyx Ready</span>
  </div>
</div>
<div class="container">

<div class="section">
  <h2>📊 Estado actual</h2>
  <div class="stats-grid">
    <div class="stat"><div class="n">{stats['total']}</div><div class="l">Conceptos aprendidos</div></div>
    <div class="stat"><div class="n">{stats.get('ok',0)}</div><div class="l">Activos</div></div>
    <div class="stat"><div class="n">{stats.get('pendientes',0)}</div><div class="l">Pendientes validación</div></div>
    <div class="stat"><div class="n">{stats.get('historial_mensajes',0)}</div><div class="l">Mensajes en historial</div></div>
  </div>
  <div class="info-box">
    <strong>Autenticación:</strong> {key_status}<br>
    <strong>Modelo:</strong> {MODEL_FULL_ID} · Contexto: {CONTEXT_WINDOW} tokens<br>
    <strong>Rate limit:</strong> {RL_RPM_IP} req/min por IP · {RL_RPM_KEY} req/min por API key<br>
    <strong>Base URL:</strong> <code style="color:var(--p3)">http://localhost:11434</code>
  </div>
</div>

<div class="section">
  <h2>🔌 Conexión rápida</h2>
  <div class="label">Python (OpenAI SDK)</div>
  <pre>from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="pako"   # cualquier valor si no hay autenticación
)

response = client.chat.completions.create(
    model="pako",
    messages=[{{"role": "user", "content": "qué es Docker?"}}]
)
print(response.choices[0].message.content)</pre>

  <div class="label">Onyx / Open WebUI</div>
  <pre># En Onyx: Settings → AI Providers → OpenAI-compatible
# Base URL:  http://localhost:11434/v1
# API Key:   pako  (o la que hayas configurado)
# Modelo:    pako</pre>

  <div class="label">curl</div>
  <pre>curl http://localhost:11434/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer pako" \\
  -d '{{"model":"pako","messages":[{{"role":"user","content":"hola"}}]}}'</pre>

  <div class="label">requests</div>
  <pre>import requests
r = requests.post("http://localhost:11434/api/chat",
    json={{"mensaje": "qué es Python"}})
print(r.json()["respuesta"])</pre>
</div>

<div class="section">
  <h2>📡 Endpoints OpenAI-compatible</h2>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method GET">GET</span><span class="ep-path">/v1/models</span><span class="ep-desc">Lista de modelos disponibles</span>
    </div>
    <div class="ep-body">
      <div class="label">Respuesta</div>
      <pre>{{"object":"list","data":[{{"id":"pako","object":"model","owned_by":"pako-local",...}}]}}</pre>
      <button class="try-btn" onclick="tryIt('/v1/models','GET',null,this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method POST">POST</span><span class="ep-path">/v1/chat/completions</span><span class="ep-desc">Chat estilo OpenAI (streaming opcional)</span>
    </div>
    <div class="ep-body">
      <div class="label">Body</div>
      <pre>{{
  "model": "pako",
  "messages": [
    {{"role": "system", "content": "Eres un asistente experto en Python"}},
    {{"role": "user",   "content": "qué es un decorator?"}}
  ],
  "stream": false,
  "max_tokens": 1024,
  "temperature": 0.7
}}</pre>
      <div class="label">Con streaming (stream: true)</div>
      <pre>data: {{"id":"chatcmpl-xxx","choices":[{{"delta":{{"content":"Un decorator"}},...}}]}}
data: {{"id":"chatcmpl-xxx","choices":[{{"delta":{{"content":" es..."}},...}}]}}
data: [DONE]</pre>
      <button class="try-btn" onclick="tryChat()">▶ Probar</button>
      <div class="try-out" id="try-chat-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method POST">POST</span><span class="ep-path">/v1/completions</span><span class="ep-desc">Completions clásico</span>
    </div>
    <div class="ep-body">
      <div class="label">Body</div>
      <pre>{{"model":"pako","prompt":"qué es REST?","max_tokens":512}}</pre>
    </div>
  </div>
</div>

<div class="section">
  <h2>🧠 Endpoints nativos PAKO</h2>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method POST">POST</span><span class="ep-path">/api/chat</span><span class="ep-desc">Chat directo con PAKO</span>
    </div>
    <div class="ep-body">
      <div class="label">Body</div><pre>{{"mensaje": "qué es Docker?"}}</pre>
      <div class="label">Respuesta</div><pre>{{"respuesta": "Docker es...","fuente":"memoria","tokens_usados":42}}</pre>
      <button class="try-btn" onclick="tryIt('/api/chat','POST',{{mensaje:'qué es Python?'}},this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method POST">POST</span><span class="ep-path">/api/learn</span><span class="ep-desc">Enseñar conocimiento a PAKO</span>
    </div>
    <div class="ep-body">
      <div class="label">Body</div><pre>{{"clave":"FastAPI","valor":"Framework web moderno para Python, muy rápido","confianza":1.0}}</pre>
      <div class="label">Respuesta</div><pre>{{"ok":true,"mensaje":"Guardado OK","hash":"abc123..."}}</pre>
      <button class="try-btn" onclick="tryIt('/api/learn','POST',{{clave:'test-api',valor:'esto es una prueba desde la documentación',confianza:1.0}},this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method POST">POST</span><span class="ep-path">/api/search</span><span class="ep-desc">Buscar en la memoria de PAKO</span>
    </div>
    <div class="ep-body">
      <div class="label">Body</div><pre>{{"query":"framework web python","limit":5}}</pre>
      <div class="label">Respuesta</div><pre>{{"results":[{{"clave":"FastAPI","valor":"...","confianza":0.95,"score":0.87}},...]}}</pre>
      <button class="try-btn" onclick="tryIt('/api/search','POST',{{query:'python framework',limit:3}},this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method GET">GET</span><span class="ep-path">/api/memory</span><span class="ep-desc">Consultar memoria (paginado)</span>
    </div>
    <div class="ep-body">
      <div class="label">Query params: ?page=1&limit=20&fuente=web</div>
      <pre>GET /api/memory?page=1&limit=10&fuente=manual</pre>
      <button class="try-btn" onclick="tryIt('/api/memory?limit=5','GET',null,this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method POST">POST</span><span class="ep-path">/api/embed</span><span class="ep-desc">Vector de embedding (bag-of-words TF-IDF)</span>
    </div>
    <div class="ep-body">
      <div class="label">Body</div><pre>{{"input":"Docker es una plataforma de contenedores"}}</pre>
      <div class="label">Respuesta (compatible con OpenAI embeddings)</div>
      <pre>{{
  "object":"list",
  "model":"pako-embed",
  "data":[{{"object":"embedding","index":0,"embedding":[0.12,0.05,...]}}],
  "usage":{{"prompt_tokens":6,"total_tokens":6}}
}}</pre>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method GET">GET</span><span class="ep-path">/api/stats</span><span class="ep-desc">Estadísticas del sistema</span>
    </div>
    <div class="ep-body">
      <button class="try-btn" onclick="tryIt('/api/stats','GET',null,this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="ep-header" onclick="tog(this)">
      <span class="method GET">GET</span><span class="ep-path">/health</span><span class="ep-desc">Health check</span>
    </div>
    <div class="ep-body">
      <div class="label">Respuesta</div><pre>{{"status":"ok","model":"pako-4.0","uptime_s":1234,"knowledge":213}}</pre>
      <button class="try-btn" onclick="tryIt('/health','GET',null,this)">▶ Probar</button>
      <div class="try-out"></div>
    </div>
  </div>

</div>
</div>

<script>
function tog(el){{el.nextElementSibling.classList.toggle('open')}}
async function tryIt(url,method,body,btn){{
  const out=btn.nextElementSibling;out.style.display='block';out.textContent='Cargando...';
  try{{
    const opts={{method,headers:{{'Content-Type':'application/json'}}}};
    if(body)opts.body=JSON.stringify(body);
    const r=await fetch(url,opts);const d=await r.json();
    out.textContent=JSON.stringify(d,null,2);
  }}catch(e){{out.textContent='Error: '+e.message;out.style.color='var(--rd)';}}
}}
async function tryChat(){{
  const out=document.getElementById('try-chat-out');out.style.display='block';out.textContent='Cargando...';
  try{{
    const r=await fetch('/v1/chat/completions',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{model:'pako',messages:[{{role:'user',content:'qué es un API REST?'}}]}})}});
    const d=await r.json();out.textContent=JSON.stringify(d,null,2);
  }}catch(e){{out.textContent='Error: '+e.message;}}
}}
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════
# VECTOR EMBEDDING APROXIMADO (bag-of-words TF-IDF)
# ══════════════════════════════════════════════════════════════════

_START_TIME = time.time()

def _make_embedding(text: str, dim: int = 256) -> list[float]:
    """
    Genera un vector de embedding aproximado usando bag-of-words
    con hashing trick. No es semántico real, pero es determinista
    y útil para similitud coseno básica.
    """
    from math import sqrt
    text = text.lower()
    for s,d in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        text = text.replace(s, d)
    tokens = re.findall(r"[a-z0-9]+", text)
    vec = [0.0] * dim
    for tok in tokens:
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim
        vec[idx] += 1.0
    # Normalizar L2
    norm = sqrt(sum(x*x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


# ══════════════════════════════════════════════════════════════════
# HANDLER HTTP
# ══════════════════════════════════════════════════════════════════

class PakoAPIHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Log silencioso excepto errores
        if any("40" in str(a) or "50" in str(a) for a in args):
            print(f"[API {time.strftime('%H:%M:%S')}] {self.client_address[0]} {fmt % args}")

    # ── Helpers ──────────────────────────────────────────────────

    def _ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def _auth(self) -> bool:
        """Verifica la API key. Si no hay key configurada, permite todo."""
        if not _API_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() == _API_KEY
        # También aceptar como query param ?key=xxx
        qs = parse_qs(urlparse(self.path).query)
        return qs.get("key", [""])[0] == _API_KEY

    def _rate_ok(self) -> bool:
        ip  = self._ip()
        key = self.headers.get("Authorization","").replace("Bearer ","").strip() or ip
        return rl_ip.check(ip) and rl_key.check(key)

    def _json(self, data: dict, st: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(st)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type",   "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg: str, st: int = 400, etype: str = "invalid_request_error"):
        self._json({"error": {"message": msg, "type": etype, "code": st}}, st)

    def _body(self) -> dict:
        try:
            ln = int(self.headers.get("Content-Length", 0))
            if ln > MAX_REQ_BYTES: return {}
            return json.loads(self.rfile.read(ln).decode("utf-8"))
        except Exception:
            return {}

    def _stream(self, chunks: list[str]):
        """Envía una respuesta SSE."""
        self.send_response(200)
        self.send_header("Content-Type",                 "text/event-stream")
        self.send_header("Cache-Control",                "no-cache")
        self.send_header("X-Accel-Buffering",            "no")
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(chunk.encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    # ── OPTIONS ──────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────

    def do_GET(self):
        if not self._rate_ok():
            self._err("Rate limit exceeded. Espera un momento.", 429, "rate_limit_error"); return
        if not self._auth():
            self._err("Invalid API key.", 401, "authentication_error"); return

        p  = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)

        dispatch = {
            "/":           lambda: self._html(_docs_html()),
            "/api/docs":   lambda: self._html(_docs_html()),
            "/health":     self._h_health,
            "/api/stats":  self._h_stats,
            "/api/memory": lambda: self._h_memory(qs),
            "/v1/models":  self._h_models,
        }

        if p in dispatch:
            dispatch[p]()
            return

        # /v1/models/{id}
        m = re.match(r"^/v1/models/(.+)$", p)
        if m:
            self._h_model_info(m.group(1)); return

        self._err("Endpoint no encontrado.", 404, "not_found")

    def _h_health(self):
        self._json({
            "status":    "ok",
            "model":     MODEL_FULL_ID,
            "version":   API_VERSION,
            "uptime_s":  round(time.time() - _START_TIME, 1),
            "knowledge": memory.stats()["total"],
            "timestamp": int(time.time()),
        })

    def _h_stats(self):
        s = memory.stats()
        s.update(brain.stats())
        cfg = {k: v for k, v in memory.config.items() if k not in ("github_token", "api_key")}
        s["config"] = cfg
        self._json(s)

    def _h_memory(self, qs: dict):
        page   = max(1, int(qs.get("page",  ["1"])[0]))
        limit  = min(100, max(1, int(qs.get("limit",["20"])[0])))
        fuente = qs.get("fuente", [None])[0]
        buscar = qs.get("q", [""])[0].strip()

        if buscar:
            items = memory.buscar(buscar, limite=limit)
            data  = [e.to_dict() for e in items]
        else:
            todos = list(memory.conocimiento.values())
            if fuente:
                todos = [e for e in todos if e.fuente == fuente]
            todos.sort(key=lambda e: e.timestamp, reverse=True)
            inicio = (page - 1) * limit
            data = [e.to_dict() for e in todos[inicio:inicio + limit]]

        self._json({
            "page":  page,
            "limit": limit,
            "total": len(memory.conocimiento),
            "items": data,
        })

    def _h_models(self):
        self._json({
            "object": "list",
            "data": [
                {
                    "id":       MODEL_ID,
                    "object":   "model",
                    "created":  CREATED_TS,
                    "owned_by": "pako-local",
                    "root":     MODEL_ID,
                    "parent":   None,
                    "permission": [{
                        "id":                   "modelperm-pako",
                        "object":               "model_permission",
                        "created":              CREATED_TS,
                        "allow_create_engine":  False,
                        "allow_sampling":       True,
                        "allow_logprobs":       False,
                        "allow_search_indices": True,
                        "allow_view":           True,
                        "allow_fine_tuning":    False,
                        "organization":         "*",
                        "group":                None,
                        "is_blocking":          False,
                    }],
                },
                {
                    "id":       MODEL_FULL_ID,
                    "object":   "model",
                    "created":  CREATED_TS,
                    "owned_by": "pako-local",
                },
                {
                    "id":       "pako-embed",
                    "object":   "model",
                    "created":  CREATED_TS,
                    "owned_by": "pako-local",
                },
            ],
        })

    def _h_model_info(self, model_id: str):
        valid = {MODEL_ID, MODEL_FULL_ID, "pako-embed"}
        if model_id not in valid:
            self._err(f"Model '{model_id}' not found.", 404, "not_found"); return
        self._json({
            "id":       model_id,
            "object":   "model",
            "created":  CREATED_TS,
            "owned_by": "pako-local",
        })

    # ── POST ─────────────────────────────────────────────────────

    def do_POST(self):
        if not self._rate_ok():
            self._err("Rate limit exceeded.", 429, "rate_limit_error"); return
        if not self._auth():
            self._err("Invalid API key.", 401, "authentication_error"); return

        p = urlparse(self.path).path
        b = self._body()

        dispatch = {
            "/v1/chat/completions":   lambda: self._p_chat_completions(b),
            "/v1/completions":        lambda: self._p_completions(b),
            "/v1/embeddings":         lambda: self._p_embeddings(b),
            "/api/chat":              lambda: self._p_api_chat(b),
            "/api/learn":             lambda: self._p_api_learn(b),
            "/api/search":            lambda: self._p_api_search(b),
            "/api/embed":             lambda: self._p_embeddings(b),
        }

        if p in dispatch:
            dispatch[p]()
            return

        self._err("Endpoint no encontrado.", 404, "not_found")

    # ── OpenAI: /v1/chat/completions ─────────────────────────────

    def _p_chat_completions(self, b: dict):
        model    = b.get("model", MODEL_ID)
        messages = b.get("messages", [])
        stream   = bool(b.get("stream", False))
        max_tok  = int(b.get("max_tokens",  MAX_TOKENS_DEF))
        # temperature, top_p, etc. → PAKO los ignora pero los acepta sin error

        if not messages:
            self._err("'messages' es requerido y no puede estar vacío."); return

        # Extraer texto de los mensajes
        texto = _extract_messages_text(messages)
        texto = _san(texto)[:MAX_MSG_LEN]

        if not texto.strip():
            self._err("Contenido de mensajes vacío."); return

        # Registrar en historial
        memory.agregar_mensaje("user", texto)

        # Generar respuesta con PAKO
        try:
            respuesta, fuente = brain.responder(texto)
        except Exception as ex:
            memory.log("error", f"API chat: {ex}")
            respuesta = "Ha ocurrido un error interno al procesar tu mensaje."
            fuente    = "error"

        # Limpiar emojis de fuente para respuestas API (más limpias)
        respuesta_limpia = respuesta

        prompt_toks = _tok_count(texto)
        comp_toks   = _tok_count(respuesta_limpia)

        if stream:
            # Dividir la respuesta en chunks para simular streaming
            words  = respuesta_limpia.split(" ")
            cid    = _completion_id()
            chunks = []

            # Chunk inicial con role
            first = {
                "id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
            }
            chunks.append(f"data: {json.dumps(first)}\n\n")

            # Chunks de contenido (grupos de 3-5 palabras para fluidez)
            group_size = 4
            for i in range(0, len(words), group_size):
                group   = " ".join(words[i:i + group_size])
                content = group + (" " if i + group_size < len(words) else "")
                chunks.append(_build_stream_chunk(content, model, None, cid))

            # Chunk final
            final = {
                "id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            chunks.append(f"data: {json.dumps(final)}\n\n")

            self._stream(chunks)
        else:
            self._json(_build_openai_response(
                respuesta_limpia, model, "stop", prompt_toks, comp_toks
            ))

    # ── OpenAI: /v1/completions ───────────────────────────────────

    def _p_completions(self, b: dict):
        model    = b.get("model", MODEL_ID)
        prompt   = str(b.get("prompt", "")).strip()[:MAX_MSG_LEN]
        stream   = bool(b.get("stream", False))

        if not prompt:
            self._err("'prompt' es requerido."); return

        prompt = _san(prompt)
        memory.agregar_mensaje("user", prompt)

        try:
            respuesta, _ = brain.responder(prompt)
        except Exception as ex:
            memory.log("error", f"API completions: {ex}")
            respuesta = "Error interno."

        prompt_toks = _tok_count(prompt)
        comp_toks   = _tok_count(respuesta)

        if stream:
            cid    = _completion_id()
            words  = respuesta.split(" ")
            chunks = []
            for i in range(0, len(words), 4):
                group   = " ".join(words[i:i+4])
                content = group + (" " if i+4 < len(words) else "")
                chunk   = {
                    "id": cid, "object": "text_completion.chunk", "created": int(time.time()),
                    "model": model,
                    "choices": [{"text": content, "index": 0, "finish_reason": None}],
                }
                chunks.append(f"data: {json.dumps(chunk)}\n\n")
            final_c = {"id": cid, "object": "text_completion.chunk", "created": int(time.time()),
                       "model": model, "choices": [{"text":"","index":0,"finish_reason":"stop"}]}
            chunks.append(f"data: {json.dumps(final_c)}\n\n")
            self._stream(chunks)
        else:
            self._json({
                "id":      "cmpl-" + uuid.uuid4().hex[:20],
                "object":  "text_completion",
                "created": int(time.time()),
                "model":   model,
                "choices": [{"text": respuesta, "index": 0, "finish_reason": "stop", "logprobs": None}],
                "usage":   {"prompt_tokens": prompt_toks, "completion_tokens": comp_toks, "total_tokens": prompt_toks + comp_toks},
            })

    # ── OpenAI: /v1/embeddings ────────────────────────────────────

    def _p_embeddings(self, b: dict):
        inp   = b.get("input", b.get("text", ""))
        model = b.get("model", "pako-embed")

        # input puede ser string o lista
        if isinstance(inp, str):
            inputs = [inp]
        elif isinstance(inp, list):
            inputs = [str(i) for i in inp[:16]]  # max 16
        else:
            self._err("'input' debe ser string o lista de strings."); return

        if not inputs or not any(i.strip() for i in inputs):
            self._err("'input' vacío."); return

        data = []
        total_toks = 0
        for idx, text in enumerate(inputs):
            text = _san(text.strip())[:2000]
            emb  = _make_embedding(text)
            total_toks += _tok_count(text)
            data.append({
                "object":    "embedding",
                "index":     idx,
                "embedding": emb,
            })

        self._json({
            "object": "list",
            "model":  model,
            "data":   data,
            "usage":  {"prompt_tokens": total_toks, "total_tokens": total_toks},
        })

    # ── API nativa: /api/chat ─────────────────────────────────────

    def _p_api_chat(self, b: dict):
        msg = _san(str(b.get("mensaje", b.get("message", b.get("prompt", ""))))).strip()[:MAX_MSG_LEN]
        if not msg:
            self._json({"respuesta": "Mensaje vacío.", "fuente": "", "ok": False}); return

        memoria_ctx = bool(b.get("memoria", True))   # Guardar en historial
        if memoria_ctx:
            memory.agregar_mensaje("user", msg)

        try:
            respuesta, fuente = brain.responder(msg)
        except Exception as ex:
            memory.log("error", f"API /api/chat: {ex}")
            respuesta, fuente = "Error interno.", "error"

        self._json({
            "ok":           True,
            "respuesta":    respuesta,
            "fuente":       fuente,
            "tokens_usados": _tok_count(respuesta),
            "timestamp":    int(time.time()),
        })

    # ── API nativa: /api/learn ────────────────────────────────────

    def _p_api_learn(self, b: dict):
        clave    = _san(str(b.get("clave",    b.get("key",   "")))).strip()[:200]
        valor    = _san(str(b.get("valor",    b.get("value", "")))).strip()[:2000]
        fuente   = _san(str(b.get("fuente",   "api"))).strip()[:50]
        confianza = float(b.get("confianza", b.get("confidence", 1.0)))
        confianza = max(0.0, min(1.0, confianza))

        if not clave or not valor:
            self._err("'clave' y 'valor' son requeridos."); return

        ok, msg = memory.guardar_conocimiento(
            clave=clave, valor=valor,
            fuente=fuente, confianza=confianza,
            auto_ok=True,
        )

        import hashlib
        h = hashlib.md5(clave.lower().strip().encode()).hexdigest()

        self._json({
            "ok":      ok,
            "mensaje": msg,
            "hash":    h,
            "clave":   clave,
        })

    # ── API nativa: /api/search ───────────────────────────────────

    def _p_api_search(self, b: dict):
        query  = _san(str(b.get("query", b.get("q", "")))).strip()[:500]
        limite = min(20, max(1, int(b.get("limit", b.get("limite", 5)))))

        if not query:
            self._err("'query' es requerido."); return

        resultados = memory.buscar(query, limite=limite)

        self._json({
            "query":   query,
            "total":   len(resultados),
            "results": [
                {
                    "clave":     r.clave,
                    "valor":     r.valor,
                    "fuente":    r.fuente,
                    "confianza": r.confianza,
                    "timestamp": r.timestamp,
                }
                for r in resultados
            ],
        })


# ══════════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════════

def iniciar_api(host: str = "0.0.0.0", port: int = 11434, api_key: str = ""):
    if api_key:
        set_api_key(api_key)
        memory.set_config("api_key", api_key)

    server = HTTPServer((host, port), PakoAPIHandler)

    local_url  = f"http://localhost:{port}"
    docs_url   = f"{local_url}/api/docs"

    print(f"\n{'═'*56}")
    print(f"  🧠 PAKO API v{API_VERSION}")
    print(f"  🌐 {local_url}")
    print(f"  📖 Docs: {docs_url}")
    print(f"  🔑 Auth: {'API key activada' if _API_KEY else 'Sin autenticación (libre)'}")
    print(f"  📚 Conocimiento: {memory.stats()['total']} entradas")
    print(f"  🔒 Rate limit: {RL_RPM_IP} req/min por IP")
    print(f"\n  Conexión desde OpenAI SDK / Onyx:")
    print(f"    base_url = \"{local_url}/v1\"")
    print(f"    api_key  = \"{'tu-api-key' if _API_KEY else 'cualquier-valor'}\"")
    print(f"    model    = \"pako\"")
    print(f"{'═'*56}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 API PAKO detenida.")
        memory.guardar_historial()
        memory._guardar_actividad()
        server.shutdown()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="PAKO API v4.0 — Servidor OpenAI-compatible")
    p.add_argument("--host",     default="0.0.0.0",  help="Host (default: 0.0.0.0)")
    p.add_argument("--port",     default=11434, type=int, help="Puerto (default: 11434, igual que Ollama)")
    p.add_argument("--key",      default="",          help="API key opcional")
    p.add_argument("--data-dir", default=None,        help="Directorio de datos")
    args = p.parse_args()
    if args.data_dir:
        os.environ["PAKO_DATA_DIR"] = args.data_dir
    iniciar_api(host=args.host, port=args.port, api_key=args.key)
