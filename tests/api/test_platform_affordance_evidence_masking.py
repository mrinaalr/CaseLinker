"""Platform-affordance evidence carries no person names, and only its two public files are served.

The evidence file is built offline and served as a static file, so it never passes through the API's
person masking. The builder masks every string it copies from a release (quote, harm, reasoning
preview, PSA sample, db-gap snippet) with the case's stored person spans, as case pages do.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "ontology" / "platform_affordance_evidence"
EVIDENCE = EVIDENCE_DIR / "platform_affordance_evidence.json"

sys.path.insert(0, str(EVIDENCE_DIR))
sys.path.insert(0, str(ROOT / "src" / "Processing Layer"))
import platform_affordance_evidence as pae  # noqa: E402
from field_assertions import people_mask as pm  # noqa: E402

TEXT = ("United States Attorney John Doe announced the sentence.\n"
        "Investigators said Richard Roe used Grindr and Kik to send images to the victim.\n"
        "Roe was charged with distribution of child sexual abuse material.")


def _span(text: str, s: str):
    i = text.index(s)
    return [i, i + len(s)]


SPANS = [_span(TEXT, "John Doe"), _span(TEXT, "Richard Roe"), _span(TEXT, "Grindr"),
         [TEXT.rindex("Roe"), TEXT.rindex("Roe") + 3]]


def _result(quote: str):
    return {
        "records": [{"evidence_quote": quote, "harm": "Richard Roe used Grindr",
                     "your_reasoning": f'Sentence ties Kik to offense conduct: "{quote}"'}],
        "exclusions": [{"exclusion_reason": 'PSA-only. Sample: "John Doe announced the..."'}],
        "db_gaps": [{"found_in": "John Doe announced the sentence."}, {"found_in": "(found in text)"}],
    }


def test_every_copied_string_is_masked():
    r = _result("Investigators said Richard Roe used Grindr and Kik to send images to the victim.")
    pae.mask_case_strings(r, TEXT, SPANS, pm)
    rec = r["records"][0]
    for s in (rec["evidence_quote"], rec["harm"], rec["your_reasoning"],
              r["exclusions"][0]["exclusion_reason"], r["db_gaps"][0]["found_in"]):
        assert "Roe" not in s and "John Doe" not in s, s
        assert pm.PERSON_MASK in s, s
    assert r["db_gaps"][1]["found_in"] == "(found in text)"


def test_platform_name_stored_as_a_person_is_kept():
    r = _result("Investigators said Richard Roe used Grindr and Kik to send images to the victim.")
    pae.mask_case_strings(r, TEXT, SPANS, pm)
    assert "Grindr" in r["records"][0]["evidence_quote"]
    assert "Kik" in r["records"][0]["evidence_quote"]


def test_truncated_quote_keeps_its_ellipsis():
    q = pae.extract_quote("Investigators said Richard Roe used Grindr and Kik to send images to the victim.", 40)
    assert q.endswith("...")
    r = _result(q)
    pae.mask_case_strings(r, TEXT, SPANS, pm)
    out = r["records"][0]["evidence_quote"]
    assert out.endswith("...") and "Roe" not in out and pm.PERSON_MASK in out


def test_fragment_not_in_release_is_masked_by_name():
    # extract_harm reads lines joined after short lines are dropped, so its text is not always a substring.
    r = _result("x")
    r["records"][0]["harm"] = "distribution while Richard  Roe was on release"
    pae.mask_case_strings(r, TEXT, SPANS, pm)
    assert "Roe" not in r["records"][0]["harm"]


def test_committed_file_is_masked():
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    masked = sum(pm.PERSON_MASK in (r.get("evidence_quote") or "") for r in data["records"])
    assert masked > 1000, masked


def _corpus_db() -> Path:
    for p in (os.environ.get("CASELINKER_DB"), ROOT / "caselinker.db"):
        if p and Path(p).is_file() and Path(p).stat().st_size > 0:
            return Path(p)
    return None


@pytest.mark.skipif(_corpus_db() is None, reason="corpus DB not present (set CASELINKER_DB)")
def test_committed_file_holds_no_stored_person_name():
    conn = sqlite3.connect(f"file:{_corpus_db()}?mode=ro", uri=True)
    if conn.execute("SELECT count(*) FROM sqlite_master WHERE name='cases'").fetchone()[0] == 0:
        pytest.skip("corpus DB has no cases table")
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    ids = {r["case_id"] for k in ("records", "excluded_platforms", "db_gaps") for r in data[k]}
    names = {}
    for cid, text, ef in conn.execute(
            "SELECT id, json_extract(raw_data, '$.case_text'), extracted_features FROM cases"):
        if cid in ids:
            text = text or ""
            spans = pae.drop_platform_spans(text, pm.spans_for(json.loads(ef) if ef else {}, text))
            names[cid] = [re.compile(r"(?<![A-Za-z])" + re.escape(" ".join(text[s:e].split())) + r"(?![A-Za-z])")
                          for s, e in spans if e - s >= 3]
    if not names:
        pytest.skip("corpus DB does not hold these cases")

    def leaks(s, cid):
        s = " ".join((s or "").split())
        return any(p.search(s) for p in names.get(cid, ()))

    bad = [r["case_id"] for r in data["records"]
           if any(leaks(r.get(k), r["case_id"]) for k in ("evidence_quote", "harm", "your_reasoning"))]
    bad += [r["case_id"] for r in data["excluded_platforms"] if leaks(r.get("exclusion_reason"), r["case_id"])]
    bad += [r["case_id"] for r in data["db_gaps"] if leaks(r.get("found_in"), r["case_id"])]
    assert bad == [], f"{len(bad)} strings hold a stored person name, e.g. {bad[:5]}"


def _app():
    spec = importlib.util.spec_from_file_location("caselinker_run_main", ROOT / "run" / "main.py")
    main = sys.modules.get("caselinker_run_main")
    if main is None:
        main = importlib.util.module_from_spec(spec)
        sys.modules["caselinker_run_main"] = main
        spec.loader.exec_module(main)
    return main.app


@pytest.mark.parametrize("name", ["platform_affordance_evidence.json",
                                  "platform_affordance_evidence_harm_analysis.json"])
def test_public_files_are_served(name):
    r = TestClient(_app()).get(f"/ontology/platform-affordance-evidence/{name}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["candidates.json", "platform_affordance_evidence.py",
                                  "platform_affordance_evidence_table.md", "afh_manifest/README.md",
                                  "afh_manifest/data/snapshot.sqlite", "afh_manifest/outputs/records.csv"])
def test_other_files_are_not_served(path):
    r = TestClient(_app()).get(f"/ontology/platform-affordance-evidence/{path}")
    assert r.status_code == 404, path
