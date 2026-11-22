"""The transition-enumeration scripts match their saved output, and the second derivation agrees."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "ontology" / "platform_affordance_evidence" / "transition_enumeration"
ENV = dict(os.environ, PYTHONHASHSEED="0")


def _run(script: Path, cwd: Path) -> str:
    result = subprocess.run(["python3", str(script)], cwd=cwd, env=ENV, check=True, capture_output=True, text=True)
    return result.stdout


def _runs(text: str, label: str) -> tuple:
    """(runs in P, runs in P+Q) from a printed line. The P count includes the empty run."""
    match = re.search(rf"{label}\s*(\d+)\s*(?:runs P\+Q|runs P\+Q:)\s*(\d+)", text)
    if match is None:
        match = re.search(rf"{label}[^\n]*?(\d+)\D+(\d+)", text)
    assert match, text
    return int(match.group(1)), int(match.group(2))


def test_canonical_scripts_match_the_saved_output():
    check = _run(DIR / "enumerate_transitions.py", DIR)
    variants = _run(DIR / "enumerate_transition_variants.py", DIR)
    assert check == (DIR / "enumerate_transitions.out").read_text(encoding="utf-8")
    assert variants == (DIR / "enumerate_transition_variants.out").read_text(encoding="utf-8")
    assert check.endswith("ALL CHECKS PASSED\n")


def test_independent_checks_agree_on_the_run_counts():
    variants = (DIR / "enumerate_transition_variants.out").read_text(encoding="utf-8")
    primary = variants.split("== PRIMARY (no t2)", 1)[1]
    canonical = _runs(primary, "runs P")
    enum_text = _run(DIR / "independent_checks" / "enum.py", DIR)
    v2_text = _run(DIR / "independent_checks" / "recompute_transition_sets.py", DIR)
    enum_primary = enum_text.split("co-present", 1)[0]
    assert _runs(enum_primary, "runs P:") == canonical
    assert _runs(v2_text, "runs P") == canonical
    # Verified by running the three scripts: P has 8 runs, counting the empty run, and P+Q has 19.
    assert canonical == (8, 19)
