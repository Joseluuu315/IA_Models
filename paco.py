#!/usr/bin/env python3
"""
paco.py — Punto de entrada principal.
Ejecuta: python paco.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    from paco_server import iniciar
    iniciar()
