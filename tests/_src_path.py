"""Puts ``src`` on ``sys.path`` for the tests (imported first by each test module)."""
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
