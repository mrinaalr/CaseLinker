#!/usr/bin/env python3
"""Corpus report CLI for location grounding.

Canonical implementation: ``src/Processing Layer/location_grounding.py``
(wired into merge_processing + features_to_cac). This script only runs the
batch report over local sqlite.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MOD = ROOT / "src" / "Processing Layer" / "location_grounding.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("location_grounding", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules["location_grounding"] = mod
    spec.loader.exec_module(mod)
    return mod.main()


if __name__ == "__main__":
    raise SystemExit(main())
