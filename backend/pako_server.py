"""
pako_server.py — Servidor de la plataforma PAKO v5.0
Importa los módulos del backend y sirve la UI.
"""
import sys, json, time, re, threading, os
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
from pako_automations  import PakoAutomations, TIPOS_NODO

DATA_DIR = Path(os.environ.get("PAKO_DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_REQ, MAX_MSG, RL_RPM = 65536, 2000, 80

class _RL:
    def __init__(self, rpm=80):
        self._rpm=rpm; self._h=defaultdict(lambda:deque()); self._l=threading.Lock()
    def ok(self, ip):
        now=time.time()
        with self._l:
            h=self._h[ip]
            while h and h[0]<now-60: h.popleft()
            if len(h)>=self._rpm: return False
            h.append(now); return True

def _san(t): return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]","",str(t))
def _ok_gh(t): return bool(re.match(r"^(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]+)$",t))
def _ok_h(h): return bool(re.match(r"^[0-9a-f]{8,32}$",h))

# Globals — pueden ser inyectados por run.py
memory       = PakoMemory(data_dir=str(DATA_DIR))
brain        = PakoBrain(memory=memory)
web_agent    = PakoWebAgent(memory=memory)
github_agent = PakoGitHubAgent(memory=memory)
file_agent   = PakoFileAgent(memory=memory)
automations  = PakoAutomations(data_dir=str(DATA_DIR), memory=memory)
rl           = _RL(RL_RPM)

brain.web_agent=web_agent; brain.github_agent=github_agent
brain.file_agent=file_agent; brain.automations=automations
automations.set_brain(brain)

for c in [DATA_DIR/"pako_conocimiento.json", Path("paco_aprendido.json")]:
    if c.exists():
        n=memory.cargar_desde_json_legacy(str(c))
        if n>0: print(f"✅ {n} entradas de '{c.name}'"); break

if memory.get_config("github_token",""):
    if github_agent.reconectar(): print(f"🐙 GitHub @{github_agent._usuario}")

print(f"🧠 Platform v5 — {memory.stats()['total']} conceptos")


# ══════════════════════════════════════════════════════════════════
# FRONTEND — UI COMPLETA
# ══════════════════════════════════════════════════════════════════


def _ui() -> str:
    # Voice-enabled UI - read from separate file
    try:
        import os
        ui_file = os.path.join(os.path.dirname(__file__), 'pako_ui.html')
        if os.path.exists(ui_file):
            return open(ui_file, encoding='utf-8').read()
    except Exception:
        pass
    return "<html><body><h1>PAKO</h1><p>UI file not found. Check pako_ui.html</p></body></html>"


class PakoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def _ip(self):
        fwd=self.headers.get("X-Forwarded-For","")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]
    def _json(self,data,st=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(st); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(body)
    def _html(self,html,st=200):
        body=html.encode(); self.send_response(st)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def _err(self,msg,st=400): self._json({"error":msg,"ok":False},st)
    def _body(self):
        try:
            ln=int(self.headers.get("Content-Length",0))
            if ln>MAX_REQ: return {}
            return json.loads(self.rfile.read(ln).decode())
        except: return {}
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type"); self.end_headers()

    def do_GET(self):
        if not rl.ok(self._ip()): self._err("Rate limit",429); return
        p=urlparse(self.path).path
        qs=parse_qs(urlparse(self.path).query)
        if p in("/","/index.html"): self._html(_ui()); return
        routes={
            "/api/stats":self._g_stats,"/api/actividad":self._g_act,
            "/api/pendientes":self._g_pend,"/api/conocimiento/recientes":lambda:self._g_know(qs),
            "/api/github/repos":self._g_gh_repos,"/api/historial":self._g_hist,
            "/api/config":self._g_cfg,"/api/auto/workflows":self._g_wfs,
            "/api/auto/tipos-nodo":lambda:self._json(TIPOS_NODO),
            "/api/tts/voices":self._g_tts_voices,
        }
        if p in routes: routes[p](); return
        m=re.match(r"^/api/auto/workflows/([a-z0-9]+)$",p)
        if m: wf=automations.get_workflow(m.group(1)); self._json(wf if wf else {"error":"not found"},200 if wf else 404); return
        if p=="/api/conocimiento/hash":
            import hashlib; clave=qs.get("clave",[""])[0]
            self._json({"hash":hashlib.md5(clave.lower().strip().encode()).hexdigest()}); return
        self._err("Not found",404)

    def _g_stats(self):
        s=memory.stats(); s.update(brain.stats())
        cfg={k:v for k,v in memory.config.items() if k not in("github_token","api_key")}
        s["config"]=cfg; s["github_conectado"]=github_agent.conectado
        s["github_usuario"]=github_agent._usuario if github_agent.conectado else ""; self._json(s)
    def _g_act(self): self._json(memory.get_actividad(80))
    def _g_pend(self): self._json(memory.get_pendientes())
    def _g_know(self,qs):
        n=int(qs.get("n",["50"])[0]); self._json(memory.get_recientes(min(n,500)))
    def _g_gh_repos(self): self._json(github_agent.listar_repos())
    def _g_hist(self): self._json(memory.get_historial(50))
    def _g_cfg(self): self._json({k:v for k,v in memory.config.items() if k not in("github_token","api_key")})
    def _g_wfs(self): self._json(automations.listar_workflows())

    def do_POST(self):
        if not rl.ok(self._ip()): self._err("Rate limit",429); return
        p=urlparse(self.path).path; b=self._body()
        routes={
            "/api/chat":self._p_chat,"/api/config":self._p_cfg,
            "/api/github/connect":self._p_gh,"/api/pendientes/aprobar":self._p_apr,
            "/api/pendientes/rechazar":self._p_rej,"/api/conocimiento/eliminar":self._p_del_know,
            "/api/auto/workflows":self._p_new_wf,"/api/auto/generar":self._p_gen_wf,
            "/api/tts":self._p_tts,
        }
        if p in routes: routes[p](b); return
        m=re.match(r"^/api/auto/workflows/([a-z0-9]+)/toggle$",p)
        if m: r=automations.toggle_activo(m.group(1)); self._json({"ok":r is not None,"activo":r}); return
        m=re.match(r"^/api/auto/workflows/([a-z0-9]+)/ejecutar$",p)
        if m: log=automations.ejecutar_workflow(m.group(1),b); self._json(log.to_dict()); return
        m=re.match(r"^/api/auto/workflows/([a-z0-9]+)/duplicar$",p)
        if m: wf=automations.duplicar_workflow(m.group(1)); self._json({"ok":bool(wf),"id":wf.id if wf else ""}); return
        self._err("Not found",404)

    def _p_chat(self,b):
        msg=_san(str(b.get("mensaje",""))).strip()[:MAX_MSG]
        if not msg: self._json({"respuesta":"Mensaje vacío.","fuente":""}); return
        memory.agregar_mensaje("user",msg)
        try: resp,fuente=brain.responder(msg)
        except Exception as ex: memory.log("error",str(ex)); resp="Error interno."; fuente="error"
        self._json({"respuesta":resp,"fuente":fuente})
    def _p_cfg(self,b):
        key=str(b.get("key","")); val=b.get("value")
        allowed={"autoaprendizaje_web","autoaprendizaje_github","validacion_manual","busqueda_web_auto","nombre_usuario","max_historial"}
        if key not in allowed: self._err("Clave no permitida"); return
        if val is None: self._err("value requerido"); return
        memory.set_config(key,val); self._json({"ok":True})
    def _p_gh(self,b):
        tok=str(b.get("token","")).strip()
        if not tok: self._json({"ok":False,"mensaje":"Token vacío"}); return
        if not _ok_gh(tok): self._json({"ok":False,"mensaje":"Formato inválido"}); return
        ok,msg=github_agent.conectar(tok)
        self._json({"ok":ok,"mensaje":msg,"usuario":github_agent._usuario if ok else ""})
    def _p_apr(self,b):
        h=str(b.get("hash","")); 
        if not _ok_h(h): self._err("Hash inválido"); return
        self._json({"ok":memory.aprobar_pendiente(h)})
    def _p_rej(self,b):
        h=str(b.get("hash",""))
        if not _ok_h(h): self._err("Hash inválido"); return
        self._json({"ok":memory.rechazar_pendiente(h)})
    def _p_del_know(self,b):
        h=str(b.get("hash",""))
        if not _ok_h(h): self._err("Hash inválido"); return
        self._json({"ok":memory.eliminar_conocimiento(h)})
    def _p_new_wf(self,b):
        n=_san(str(b.get("nombre",""))).strip()[:100]
        d=_san(str(b.get("descripcion",""))).strip()[:500]
        if not n: self._err("nombre requerido"); return
        wf=automations.crear_workflow(n,d); self._json({"ok":True,"id":wf.id,"nombre":wf.nombre})
    def _p_gen_wf(self,b):
        desc=_san(str(b.get("descripcion",""))).strip()[:500]
        if not desc: self._err("descripcion requerida"); return
        self._json(automations.generar_workflow_desde_descripcion(desc))

    def _g_tts_voices(self):
        """Lista voces disponibles en el servidor (informativo)."""
        self._json({"voices":["es-ES","es-MX","es-AR"],"engine":"browser_web_speech_api","note":"TTS se ejecuta en el navegador via Web Speech API"})

    def _p_tts(self,b):
        """
        Endpoint TTS opcional: genera audio MP3 con gTTS (Google TTS).
        Requiere conexión a internet. Si falla, el frontend usa Web Speech API.
        """
        texto = _san(str(b.get("texto",""))).strip()[:500]
        lang  = str(b.get("lang","es")).strip()[:5]
        if not texto:
            self._err("texto requerido"); return
        try:
            from gtts import gTTS
            import io
            tts = gTTS(texto, lang=lang, slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            audio = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type","audio/mpeg")
            self.send_header("Content-Length",str(len(audio)))
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Cache-Control","no-cache")
            self.end_headers()
            self.wfile.write(audio)
        except ImportError:
            self._err("gTTS no instalado. Usa: pip install gtts",503)
        except Exception as ex:
            self._err(f"TTS error: {ex}",503)

    def do_PATCH(self):
        if not rl.ok(self._ip()): self._err("Rate limit",429); return
        p=urlparse(self.path).path; b=self._body()
        m=re.match(r"^/api/auto/workflows/([a-z0-9]+)$",p)
        if m: self._json({"ok":automations.actualizar_workflow(m.group(1),b)}); return
        self._err("Not found",404)

    def do_DELETE(self):
        if not rl.ok(self._ip()): self._err("Rate limit",429); return
        p=urlparse(self.path).path
        m=re.match(r"^/api/auto/workflows/([a-z0-9]+)$",p)
        if m: self._json({"ok":automations.eliminar_workflow(m.group(1))}); return
        self._err("Not found",404)


def iniciar(host="localhost",port=8765):
    server=HTTPServer((host,port),PakoHandler)
    print(f"\n  🌐 Platform → http://{host}:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt:
        memory.guardar_historial(); memory._guardar_actividad(); server.shutdown()

if __name__=="__main__": iniciar()
