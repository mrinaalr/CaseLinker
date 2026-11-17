"""ontology/MAPPING_PLAN.md is generated from the mapper and must match it."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_mapping_doc_matches_the_mapper():
    r = subprocess.run([sys.executable, str(REPO / "ontology" / "pipeline" / "mapping_table.py"), "--check"],
                       cwd=REPO, capture_output=True, text=True, env={"DATABASE_URL": "", "PATH": ""})
    assert r.returncode == 0, r.stderr or r.stdout
