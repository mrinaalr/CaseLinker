"""Object link text on /resource pages prefers the target node's rdfs:label."""

from __future__ import annotations

import sys
from pathlib import Path

import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import RDFS

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "run"
sys.path.insert(0, str(RUN))
import deref  # noqa: E402


def test_render_object_uses_rdfs_label_when_present():
    g = rdflib.Graph()
    target = URIRef("https://w3id.org/caselinker/resource/case/x/target/1")
    g.add((target, RDFS.label, Literal("passage · age 22")))
    html = deref._render_object(target, g)
    assert "passage · age 22" in html
    assert ">target<" not in html
    assert 'href="/resource/case/x/target/1"' in html


def test_render_object_falls_back_to_short_path_without_label():
    g = rdflib.Graph()
    target = URIRef("https://w3id.org/caselinker/resource/case/x/target/1")
    html = deref._render_object(target, g)
    assert "target/1" in html or "target" in html
