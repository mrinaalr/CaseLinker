"""Run a proposal over documents in a child process and print what it produced.

The gate in ``repair_expand`` never runs proposed code or a proposed pattern
itself. It starts this module, sends the documents on stdin and reads JSON from
stdout. Whatever a proposal does to this process (patch the span gate, loop,
print) stays here; the parent checks every candidate with its own gate and
resolver, and stops the child when it runs out of time.

    python -m caselinker_mcp.proposal_runner < payload.json

Payload ``{"mode", "root", "docs": [{"case_id", "text", ...}], ...}``:

``rule``       one candidate compiled rule (``rule``) -> raw candidates
``extension``  every ``detect_*`` function in ``extension`` (a path to
               ``extension.py``) -> raw candidates
``replay``     the deterministic pipeline of the checkout at ``root`` on each
               stored ``raw_data`` -> per-case digests, for a before/after of code
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

CANDIDATE_KEYS = ("field", "value", "role", "span_start", "span_end", "confidence")
# Not part of what extraction decides: timestamps, the input itself, and the two
# structures the replay reports on their own.
_SKIP_KEYS = frozenset({"created_at", "updated_at", "raw_data", "case_text", "assertions", "resolutions"})
_MAX_ERRORS = 20


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _digest(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _rule_candidates(root: Path, payload: Dict) -> Dict:
    field_layer = root / "src" / "Processing Layer" / "field_assertions"
    compiled_rules = _load("caselinker_compiled_rules", field_layer / "compiled_rules.py")
    rule = payload["rule"]
    # Validation compiles and runs the proposed regex, so it runs here too, never in the parent.
    reason = compiled_rules.validate_proposal(rule, rule.get("positives") or [], rule.get("negatives") or [])
    if reason:
        return {"invalid": reason, "candidates": [], "errors": []}
    out = []
    for doc in payload["docs"]:
        for a in compiled_rules.assertions_for(doc["text"], doc.get("doc_kind") or "press_release", [rule]):
            out.append({"case_id": doc["case_id"], "detector": f"compiled_rule:{rule['id']}",
                        **{k: a.get(k) for k in CANDIDATE_KEYS}})
    return {"candidates": out, "errors": []}


def _extension_candidates(root: Path, payload: Dict) -> Dict:
    field_layer = root / "src" / "Processing Layer" / "field_assertions"
    sys.path.insert(0, str(field_layer))
    import detectors  # the real registry: an unknown kind or a duplicate name fails here as it would in core

    path = Path(payload["extension"])
    ext = _load(f"caselinker_extension_{path.parent.name}", path)
    names = sorted(n for n in vars(ext) if n.startswith("detect_") and callable(getattr(ext, n)))
    kinds = tuple(getattr(ext, "DOCUMENT_KINDS", ("press_release",)))
    for order, name in enumerate(names):
        detectors.register_detector(f"{path.parent.name}.{name}", kinds, getattr(ext, name), order=1000 + order)
    out: List[Dict] = []
    errors: List[Dict] = []
    for doc in payload["docs"]:
        kind = doc.get("doc_kind") or "press_release"
        if kind not in kinds:
            continue
        ctx = detectors.DetectorContext(text=doc["text"], doc_kind=kind, case_id=doc["case_id"], use_spacy=False)
        for det in detectors.detectors_for(kind):
            try:
                found = list(det.fn(ctx) or [])
            except Exception as exc:  # the extension's bug, reported by type only (a message can quote text)
                if len(errors) < _MAX_ERRORS:
                    errors.append({"case_id": doc["case_id"], "detector": det.name, "error": type(exc).__name__})
                continue
            for a in found:
                if isinstance(a, dict):
                    out.append({"case_id": doc["case_id"], "detector": det.name,
                                **{k: a.get(k) for k in CANDIDATE_KEYS}})
    return {"candidates": out, "errors": errors, "detectors": [f"{path.parent.name}.{n}" for n in names]}


def _replay(root: Path, payload: Dict) -> Dict:
    """Pattern extract -> assertions (no spaCy, no NER, no human file) -> resolve -> merge, as stored columns."""
    for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
        sys.path.insert(0, str(root / sub))
    processing = _load("caselinker_processing", root / "src" / "Processing Layer" / "processing.py")
    amod = processing.assertions_module
    merger = processing.MergeProcessing()
    cases = []
    errors: List[Dict] = []
    for doc in payload["docs"]:
        raw = dict(doc.get("raw") or {})
        raw.setdefault("case_text", doc["text"])
        raw.setdefault("case_id", doc["case_id"])
        try:
            features = processing.extract_features(raw)
            text = features.get("case_text") or doc["text"]
            year = raw.get("year")
            assertions = amod.collect_assertions(
                text, case_id=doc["case_id"], use_spacy=False, overrides={},
                batch_year=int(year) if str(year or "").isdigit() else None,
                doc_kind=raw.get("document_kind") or "press_release",
            )
            resolutions = amod.resolve(
                assertions, batch_date=(features.get("date_range") or {}).get("start"), text=text
            )
            case = processing.assign_comparison_values(
                merger.merge_features(features, None, assertions=assertions, resolutions=resolutions)
            )
        except Exception as exc:
            if len(errors) < _MAX_ERRORS:
                errors.append({"case_id": doc["case_id"], "error": type(exc).__name__})
            continue
        cases.append({
            "case_id": doc["case_id"],
            "columns": {k: _digest(v) for k, v in case.items() if k not in _SKIP_KEYS},
            "assertions": sorted(
                [a["field"], a["method"], str(a.get("role")), a.get("span_start"), a.get("span_end")]
                for a in assertions
            ),
            "resolutions": {f: [r["status"], _digest(r.get("final_value"))] for f, r in resolutions.items()},
        })
    return {"cases": cases, "errors": errors}


def main() -> int:
    wire = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)  # anything the proposal or the pipeline prints goes to stderr, never into the result
    sys.stdout = sys.stderr
    payload = json.load(sys.stdin)
    root = Path(payload["root"])
    run = {"rule": _rule_candidates, "extension": _extension_candidates, "replay": _replay}[payload["mode"]]
    json.dump(run(root, payload), wire, ensure_ascii=False, default=str)
    wire.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
