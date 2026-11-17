"""Docs render: balanced math with braced sub/superscripts, live relative links and anchors,
and well-formed tables, for every markdown file this work maintains."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted([*(ROOT / "state_machines").rglob("*.md"), ROOT / "ontology" / "PACER" / "README.md"])


def _strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "``", text)


def _slug(heading: str) -> str:
    h = re.sub(r"`|\*|\$[^$]*\$", lambda m: m.group(0).strip("`*") if m.group(0)[0] in "`*" else "", heading.strip())
    h = re.sub(r"[^\w\- ]", "", h.lower())
    return h.replace(" ", "-")


def _anchors(path: Path) -> set:
    return {_slug(m.group(1)) for m in re.finditer(r"^#{1,6} (.+)$", _strip_code(path.read_text(encoding="utf-8")), re.M)}


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_math_is_balanced_and_braced(doc):
    text = _strip_code(doc.read_text(encoding="utf-8"))
    assert text.count("$$") % 2 == 0, "unbalanced $$ block"
    inline = re.sub(r"\$\$.*?\$\$", "", text, flags=re.S)
    for para in inline.split("\n\n"):
        assert para.count("$") % 2 == 0, f"unbalanced inline math in: {para[:80]!r}"
    for m in re.finditer(r"\$\$(.+?)\$\$|\$([^$\n]+)\$", text, flags=re.S):
        body = m.group(1) or m.group(2)
        bad = re.findall(r"[_^][A-Za-z0-9\\]", body)
        assert not bad, f"unbraced sub/superscript {bad} in ${body.strip()[:60]}$ (write _{{x}})"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_and_anchors_resolve(doc):
    text = _strip_code(doc.read_text(encoding="utf-8"))
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"^[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        dest = (doc.parent / path).resolve() if path else doc
        assert dest.exists(), f"broken link {target}"
        if anchor and dest.suffix == ".md":
            assert anchor in _anchors(dest), f"missing anchor #{anchor} in {dest.relative_to(ROOT)}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_tables_are_well_formed(doc):
    lines = _strip_code(doc.read_text(encoding="utf-8")).splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            width = lines[i].count("|") - lines[i].count("\\|")
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                assert lines[j].count("|") - lines[j].count("\\|") == width, f"row width differs: {lines[j][:80]}"
                j += 1
            i = j
        else:
            i += 1
