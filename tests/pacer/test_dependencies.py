"""The research SDK stays out of the Railway install and out of runtime imports."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIRS = ("run", "caselinker_mcp", "src")


def test_runtime_requirements_have_no_vcs_or_sdk_pins():
    text = (ROOT / "requirements.txt").read_text()
    assert "git+" not in text and "case-uco" not in text


def test_research_requirements_pin_the_sdk_to_an_immutable_commit():
    text = (ROOT / "requirements-research.txt").read_text()
    line = next(l for l in text.splitlines() if l.startswith("case-uco @"))
    assert "@3455cc10682434fbff4ff95e6b9e887700287632#" in line
    assert "3455cc10682434fbff4ff95e6b9e887700287632" in (ROOT / "ontology" / "SDK_VERSION").read_text()


def test_no_runtime_module_imports_the_sdk():
    offenders = []
    for d in RUNTIME_DIRS:
        for path in (ROOT / d).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                        [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                if any(n.split(".")[0] == "case_uco" or n == "state_machines.graphs.emit" for n in names):
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
