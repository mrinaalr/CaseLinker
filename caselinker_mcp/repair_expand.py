"""Repair and expand: local tools that let an agent propose a change to extraction and measure it.

describe_pipeline   what can be extended, and what is the maintainer's to decide
diagnose_case       why a stored value is what it is: stored evidence beside a replay of today's readers
profile_new_source  what today's readers extract from a new document, with no database write
scaffold_extension  an extension folder: a detector stub and a test that fails until it is written
run_gate            fixed checks on the checkout, a candidate rule or an extension, and the cases each would change

None of them writes to the corpus or admits a change. A proposal (a candidate rule,
an extension's detectors, or the checkout's own extraction code) runs in a child
process (``proposal_runner``). This module gates, resolves and compares what comes
back, so a proposal cannot reach the code that grades it.

The gate measures change, not correctness. It has no labelled answers; it lists the
cases a change would move so a person can read them.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_DIR = _REPO_ROOT / "extensions"

GATE_VERSION = "gate_v1"
BASE_REF = "origin/main"
# The same three fields scripts/run/propose_compiled_rule.py accepts: the gate derives or
# checks the value of each from the span, so a proposal cannot assert a value the text lacks.
RULE_FIELDS = ("age", "sentence", "investigation_type")
# How the gate reads the value of an extension field out of its span.
VALUE_TYPES = ("number", "money", "duration", "literal")
# What the gate will not grade a change to: itself and the fixed tests.
GRADER = ("caselinker_mcp/repair_expand.py", "caselinker_mcp/proposal_runner.py")
TEST_TIER = (
    "tests/test_field_assertions.py",
    "tests/test_no_direct_identifiers.py",
    "tests/test_public_assertion_names.py",
    "tests/test_repair_expand.py",
)
# Readers a replay does not run. Their stored rows are kept as stored.
NOT_REPLAYED = ("ner_stanza", "llm", "human")
SPACY_METHODS = ("spacy_token", "spacy_dep")
DEFAULT_SAMPLE = 200

INTERPRETATION = {
    "extraction_trace": (
        "Stored rows beside a replay of today's deterministic readers on the stored text. Readers "
        "that were not replayed keep their stored rows. A difference means the code changed since "
        "this case was extracted; it does not say which value is right."
    ),
    "source_profile": (
        "Counts of what today's readers extract from this file, with spaCy, Stanza, the semantic "
        "model and the LLM off, so an ingest can settle more than this shows. Nothing was stored. "
        "A count is not a check: read a sample of cases against the text before ingest."
    ),
    "regression_evidence": (
        "A pass means the fixed checks hold on this checkout. It does not mean the change is "
        "correct: the gate has no labelled answers. It lists every case the change would move; "
        "read them before proposing. Admission is a commit the maintainer reviews."
    ),
}

_NAME_RE = re.compile(r"[a-z][a-z0-9_]{2,39}")
_ROLE_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")
_EXCERPT = 70
_MAX_LISTED = 200

_pipeline_module = None


# --- the pipeline, the corpus, git --------------------------------------------

def _pipeline():
    """The module ingest runs (``process_cases``), loaded by path.

    ``import processing`` is not safe here: the pattern layer has a file of the same
    name and the first one on ``sys.path`` wins.
    """
    global _pipeline_module
    if _pipeline_module is None:
        for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
            path = str(_REPO_ROOT / sub)
            if path not in sys.path:
                sys.path.insert(0, path)
        spec = importlib.util.spec_from_file_location(
            "caselinker_processing", _REPO_ROOT / "src" / "Processing Layer" / "processing.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        _pipeline_module = module
    return _pipeline_module


def _db_path() -> Path:
    env = os.environ.get("CASELINKER_DB", "").strip()
    return Path(env) if env else _REPO_ROOT / "caselinker.db"


def _connect() -> sqlite3.Connection:
    """The local corpus, read-only. These tools never open it any other way."""
    path = _db_path()
    if not path.exists():
        raise FileNotFoundError(f"no local corpus at {path} (set CASELINKER_DB)")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _json(blob: Any) -> Dict:
    try:
        value = json.loads(blob) if blob else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_case(cursor: Any, case_id: str) -> Optional[Dict[str, Any]]:
    row = cursor.execute(
        "SELECT id, raw_data, extracted_features, date_start FROM cases WHERE id = ?", (case_id,)
    ).fetchone()
    if not row:
        return None
    raw = _json(row[1])
    return {"case_id": row[0], "raw": raw, "text": raw.get("case_text") or "",
            "features": _json(row[2]), "batch_date": row[3],
            "doc_kind": raw.get("document_kind") or "press_release"}


def _git(*args: str, root: Path = _REPO_ROOT) -> Optional[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _where(fn: Any) -> str:
    code = getattr(fn, "__code__", None)
    if code is None:
        return ""
    try:
        path = Path(code.co_filename).resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        path = code.co_filename
    return f"{path}:{code.co_firstlineno}"


def _core_fields(amod: Any) -> List[str]:
    """The fields the resolver settles, read from the resolver itself."""
    return list(amod.resolution.resolve_case([]))


def _digest(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _batch_year(raw: Dict) -> Optional[int]:
    year = raw.get("year")
    return int(year) if str(year or "").isdigit() else None


# --- proposals run in a child ---------------------------------------------------

def _run_child(payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """Run ``proposal_runner`` on a payload. The child gets no secrets from this process."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR") if k in os.environ}
    env["PYTHONHASHSEED"] = "0"  # set-ordered lists come out in the same order on both sides of a comparison
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "caselinker_mcp.proposal_runner"], input=json.dumps(payload),
            capture_output=True, text=True, cwd=_REPO_ROOT, env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"failed": f"timed out after {int(timeout)}s"}
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        return {"failed": f"exited {proc.returncode}: {last[:200]}"}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"failed": "did not return JSON"}


def read_manifest(name: str) -> Dict[str, Any]:
    """An extension's declared fields, kinds and detectors, read without importing it."""
    if not _NAME_RE.fullmatch(name or ""):
        return {"error": "extension names are lowercase letters, digits and underscores (3 to 40 characters)"}
    path = EXTENSIONS_DIR / name / "extension.py"
    if not path.exists():
        return {"error": f"no extension at extensions/{name}/extension.py"}
    amod = _pipeline().assertions_module
    out: Dict[str, Any] = {"name": name, "path": str(path), "fields": {}, "document_kinds": ["press_release"],
                           "detectors": []}
    try:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("detect_"):
                out["detectors"].append(node.name)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == "FIELDS":
                    out["fields"] = dict(ast.literal_eval(node.value))
                elif node.targets[0].id == "DOCUMENT_KINDS":
                    out["document_kinds"] = list(ast.literal_eval(node.value))
    except (SyntaxError, ValueError, TypeError) as exc:
        return {"error": f"extension.py does not parse: FIELDS and DOCUMENT_KINDS must be literals ({type(exc).__name__})"}
    core = _core_fields(amod)
    for field, vtype in out["fields"].items():
        if not _ROLE_RE.fullmatch(str(field)) or vtype not in VALUE_TYPES:
            return {"error": f"FIELDS[{field!r}] must name one of {VALUE_TYPES}"}
        if field in core:
            return {"error": f"{field} is already gated by CaseLinker; leave it out of FIELDS"}
    unknown = [k for k in out["document_kinds"] if k not in amod.detectors.DOCUMENT_KINDS]
    if unknown:
        return {"error": f"unknown document kinds {unknown}; a new kind is the maintainer's decision"}
    if not out["detectors"]:
        return {"error": "no detect_* function"}
    return out


def _value_in_span(amod: Any, text: str, start: int, end: int, vtype: str,
                   person_spans: Sequence[Sequence[int]]) -> Tuple[bool, Any, str]:
    """Read an extension field's value out of its span. The candidate's own value is never used."""
    sg = amod.sg
    span = text[start:end].strip()
    if vtype == "number":
        number = sg.parse_number(span)
        return number is not None, number, "number_in_span" if number is not None else "span_is_not_a_number"
    if vtype == "money":
        amount = sg.money_value(span) if sg.MONEY_RE.fullmatch(span) else None
        return amount is not None, amount, "amount_in_span" if amount is not None else "span_is_not_an_amount"
    if vtype == "duration":
        ok = bool(sg.DURATION_RE.fullmatch(span))
        return ok, re.sub(r"\s+", " ", sg.normalize_surface(span)) if ok else None, \
            "duration_in_span" if ok else "span_is_not_a_duration"
    if not span or len(span) > 80:
        return False, None, "literal_span_empty_or_over_80_characters"
    if any(s < end and start < e for s, e in person_spans):
        return False, None, "span_names_a_person"
    return True, None, "literal_span"  # the text of a literal is never returned: it could be anything


def _grade_candidate(amod: Any, text: str, cand: Dict, ext_fields: Dict[str, str], version: str,
                     person_spans: Sequence[Sequence[int]]) -> Tuple[Optional[Dict], str]:
    """One raw candidate from an extension -> a gated assertion, or the reason it was dropped."""
    start, end, role, conf = cand.get("span_start"), cand.get("span_end"), cand.get("role"), cand.get("confidence")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        return None, "bad_offsets"
    if not isinstance(role, str) or not _ROLE_RE.fullmatch(role):
        return None, "bad_role"
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        return None, "bad_confidence"
    field = cand.get("field")
    assertion = {"field": field, "method": "extension", "method_version": version, "value": None, "role": role,
                 "span_start": start, "span_end": end, "confidence": float(conf), "extras": {}}
    if field in RULE_FIELDS:
        gated = amod.gate_assertion(text, {**assertion, "value": cand.get("value")})
        if not gated["span_ok"]:
            return None, gated["extras"]["gate_reason"]
        if field == "investigation_type":
            gated["value"] = "cybertip"
        return gated, gated["extras"]["gate_reason"]
    vtype = ext_fields.get(field)
    if vtype is None:
        return None, "undeclared_field"
    ok, value, reason = _value_in_span(amod, text, start, end, vtype, person_spans)
    if not ok:
        return None, reason
    return {**assertion, "value": value, "family": "extension", "span_ok": 1,
            "extras": {"gate_reason": reason}}, reason


def _resolve_extension_field(amod: Any, assertions: List[Dict], field: str) -> Dict[str, Any]:
    """Family vote per mention for a field CaseLinker has no rule for (rules 2 to 6 of resolve_v3.0)."""
    res = amod.resolution
    mentions = res._mentions(assertions, field)
    if not mentions:
        return res._result(field, "empty", None, "no_assertions")
    settled, contested, open_items = [], {}, []
    for (start, end), items in mentions.items():
        vote = res._vote(items)
        if vote["state"] == "contested":
            contested[str(start)] = {"span": [start, end], "roles": vote["roles"]}
        elif vote["state"] in ("agreed", "resolved"):
            settled.append({"value": items[0]["value"], "role": vote["role"], "span": [start, end]})
        else:
            open_items.append({"span": [start, end], "state": vote["state"]})
    if settled:
        status = "partial" if contested else "resolved"
    else:
        status = "disagreement" if contested else "needs_review"
    return res._result(field, status, settled, "extension_family_vote", (),
                       {"contested": contested, "open": open_items})


def rehearse_extension(name: str, docs: Sequence[Dict[str, Any]], timeout: float = 600) -> Dict[str, Any]:
    """Run an extension's detectors on documents in a child, then gate each candidate here.

    ``docs`` are ``{"case_id", "text", "doc_kind"?}``. Returns the manifest, ``kept``
    (gated assertions with their ``case_id``), ``dropped`` (reason counts) and ``errors``.
    """
    manifest = read_manifest(name)
    if manifest.get("error"):
        return {"manifest": manifest, "kept": [], "dropped": {}, "errors": [manifest["error"]]}
    amod = _pipeline().assertions_module
    texts = {d["case_id"]: d["text"] for d in docs}
    result = _run_child({"mode": "extension", "root": str(_REPO_ROOT), "extension": manifest["path"],
                         "docs": [{"case_id": d["case_id"], "text": d["text"],
                                   "doc_kind": d.get("doc_kind") or "press_release"} for d in docs]}, timeout)
    if result.get("failed"):
        return {"manifest": manifest, "kept": [], "dropped": {}, "errors": [result["failed"]]}
    kept: List[Dict] = []
    dropped: Counter = Counter()
    spans_by_case: Dict[str, Any] = {}
    for cand in result.get("candidates") or []:
        case_id = cand.get("case_id")
        if case_id not in texts:
            dropped["unknown_case"] += 1
            continue
        text = texts[case_id]
        if case_id not in spans_by_case:
            spans_by_case[case_id] = amod.people_mask.person_spans(text, ()) if "literal" in manifest["fields"].values() else ()
        assertion, reason = _grade_candidate(amod, text, cand, manifest["fields"], name, spans_by_case[case_id])
        if assertion is None:
            dropped[reason] += 1
        else:
            kept.append({**assertion, "case_id": case_id, "detector": str(cand.get("detector"))})
    return {"manifest": manifest, "kept": kept, "dropped": dict(dropped), "raised": len(result.get("candidates") or []),
            "errors": [f"{e.get('detector')}: {e.get('error')} on {e.get('case_id')}" for e in result.get("errors") or []]}


# --- describe_pipeline ----------------------------------------------------------

_LAYERS = (
    ("collection", "collector", "ordinary",
     "a listing, URL file or harvest: the collector tools write PDFs, nothing is ingested"),
    ("ingestion", "src/Ingestion Layer/ingestion.py", "ordinary",
     "a new source is a branch in detect_source_from_content, a split rule in src/Processing Layer/batching.py, "
     "a state in location_grounding.SOURCE_TO_STATE, a card in visualization/sources.html and a test "
     "(tests/test_new_agency_sources.py is the pattern); profile_new_source shows which of these a file still needs"),
    ("extraction", "src/Processing Layer/field_assertions", "ordinary",
     "a compiled rule (one regex) or a detector registered for a document kind; both are proposed, "
     "measured by run_gate and admitted by a commit"),
    ("storage", "src/Storage Layer", "maintainer",
     "cases columns and every write to the corpus"),
    ("knowledge graphs", "ontology/features_to_cac.py", "maintainer",
     "the mapping to CAC, UCO and CASE terms and the pinned ontology versions"),
    ("interfaces", "caselinker_mcp/server.py", "ordinary",
     "a new endpoint or MCP tool is ordinary; changing what an existing one returns is the maintainer's"),
)


def _ontology_pins() -> Dict[str, str]:
    path = _REPO_ROOT / "ontology" / "CAC_ONTOLOGY_VERSION"
    if not path.exists():
        return {}
    return dict(re.findall(r"^(\w[\w-]*):\n(?:[ \t].*\n)*?[ \t]+describe:[ \t]*(\S+)", path.read_text(encoding="utf-8"), re.M))


def _list_extensions() -> List[Dict[str, Any]]:
    if not EXTENSIONS_DIR.is_dir():
        return []
    out = []
    for path in sorted(EXTENSIONS_DIR.glob("*/extension.py")):
        manifest = read_manifest(path.parent.name)
        manifest.pop("path", None)
        out.append(manifest if not manifest.get("error") else {"name": path.parent.name, "error": manifest["error"]})
    return out


def _corpus_summary() -> Dict[str, Any]:
    try:
        con = _connect()
    except FileNotFoundError as exc:
        return {"available": False, "reason": str(exc)}
    import assertion_store

    with closing(con):
        cur = con.cursor()
        cases, sources = cur.execute("SELECT COUNT(*), COUNT(DISTINCT source) FROM cases").fetchone()
        review = cur.execute(
            "SELECT field, reason, COUNT(*) FROM review_queue WHERE status = 'open' GROUP BY field, reason"
        ).fetchall()
        columns = [row[1] for row in cur.execute("PRAGMA table_info(cases)")]
        counts = assertion_store.read_disagreements(cur, limit=1)["status_counts"]
    return {
        "available": True, "cases": cases, "sources": sources, "resolution_status": counts,
        "open_review": sorted(({"field": f, "reason": r, "n": n} for f, r, n in review), key=lambda x: -x["n"]),
        "domain_columns": [c for c in columns if "victim" in c or "perpetrator" in c],
    }


def describe_pipeline() -> Dict[str, Any]:
    """Extension points and reserved decisions, read from the code and the local corpus."""
    amod = _pipeline().assertions_module
    amod._register_builtin_detectors()
    dets, res = amod.detectors, amod.resolution
    registered: Dict[str, Dict[str, Any]] = {}
    for kind in dets.DOCUMENT_KINDS:
        for det in dets.detectors_for(kind):
            registered.setdefault(det.name, {"name": det.name, "kinds": list(det.kinds), "order": det.order,
                                             "defined_in": _where(det.fn)})
    core = _core_fields(amod)
    corpus = _corpus_summary()
    return {
        "layers": [{"layer": layer, "path": path, "exists": (_REPO_ROOT / path).exists(), "decision": decision,
                    "extend": extend} for layer, path, decision, extend in _LAYERS],
        "document_kinds": list(dets.DOCUMENT_KINDS),
        "detectors": sorted(registered.values(), key=lambda d: (d["order"], d["name"])),
        "fields": [{"field": f, "resolver": _where(getattr(res, f"resolve_{f}", None)),
                    "compiled_rule_or_extension": f in RULE_FIELDS} for f in core],
        "resolution": {"rule_set_version": res.RULE_SET_VERSION, "families": dict(res.FAMILY),
                       "single_family_min_confidence": res.SINGLE_FAMILY_MIN_CONFIDENCE,
                       "gate": _where(amod.gate_assertion)},
        "compiled_rules": {"approved": [r["id"] for r in amod.compiled_rules.APPROVED],
                           "admit_by": "committing the rule into APPROVED in "
                                       "src/Processing Layer/field_assertions/compiled_rules.py"},
        "extensions": {"dir": "extensions", "value_types": list(VALUE_TYPES), "found": _list_extensions(),
                       "runs_in": "rehearsal only: profile_new_source and run_gate; ingest never loads one"},
        "gate": {"version": GATE_VERSION, "base_ref": BASE_REF, "grader": list(GRADER), "tests": list(TEST_TIER),
                 "sample": DEFAULT_SAMPLE},
        "reserved_for_maintainer": [
            {"decision": "a new document kind", "today": list(dets.DOCUMENT_KINDS)},
            {"decision": "a new stored field or a change to what one means", "today": core},
            {"decision": "cases table columns", "today": corpus.get("domain_columns") or "see src/Storage Layer/storage.py"},
            {"decision": "ontology mapping and pinned versions", "today": _ontology_pins()},
            {"decision": "any write to the corpus, the graphs or the SPARQL store", "today": "none of these tools write"},
        ],
        "corpus": corpus,
        "loops": {
            "repair": ["get_field_disagreements", "diagnose_case", "run_gate(rule=...) or run_gate()"],
            "expand": ["profile_new_source", "scaffold_extension", "run_gate(extension=...)",
                       "profile_new_source(extension=...)"],
        },
        "tool_kind": "READ", "write": False,
    }


# --- diagnose_case --------------------------------------------------------------

def _key(a: Dict) -> Tuple:
    return (a.get("field"), a.get("method"), str(a.get("role")), a.get("span_start"), a.get("span_end"))


def _excerpt(amod: Any, text: str, spans: Any, start: Optional[int], end: Optional[int]) -> Optional[str]:
    """The passage around a span with people masked, on one line."""
    if start is None or end is None:
        return None
    lo, hi = max(0, start - _EXCERPT), min(len(text), end + _EXCERPT)
    return re.sub(r"\s+", " ", amod.people_mask.redact(text[lo:hi], spans, lo)).strip()


def _shaped_spans(amod: Any, text: str, field: str) -> List[Tuple[int, int]]:
    """Spans that look like the field, whether or not a reader raised them."""
    if field == "age":
        return [(s, e) for s, e, _age, _shape in amod.patterns.age_mentions(text)]
    if field == "sentence":
        return [m.span() for m in amod.sg.DURATION_RE.finditer(text)]
    if field == "investigation_type":
        return [m.span() for m in amod.patterns._TIP_TOKEN_RE.finditer(text)]
    return []


def _brief(resolution: Optional[Dict]) -> Optional[Dict[str, Any]]:
    if not resolution:
        return None
    return {"status": resolution.get("status"), "rule_id": resolution.get("rule_id"),
            "final_value": resolution.get("final_value")}


def diagnose_case(case_id: str, field: str = "", use_spacy: bool = False) -> Dict[str, Any]:
    """Stored evidence for one case beside a replay of today's readers on its stored text."""
    case_id = (case_id or "").strip()
    amod = _pipeline().assertions_module
    import assertion_store

    core = _core_fields(amod)
    if field and field not in core:
        return {"error": f"unknown field {field!r}", "fields": core}
    with closing(_connect()) as con:
        cur = con.cursor()
        case = _load_case(cur, case_id)
        if case is None:
            return {"error": f"case {case_id!r} is not in the local corpus", "case_id": case_id}
        stored = assertion_store.load_assertions(cur, case_id)
        latest = assertion_store.latest_resolutions(cur, case_id)
    text = case["text"]
    people = amod.people_mask.spans_for(case["features"], text)
    trace: List[Dict] = []
    replayed = amod.collect_assertions(
        text, case_id=case_id, use_spacy=use_spacy, overrides={}, batch_year=_batch_year(case["raw"]),
        doc_kind=case["doc_kind"], trace=trace,
    )
    skipped = NOT_REPLAYED + (() if use_spacy else SPACY_METHODS)
    carried = [dict(a) for a in stored if a["method"] in skipped]
    from_stored = amod.resolve([dict(a) for a in stored], batch_date=case["batch_date"], text=text)
    from_replay = amod.resolve(replayed + carried, batch_date=case["batch_date"], text=text)

    stored_keys = {_key(a) for a in stored}
    replay_keys = {_key(a) for a in replayed}
    wanted = [field] if field else core
    fields: Dict[str, Any] = {}
    for name in wanted:
        raised = [t for t in trace if t["raw"].get("field") == name]
        candidates = []
        for t in raised:
            raw, gated = t["raw"], t["gated"]
            kept = bool(gated["span_ok"])
            start = gated["span_start"] if kept else raw.get("span_start")
            end = gated["span_end"] if kept else raw.get("span_end")
            candidates.append({
                "detector": t["detector"], "method": raw.get("method"), "role": gated.get("role"),
                "value": gated.get("value") if kept else None, "span": [start, end], "kept": kept,
                "gate_reason": (gated.get("extras") or {}).get("gate_reason"),
                "in_store": kept and _key(gated) in stored_keys,
                "excerpt": _excerpt(amod, text, people, start, end),
            })
        claimed = [(t["raw"].get("span_start"), t["raw"].get("span_end")) for t in raised]
        unread = [span for span in _shaped_spans(amod, text, name)
                  if not any(s is not None and s < span[1] and span[0] < e for s, e in claimed)]
        stored_only = [
            {"method": a["method"], "role": a.get("role"), "span": [a.get("span_start"), a.get("span_end")],
             "why": "reader not replayed" if a["method"] in skipped else "today's readers do not raise it"}
            for a in stored if a["field"] == name and _key(a) not in replay_keys
        ]
        fields[name] = {
            "stored": {**(_brief(latest.get(name)) or {"status": None}),
                       "assertions": sum(1 for a in stored if a["field"] == name)},
            "stored_rows_resolved_today": _brief(from_stored.get(name)),
            "replay": _brief(from_replay.get(name)),
            "changed_if_reextracted": _digest(_brief(from_replay.get(name))) != _digest(_brief(from_stored.get(name))),
            "candidates": candidates,
            "stored_only": stored_only,
            "unread": [{"span": list(span), "excerpt": _excerpt(amod, text, people, *span)} for span in unread[:10]],
        }
    amod._register_builtin_detectors()
    return {
        "case_id": case_id, "doc_kind": case["doc_kind"], "text_length": len(text),
        "run_id": stored[0]["run_id"] if stored else None,
        "readers_not_replayed": list(skipped),
        "fields": fields,
        "where_to_look": {
            "detectors": [{"name": d.name, "defined_in": _where(d.fn)}
                          for d in amod.detectors.detectors_for(case["doc_kind"])],
            "gate": _where(amod.gate_assertion),
            "resolvers": {name: _where(getattr(amod.resolution, f"resolve_{name}", None)) for name in wanted},
        },
        "interpretation_kind": "extraction_trace", "interpretation_note": INTERPRETATION["extraction_trace"],
        "tool_kind": "READ", "write": False,
    }


# --- profile_new_source ---------------------------------------------------------

_PROFILE_SKIP = frozenset({"case_text", "raw_data", "assertions", "resolutions", "person_spans", "ml_features",
                           "comparison_values", "created_at", "updated_at", "id", "source"})


def _filled(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_filled(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_filled(v) for v in value)
    return value not in (None, "", False)


def _split_source(path: Path) -> Tuple[str, List[Dict[str, Any]]]:
    """Text -> source -> cases, the way ingest does it, with nothing stored."""
    pipeline = _pipeline()
    spec = importlib.util.spec_from_file_location(
        "caselinker_ingestion", _REPO_ROOT / "src" / "Ingestion Layer" / "ingestion.py"
    )
    ingestion = sys.modules.get("caselinker_ingestion")
    if ingestion is None:
        ingestion = importlib.util.module_from_spec(spec)
        assert spec.loader
        sys.modules["caselinker_ingestion"] = ingestion
        spec.loader.exec_module(ingestion)
    if path.suffix.lower() == ".pdf":
        row = ingestion.ingest_file(str(path)).iloc[0]
        text, source = row["extracted_text"], row["source"]
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        source = ingestion.detect_source_from_content(text, path.name)
    # The id prefix rule process_cases uses.
    org = source.lower() if source and source != "unknown" else "case"
    if org == "case":
        match = re.search(r"([A-Z]+)", path.name)
        org = match.group(1).lower() if match else org
    batches = pipeline.case_batching(text, org_name=org, source=source, source_file=path.name)
    return source, [{**b, "source": source, "source_file": path.name} for b in batches]


def profile_new_source(path: str, doc_kind: str = "press_release", extension: str = "",
                       max_cases: int = 200) -> Dict[str, Any]:
    """Split a PDF or text file into cases and count what today's readers extract. No write."""
    pipeline = _pipeline()
    amod = pipeline.assertions_module
    file = Path(path).expanduser()
    if not file.is_file() or file.suffix.lower() not in (".pdf", ".txt"):
        return {"error": "path must be an existing .pdf or .txt file", "write": False}
    if doc_kind not in amod.detectors.DOCUMENT_KINDS:
        return {"error": f"unknown document kind {doc_kind!r}", "document_kinds": list(amod.detectors.DOCUMENT_KINDS),
                "write": False}
    source, batches = _split_source(file)
    total = len(batches)
    batches = batches[: max(1, max_cases)] if max_cases else batches

    merger = pipeline.MergeProcessing()
    detectors: Dict[str, Counter] = {}
    status: Dict[str, Counter] = {}
    review: Counter = Counter()
    columns: Counter = Counter()
    unread: Counter = Counter()
    lengths, docs, by_case = [], [], {}
    for batch in batches:
        text = batch.get("case_text") or ""
        case_id = batch.get("case_id") or f"case_{len(docs) + 1}"
        raw = {k: batch.get(k) for k in ("case_text", "month_year", "month", "year", "case_id", "source",
                                         "source_file", "state", "source_url") if batch.get(k) is not None}
        features = pipeline.extract_features(raw)
        trace: List[Dict] = []
        assertions = amod.collect_assertions(text, case_id=case_id, use_spacy=False, overrides={},
                                             batch_year=_batch_year(raw), doc_kind=doc_kind, trace=trace)
        resolutions = amod.resolve(assertions, batch_date=(features.get("date_range") or {}).get("start"), text=text)
        case = pipeline.assign_comparison_values(
            merger.merge_features(features, None, assertions=assertions, resolutions=resolutions)
        )
        lengths.append(len(text))
        docs.append({"case_id": case_id, "text": text, "doc_kind": doc_kind})
        by_case[case_id] = (assertions, features, text)
        for entry in trace:
            tally = detectors.setdefault(entry["detector"], Counter())
            tally["raised"] += 1
            if entry["gated"]["span_ok"]:
                tally["kept"] += 1
            else:
                tally[f"dropped:{entry['gated']['extras']['gate_reason']}"] += 1
        for name, res in resolutions.items():
            status.setdefault(name, Counter())[res["status"]] += 1
            for item in res.get("review") or []:
                review[f"{name}:{item.get('reason')}"] += 1
        for key, value in case.items():
            if key not in _PROFILE_SKIP and _filled(value):
                columns[key] += 1
        for name in ("age", "sentence"):
            claimed = [(t["raw"].get("span_start"), t["raw"].get("span_end")) for t in trace
                       if t["raw"].get("field") == name]
            unread[name] += sum(
                1 for span in _shaped_spans(amod, text, name)
                if not any(s is not None and s < span[1] and span[0] < e for s, e in claimed)
            )

    n = len(docs)
    out: Dict[str, Any] = {
        "file": file.name, "source_detected": source, "doc_kind": doc_kind,
        "cases_split": total, "cases_profiled": n,
        "case_length": {"min": min(lengths), "median": int(statistics.median(lengths)), "max": max(lengths)} if lengths else {},
        "columns_filled": {k: {"cases": v, "share": round(v / n, 3)} for k, v in sorted(columns.items(), key=lambda kv: -kv[1])},
        "detectors": {name: dict(tally) for name, tally in sorted(detectors.items())},
        "resolution_status": {name: dict(tally) for name, tally in status.items()},
        "review_items": dict(review),
        "shaped_spans_no_reader_raised": dict(unread),
        "readers_off": ["ner_stanza", *SPACY_METHODS, "semantic_concepts", "llm"],
        "interpretation_kind": "source_profile", "interpretation_note": INTERPRETATION["source_profile"],
        "tool_kind": "READ", "write": False,
    }
    if source == "unknown":
        out["source_note"] = ("no source matched; a new source needs a detect_source_from_content branch "
                              "(describe_pipeline lists the other places it touches)")
    try:
        import case_fingerprint

        with closing(_connect()) as con:
            known = {row[0] for row in con.execute("SELECT fingerprint FROM case_fingerprints")}
        out["already_in_corpus"] = sum(1 for d in docs if case_fingerprint.fingerprint_case_text(d["text"]) in known)
    except (FileNotFoundError, sqlite3.Error):
        out["already_in_corpus"] = None
    if extension:
        out["extension"] = _profile_extension(amod, extension, docs, by_case)
    return out


def _profile_extension(amod: Any, name: str, docs: List[Dict], by_case: Dict[str, Tuple]) -> Dict[str, Any]:
    rehearsal = rehearse_extension(name, docs)
    manifest = rehearsal["manifest"]
    report: Dict[str, Any] = {"name": name, "raised": rehearsal.get("raised", 0), "kept": len(rehearsal["kept"]),
                              "dropped": rehearsal["dropped"], "errors": rehearsal["errors"][:5], "fields": {}}
    if manifest.get("error"):
        return report
    kept_by_case: Dict[str, List[Dict]] = {}
    for a in rehearsal["kept"]:
        kept_by_case.setdefault(a["case_id"], []).append(a)
    core_moved = Counter()
    for field in manifest["fields"]:
        tally = Counter()
        for doc in docs:
            mine = [a for a in kept_by_case.get(doc["case_id"], []) if a["field"] == field]
            tally[_resolve_extension_field(amod, mine, field)["status"]] += 1
        report["fields"][field] = {"value_type": manifest["fields"][field], "status": dict(tally),
                                   "cases_with_a_settled_value": tally["resolved"] + tally["partial"]}
    for case_id, added in kept_by_case.items():
        core = [a for a in added if a["field"] in RULE_FIELDS]
        if not core:
            continue
        assertions, features, text = by_case[case_id]
        batch_date = (features.get("date_range") or {}).get("start")
        before = amod.resolve([dict(a) for a in assertions], batch_date=batch_date, text=text)
        after = amod.resolve([dict(a) for a in assertions] + [dict(a) for a in core], batch_date=batch_date, text=text)
        for field in {a["field"] for a in core}:
            if _digest(_brief(before[field])) != _digest(_brief(after[field])):
                core_moved[f"{field}: {before[field]['status']} -> {after[field]['status']}"] += 1
    report["core_fields_moved"] = dict(core_moved)
    return report


# --- scaffold_extension ---------------------------------------------------------

_EXTENSION_TEMPLATE = '''"""{name}: reads {field} from {kind} documents. Rehearsal only until the maintainer admits it.

The contract (caselinker_mcp/README.md, "Repair and expand"):

- Every function named detect_* is a detector. It gets a DetectorContext (ctx.text,
  ctx.doc_kind, ctx.case_id) and returns a list of candidates.
- A candidate is field, role, span_start, span_end and confidence. The span must be
  the value itself: the gate reads the value from the span and ignores any other.
- FIELDS lists only fields CaseLinker does not already gate, each with the value type
  the gate checks the span against: number, money, duration or literal.
- The gate never imports this file. It runs in a child process.
"""

import re

DOCUMENT_KINDS = ("{kind}",)
FIELDS = {fields}

# Group 1 is the value. This placeholder matches nothing: write the pattern.
_PATTERN = re.compile(r"(?!)")


def detect_{field}(ctx):
    return [
        {{"field": "{field}", "role": "{role}", "span_start": m.start(1), "span_end": m.end(1), "confidence": 0.8}}
        for m in _PATTERN.finditer(ctx.text)
    ]
'''

_TEST_TEMPLATE = '''"""{name}: the detector finds the value in a made-up document and the gate keeps it."""

from caselinker_mcp import repair_expand

# A made-up document. Never paste a real release or a real person's name into a test.
SAMPLE = ""
# One [start, end] per value the gate should keep, as offsets into SAMPLE.
EXPECTED_SPANS = []


def test_detector_finds_the_value_and_the_gate_keeps_it():
    assert SAMPLE and EXPECTED_SPANS, "write SAMPLE and EXPECTED_SPANS first"
    out = repair_expand.rehearse_extension("{name}", [{{"case_id": "sample", "text": SAMPLE}}])
    assert out["errors"] == []
    assert [[a["span_start"], a["span_end"]] for a in out["kept"]] == EXPECTED_SPANS
'''


def scaffold_extension(name: str, field: str, value_type: str = "", role: str = "stated",
                       doc_kind: str = "press_release", dry_run: bool = True) -> Dict[str, Any]:
    """Write ``extensions/<name>/`` with a detector stub and a test that fails until both are written."""
    amod = _pipeline().assertions_module
    done = {"tool_kind": "WRITE", "write": False, "created": []}
    core = _core_fields(amod)
    if not _NAME_RE.fullmatch(name or ""):
        return {**done, "error": "name: lowercase letters, digits and underscores, 3 to 40 characters"}
    if not _ROLE_RE.fullmatch(field or "") or not _ROLE_RE.fullmatch(role or ""):
        return {**done, "error": "field and role: lowercase letters, digits and underscores"}
    if doc_kind not in amod.detectors.DOCUMENT_KINDS:
        return {**done, "error": f"unknown document kind {doc_kind!r}; a new kind is the maintainer's decision",
                "document_kinds": list(amod.detectors.DOCUMENT_KINDS)}
    if field in core and field not in RULE_FIELDS:
        return {**done, "error": f"an extension can raise {', '.join(RULE_FIELDS)} or a new field; "
                                 f"{field} is read by its own detector"}
    if field not in core and value_type not in VALUE_TYPES:
        return {**done, "error": f"{field} is a new field: value_type must be one of {VALUE_TYPES}"}
    folder = EXTENSIONS_DIR / name
    if folder.exists():
        return {**done, "error": f"extensions/{name} already exists"}
    fields = "{}" if field in core else json.dumps({field: value_type})
    files = {
        "extension.py": _EXTENSION_TEMPLATE.format(name=name, field=field, kind=doc_kind, fields=fields, role=role),
        "test_extension.py": _TEST_TEMPLATE.format(name=name),
    }
    relative = [f"extensions/{name}/{filename}" for filename in files]
    note = ("A new field is rehearsed, never stored: storing it is the maintainer's decision."
            if field not in core else f"{field} candidates go through the same span gate as every other reader.")
    next_steps = [f"write the pattern and the test in extensions/{name}/",
                  f"run_gate(extension=\"{name}\")", f"profile_new_source(path, extension=\"{name}\")"]
    if dry_run:
        return {**done, "would_create": relative, "files": files, "note": note, "next": next_steps}
    folder.mkdir(parents=True)
    for filename, body in files.items():
        (folder / filename).write_text(body, encoding="utf-8")
    return {**done, "write": True, "created": relative, "note": note, "next": next_steps}


# --- run_gate -------------------------------------------------------------------

def _integrity(root: Path = _REPO_ROOT) -> Dict[str, Any]:
    """What differs from the base ref: the grader, the fixed tests, and extraction code."""
    base = _git("merge-base", "HEAD", BASE_REF, root=root)
    if not base:
        return {"ran": False, "ok": False, "reason": f"{BASE_REF} is not available in this checkout"}
    # A grader file the base does not have is this change adding it, not editing it.
    grader = (_git("diff", "--name-only", "--diff-filter=MDRT", base, "--", *GRADER, root=root) or "").splitlines()
    rewritten = []
    for line in (_git("diff", "--numstat", base, "--", *TEST_TIER, root=root) or "").splitlines():
        added, deleted, path = line.split("\t", 2)
        if deleted != "0":
            rewritten.append({"file": path, "lines_removed": deleted, "lines_added": added})
    core = (_git("diff", "--name-only", base, "--", "src", root=root) or "").splitlines()
    return {
        "ran": True, "ok": not grader and not rewritten,
        "base_ref": BASE_REF, "base_commit": base[:9], "head": (_git("rev-parse", "HEAD", root=root) or "")[:9],
        "uncommitted": bool(_git("status", "--porcelain", "--untracked-files=no", root=root)),
        "grader_changed": grader, "tests_rewritten": rewritten, "extraction_code_changed": core,
        "note": "The gate does not grade a change to itself or to lines of its fixed tests. Added tests are fine.",
    }


def _run_tests(extension: str = "") -> Dict[str, Any]:
    """Each fixed test file in its own process (a whole-suite run collides on module names)."""
    targets = [t for t in TEST_TIER if (_REPO_ROOT / t).exists()]
    if extension:
        targets.append(f"extensions/{extension}/test_extension.py")
    db = _REPO_ROOT / "caselinker.db"
    had_db = db.exists()
    files, failing = [], []
    for target in targets:
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", target],
                cwd=_REPO_ROOT, capture_output=True, text=True, timeout=900,
            )
            output = proc.stdout
        except subprocess.TimeoutExpired:
            output = "timed out"
        counts = {word: int(n) for n, word in re.findall(r"(\d+) (passed|failed|skipped|error)", output)}
        ok = bool(counts.get("passed")) and not counts.get("failed") and not counts.get("error")
        failing += re.findall(r"^FAILED (\S+)", output, re.M) or ([] if ok else [target])
        files.append({"file": target, **counts, "ok": ok, "seconds": round(time.perf_counter() - started, 1)})
    # Loading run/main.py in a test creates an empty caselinker.db in a checkout that had none,
    # and an empty one turns ten skipped full-text tests into failures on the next run.
    if not had_db and db.exists():
        with closing(sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)) as con:
            empty = con.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0
        if empty:
            db.unlink()
    return {"ran": True, "ok": all(f["ok"] for f in files) and len(files) == len(targets), "files": files,
            "failing": failing[:50], "missing": [t for t in TEST_TIER if not (_REPO_ROOT / t).exists()]}


def _all_docs(cursor: Any, case_ids: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    rows = cursor.execute("SELECT id, raw_data FROM cases ORDER BY id").fetchall()
    wanted = set(case_ids) if case_ids else None
    docs = []
    for case_id, raw_blob in rows:
        if wanted is not None and case_id not in wanted:
            continue
        raw = _json(raw_blob)
        docs.append({"case_id": case_id, "text": raw.get("case_text") or "",
                     "doc_kind": raw.get("document_kind") or "press_release", "raw": raw})
    return docs


def _frozen_sample(docs: List[Dict], n: int, named: Optional[Sequence[str]]) -> Tuple[List[Dict], str]:
    """Every k-th case in id order, plus the cases named: the same cases on every run of the same corpus."""
    if not n or n >= len(docs):
        return docs, f"all {len(docs)} cases"
    step = len(docs) // n
    picked = docs[::step][:n]
    have = {d["case_id"] for d in picked}
    extra = [d for d in docs if named and d["case_id"] in set(named) and d["case_id"] not in have]
    rule = f"every {step}th case id in sorted order ({len(picked)} of {len(docs)})"
    return picked + extra, rule + (f" plus {len(extra)} named" if extra else "")


def _impact_on_stored(amod: Any, cursor: Any, added: Dict[str, List[Dict]]) -> Dict[str, Any]:
    """Stored assertions with and without the proposal's, resolved the way reresolve_assertions.py does."""
    import assertion_store

    changes, transitions, stale = [], Counter(), 0
    for case_id in sorted(added):
        case = _load_case(cursor, case_id)
        stored = assertion_store.load_assertions(cursor, case_id)
        latest = assertion_store.latest_resolutions(cursor, case_id)
        before = amod.resolve([dict(a) for a in stored], batch_date=case["batch_date"], text=case["text"])
        after = amod.resolve([dict(a) for a in stored] + [dict(a) for a in added[case_id]],
                             batch_date=case["batch_date"], text=case["text"])
        for field in sorted({a["field"] for a in added[case_id]} | {"cybertip_reporter"}):
            if field not in before:
                continue
            if latest.get(field) and latest[field]["status"] != before[field]["status"]:
                stale += 1
            if _digest(_brief(before[field])) == _digest(_brief(after[field])):
                continue
            transitions[f"{field}: {before[field]['status']} -> {after[field]['status']}"] += 1
            changes.append({"case_id": case_id, "field": field, "before": before[field]["status"],
                            "after": after[field]["status"],
                            "final_changed": _digest(before[field]["final_value"]) != _digest(after[field]["final_value"])})
    return {"cases_changed": len({c["case_id"] for c in changes}), "transitions": dict(transitions),
            "changes": changes[:_MAX_LISTED], "changes_truncated": len(changes) > _MAX_LISTED,
            "cases_with_assertions_but_no_change": len(added) - len({c["case_id"] for c in changes}),
            "stored_resolutions_already_stale": stale}


def _check_rule(amod: Any, rule: Dict[str, Any]) -> Tuple[Optional[Dict], Dict[str, Any]]:
    cr = amod.compiled_rules
    problem = None
    if not isinstance(rule, dict):
        problem = "rule must be an object"
    elif not _NAME_RE.fullmatch(str(rule.get("id") or "")):
        problem = "id: lowercase letters, digits and underscores, 3 to 40 characters"
    elif rule.get("field") not in RULE_FIELDS:
        problem = f"field must be one of {RULE_FIELDS}"
    elif not _ROLE_RE.fullmatch(str(rule.get("role") or "")):
        problem = "role: lowercase letters, digits and underscores"
    elif any(r["id"] == rule["id"] for r in cr.APPROVED):
        problem = f"a rule named {rule['id']} is already approved"
    elif not all(isinstance(q, str) for q in list(rule.get("positives") or []) + list(rule.get("negatives") or [])):
        problem = "positives and negatives are lists of quotes"
    kinds = list((rule or {}).get("document_kinds") or ["press_release"]) if isinstance(rule, dict) else []
    if not problem and any(k not in amod.detectors.DOCUMENT_KINDS for k in kinds):
        problem = f"document_kinds must come from {list(amod.detectors.DOCUMENT_KINDS)}"
    if problem:
        return None, {"ran": True, "ok": False, "kind": "rule", "reason": problem}
    proposal = cr.proposal_dict(
        rule_id=rule["id"], field=rule["field"], role=rule["role"], regex=str(rule.get("regex") or ""),
        document_kinds=kinds, positives=list(rule.get("positives") or []), negatives=list(rule.get("negatives") or []),
        rationale=str(rule.get("rationale") or ""), group=int(rule.get("group") or 1),
    )
    entry = {k: v for k, v in proposal.items() if k not in ("positives", "negatives", "prompt_id", "approved")}
    return proposal, {"ran": True, "ok": True, "kind": "rule", "approved_entry": entry}


def _measure_rule(amod: Any, proposal: Dict[str, Any], check: Dict[str, Any], docs: List[Dict]) -> Dict[str, Any]:
    """The candidate rule over every document, in a child; each candidate gated here."""
    result = _run_child({"mode": "rule", "root": str(_REPO_ROOT), "rule": proposal,
                         "docs": [{k: d[k] for k in ("case_id", "text", "doc_kind")} for d in docs]}, timeout=900)
    if result.get("failed") or result.get("invalid"):
        check.update(ok=False, reason=result.get("failed") or result["invalid"])
        return {"ran": False}
    texts = {d["case_id"]: d["text"] for d in docs}
    added: Dict[str, List[Dict]] = {}
    dropped: Counter = Counter()
    for cand in result["candidates"]:
        case_id = cand.get("case_id")
        if case_id not in texts:
            dropped["unknown_case"] += 1
            continue
        raw = {k: cand.get(k) for k in ("field", "value", "role", "span_start", "span_end", "confidence")}
        raw.update(method="compiled_rule", method_version=proposal["id"],
                   extras={"rule_id": proposal["id"], "pattern": "compiled_rule"})
        gated = amod.gate_assertion(texts[case_id], raw)
        if gated["span_ok"]:
            added.setdefault(case_id, []).append(gated)
        else:
            dropped[gated["extras"]["gate_reason"]] += 1
    return {"ran": True, "raised": len(result["candidates"]), "kept": sum(map(len, added.values())),
            "dropped": dict(dropped), "cases_matched": len(added), "added": added}


def _replay_code(docs: List[Dict], base: str) -> Dict[str, Any]:
    """The deterministic pipeline of the base commit and of this checkout on the same stored texts."""
    payload_docs = [{"case_id": d["case_id"], "text": d["text"], "raw": d["raw"]} for d in docs]
    with tempfile.TemporaryDirectory(prefix="caselinker_gate_") as tmp:
        archive = subprocess.run(["git", "archive", base, "src", "data", "config.py"], cwd=_REPO_ROOT,
                                 capture_output=True, timeout=300)
        if archive.returncode != 0:
            return {"ran": False, "reason": f"git archive {base} failed"}
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True, timeout=300)
        before = _run_child({"mode": "replay", "root": tmp, "docs": payload_docs}, timeout=3600)
    after = _run_child({"mode": "replay", "root": str(_REPO_ROOT), "docs": payload_docs}, timeout=3600)
    for side, result in (("base", before), ("checkout", after)):
        if result.get("failed"):
            return {"ran": False, "reason": f"{side} replay {result['failed']}"}
    old = {c["case_id"]: c for c in before["cases"]}
    columns, fields, changes = Counter(), Counter(), []
    for case in after["cases"]:
        prior = old.get(case["case_id"])
        if prior is None:
            continue
        moved_columns = sorted(k for k in case["columns"].keys() | prior["columns"].keys()
                               if case["columns"].get(k) != prior["columns"].get(k))
        moved_fields = {f: {"before": prior["resolutions"][f][0], "after": r[0]}
                        for f, r in case["resolutions"].items() if prior["resolutions"].get(f) != r}
        assertions_changed = case["assertions"] != prior["assertions"]
        if moved_columns or moved_fields or assertions_changed:
            columns.update(moved_columns)
            fields.update(f"{f}: {v['before']} -> {v['after']}" for f, v in moved_fields.items())
            changes.append({"case_id": case["case_id"], "columns": moved_columns, "resolutions": moved_fields,
                            "assertions_changed": assertions_changed})
    return {"ran": True, "base_commit": base[:9], "cases_compared": len(after["cases"]),
            "cases_changed": len(changes), "columns": dict(columns), "resolutions": dict(fields),
            "changes": changes[:_MAX_LISTED], "changes_truncated": len(changes) > _MAX_LISTED,
            "errors": {"base": before["errors"], "checkout": after["errors"]},
            "readers_off": ["ner_stanza", *SPACY_METHODS, "semantic_concepts", "llm", "human"]}


def run_gate(rule: Optional[Dict[str, Any]] = None, extension: str = "", case_ids: Optional[List[str]] = None,
             sample: int = DEFAULT_SAMPLE, checks: Optional[List[str]] = None) -> Dict[str, Any]:
    """Fixed checks on this checkout, plus the cases a candidate rule or an extension would change.

    With no rule or extension the gate grades the checkout: integrity, the fixed tests and,
    when extraction code differs from the base, a replay of base and checkout on a frozen sample.
    ``checks`` picks a subset of ``integrity``, ``tests`` and ``replay`` (``replay`` forces one).
    """
    if rule and extension:
        return {"error": "pass a rule or an extension, not both", "write": False}
    amod = _pipeline().assertions_module
    started = time.perf_counter()
    wanted = set(checks or ("integrity", "tests", "replay"))
    unknown = wanted - {"integrity", "tests", "replay"}
    if unknown:
        return {"error": f"unknown checks {sorted(unknown)}", "write": False}
    out: Dict[str, Any] = {"gate_version": GATE_VERSION, "checks": {}}
    integrity = _integrity()
    out["checks"]["integrity"] = integrity
    proposal = None
    if rule:
        proposal, out["checks"]["proposal"] = _check_rule(amod, rule)
    elif extension:
        manifest = read_manifest(extension)
        out["checks"]["proposal"] = {"ran": True, "ok": not manifest.get("error"), "kind": "extension",
                                     **({"reason": manifest["error"]} if manifest.get("error") else
                                        {k: manifest[k] for k in ("fields", "document_kinds", "detectors")})}
    if "tests" in wanted and not rule:
        out["checks"]["tests"] = _run_tests(extension if out["checks"].get("proposal", {}).get("ok") else "")

    with closing(_connect()) as con:
        cur = con.cursor()
        docs = _all_docs(cur)
        if proposal is not None and out["checks"]["proposal"]["ok"]:
            measured = _measure_rule(amod, proposal, out["checks"]["proposal"], docs)
            if measured["ran"]:
                added = measured.pop("added")
                out["impact"] = {"scope": f"all {len(docs)} stored cases, stored assertions plus the rule's",
                                 **measured, **_impact_on_stored(amod, cur, added)}
        elif extension and out["checks"]["proposal"]["ok"]:
            picked, how = _frozen_sample(docs, sample, case_ids)
            rehearsal = rehearse_extension(extension, picked)
            core = {}
            for a in rehearsal["kept"]:
                if a["field"] in RULE_FIELDS:
                    core.setdefault(a["case_id"], []).append({k: v for k, v in a.items() if k not in ("case_id", "detector")})
            new_fields = {}
            for field in rehearsal["manifest"]["fields"]:
                tally = Counter(_resolve_extension_field(
                    amod, [a for a in rehearsal["kept"] if a["case_id"] == d["case_id"] and a["field"] == field], field
                )["status"] for d in picked)
                new_fields[field] = {"status": dict(tally), "stored": False}
            out["impact"] = {"scope": how, "raised": rehearsal.get("raised", 0), "kept": len(rehearsal["kept"]),
                             "dropped": rehearsal["dropped"], "errors": rehearsal["errors"][:10],
                             "new_fields": new_fields, **_impact_on_stored(amod, cur, core)}
            if rehearsal["errors"]:
                out["checks"]["proposal"].update(ok=False, reason="the extension raised or timed out")
        elif not rule and not extension and "replay" in wanted:
            changed = integrity.get("extraction_code_changed")
            if changed or checks:
                picked, how = _frozen_sample(docs, sample, case_ids)
                out["checks"]["replay"] = {"scope": how, **_replay_code(picked, integrity["base_commit"])} \
                    if integrity.get("ran") else {"ran": False, "reason": integrity.get("reason")}
            else:
                out["checks"]["replay"] = {"ran": False, "reason": "no extraction code differs from the base"}

    ran = [c for c in out["checks"].values() if c.get("ran", True)]
    out["passed"] = all(c.get("ok", True) for c in ran) and not any(
        c.get("errors", {}).get("checkout") for c in out["checks"].values() if isinstance(c.get("errors"), dict))
    out["seconds"] = round(time.perf_counter() - started, 1)
    if proposal is not None and out["passed"]:
        out["to_admit"] = ("commit checks.proposal.approved_entry into APPROVED in "
                           "src/Processing Layer/field_assertions/compiled_rules.py; stored cases change only after "
                           "a re-extraction or a re-resolve the maintainer runs")
    out.update(interpretation_kind="regression_evidence", interpretation_note=INTERPRETATION["regression_evidence"],
               tool_kind="READ", write=False)
    return out
