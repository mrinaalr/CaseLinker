#!/usr/bin/env python3
"""Rewrite the committed PACER JSON-LD so every term and instance IRI is real (#57 §2).

The CASE-UCO SDK modeled these graphs with a few placeholders that can never
resolve. This script replaces them in place, deterministically:

* Instance IRIs under ``http(s)://example.org/…`` move to
  ``https://w3id.org/caselinker/resource/pacer/…`` (CaseLinker's dereferenceable space).
* ``example.org/ontology/{cryptoinv,rico,drugs,weapons}`` terms map to a declared
  legalproc / CAC term with the same meaning, or are dropped when none exists.
* ``legal-outcomes#FederalProsecution`` (wrong module) becomes
  ``usa-federal-law#FederalProsecution``.
* ``cacontology:startDate`` (undeclared) becomes ``dcterms:date`` at the precision
  the graph states; ``cacontology:leadAgency`` becomes a ``uco-core:Relationship``
  of kind ``Lead_Agency`` to the organization node with that name.

Run with ``--check`` to list what would change without writing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
PACER = REPO / "ontology" / "PACER"
RESOURCE = "https://w3id.org/caselinker/resource/pacer/"
_PLACEHOLDER_VOCAB = re.compile(r"^https?://example\.org/ontology/(cryptoinv|rico|drugs|weapons)/$")
_PLACEHOLDER_INSTANCE = re.compile(r"^https?://example\.org/(?!ontology/)(.*)$")

LEGALPROC = "https://ontology.caseontology.org/case/criminal/"
USA_FEDERAL = "https://cacontology.projectvic.org/usa-federal-law#"
CAC_ENTERPRISES = "https://cacontology.projectvic.org/extremist-enterprises#"
CAC = "https://cacontology.projectvic.org#"
UCO_CORE = "https://ontology.unifiedcyberontology.org/uco/core/"

# Placeholder local name -> declared IRI with the same meaning. Anything not listed is dropped.
TERM_MAP: Dict[str, str] = {
    "CriminalCharge": LEGALPROC + "CriminalCharge",
    "PleaAgreement": LEGALPROC + "PleaAgreement",
    "ForfeitureOrder": LEGALPROC + "ForfeitureOrder",
    "RestitutionOrder": LEGALPROC + "RestitutionOrder",
    "SentencingOutcome": LEGALPROC + "Sentence",
    "countNumber": LEGALPROC + "countNumber",
    "statuteCitation": LEGALPROC + "statuteCitation",
    "chargedWith": LEGALPROC + "chargedWith",
    "sentenceStatus": LEGALPROC + "sentenceStatus",
    "EnterpriseRole": CAC_ENTERPRISES + "EnterpriseRole",
    "RacketeeringEnterprise": CAC + "CriminalEnterprise",
    "predicateStatute": LEGALPROC + "statuteCitation",
    "roleFunction": UCO_CORE + "description",
    "enterpriseType": UCO_CORE + "description",
    "chargeDescription": UCO_CORE + "description",
    "restitutionDescription": UCO_CORE + "description",
    "sentenceDurationMonths": "https://cacontology.projectvic.org/legal-outcomes#sentenceDurationMonths",
    "moneyJudgmentAmount": LEGALPROC + "monetaryAmount",
    "moneyJudgmentCurrencyCode": LEGALPROC + "currencyCode",
    "pleaDate": "http://purl.org/dc/terms/date",
    "sentencingDate": "http://purl.org/dc/terms/date",
}

_RENAMES = {
    "https://cacontology.projectvic.org/legal-outcomes#FederalProsecution": USA_FEDERAL + "FederalProsecution",
}


def _expand(term: str, ctx: Dict[str, str]) -> str:
    if ":" in term and not term.startswith(("http://", "https://", "urn:", "_:")):
        prefix, local = term.split(":", 1)
        if prefix in ctx and isinstance(ctx[prefix], str):
            return ctx[prefix] + local
    return term


def _rebase(iri: str) -> str:
    m = _PLACEHOLDER_INSTANCE.match(iri)
    return RESOURCE + m.group(1) if m else iri


class _Remapper:
    def __init__(self, ctx: Dict[str, str]):
        self.ctx = ctx
        self.dropped: List[str] = []
        self.mapped: List[Tuple[str, str]] = []

    def term(self, compact: str) -> str | None:
        """Return the IRI to use for a key or type, or None to drop it."""
        full = _expand(compact, self.ctx)
        if full in _RENAMES:
            self.mapped.append((compact, _RENAMES[full]))
            return _RENAMES[full]
        for prefix, base in self.ctx.items():
            if isinstance(base, str) and _PLACEHOLDER_VOCAB.match(base) and full.startswith(base):
                local = full[len(base):]
                if local in TERM_MAP:
                    self.mapped.append((compact, TERM_MAP[local]))
                    return TERM_MAP[local]
                self.dropped.append(compact)
                return None
        return compact

    def value(self, v: Any) -> Any:
        if isinstance(v, list):
            return [x for x in (self.value(i) for i in v) if x is not _DROP]
        if isinstance(v, dict):
            return self.node(v)
        return v

    def node(self, n: Dict[str, Any]) -> Any:
        """A node with every placeholder term mapped or removed; ``_DROP`` if nothing real is left."""
        out: Dict[str, Any] = {}
        had_types = "@type" in n
        for k, v in n.items():
            if k == "@id" and isinstance(v, str):
                out[k] = _rebase(v)
            elif k == "@type":
                types = v if isinstance(v, list) else [v]
                kept = [t for t in (self.term(t) for t in types) if t is not None]
                if kept:
                    out[k] = kept if isinstance(v, list) else kept[0]
            elif k.startswith("@"):
                out[k] = self.value(v)
            else:
                key = self.term(k)
                if key is not None:
                    out[key] = self.value(v)
        if had_types and "@type" not in out and set(out) <= {"@id"}:
            return _DROP
        return out


_DROP = object()


def _lead_agency(graph: List[Dict[str, Any]], ctx: Dict[str, str], case_tag: str) -> List[str]:
    """``cacontology:leadAgency "Name"`` → Relationship to the organization named Name."""
    notes: List[str] = []
    orgs = {n.get("uco-core:name"): n.get("@id") for n in graph if isinstance(n, dict)}
    extra: List[Dict[str, Any]] = []
    for n in graph:
        if not isinstance(n, dict):
            continue
        for key in ("cacontology:leadAgency", CAC + "leadAgency"):
            if key in n:
                name = n.pop(key)
                target = orgs.get(name)
                if target is None:
                    raise SystemExit(f"{case_tag}: leadAgency {name!r} has no organization node")
                extra.append({
                    "@id": f"{n['@id']}-lead-agency",
                    "@type": "uco-core:Relationship",
                    "uco-core:source": {"@id": n["@id"]},
                    "uco-core:target": {"@id": target},
                    "uco-core:kindOfRelationship": "Lead_Agency",
                    "uco-core:isDirectional": True,
                })
                notes.append(f"leadAgency -> Relationship to {target}")
        for key in ("cacontology:startDate", CAC + "startDate"):
            if key in n:
                n["dcterms:date"] = n.pop(key)
                ctx.setdefault("dcterms", "http://purl.org/dc/terms/")
                notes.append("startDate -> dcterms:date")
    graph.extend(extra)
    return notes


def _dump_like(data: Any, original: str) -> str:
    """Serialize with the original file's indent, escaping and final newline, so the diff is only the remap."""
    m = re.search(r"\n( +)\S", original)
    indent = len(m.group(1)) if m else 2
    out = json.dumps(data, indent=indent, ensure_ascii="\\u" in original)
    return out + ("\n" if original.endswith("\n") else "")


def remap_file(path: Path, write: bool) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    ctx = data.get("@context")
    if not isinstance(ctx, dict):
        return {}
    before = json.dumps(data, sort_keys=True)
    r = _Remapper(ctx)
    graph = data.get("@graph") or []
    notes = _lead_agency(graph, ctx, path.name)
    data["@graph"] = [x for x in (r.node(n) if isinstance(n, dict) else n for n in graph) if x is not _DROP]
    for prefix, base in list(ctx.items()):
        if isinstance(base, str) and _PLACEHOLDER_VOCAB.match(base):
            del ctx[prefix]
        elif isinstance(base, str) and _PLACEHOLDER_INSTANCE.match(base):
            ctx[prefix] = _rebase(base)
    if any(USA_FEDERAL in t for _, t in r.mapped):
        ctx.setdefault("cacontology-usa-federal-law", USA_FEDERAL)
    after = json.dumps(data, sort_keys=True)
    if write and after != before:
        path.write_text(_dump_like(data, text), encoding="utf-8")
    return {"changed": after != before, "dropped": sorted(set(r.dropped)), "mapped": sorted(set(r.mapped)), "notes": notes}


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report changes, write nothing")
    args = ap.parse_args(argv)
    changed = 0
    for path in sorted(PACER.rglob("*.jsonld")):
        res = remap_file(path, write=not args.check)
        if res.get("changed"):
            changed += 1
            rel = path.relative_to(REPO)
            print(f"{rel}: mapped {len(res['mapped'])}, dropped {len(res['dropped'])} {res['dropped'] or ''} {res['notes'] or ''}")
    print(f"{changed} file(s) {'would change' if args.check else 'rewritten'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
