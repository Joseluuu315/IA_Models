#!/usr/bin/env python3
"""pako.py — Lanzador legacy (usa run.py para todo junto)"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PAKO_DATA_DIR", str(ROOT / "data"))

import argparse
p = argparse.ArgumentParser()
p.add_argument("--host", default="localhost")
p.add_argument("--port", default=8765, type=int)
p.add_argument("--import-json", metavar="F")
args = p.parse_args()

Path(os.environ["PAKO_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
if args.import_json:
    from backend.pako_memory import PakoMemory
    m = PakoMemory(data_dir=os.environ["PAKO_DATA_DIR"])
    print(f"Importadas {m.cargar_desde_json_legacy(args.import_json)} entradas")
else:
    from backend.pako_server import iniciar
    iniciar(host=args.host, port=args.port)
