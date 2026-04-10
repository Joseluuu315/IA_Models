#!/usr/bin/env python3
"""
pako_api_server.py — Lanzador del servidor API de PAKO

Uso:
  python pako_api_server.py                     → puerto 11434 (igual que Ollama)
  python pako_api_server.py --port 8000
  python pako_api_server.py --key mi-clave      → activa autenticación
  python pako_api_server.py --host 0.0.0.0      → accesible en toda la red
  python pako_api_server.py --port 11434 --key secret

Una vez arrancado, configura en Onyx / Open WebUI:
  Base URL: http://localhost:11434/v1
  API Key:  pako  (o la que hayas puesto con --key)
  Modelo:   pako
"""

import sys, os, argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PAKO_DATA_DIR", str(ROOT / "data"))


def main():
    parser = argparse.ArgumentParser(
        description="PAKO API Server v4.0 — Compatible con OpenAI / Onyx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python pako_api_server.py
  python pako_api_server.py --port 8000 --key supersecret
  python pako_api_server.py --host 0.0.0.0 --port 11434

Configurar en Onyx:
  Settings → AI Providers → OpenAI-compatible
  Base URL:  http://localhost:11434/v1
  API Key:   pako
  Model:     pako

Desde Python:
  from openai import OpenAI
  client = OpenAI(base_url="http://localhost:11434/v1", api_key="pako")
  r = client.chat.completions.create(
      model="pako",
      messages=[{"role":"user","content":"hola"}]
  )
  print(r.choices[0].message.content)
        """
    )
    parser.add_argument("--host",     default="0.0.0.0",  help="Host (default: 0.0.0.0)")
    parser.add_argument("--port",     default=11434, type=int, help="Puerto (default: 11434)")
    parser.add_argument("--key",      default="",    help="API key para autenticación (opcional)")
    parser.add_argument("--data-dir", default=None,  help="Directorio de datos")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["PAKO_DATA_DIR"] = str(Path(args.data_dir).resolve())

    Path(os.environ["PAKO_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

    from backend.pako_api import iniciar_api
    iniciar_api(host=args.host, port=args.port, api_key=args.key)


if __name__ == "__main__":
    main()
