"""Conftest for green-hard fixture."""
import sys
from pathlib import Path

# Ensure src is on path
src_dir = Path(__file__).resolve().parents[2] / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
