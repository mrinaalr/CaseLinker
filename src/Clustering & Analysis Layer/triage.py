"""
Live triage: ingest pasted narratives through the same processing pipeline as production,
then classify tiers with a trained triage bundle (train_triage_model.py).

Nothing is persisted — callers must not write results to the database.

Offline export: ``--write-corpus`` writes ``triage_corpus_predictions.json`` (bundle on every DB case)
for backups or external tools. The FastAPI triage UI uses **live** inference instead and does not
read this file. **Live** triage needs only the ``.joblib`` bundle.

Paths (see docs/railway.md):
- ``CASELINKER_TRIAGE_BUNDLE`` / ``CASELINKER_TRIAGE_CORPUS_JSON`` override defaults.
- If ``CASELINKER_MODELS_DIR`` is set (e.g. ``/data/models`` on Railway), defaults are
  ``{MODELS_DIR}/triage_bundle.joblib`` and ``{MODELS_DIR}/triage_corpus_predictions.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROC = _REPO_ROOT / "src" / "Processing Layer"
_SCRIPTS_RUN = _REPO_ROOT / "scripts" / "run"
# Processing Layer wrapper (processing.py) and its siblings.
if str(_PROC) not in sys.path:
    sys.path.insert(0, str(_PROC))
if str(_SCRIPTS_RUN) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_RUN))

import joblib  # noqa: E402

from processing import (  # noqa: E402
    MergeProcessing,
    NERExtractor,
    SemanticConcepts,
    assign_comparison_values,
    extract_features,
)
from train_triage_model import (  # noqa: E402
    TriageModelBundle,
    cases_to_dataframe,
    normalize_triage_bundle_after_load,
)


def parse_live_case_input(raw: str) -> List[Dict[str, Any]]:
    """
    Split pasted batch text: each "Case N :" starts a block until the next "Case M :" or EOF.
    If no Case headers, treat the whole string as case 1.
    Mirrors visualization/triage.html parseLiveCaseBatch.
    """
    text = (raw or "").replace("\r\n", "\n")
    if not text.strip():
        return []

    header_re = re.compile(r"Case\s+(\d+)\s*:", re.IGNORECASE)
    matches: List[Tuple[int, int, int]] = []
    for m in header_re.finditer(text):
        matches.append((m.start(), m.end(), int(m.group(1))))

    if not matches:
        single = text.strip()
        return [{"case_number": 1, "text": single}] if single else []

    out: List[Dict[str, Any]] = []
    for i, (_start, header_end, n) in enumerate(matches):
        slice_end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        body = text[header_end:slice_end].strip()
        out.append({"case_number": n, "text": body})
    return out


def _process_one_narrative(
    text: str,
    case_label: str,
) -> Dict[str, Any]:
    """
    Run the same pattern → optional semantic → NER → merge → comparison path as
    Processing Layer process_cases() for a single narrative, without batching.
    """
    raw_case: Dict[str, Any] = {
        "case_text": text.strip(),
        "case_id": case_label,
        "source": "live_triage",
        "source_file": "live_paste.txt",
        "month_year": None,
        "month": None,
        "year": None,
    }

    merger = MergeProcessing()
    ner_extractor: Optional[NERExtractor] = None
    try:
        ner_extractor = NERExtractor(backend="stanza")
        if not ner_extractor.is_available():
            ner_extractor = NERExtractor(backend="transformers")
            if not ner_extractor.is_available():
                ner_extractor = None
    except Exception:
        ner_extractor = None

    semantic_detector: Optional[SemanticConcepts] = None
    try:
        semantic_detector = SemanticConcepts()
        if not semantic_detector.is_available():
            semantic_detector = None
    except Exception:
        semantic_detector = None

    pattern_features = extract_features(raw_case)
    if semantic_detector and semantic_detector.is_available():
        try:
            semantic_detector.enhance_case_with_concepts(pattern_features)
        except Exception:
            pass

    ner_entities = None
    if ner_extractor and ner_extractor.is_available():
        try:
            ct = raw_case.get("case_text") or ""
            if ct:
                ner_entities = ner_extractor.extract_entities(ct)
        except Exception:
            ner_entities = None

    merged = merger.merge_features(pattern_features, ner_entities)
    case_with_values = assign_comparison_values(merged)
    ts = datetime.now().isoformat()
    case_with_values["created_at"] = ts
    case_with_values["updated_at"] = ts
    if not case_with_values.get("id"):
        case_with_values["id"] = case_label
    return case_with_values


def _models_dir_from_env() -> Optional[Path]:
    d = os.environ.get("CASELINKER_MODELS_DIR")
    if d and str(d).strip():
        return Path(d).expanduser()
    return None


def default_bundle_path() -> Path:
    p = os.environ.get("CASELINKER_TRIAGE_BUNDLE")
    if p:
        return Path(p)
    md = _models_dir_from_env()
    if md is not None:
        return md / "triage_bundle.joblib"
    return _REPO_ROOT / "models" / "triage_bundle.joblib"


def default_corpus_predictions_path() -> Path:
    p = os.environ.get("CASELINKER_TRIAGE_CORPUS_JSON")
    if p:
        return Path(p)
    md = _models_dir_from_env()
    if md is not None:
        return md / "triage_corpus_predictions.json"
    return _REPO_ROOT / "models" / "triage_corpus_predictions.json"


def build_corpus_predictions_payload(
    cases: List[Dict[str, Any]],
    bundle: TriageModelBundle,
    bundle_path_resolved: str,
) -> Dict[str, Any]:
    """
    Run the saved bundle on every case row (same features as training inference).
    """
    if not cases:
        raise ValueError("no cases")

    df = cases_to_dataframe(cases, include_agencies=bundle.use_agencies)
    X = df.drop(columns=["id"])
    pred = bundle.pipeline.predict(X)
    class_names = list(bundle.class_names)

    ids = df["id"].tolist()
    model_case_ids_by_tier: Dict[str, List[str]] = {n: [] for n in class_names}
    for i, cid in enumerate(ids):
        if cid is None:
            continue
        tier = class_names[int(pred[i])]
        model_case_ids_by_tier[tier].append(str(cid))

    for t in model_case_ids_by_tier:
        model_case_ids_by_tier[t] = sorted(model_case_ids_by_tier[t])

    return {
        "version": 1,
        "generated_at": datetime.now().isoformat(),
        "bundle_path": bundle_path_resolved,
        "class_names": class_names,
        "model_case_ids_by_tier": model_case_ids_by_tier,
        "n_cases": len(cases),
    }


def write_corpus_predictions_file(
    out_path: Optional[Path] = None,
    bundle_path: Optional[Path] = None,
    db_path: Optional[str] = None,
) -> Path:
    """
    Offline: load DB cases + triage bundle, predict tier for every case, write JSON for the API/UI.

    Example:
      python3 "src/Clustering & Analysis Layer/triage.py" --write-corpus
    """
    _storage = _REPO_ROOT / "src" / "Storage Layer"
    if str(_storage) not in sys.path:
        sys.path.insert(0, str(_storage))

    bundle_path = bundle_path or default_bundle_path()
    out_path = out_path or default_corpus_predictions_path()

    bundle = load_triage_bundle(bundle_path)
    if os.getenv("DATABASE_URL"):
        try:
            from storage_postgres import CaseStorage
        except ImportError as e:
            raise SystemExit(
                "DATABASE_URL is set but PostgreSQL storage is unavailable "
                "(install psycopg2-binary). " + str(e)
            ) from e
        storage = CaseStorage()
    else:
        from storage import CaseStorage

        db = db_path or os.environ.get("CASELINKER_DB") or str(_REPO_ROOT / "caselinker.db")
        storage = CaseStorage(str(db))
    cases = storage.get_all_cases(include_raw_data=False)
    payload = build_corpus_predictions_payload(
        cases,
        bundle,
        str(Path(bundle_path).resolve()),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _patch_main_for_train_triage_pickles() -> None:
    """
        joblib bundles created by running `python scripts/run/train_triage_model.py` pickle
    classes as __main__.TriageModelBundle / __main__.TriageFeatures. The API process
    has a different __main__ (e.g. uvicorn / run.main), so unpickling fails unless we
    alias those names onto sys.modules['__main__'] before load.
    """
    import train_triage_model as tm

    main_mod = sys.modules.get("__main__")
    if main_mod is None:
        return
    for name in ("TriageModelBundle", "TriageFeatures"):
        if hasattr(tm, name) and not hasattr(main_mod, name):
            setattr(main_mod, name, getattr(tm, name))


def load_triage_bundle(path: Optional[Path] = None) -> TriageModelBundle:
    bundle_path = path or default_bundle_path()
    if not bundle_path.is_file():
        raise FileNotFoundError(
            f"Triage model bundle not found: {bundle_path}. "
            "Train one with: python3 scripts/run/train_triage_model.py --out models/triage_bundle.joblib"
        )
    _patch_main_for_train_triage_pickles()
    bundle: TriageModelBundle = joblib.load(bundle_path)
    normalize_triage_bundle_after_load(bundle)
    return bundle


def run_live_triage(
    raw_text: str,
    bundle_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Parse batch text, run processing pipeline per segment, predict tiers with the bundle.

    Returns:
      class_names, case_ids_by_tier (predicted), predictions (per case), n_cases
    """
    segments = parse_live_case_input(raw_text)
    if not segments:
        return {
            "ok": False,
            "error": "empty_input",
            "message": "No case text to process.",
            "class_names": [],
            "case_ids_by_tier": {},
            "predictions": [],
            "n_cases": 0,
        }

    bundle = load_triage_bundle(bundle_path)
    structured: List[Dict[str, Any]] = []
    for seg in segments:
        label = f"Case {seg['case_number']}"
        structured.append(_process_one_narrative(seg["text"], label))

    df = cases_to_dataframe(structured, include_agencies=bundle.use_agencies)
    X = df.drop(columns=["id"])

    pipe = bundle.pipeline
    pred_idx = pipe.predict(X)
    proba = pipe.predict_proba(X)
    class_names = list(bundle.class_names)

    case_ids_by_tier: Dict[str, List[str]] = {name: [] for name in class_names}
    predictions: List[Dict[str, Any]] = []

    for row_i, seg in enumerate(segments):
        pi = int(pred_idx[row_i])
        label_name = class_names[pi] if pi < len(class_names) else str(pi)
        cid = f"Case {seg['case_number']}"
        case_ids_by_tier.setdefault(label_name, []).append(cid)

        probs_row = proba[row_i]
        prob_map: Dict[str, float] = {}
        for j, cname in enumerate(class_names):
            if j < len(probs_row):
                prob_map[cname] = float(probs_row[j])

        predictions.append(
            {
                "case_number": seg["case_number"],
                "case_label": cid,
                "label": label_name,
                "class_index": pi,
                "probabilities": prob_map,
            }
        )

    for tier in case_ids_by_tier:
        case_ids_by_tier[tier] = sorted(case_ids_by_tier[tier])

    return {
        "ok": True,
        "class_names": class_names,
        "case_ids_by_tier": case_ids_by_tier,
        "predictions": predictions,
        "n_cases": len(segments),
        "bundle_path": str(bundle_path or default_bundle_path()),
        "use_agencies": bundle.use_agencies,
    }


def _cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="CaseLinker triage helpers (live bundle + offline corpus predictions).",
    )
    parser.add_argument(
        "--write-corpus",
        action="store_true",
        help="Predict tiers for all DB cases with the saved bundle; write triage_corpus_predictions.json",
    )
    parser.add_argument("--db", type=str, default=None, help="SQLite path (default: CASELINKER_DB or caselinker.db)")
    parser.add_argument("--bundle", type=str, default=None, help="Triage .joblib path (default: models/triage_bundle.joblib)")
    parser.add_argument("--out", type=str, default=None, help="Output JSON path (default: models/triage_corpus_predictions.json)")
    args = parser.parse_args()

    if args.write_corpus:
        bp = Path(args.bundle) if args.bundle else None
        op = Path(args.out) if args.out else None
        out = write_corpus_predictions_file(out_path=op, bundle_path=bp, db_path=args.db)
        print(f"Wrote full-corpus model predictions: {out}")
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
