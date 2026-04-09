#!/usr/bin/env python3
"""pako.py — PAKO Platform v4.0"""
import sys, argparse, os
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))

def main():
    p = argparse.ArgumentParser(description="PAKO Platform v4.0")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", default=8765, type=int)
    p.add_argument("--import-json", metavar="FILE")
    p.add_argument("--data-dir", default=None)
    args = p.parse_args()
    data_dir = args.data_dir or str(ROOT / "data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    if args.import_json:
        from backend.pako_memory import PakoMemory
        m = PakoMemory(data_dir=data_dir)
        n = m.cargar_desde_json_legacy(args.import_json)
        print(f"✅ {n} entradas importadas"); return
    os.environ["PAKO_DATA_DIR"] = data_dir
    from backend.pako_server import iniciar
    iniciar(host=args.host, port=args.port)

if __name__ == "__main__":
    main()
