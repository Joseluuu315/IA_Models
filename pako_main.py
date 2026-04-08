#!/usr/bin/env python3
"""
pako.py — Punto de entrada de PAKO.

Uso:
  python pako.py               → inicia en localhost:8765
  python pako.py --port 9000   → puerto personalizado
  python pako.py --host 0.0.0.0  → accesible desde la red local
  python pako.py --import-json paco_aprendido_informatica.json
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))


def main():
    parser = argparse.ArgumentParser(description="PAKO — IA Propia v2.0")
    parser.add_argument("--host",        default="localhost", help="Host (default: localhost)")
    parser.add_argument("--port",        default=8765, type=int, help="Puerto (default: 8765)")
    parser.add_argument("--import-json", metavar="ARCHIVO", help="Importar conocimiento desde JSON legacy")
    parser.add_argument("--data-dir",    default=None, help="Directorio de datos (default: ./data)")
    args = parser.parse_args()

    # Importación previa si se especifica
    if args.import_json:
        from backend.pako_memory import PakoMemory
        data_dir = args.data_dir or str(Path(__file__).parent / "data")
        mem = PakoMemory(data_dir=data_dir)
        n = mem.cargar_desde_json_legacy(args.import_json)
        print(f"✅ Importadas {n} entradas de '{args.import_json}'")
        return

    from backend.pako_server import iniciar
    iniciar(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
