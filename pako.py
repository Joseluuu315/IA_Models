#!/usr/bin/env python3
"""pako.py — Punto de entrada de PAKO v3.0"""

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser(description="PAKO v3.0")
    parser.add_argument("--host",        default="localhost")
    parser.add_argument("--port",        default=8765, type=int)
    parser.add_argument("--import-json", metavar="ARCHIVO")
    parser.add_argument("--data-dir",    default=None)
    args = parser.parse_args()

    data_dir = args.data_dir or str(ROOT / "data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    if args.import_json:
        from backend.pako_memory import PakoMemory
        mem = PakoMemory(data_dir=data_dir)
        n = mem.cargar_desde_json_legacy(args.import_json)
        print(f"Importadas {n} entradas de '{args.import_json}'")
        return

    import os
    os.environ["PAKO_DATA_DIR"] = data_dir
    from backend.pako_server import iniciar
    iniciar(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
