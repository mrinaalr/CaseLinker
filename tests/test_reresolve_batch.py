"""A batched re-resolve writes the same payloads as one commit per case."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import processing  # noqa: E402
from storage import CaseStorage  # noqa: E402

A = processing.assertions_module

_SCRIPT = REPO / "scripts" / "run" / "reresolve_assertions.py"


def _reresolve():
    spec = importlib.util.spec_from_file_location("reresolve_assertions", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case(text: str, case_id: str) -> dict:
    raw = {"case_text": text, "case_id": case_id, "source": "TEST", "source_file": "t.pdf", "year": "2025"}
    features = processing.extract_features(raw)
    return processing.assign_comparison_values(processing.MergeProcessing().merge_features(features, None))


def _seed(path: Path, cases: list[dict]) -> None:
    storage = CaseStorage(str(path))
    assert storage.store_cases(cases) == len(cases)


def _payload(path: Path) -> dict:
    conn = sqlite3.connect(path)
    resolutions = conn.execute(
        """SELECT case_id, field, status, rule_id, rule_set_version, final_json,
                  disagreement_json, winning_assertion_ids
           FROM field_resolutions ORDER BY case_id, field, id"""
    ).fetchall()
    reviews = conn.execute(
        """SELECT case_id, field, reason, detail_json, status
           FROM review_queue ORDER BY case_id, field, reason, detail_json"""
    ).fetchall()
    features = [
        (case_id, json.loads(blob))
        for case_id, blob in conn.execute(
            "SELECT id, extracted_features FROM cases ORDER BY id"
        )
    ]
    sentences = conn.execute(
        "SELECT case_id, status, charges, sentences FROM prosecution_outcomes ORDER BY case_id"
    ).fetchall()
    conn.close()
    return {"resolutions": resolutions, "reviews": reviews, "features": features, "sentences": sentences}


def _reresolve_items(storage: CaseStorage, case_ids: list[str]) -> list[dict]:
    module = _reresolve()
    items = []
    for case_id in case_ids:
        run_id, stored = storage.load_case_assertions(case_id)
        case = storage.get_case(case_id) or {}
        text = case.get("case_text") or ""
        resolutions = A.resolve(
            stored,
            batch_date=(case.get("date_range") or {}).get("start"),
            text=text,
        )
        items.append({
            "case_id": case_id,
            "run_id": run_id,
            "resolutions": resolutions,
            "new_assertions": None,
            "case": module._rederive_case(case, stored, resolutions),
        })
    return items


TWO_UNNAMED = (
    "Police arrested a 40-year-old man in Tulsa and a 40-year-old man in Omaha. "
    "Both men were charged with sexual exploitation of a minor."
)


def test_reresolve_script_passes_case_text_into_resolve(tmp_path: Path, monkeypatch):
    """The re-resolve script must pass case_text; without it two places collapse to one age."""
    case = _case(TWO_UNNAMED, "two_unnamed_40")
    path = tmp_path / "two.db"
    _seed(path, [case])
    monkeypatch.setenv("CASELINKER_DB", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    calls = []
    real_resolve = A.resolve

    def spy(assertions, *, batch_date=None, text=None):
        calls.append(text)
        return real_resolve(assertions, batch_date=batch_date, text=text)

    monkeypatch.setattr(A, "resolve", spy)
    module = _reresolve()
    # Re-bind the script's processing.assertions_module.resolve after reload.
    monkeypatch.setattr(module.processing.assertions_module, "resolve", spy)
    monkeypatch.setattr(sys, "argv", ["reresolve_assertions.py", "--case-ids", "two_unnamed_40"])
    assert module.main() == 0
    assert calls and all(c and "Tulsa" in c and "Omaha" in c for c in calls)

    storage = CaseStorage(str(path))
    latest = storage.get_case_assertions("two_unnamed_40")["resolutions"]["age"]
    entities = (latest.get("final_value") or {}).get("perpetrator_entities") or []
    assert len(entities) == 2
    assert [e["age"] for e in entities] == [40, 40]


def test_reresolve_applies_resolved_publication_dates(tmp_path: Path):
    """Legacy date_range must pick up a resolved publication day on re-derive."""
    module = _reresolve()
    case = {
        "id": "date_reresolve",
        "source": "TEST",
        "date_range": {"start": "2024-01-01", "end": "2024-01-01"},
        "case_text": "Published March 15, 2024.",
        "extracted_features": {},
    }
    resolutions = {
        "date": {
            "rule_set_version": "resolve_v3.0",
            "status": "resolved",
            "rule_id": "publication",
            "final_value": {"publication": "2024-03-15", "batch_date": "2024-01-01"},
            "winning_assertion_ids": [],
            "disagreement": {},
            "review": [],
        }
    }
    rebuilt = module._rederive_case(case, [], resolutions)
    assert rebuilt["date_range"]["start"] == "2024-03-15"


def test_batched_reresolve_matches_one_commit_per_case(tmp_path: Path):
    texts = {
        "doj_safe_childhood_2025_325": (
            "LEXINGTON, Ky. – A Lexington man, Avery Quinn Oakhollow, 30, was sentenced to 50 years in prison. "
            "Oakhollow, then 27 years-old, met the 12-year-old victim on Snapchat."
        ),
        "self_contradiction_student": (
            "The jailing of a 22-year-old student followed his arrest on the charge."
        ),
    }
    cases = [_case(text, case_id) for case_id, text in texts.items()]
    single = tmp_path / "single.db"
    batched = tmp_path / "batched.db"
    _seed(single, cases)
    _seed(batched, cases)

    one = CaseStorage(str(single))
    for item in _reresolve_items(one, list(texts)):
        one.append_resolutions(item["case_id"], item["run_id"], item["resolutions"], item["new_assertions"])
        assert one.store_case(item["case"])

    many = CaseStorage(str(batched))
    assert many.apply_reresolve_batch(_reresolve_items(many, list(texts))) == 2

    assert _payload(single) == _payload(batched)


def test_batch_of_one_still_commits(tmp_path: Path):
    case = _case("Rowan Pinecrest, 40, of Tulsa, was sentenced to 8 years in prison.", "batch_one")
    path = tmp_path / "one.db"
    _seed(path, [case])
    storage = CaseStorage(str(path))
    items = _reresolve_items(storage, ["batch_one"])
    assert storage.apply_reresolve_batch(items) == 1
    conn = sqlite3.connect(path)
    # The ingest resolution plus the re-resolve.
    assert conn.execute("SELECT COUNT(*) FROM field_resolutions WHERE field = 'age'").fetchone()[0] == 2
    conn.close()
