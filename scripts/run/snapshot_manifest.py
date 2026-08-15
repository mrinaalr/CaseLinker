#!/usr/bin/env python3
"""Build or verify a CaseLinker vNext snapshot manifest."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def _main() -> int:
    from caselinker.snapshots.cli import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_main())
