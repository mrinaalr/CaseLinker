"""Build a PACER graph release from coded case bundles, and check a store against it.

A release is a folder ``state_machines/data/<release_id>/``:

    cases/<case_id>.json                    coded bundles (schema 2.0), the canonical input; they hold
                                            coder-written text, so they stay local (gitignored)
    derived/<case_id>.<threshold>.json      derived views (partial order, chains, levels)
    graphs/<case_id>.evidence.jsonld        evidence graph (canonical)
    graphs/<case_id>.trajectories.jsonld    derived trajectory graph (INFERRED threshold)
    manifest.json                           what was built from what, with hashes
    lifecycle.json                          the /lifecycle payload: codes, roles, dates, standing, pages; no text
    <release_id>.nq                         N-Quads for Oxigraph (written by ``nquads``)

Named graphs use stable logical IRIs; the manifest records which release filled them:

    urn:caselinker:pacer:<case_id>:evidence        source-grounded actions, participants, roles, provenance
    urn:caselinker:pacer:<case_id>:trajectories    derived order and affordance views; every lifecycle and
                                                   step names its derivation rule and evidence threshold

A load selects ``evidence`` or ``all`` (evidence plus trajectories); ``verify_store`` checks
that exactly the selected kinds are present and that each graph is of its kind.

``build`` refuses a bundle with validation errors and records each case's SHACL result
(full, partial or fails, upstream defects apart) and its review status, so a release can
never present unadjudicated coding as adjudicated: its ``review_mode`` is adjudicated, machine
(two independent coders agreed on everything published) or preview. ``verify_store`` compares a loaded
store with the manifest through SPARQL.

    python -m state_machines.graphs.release build <release_id> [--allow-unreviewed]
    python -m state_machines.graphs.release nquads <release_id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional

from state_machines.evidence import vocab as V

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "state_machines" / "data"
GRAPH_PREFIX = "urn:caselinker:pacer:"
LEGACY_PREFIX = "urn:pacer:kg:"
MANIFEST_VERSION = "1"
GRAPH_KINDS = ("evidence", "trajectories")
SELECTIONS = {"evidence": ("evidence",), "all": GRAPH_KINDS}
CLT = "https://w3id.org/caselinker/trajectory#"
INVESTIGATION = "https://ontology.caseontology.org/case/investigation/Investigation"
LIFECYCLE = "https://ontology.unifiedcyberontology.org/uco/action/ActionLifecycle"


def graph_iri(case_id: str, kind: str) -> str:
    if kind not in GRAPH_KINDS:
        raise ValueError(kind)
    return f"{GRAPH_PREFIX}{case_id}:{kind}"


def _sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _review_summary(bundle: dict) -> Dict[str, int]:
    c = Counter(e["review"]["status"] for e in bundle["events"])
    c.update(r["review"]["status"] for r in bundle["relations"] if r.get("review"))
    return dict(sorted(c.items()))


def build(release_id: str, *, data_root: Path = DATA, text_root: Optional[Path] = None,
          deny_lists: Optional[Dict[str, List[str]]] = None, allow_unreviewed: bool = False,
          mode: str = "adjudicated") -> dict:
    """Validate, derive, emit and SHACL-check every bundle of a release; write the manifest."""
    from state_machines.evidence.validate import release_errors
    from state_machines.graphs.emit import evidence_graph, serialize, trajectory_graph
    from state_machines.graphs.shacl import validation_report
    from state_machines.trajectories.derive import RULE_VERSION, derive, derived_json

    root = data_root / release_id
    bundles = sorted((root / "cases").glob("*.json"))
    if not bundles:
        raise SystemExit(f"no bundles under {root / 'cases'}")
    (root / "graphs").mkdir(exist_ok=True)
    (root / "derived").mkdir(exist_ok=True)
    cases = []
    for path in bundles:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        case_id = bundle["case_id"]
        problems = release_errors(bundle, text_root=text_root, deny_list=(deny_lists or {}).get(case_id, ()),
                                  mode="preview" if allow_unreviewed else mode)
        if problems:
            raise SystemExit(f"{case_id}: not releasable:\n  " + "\n  ".join(problems[:20]))
        for threshold in ("DIRECT", "INFERRED"):
            (root / "derived" / f"{case_id}.{threshold.lower()}.json").write_text(derived_json(bundle, threshold), encoding="utf-8")
        ev = serialize(evidence_graph(bundle))
        derived_inferred = derive(bundle, "INFERRED")
        chains = sum(len(t["trajectories"]) for t in derived_inferred["tracks"])
        tr = serialize(trajectory_graph(bundle, derived_inferred))
        (root / "graphs" / f"{case_id}.evidence.jsonld").write_text(ev, encoding="utf-8")
        (root / "graphs" / f"{case_id}.trajectories.jsonld").write_text(tr, encoding="utf-8")
        shacl = validation_report(ev, tr)
        cases.append({
            "case_id": case_id,
            "bundle_sha256": _sha(path.read_bytes()),
            "source_documents": sorted({d["sha256"] for d in bundle["documents"]}),
            "review": _review_summary(bundle),
            "passages": {"total": len(bundle["passages"]),
                         "ocr_text_only": sum(p["verification"].get("method") == "ocr_text_exact" for p in bundle["passages"])},
            "graphs": {"evidence": {"iri": graph_iri(case_id, "evidence"), "sha256": _sha(ev)},
                       "trajectories": {"iri": graph_iri(case_id, "trajectories"), "sha256": _sha(tr), "chains": chains}},
            "shacl": {"conformance": shacl["conformance"], "violations": len(shacl["violations"]),
                      "upstream_defect_violations": len(shacl["upstream_defect_violations"]),
                      "applicable_skipped": shacl["applicable_skipped"]},
        })
    from state_machines.graphs.shacl import EXTENSION
    manifest = {
        "manifest_version": MANIFEST_VERSION, "release_id": release_id,
        "schema_version": V.SCHEMA_VERSION, "codebook_version": V.CODEBOOK_VERSION,
        "derivation_rule": RULE_VERSION, "extension": EXTENSION.name,
        "sdk": (REPO / "ontology" / "SDK_VERSION").read_text(encoding="utf-8").split("\n")[0] if (REPO / "ontology" / "SDK_VERSION").is_file() else None,
        "review_mode": "preview" if allow_unreviewed else mode,
        "adjudicated": all(set(c["review"]) <= {"adjudicated"} for c in cases),
        "cases": cases,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    from state_machines.trajectories.payload import build_payload
    (root / "lifecycle.json").write_text(json.dumps(build_payload(root, from_bundles=True), sort_keys=True) + "\n",
                                         encoding="utf-8")
    return manifest


def nquads(release_id: str, *, data_root: Path = DATA, out: Optional[Path] = None, select: str = "all") -> Path:
    """Write the selected graph kinds of a release as N-Quads, one named graph per case and kind."""
    import rdflib

    root = data_root / release_id
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    ds = rdflib.Dataset()
    for c in manifest["cases"]:
        for kind, meta in c["graphs"].items():
            if kind not in SELECTIONS[select] or meta.get("chains") == 0:   # an empty graph has nothing to load
                continue
            text = (root / "graphs" / f"{c['case_id']}.{kind}.jsonld").read_text(encoding="utf-8")
            if _sha(text) != meta["sha256"]:
                raise SystemExit(f"{c['case_id']} {kind}: graph file does not match the manifest")
            g = ds.graph(rdflib.URIRef(meta["iri"]))
            g.parse(data=text, format="json-ld")
    out = out or root / f"{release_id}.nq"
    out.write_text(ds.serialize(format="nquads"), encoding="utf-8")
    return out


def verify_store(manifest: dict, query: Callable[[str], List[dict]], *, min_case_graphs: int = 0,
                 select: str = "all") -> List[str]:
    """Problems with a loaded store, checked through SPARQL (empty list = as expected).

    ``query(sparql)`` returns SPARQL JSON bindings as dicts of plain strings."""
    problems: List[str] = []
    rows = query("SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")
    counts = {r["g"]: int(r["n"]) for r in rows}
    expected = {meta["iri"] for c in manifest["cases"] for kind, meta in c["graphs"].items()
                if kind in SELECTIONS[select] and meta.get("chains") != 0}   # a case with no offender chain has no trajectory graph
    present = {g for g in counts if g.startswith(GRAPH_PREFIX)}
    for g in sorted(expected - present):
        problems.append(f"missing PACER graph {g}")
    for g in sorted(present - expected):
        problems.append(f"PACER graph not in this release: {g}")
    for g in sorted(expected & present):
        if counts[g] == 0:
            problems.append(f"empty PACER graph {g}")
    legacy = sorted(g for g in counts if g.startswith(LEGACY_PREFIX))
    if legacy:
        problems.append(f"{len(legacy)} superseded {LEGACY_PREFIX} graphs are still loaded")
    case_graphs = [g for g in counts if g.startswith("https://w3id.org/caselinker/resource/case/") and not g.endswith("/provenance")]
    if len(case_graphs) < min_case_graphs:
        problems.append(f"only {len(case_graphs)} press-release case graphs (expected at least {min_case_graphs})")
    def count(g: str, pattern: str) -> int:
        rows = query("SELECT (COUNT(*) AS ?n) WHERE { GRAPH <%s> { %s } }" % (g, pattern))
        return int(rows[0]["n"]) if rows else 0
    for c in manifest["cases"]:
        ev, tr = c["graphs"]["evidence"]["iri"], c["graphs"]["trajectories"]["iri"]
        if ev in present:   # an evidence graph: one investigation, no derived lifecycles
            if count(ev, f"?i a <{INVESTIGATION}>") != 1:
                problems.append(f"{ev}: expected exactly one investigation node")
            if count(ev, f"?l a <{LIFECYCLE}>"):
                problems.append(f"{ev}: holds derived trajectories")
        if tr in present:   # a trajectory graph: no investigation; every lifecycle states its rule and threshold
            if count(tr, f"?i a <{INVESTIGATION}>"):
                problems.append(f"{tr}: holds an investigation (evidence) node")
            unstamped = count(tr, f"?l a <{LIFECYCLE}> . FILTER NOT EXISTS {{ ?l <{CLT}derivationRule> ?r ; <{CLT}affordanceThreshold> ?t }}")
            if unstamped:
                problems.append(f"{tr}: {unstamped} trajectories without derivation rule and threshold")
    return problems


COMMITTED = ("graphs/*", "derived/*", "manifest.json", "lifecycle.json", "report.json", "REPORT.md", "ADJUDICATION.md")


def privacy_scan(release_id: str, text_root: Path, *, data_root: Path = DATA) -> dict:
    """Committed release files checked against each case's deny list (names from the caption) and
    every stored quote of six or more words. Returns counts and the files with hits (no hit text)."""
    import re
    root = data_root / release_id
    files = sorted({p for pat in COMMITTED for p in root.glob(pat) if p.is_file()})
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    lowered = {p: t.lower() for p, t in texts.items()}
    hits, checked_terms, checked_quotes = [], 0, 0
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for case in sorted(c["case_id"] for c in manifest["cases"]):
        deny_path, quote_path = text_root / case / "deny.json", text_root / case / "quotes.json"
        deny = json.loads(deny_path.read_text(encoding="utf-8")) if deny_path.is_file() else []
        quotes = json.loads(quote_path.read_text(encoding="utf-8")) if quote_path.is_file() else {}
        for term in deny:
            checked_terms += 1
            pat = re.compile(r"\b" + re.escape(term.lower()) + r"\b")
            hits += [{"case": case, "kind": "deny", "file": str(p.relative_to(root))} for p, t in lowered.items() if pat.search(t)]
        for q in quotes.values():
            q = q if isinstance(q, str) else ""
            if len(q.split()) >= 6:
                checked_quotes += 1
                probe = q[:60]
                hits += [{"case": case, "kind": "quote", "file": str(p.relative_to(root))} for p, t in texts.items() if probe in t]
    return {"files": len(files), "deny_terms": checked_terms, "quotes": checked_quotes, "hits": hits}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("release_id")
    b.add_argument("--mode", choices=("adjudicated", "machine", "preview"), default="adjudicated",
                   help="adjudicated: a named reviewer decided every item; machine: two independent coders agreed "
                        "on everything published; preview: anything that validates, local only")
    b.add_argument("--allow-unreviewed", action="store_true", help="same as --mode preview")
    n = sub.add_parser("nquads")
    n.add_argument("release_id")
    n.add_argument("--graphs", choices=sorted(SELECTIONS), default="all", help="evidence only, or evidence plus trajectories")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        m = build(args.release_id, allow_unreviewed=args.allow_unreviewed, mode=args.mode)
        print(json.dumps({"release": m["release_id"], "cases": len(m["cases"]), "review_mode": m["review_mode"]}))
    else:
        print(nquads(args.release_id, select=args.graphs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
