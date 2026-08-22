"""Put Storage Layer on sys.path the same way src/main.py does."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "src" / "Storage Layer"
if str(STORAGE) not in sys.path:
    sys.path.insert(0, str(STORAGE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
