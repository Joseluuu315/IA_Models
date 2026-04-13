#!/usr/bin/env python3
"""
run.py — Lanzador único de PAKO v5.0
=====================================
Arranca TODO desde un solo archivo:
  - Plataforma web  (chat + automatizaciones + conocimiento + ajustes)
  - API OpenAI-compatible (para Onyx, Open WebUI, scripts externos)

Uso:
  python run.py                         # todo en puertos por defecto
  python run.py --no-api                # solo la plataforma web
  python run.py --no-platform           # solo la API
  python run.py --web-port 8080         # puerto web personalizado
  python run.py --api-port 11435        # puerto API personalizado
  python run.py --api-key secreto       # proteger la API con clave
  python run.py --host 0.0.0.0          # exponer en red local
  python run.py --import conocimiento.json  # importar base de conocimiento

Conectar Onyx / Open WebUI:
  Base URL:  http://localhost:11434/v1
  API Key:   pako   (o la que pongas con --api-key)
  Modelo:    pako
"""

import sys
import os
import time
import argparse
import threading
import signal
from pathlib import Path

# ── Setup de paths ────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))


# ══════════════════════════════════════════════════════════════════
# ARGS
# ══════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="PAKO v5.0 — Lanzador único",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    p.add_argument("--host",         default="localhost",
                   help="Host (default: localhost | usa 0.0.0.0 para red local)")
    p.add_argument("--web-port",     default=8765, type=int,
                   help="Puerto de la plataforma web (default: 8765)")
    p.add_argument("--api-port",     default=11434, type=int,
                   help="Puerto de la API OpenAI-compatible (default: 11434)")
    p.add_argument("--api-key",      default="",
                   help="API key para proteger la API (opcional)")
    p.add_argument("--data-dir",     default=None,
                   help="Directorio de datos (default: ./data)")
    p.add_argument("--import",       dest="import_file", metavar="ARCHIVO",
                   help="Importar conocimiento desde JSON legacy antes de arrancar")
    p.add_argument("--no-api",       action="store_true",
                   help="No arrancar el servidor API")
    p.add_argument("--no-platform",  action="store_true",
                   help="No arrancar la plataforma web")
    p.add_argument("--version",      action="store_true",
                   help="Mostrar versión y salir")
    return p.parse_args()


# ══════════════════════════════════════════════════════════════════
# SHARED ENGINE — un único motor compartido entre ambos servidores
# ══════════════════════════════════════════════════════════════════

def build_engine(data_dir: str):
    """Construye e inicializa el motor PAKO una sola vez."""
    from pako_memory      import PakoMemory
    from pako_brain       import PakoBrain
    from pako_web_agent   import PakoWebAgent
    from pako_github_agent import PakoGitHubAgent
    from pako_file_agent  import PakoFileAgent
    from pako_automations import PakoAutomations

    memory       = PakoMemory(data_dir=data_dir)
    brain        = PakoBrain(memory=memory)
    web_agent    = PakoWebAgent(memory=memory)
    github_agent = PakoGitHubAgent(memory=memory)
    file_agent   = PakoFileAgent(memory=memory)
    automations  = PakoAutomations(data_dir=data_dir, memory=memory)

    brain.web_agent    = web_agent
    brain.github_agent = github_agent
    brain.file_agent   = file_agent
    brain.automations  = automations
    automations.set_brain(brain)

    # Cargar base de conocimiento
    for candidate in [
        Path(data_dir) / "pako_conocimiento.json",
        ROOT / "paco_aprendido.json",
        ROOT / "pako_conocimiento_base.json",
    ]:
        if candidate.exists():
            n = memory.cargar_desde_json_legacy(str(candidate))
            if n > 0:
                print(f"  📚 {n} entradas cargadas de '{candidate.name}'")
                break

    # Reconectar GitHub si hay token guardado
    if memory.get_config("github_token", ""):
        if github_agent.reconectar():
            print(f"  🐙 GitHub: @{github_agent._usuario}")

    total = memory.stats()["total"]
    print(f"  🧠 Motor listo — {total} conceptos en memoria")

    return {
        "memory":       memory,
        "brain":        brain,
        "web_agent":    web_agent,
        "github_agent": github_agent,
        "file_agent":   file_agent,
        "automations":  automations,
    }


# ══════════════════════════════════════════════════════════════════
# ARRANQUE DE SERVIDORES
# ══════════════════════════════════════════════════════════════════

def start_platform(engine: dict, host: str, port: int) -> threading.Thread:
    """Arranca la plataforma web en un hilo separado."""
    import pako_server as srv

    # Inyectar el engine compartido en el módulo del servidor
    srv.memory       = engine["memory"]
    srv.brain        = engine["brain"]
    srv.web_agent    = engine["web_agent"]
    srv.github_agent = engine["github_agent"]
    srv.file_agent   = engine["file_agent"]
    srv.automations  = engine["automations"]

    from http.server import HTTPServer
    server = HTTPServer((host, port), srv.PakoHandler)

    def run():
        try:
            server.serve_forever()
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True, name="PakoPlatform")
    t.server = server
    t.start()
    return t


def start_api(engine: dict, host: str, port: int, api_key: str = "") -> threading.Thread:
    """Arranca la API OpenAI-compatible en un hilo separado."""
    import pako_api as api_mod

    # Inyectar el engine compartido
    api_mod.memory       = engine["memory"]
    api_mod.brain        = engine["brain"]
    api_mod.web_agent    = engine["web_agent"]
    api_mod.github_agent = engine["github_agent"]
    api_mod.file_agent   = engine["file_agent"]

    if api_key:
        api_mod.set_api_key(api_key)
        engine["memory"].set_config("api_key", api_key)

    from http.server import HTTPServer
    server = HTTPServer((host, port), api_mod.PakoAPIHandler)

    def run():
        try:
            server.serve_forever()
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True, name="PakoAPI")
    t.server = server
    t.start()
    return t


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    args = parse_args()

    if args.version:
        print("PAKO Platform v5.0"); return

    if args.no_api and args.no_platform:
        print("❌ No puedes usar --no-api y --no-platform a la vez."); return

    # Directorio de datos
    data_dir = args.data_dir or str(ROOT / "data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    os.environ["PAKO_DATA_DIR"] = data_dir

    # ── Banner ────────────────────────────────────────────────────
    print(f"""
╔═══════════════════════════════════════════════╗
║          🧠  PAKO Platform  v5.0              ║
╚═══════════════════════════════════════════════╝
  Iniciando motor...
""")

    # ── Importar conocimiento previo si se pide ───────────────────
    if args.import_file:
        from pako_memory import PakoMemory
        tmp = PakoMemory(data_dir=data_dir)
        n   = tmp.cargar_desde_json_legacy(args.import_file)
        print(f"  ✅ Importadas {n} entradas de '{args.import_file}'")

    # ── Construir el motor compartido ─────────────────────────────
    engine = build_engine(data_dir)

    # ── Arrancar servidores ───────────────────────────────────────
    threads = []

    if not args.no_platform:
        t_platform = start_platform(engine, args.host, args.web_port)
        threads.append(("platform", t_platform, args.host, args.web_port))

    if not args.no_api:
        t_api = start_api(engine, args.host, args.api_port, args.api_key)
        threads.append(("api", t_api, args.host, args.api_port))

    # Pequeña espera para que arranquen
    time.sleep(0.3)

    # ── Info de acceso ────────────────────────────────────────────
    local_host = "localhost" if args.host == "0.0.0.0" else args.host
    print(f"""
┌─────────────────────────────────────────────────┐""")

    if not args.no_platform:
        print(f"│  🌐 Plataforma web → http://{local_host}:{args.web_port:<18}│")

    if not args.no_api:
        key_hint = args.api_key if args.api_key else "pako (sin autenticación)"
        print(f"│  🔌 API OpenAI    → http://{local_host}:{args.api_port:<18}│")
        print(f"│     Docs API      → http://{local_host}:{args.api_port}/api/docs{' '*(12-len(str(args.api_port)))}│")
        print(f"│     API Key       → {key_hint:<29}│")

    print(f"""│                                                 │
│  Conectar Onyx / Open WebUI:                    │
│    base_url = "http://{local_host}:{args.api_port}/v1"{'':>{max(0,15-len(str(args.api_port)))}}│
│    model    = "pako"                            │
│                                                 │
│  Ctrl+C para detener                            │
└─────────────────────────────────────────────────┘
""")

    # ── Shutdown handler ──────────────────────────────────────────
    def shutdown(sig, frame):
        print("\n\n  👋 Deteniendo PAKO...")
        for name, t, _, _ in threads:
            if hasattr(t, "server"):
                t.server.shutdown()
                print(f"  ✅ {name} detenido")
        engine["memory"].guardar_historial()
        engine["memory"]._guardar_actividad()
        print("  💾 Datos guardados. ¡Hasta pronto!\n")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── Loop principal ────────────────────────────────────────────
    try:
        while True:
            time.sleep(1)
            # Verificar que los hilos siguen vivos
            for name, t, host, port in threads:
                if not t.is_alive():
                    print(f"  ⚠️  Servidor {name} se detuvo inesperadamente.")
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
