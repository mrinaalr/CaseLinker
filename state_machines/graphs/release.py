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
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional

from state_machines.evidence import vocab as V

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "state_machines" / "data"
GRAPH_PREFIX = "urn:caselinker:pacer:"
RELEASE_GRAPH_PREFIX = "urn:caselinker:pacer-release:"   # one graph per release: how its case graphs were made
LEGACY_PREFIX = "urn:pacer:kg:"
MANIFEST_VERSION = "1"
GRAPH_KINDS = ("evidence", "trajectories", "observations")
SELECTIONS = {"evidence": ("evidence",), "all": GRAPH_KINDS}
CLT = "https://w3id.org/caselinker/trajectory#"
OA = "http://www.w3.org/ns/oa#"
INVESTIGATION = "https://ontology.caseontology.org/case/investigation/Investigation"
LIFECYCLE = "https://ontology.unifiedcyberontology.org/uco/action/ActionLifecycle"


def graph_iri(case_id: str, kind: str) -> str:
    if kind not in GRAPH_KINDS:
        raise ValueError(kind)
    return f"{GRAPH_PREFIX}{case_id}:{kind}"


def _sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _review_summary(bundle: dict) -> Dict[str, int]:
    """Review status of the acts. Relations are counted apart (``relations``), since a machine release makes some by rule."""
    return dict(sorted(Counter(e["review"]["status"] for e in bundle["events"]).items()))


def _registry_loaded() -> bool:
    """Whether the capability registry this process would derive against has any platforms.

    A missing source directory is an empty registry. Reading a release does not call this.
    """
    from state_machines.trajectories.affordances import load as load_registry

    try:
        return bool(load_registry().get("platforms"))
    except FileNotFoundError:
        return False


def _v2_release_guard() -> bool:
    """A v2 flag is on, so an empty registry is refused unless the switch allows it."""
    from state_machines.coding.workflow import v2_active
    return v2_active()


def build(release_id: str, *, data_root: Path = DATA, text_root: Optional[Path] = None,
          deny_lists: Optional[Dict[str, List[str]]] = None, allow_unreviewed: bool = False,
          mode: str = "adjudicated", observations: bool = False, coders_root: Optional[Path] = None,
          allow_empty_registry: bool = False, require_registry: bool = False,
          frame_drops: Optional[dict] = None) -> dict:
    """Validate, derive, emit and SHACL-check every bundle of a release; write the manifest.

    ``observations`` also reads every page of each case for the platforms and features it names
    (state_machines/observations), writes ``observations/<case>.json`` and a third graph per case."""
    root = data_root / release_id
    bundles = sorted((root / "cases").glob("*.json"))
    if not bundles:
        raise SystemExit(f"no bundles under {root / 'cases'}")
    # A new release records whether the registry loaded. pacer-v1 was built when it did not;
    # reading that release does not come through here. The check is before the graph
    # libraries load, so a refusal does not depend on them.
    loaded = _registry_loaded()
    if (require_registry or _v2_release_guard()) and not loaded and not allow_empty_registry:
        raise SystemExit("refusing to build a release with capability_registry_loaded false; "
                         "pass --allow-empty-registry to build one anyway")
    from state_machines.evidence.validate import release_errors
    from state_machines.graphs.emit import evidence_graph, observation_graph, serialize, trajectory_graph
    from state_machines.graphs.shacl import validation_report
    from state_machines.trajectories.act_policy import POLICY_ID
    from state_machines.trajectories.derive import RULE_VERSION, derive, derived_json

    (root / "graphs").mkdir(exist_ok=True)
    (root / "derived").mkdir(exist_ok=True)
    cases = []
    for path in bundles:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        case_id = bundle["case_id"]
        if bundle.get("no_acts") is True or bundle.get("no_agreed_acts") is True:
            if bundle.get("events"):
                raise SystemExit(f"{case_id}: a record of no published acts cannot contain events")
        else:
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
        graphs = {"evidence": {"iri": graph_iri(case_id, "evidence"), "sha256": _sha(ev)},
                  "trajectories": {"iri": graph_iri(case_id, "trajectories"), "sha256": _sha(tr), "chains": chains}}
        documents = [ev, tr]
        observed = None
        if not observations:      # nothing left from an earlier build that had them
            for stale in (root / "observations" / f"{case_id}.json", root / "graphs" / f"{case_id}.observations.jsonld"):
                stale.unlink(missing_ok=True)
        if observations:
            from state_machines.observations import observe as O
            listed = text_root / case_id / "sources.json"
            if listed.is_file():
                stored = {d["sha256"] for d in json.loads(listed.read_text(encoding="utf-8"))["documents"]}
                if stored != {d["sha256"] for d in bundle["documents"]}:
                    raise SystemExit(f"{case_id}: the coded bundle and the text store list different documents; "
                                     "recode the case before building (a filing was added or removed)")
            coded = {}
            for name in ("coder_A", "coder_B"):       # each coder's own bundle, for the disputed tier; absent in an adjudicated build
                coder_file = (coders_root / name / f"{case_id}.json") if coders_root else None
                if coder_file and coder_file.is_file():
                    coded[name] = json.loads(coder_file.read_text(encoding="utf-8"))
            doc = O.relate(O.observe(case_id, text_root), bundle, text_root, coded if len(coded) == 2 else None)
            unsound = O.check(doc, text_root, bundle)
            if unsound:
                raise SystemExit(f"{case_id}: observations not sound:\n  " + "\n  ".join(unsound[:20]))
            (root / "observations").mkdir(exist_ok=True)
            (root / "observations" / f"{case_id}.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            ob = serialize(observation_graph(bundle, doc))
            (root / "graphs" / f"{case_id}.observations.jsonld").write_text(ob, encoding="utf-8")
            observed = O.summary(doc)
            graphs["observations"] = {"iri": graph_iri(case_id, "observations"), "sha256": _sha(ob), "observations": observed["observations"]}
            documents.append(ob)
        shacl = validation_report(*documents)
        cases.append({
            "case_id": case_id,
            "bundle_sha256": _sha(path.read_bytes()),
            "source_documents": sorted({d["sha256"] for d in bundle["documents"]}),
            "review": _review_summary(bundle),
            "relations": dict(sorted(Counter((r.get("review") or {}).get("status", "adjudicated") for r in bundle["relations"]).items())),
            "passages": {"total": len(bundle["passages"]),
                         "ocr_text_only": sum(p["verification"].get("method") == "ocr_text_exact" for p in bundle["passages"])},
            "graphs": graphs,
            **({"observations": observed} if observed is not None else {}),
            "shacl": {"conformance": shacl["conformance"], "violations": len(shacl["violations"]),
                      "upstream_defect_violations": len(shacl["upstream_defect_violations"]),
                      "applicable_skipped": shacl["applicable_skipped"]},
            **({"no_acts": True} if bundle.get("no_acts") is True else {}),
            **({"no_agreed_acts": True} if bundle.get("no_agreed_acts") is True else {}),
            **({"pages": bundle["pages"], "model_pages": bundle["model_pages"], "unparsable": bundle["unparsable"]}
               if "pages" in bundle else {}),
        })
    from state_machines.graphs.shacl import EXTENSION
    manifest = {
        "manifest_version": MANIFEST_VERSION, "release_id": release_id,
        "schema_version": V.SCHEMA_VERSION, "codebook_version": V.CODEBOOK_VERSION,
        "derivation_rule": RULE_VERSION, "act_policy": POLICY_ID,
        "capability_registry_loaded": loaded,
        "extension": EXTENSION.name,
        "sdk": sdk_pin(),
        "review_mode": "preview" if allow_unreviewed else mode,
        "adjudicated": all(set(c["review"]) <= {"adjudicated"} for c in cases),
        "cases": cases,
    }
    if os.environ.get("CASELINKER_MEANS_PARSER") == "dep":
        manifest["means_parser"] = _means_parser_record()
    from state_machines.coding.parties import snapshot_record
    recorded = snapshot_record()
    if recorded:
        manifest["party_snapshot"] = recorded["sha256"]
    if _v2_release_guard():
        from state_machines.coding.workflow import spacy_model_record
        manifest["spacy_model"] = spacy_model_record()
    if os.environ.get("CASELINKER_EXTRACTOR") == "frame-1.0" and frame_drops is not None:
        manifest["frame_drops"] = frame_drops
    if allow_empty_registry:
        manifest["allow_empty_registry"] = True
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    from state_machines.trajectories.payload import build_payload
    (root / "lifecycle.json").write_text(json.dumps(build_payload(root, from_bundles=True), sort_keys=True) + "\n",
                                         encoding="utf-8")
    if observations:      # the case-level research table, from the files just written
        from state_machines.observations.table import write as write_table
        write_table(root)
        from state_machines.observations.affordance_matrix import write as write_matrix
        write_matrix(root)
    else:
        for stale in ("research_table.json", "research_table.csv", "validation.json", "affordance_matrix.json", "affordance_matrix.csv",
                      "affordance_case_grid.csv"):
            (root / stale).unlink(missing_ok=True)
    return manifest


def release_graph_iri(release_id: str) -> str:
    return f"{RELEASE_GRAPH_PREFIX}{release_id}"


_REVIEW_MODE_TEXT = {
    "machine": "Machine-coded: two local model coders coded every case independently and a fixed rule "
               "published only what both coded; no person reviewed the real cases. clt:reviewStatus "
               "\"agreed\" on an act means the two model coders agreed.",
    "adjudicated": "Adjudicated: a named reviewer decided every disagreement between the coders.",
    "preview": "Preview: unreviewed coding, not for a public store.",
}


def release_graph(manifest: dict, ds, *, models: Optional[dict] = None, select: str = "all") -> None:
    """Add the release graph: review mode, act policy, coder models, and every case graph it covers,
    so a query over the store can tell how the acts in a case graph were published."""
    import rdflib
    from rdflib.namespace import DCTERMS, PROV

    clt = rdflib.Namespace(CLT)
    rid = manifest["release_id"]
    node = rdflib.URIRef(release_graph_iri(rid))
    g = ds.graph(node)
    mode = manifest["review_mode"]
    g.add((node, rdflib.RDF.type, PROV.Entity))
    g.add((node, DCTERMS.identifier, rdflib.Literal(rid)))
    g.add((node, clt.reviewMode, rdflib.Literal(mode)))
    g.add((node, DCTERMS.description, rdflib.Literal(_REVIEW_MODE_TEXT.get(mode, mode))))
    for key, prop in (("act_policy", clt.actPolicy), ("derivation_rule", clt.derivationRule)):
        if manifest.get(key):
            g.add((node, prop, rdflib.Literal(manifest[key])))
    for coder in sorted(((models or {}).get("coders") or {}).values(), key=lambda c: c.get("model", "")):
        g.add((node, clt.coderModel, rdflib.Literal(f"{coder['model']}@{coder['digest']}")))
    for c in manifest["cases"]:
        for kind, meta in c["graphs"].items():
            if kind in SELECTIONS[select] and 0 not in (meta.get("chains"), meta.get("observations")):
                g.add((node, DCTERMS.hasPart, rdflib.URIRef(meta["iri"])))


def nquads(release_id: str, *, data_root: Path = DATA, out: Optional[Path] = None, select: str = "all") -> Path:
    """Write the selected graph kinds of a release as N-Quads, one named graph per case and kind,
    plus the release graph (``release_graph``)."""
    import rdflib

    root = data_root / release_id
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    report = root / "report.json"
    models = json.loads(report.read_text(encoding="utf-8")).get("models") if report.is_file() else None
    ds = rdflib.Dataset()
    release_graph(manifest, ds, models=models, select=select)
    for c in manifest["cases"]:
        for kind, meta in c["graphs"].items():
            if kind not in SELECTIONS[select] or 0 in (meta.get("chains"), meta.get("observations")):   # an empty graph has nothing to load
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
                if kind in SELECTIONS[select] and 0 not in (meta.get("chains"), meta.get("observations"))}   # no chain, or nothing observed: no graph
    present = {g for g in counts if g.startswith(GRAPH_PREFIX)}
    for g in sorted(expected - present):
        problems.append(f"missing PACER graph {g}")
    for g in sorted(present - expected):
        problems.append(f"PACER graph not in this release: {g}")
    for g in sorted(expected & present):
        if counts[g] == 0:
            problems.append(f"empty PACER graph {g}")
    rel = release_graph_iri(manifest["release_id"])
    if rel not in counts:
        problems.append(f"missing release graph {rel}")
    else:
        modes = [r["m"] for r in query("SELECT ?m WHERE { GRAPH <%s> { <%s> <%sreviewMode> ?m } }" % (rel, rel, CLT))]
        if modes != [manifest["review_mode"]]:
            problems.append(f"{rel}: review mode {modes} does not match the manifest's {manifest['review_mode']!r}")
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
        ob = c["graphs"].get("observations", {}).get("iri")
        if ob in present:   # an observation graph: annotations only, each stamped with its rule
            if count(ob, f"?i a <{INVESTIGATION}>") or count(ob, f"?l a <{LIFECYCLE}>"):
                problems.append(f"{ob}: holds evidence or trajectory nodes")
            if not count(ob, f"?a <{OA}motivatedBy> ?m"):
                problems.append(f"{ob}: no observation")
            unstamped = count(ob, f"?a <{OA}motivatedBy> ?m . FILTER NOT EXISTS {{ ?a <{CLT}derivationRule> ?r }}")
            if unstamped:
                problems.append(f"{ob}: {unstamped} observations without a derivation rule")
    return problems


COMMITTED = ("graphs/*", "derived/*", "observations/*", "research_table.json", "research_table.csv", "affordance_matrix.json", "affordance_matrix.csv",
             "affordance_case_grid.csv", "validation.json", "manifest.json", "lifecycle.json", "report.json", "REPORT.md", "ADJUDICATION.md")


def _means_parser_record() -> dict:
    """The dependency parser this release was built with. Null fields when it is off."""
    from state_machines.observations.means_parse import manifest_parser
    return manifest_parser()


def sdk_pin() -> Optional[str]:
    """The pinned CASE-UCO SDK that writes the graphs, as "<tag> <commit>", from ontology/SDK_VERSION."""
    import re
    path = REPO / "ontology" / "SDK_VERSION"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    tag, commit = re.search(r"^\s*tag:\s*(\S+)", text, re.M), re.search(r"^\s*commit:\s*([0-9a-f]{40})", text, re.M)
    return f"{tag.group(1)} {commit.group(1)}" if tag and commit else None


def privacy_scan(release_id: str, text_root: Path, *, data_root: Path = DATA) -> dict:
    """Committed release files checked against each case's deny list (names from the caption) and
    every stored quote of six or more words; and, in machine-coded bundles, every platform name and
    feature word checked against the fixed lists they must come from (``open_text`` hits).
    Returns counts and the files with hits (no hit text)."""
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
    ledger = REPO / "ontology" / "PACER" / "BULK_FOLDER" / "pacer_cost.csv"       # tracked: case ids, docket numbers, document types, costs
    if ledger.is_file():
        low = ledger.read_text(encoding="utf-8", errors="replace").lower()
        for folder in sorted(p for p in text_root.iterdir() if (p / "deny.json").is_file()) if text_root.is_dir() else []:
            for term in json.loads((folder / "deny.json").read_text(encoding="utf-8")):
                if len(term) > 3 and re.search(r"\b" + re.escape(term.lower()) + r"\b", low):
                    hits.append({"case": folder.name, "kind": "deny", "file": "ontology/PACER/BULK_FOLDER/pacer_cost.csv"})

    from state_machines.coding.enrich import FEATURES, known_platform
    words = {ph.lower() for phrases in FEATURES.values() for ph in phrases}
    open_values = 0
    for path in sorted((root / "cases").glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not str(bundle["coding"].get("note", "")).startswith("machine resolution"):
            continue
        for d in bundle["documents"]:      # a path on disk can carry a surname: only the normalized form is published
            open_values += 1
            tail = d["source_path"].rsplit(" -- ", 1)[-1]
            if not re.fullmatch(r"[A-Z_]+/(?:pacer -- )?" + re.escape(bundle["case_id"]) + r" -- [a-z0-9 _]+\.pdf", d["source_path"]) \
                    or tail not in {d["doc_id"].replace("_", " ") + ".pdf", d["doc_type"].replace("_", " ") + ".pdf", d["doc_type"] + ".pdf"}:
                hits.append({"case": bundle["case_id"], "kind": "open_text", "file": f"cases/{path.name}"})
        for e in bundle["events"]:
            values = ([(i["platform_surface"], known_platform) for i in e["platform_interactions"]]
                      + [(m["platform_surface"], known_platform) for m in e["platform_mentions"]]
                      + [(a.get("platform_surface"), known_platform) for a in e["affordances"] if a.get("platform_surface")]
                      + [(a["feature_term"], lambda v: v.lower() in words) for a in e["affordances"] if a.get("feature_term")])
            for value, ok in values:
                open_values += 1
                if not ok(value):
                    hits.append({"case": bundle["case_id"], "kind": "open_text", "file": f"cases/{path.name}"})
    from state_machines.observations.observe import FEATURES as OBSERVED_FEATURES, listed_platform, listed_service_term
    phrases = {(cls, ph) for cls, group in OBSERVED_FEATURES.items() for ph in group}
    for path in sorted((root / "observations").glob("*.json")):      # observation files: listed names and phrases only
        doc = json.loads(path.read_text(encoding="utf-8"))
        for o in doc["observations"]:
            open_values += 1
            ok = listed_platform(o) if o["kind"] == "platform" else listed_service_term(o) if o["kind"] == "service_description" else (o["feature_class"], o["feature_term"]) in phrases
            if not ok:
                hits.append({"case": doc["case_id"], "kind": "open_text", "file": f"observations/{path.name}"})
    return {"files": len(files), "deny_terms": checked_terms, "quotes": checked_quotes, "listed_values": open_values, "hits": hits}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("release_id")
    b.add_argument("--mode", choices=("adjudicated", "machine", "preview"), default="adjudicated",
                   help="adjudicated: a named reviewer decided every item; machine: two independent coders agreed "
                        "on everything published; preview: anything that validates, local only")
    b.add_argument("--allow-unreviewed", action="store_true", help="same as --mode preview")
    b.add_argument("--allow-empty-registry", action="store_true",
                   help="build even when the capability registry has no platforms")
    n = sub.add_parser("nquads")
    n.add_argument("release_id")
    n.add_argument("--graphs", choices=sorted(SELECTIONS), default="all", help="evidence only, or evidence, trajectories and observations")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        m = build(args.release_id, allow_unreviewed=args.allow_unreviewed, mode=args.mode,
                  allow_empty_registry=args.allow_empty_registry)
        print(json.dumps({"release": m["release_id"], "cases": len(m["cases"]), "review_mode": m["review_mode"]}))
    else:
        print(nquads(args.release_id, select=args.graphs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
