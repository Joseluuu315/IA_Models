"""
Test configuration for PAKO brain tests.

Ensures the `backend/` directory is importable so tests can do
`from pako_brain import ...` etc.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
