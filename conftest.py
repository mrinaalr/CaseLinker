"""Keep this repository's tests package ahead of any dependency named tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
root = str(ROOT)
if root in sys.path:
    sys.path.remove(root)
sys.path.insert(0, root)
for name in list(sys.modules):
    if name != "tests" and not name.startswith("tests."):
        continue
    module = sys.modules.get(name)
    origin = getattr(module, "__file__", "") or ""
    if origin and not origin.startswith(root):
        del sys.modules[name]
