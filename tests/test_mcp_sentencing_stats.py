"""get_sentencing_stats: imposed-only, one outcome or drop reason per case (#29)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from assertion_store import write_case_assertions
from caselinker_mcp import server
from storage import CaseStorage

FINAL_KEYS = ("imposed", "exposure", "supervised_release", "probation", "fine", "custody", "prior")


def _res(status="resolved", unknown=(), **buckets):
    final = {k: list(buckets.get(k, [])) for k in FINAL_KEYS}
    final["contested"] = {}
    return {
        "rule_set_version": "resolve_v3.0",
        "status": status,
        "rule_id": "test",
        "final_value": final,
        "winning_assertion_ids": [],
        "disagreement": {"contested": {}, "unknown_spans": [{"value": u, "span": [0, 1]} for u in unknown]},
        "review": [],
    }


def _imposed(text: str, value: str, role: str = "imposed", nth: int = 0) -> dict:
    start = -1
    for _ in range(nth + 1):
        start = text.index(value, start + 1)
    return {
        "field": "sentence", "method": "regex", "method_version": "test", "family": "surface_pattern",
        "value": value, "role": role, "span_start": start, "span_end": start + len(value),
        "span_text": value, "span_ok": True, "confidence": 0.9, "extras": {},
    }


TEXT_CLEAN = "A man was sentenced to 15 years in federal prison followed by 20 years of supervised release."
TEXT_TWO = "He was sentenced to 10 years in prison. Unrelated filler text follows here. Also sentenced to 5 years."
TEXT_SPLIT = "He was sentenced to 100 years with 50 years suspended."
TEXT_CODEF = "Both men were sentenced; the co-defendant received 12 years and he received 8 years."

# case_id -> (case_text, booking_status, sentence resolution or None, asserted spans).
# A span is a value (role imposed) or a (role, value) pair.
CASES = {
    "clean": (TEXT_CLEAN, "sentenced", _res(imposed=["15 years"], supervised_release=["20 years"]), ["15 years"]),
    "two_terms": (TEXT_TWO, "sentenced", _res(imposed=["10 years", "5 years"]), ["10 years", "5 years"]),
    "list_form": ("He was sentenced to 360 and 24 months.", "sentenced", _res(imposed=["360 and 24 months"]), ["360 and 24 months"]),
    "life": ("He was sentenced to life in prison.", "sentenced", _res(imposed=["sentenced to life"]), ["sentenced to life"]),
    "to_life": ("He was sentenced to three years to life.", "sentenced", _res(imposed=["three years to life"]), ["three years to life"]),
    "probation": ("He was sentenced to five years of probation.", "sentenced", _res(probation=["five years"]),
                  [("probation", "five years")]),
    "exposure": ("He faces up to 30 years in prison.", "charged", _res(exposure=["30 years"]), []),
    "pending": ("He was charged and booked into the county jail.", "charged", _res(custody=["booked into the county jail"]), []),
    "nothing": ("A press release with no sentence.", "sentenced", _res(status="empty"), []),
    "unlabelled": (TEXT_CLEAN, "sentenced", _res(unknown=["the following two days"], imposed=["15 years"]), ["15 years"]),
    "review": (TEXT_CLEAN, "sentenced", _res(status="needs_review"), []),
    "no_resolution": (TEXT_CLEAN, "sentenced", None, []),
    "split": (TEXT_SPLIT, "sentenced", _res(imposed=["100 years", "50 years"]), ["100 years", "50 years"]),
    "suspended": ("He was sentenced to 10 years in prison, all but 4 suspended.", "sentenced", _res(imposed=["10 years"]), ["10 years"]),
    "codefendant": (TEXT_CODEF, "sentenced", _res(imposed=["12 years", "8 years"]), ["12 years", "8 years"]),
    "money": ("He was ordered to pay $500.", "sentenced", _res(imposed=["$500"]), ["$500"]),
    # Resolver mislabels the context guard must catch.
    "no_context": ("Recruits may one day wear the uniform.", "sentenced", _res(imposed=["one day"]), ["one day"]),
    "statutory": ("If sentenced, he faces a maximum of 15 years in prison.", "sentenced", _res(imposed=["15 years"]), ["15 years"]),
    "plea_term": ("The plea agreement calls for him to be sentenced to 25 years in prison.", "sentenced",
                  _res(imposed=["25 years"]), ["25 years"]),
    "recommended": ("Prosecutors are recommending that he be sentenced to 30 years in prison.", "sentenced",
                    _res(imposed=["30 years"]), ["30 years"]),
    "law_provides": ("The law provides for a total sentence of 80 years in prison.", "sentenced", _res(imposed=["80 years"]), ["80 years"]),
    "prior": ("He has a prior federal conviction, for which he was sentenced to 7 years in prison.", "sentenced",
              _res(imposed=["7 years"]), ["7 years"]),
    "other_sentence": ("He was sentenced on Monday. The program lasts 3 years for most participants.", "sentenced",
                       _res(imposed=["3 years"]), ["3 years"]),
    # Kept: initials and "U.S." do not end the sentence; "by agreement" after "sentenced" is imposed.
    "initials": ("He was sentenced by U.S. District Judge James D. Cain, Jr. to 180 months for receipt.", "sentenced",
                 _res(imposed=["180 months"]), ["180 months"]),
    "jailed_for": ("A man has been jailed for 18 years for the offences.", "sentenced", _res(imposed=["18 years"]), ["18 years"]),
    "custody_after": ("A man got 6 years in prison for the offences.", "sentenced", _res(imposed=["6 years"]), ["6 years"]),
    "by_agreement": ("The Court sentenced the defendant by agreement to 2 years in jail.", "sentenced",
                     _res(imposed=["2 years"]), ["2 years"]),
    # Non-custodial only through an imposed probation or fine span.
    "fined": ("The court fined him $5,000 for the offence.", "sentenced", _res(fine=["$5,000"]), [("fine", "$5,000")]),
    "statutory_fine": ("If sentenced, he faces a fine of up to $250,000.", "sentenced", _res(fine=["$250,000"]),
                       [("fine", "$250,000")]),
    "restitution": ("The judge ordered him to pay a fine and $5,000 restitution.", "sentenced", _res(fine=["$5,000"]),
                    [("fine", "$5,000")]),
    # The same value restated without a verb does not sink the sentence that has one.
    "restated": ("He was sentenced to 360 months in prison. His term of imprisonment consists of 360 months on each count.",
                 "sentenced", _res(imposed=["360 months"]), ["360 months", ("imposed", "360 months", 1)]),
    "restated_prior": ("He was sentenced to 9 years in prison. A co-defendant was previously sentenced to 9 years.", "sentenced",
                       _res(imposed=["9 years"]), ["9 years", ("imposed", "9 years", 1)]),
    "range_cut": ("He will serve 16½ to 33 years in prison.", "sentenced", _res(imposed=["33 years"]), ["33 years"]),
    "convicted_in_year": ("He was convicted in May 2022 and was placed on probation for five years.", "sentenced",
                          _res(probation=["five years"]), [("probation", "five years")]),
    "exposure_and_probation": ("He faced up to 10 years. He was sentenced to 3 years of probation.", "sentenced",
                               _res(exposure=["10 years"], probation=["3 years"]), [("probation", "3 years")]),
}


@pytest.fixture
def db(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "sent.db"
    storage = CaseStorage(str(path))
    for cid, (text, status, _res_, _imp) in CASES.items():
        storage.store_case({
            "id": cid,
            "source": "TEST",
            "raw_data": {"source_file": "t.pdf", "case_text": text, "case_id": cid},
            "prosecution_outcome": {"booking_status": status, "charges": [], "sentences": []},
        })
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    for cid, (text, _status, res, imposed) in CASES.items():
        if res is None:
            continue
        write_case_assertions(
            cur, case_id=cid, run_id=f"run-{cid}",
            assertions=[_imposed(text, v[1], v[0], *v[2:]) if isinstance(v, tuple) else _imposed(text, v) for v in imposed]
            or [_imposed("x", "x")],
            resolutions={"sentence": res}, dialect="sqlite",
        )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CASELINKER_DB", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return path


def _run(ids):
    fn = getattr(server.get_sentencing_stats, "fn", server.get_sentencing_stats)
    return asyncio.run(fn(case_ids=ids))


def test_each_case_gets_one_outcome_or_drop_reason(db):
    out = _run(list(CASES) + ["missing_id"])
    by = {c["case_id"]: (c.get("outcome") or c["reason"]) for c in out["cases"]}
    assert by == {
        "clean": "custodial",
        "two_terms": "split_or_suspended_term",  # 10 vs 5 years: max/min >= 2
        "list_form": "custodial",
        "life": "life",
        "to_life": "indeterminate_term",
        "probation": "non_custodial",
        "exposure": "statutory_max",
        "pending": "pending",
        "nothing": "no_sentence",
        "unlabelled": "kind_unknown",
        "review": "kind_unknown",
        "no_resolution": "kind_unknown",
        "split": "split_or_suspended_term",
        "suspended": "split_or_suspended_term",
        "codefendant": "multi_defendant_suspected",
        "money": "unparseable_term",
        "no_context": "doubtful_imposed_context",
        "statutory": "doubtful_imposed_context",
        "plea_term": "doubtful_imposed_context",
        "recommended": "doubtful_imposed_context",
        "law_provides": "doubtful_imposed_context",
        "prior": "doubtful_imposed_context",
        "other_sentence": "doubtful_imposed_context",
        "initials": "custodial",
        "jailed_for": "custodial",
        "custody_after": "custodial",
        "by_agreement": "custodial",
        "fined": "non_custodial",
        "statutory_fine": "statutory_max",
        "restitution": "doubtful_imposed_context",
        "exposure_and_probation": "non_custodial",
        "range_cut": "indeterminate_term",
        "restated": "custodial",
        "restated_prior": "doubtful_imposed_context",
        "convicted_in_year": "doubtful_imposed_context",
        "missing_id": "not_found",
    }
    assert out["n_requested"] == 36
    assert out["n_used"] == 11
    assert out["n_dropped"] == 25
    assert out["dropped"]["kind_unknown"] == 3
    assert out["kind_unknown_detail"] == {"unlabelled_span": 1, "review_status": 1, "no_current_resolution": 1}
    assert out["dropped"]["statutory_max"] == 2 and out["dropped"]["pending"] == 1
    assert out["outcomes"] == {"custodial": 7, "life": 1, "non_custodial": 3}
    assert out["dropped"]["doubtful_imposed_context"] == 10
    assert out["interpretation_kind"] == "imposed_sentence_summary"
    assert "not a validated disparity" in out["interpretation_note"]


def test_aggregation_is_longest_single_term_and_lists_are_not_ranges(db):
    out = _run(["clean", "list_form"])
    months = {c["case_id"]: c["months"] for c in out["cases"]}
    # Supervised release never counts; "360 and 24 months" is two terms, longest is 360.
    assert months == {"clean": 180, "list_form": 360}
    assert out["custodial_months"] == {"n": 2, "median": 270.0, "mean": 270.0, "min": 180.0, "max": 360.0}
    assert out["flags"]["list_form"] == 1


def test_exposure_beats_pending_and_never_becomes_months(db):
    out = _run(["exposure"])
    assert out["n_used"] == 0 and out["custodial_months"] == {"n": 0}
    assert out["dropped"]["statutory_max"] == 1


def test_fails_closed_on_empty_input():
    out = asyncio.run(getattr(server.get_sentencing_stats, "fn", server.get_sentencing_stats)(case_ids=[]))
    assert out["error"]
