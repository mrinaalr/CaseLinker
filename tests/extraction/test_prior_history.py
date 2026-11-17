"""prior_history: earlier convictions, registration and supervision per masked defendant (#64).

Every person is made up. Sentence shapes come from the issue's reads (case ids in comments).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROC = REPO / "src" / "Processing Layer"


def _load(name: str, path: Path):
    saved = list(sys.path)
    sys.path[:0] = [str(REPO / "src"), str(PROC)]
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path[:] = saved


A = _load("processing_prior_history_under_test", PROC / "processing.py").assertions_module
P = A.patterns

TWO = ("Corin Ashcombe, 34, of Riverton, was sentenced to 20 years. Ashcombe has two prior convictions for child "
       "sexual abuse and was on parole at the time. Reese Thistlewood, 41, a registered sex offender, was also "
       "charged. Thistlewood was convicted in 2008 of indecent exposure.")


def _persons(text, *names):
    out = []
    for name in names:
        start = 0
        while (i := text.find(name, start)) >= 0:
            out.append([i, i + len(name), name])
            start = i + len(name)
    return {"person_spans": sorted(out)}


def _roles(text, year=2024):
    return [a["role"] for a in P.prior_history_assertions(text, year)]


@pytest.mark.parametrize("text, kind", [
    ("He had two prior convictions for possession.", "prior_conviction"),             # doj_safe_childhood_2022_458
    ("He has a previous federal felony conviction for receipt.", "prior_conviction"),  # doj_safe_childhood_2025_193
    ("He was on parole at the time for an earlier offense.", "on_supervision"),        # us_marshals_2026_021
    ("Ashcombe, a registered sex offender, was arrested.", "registered_offender"),
    ("He was charged with failure to register as a sex offender.", "registered_offender"),  # ncmec_2023_288
    ("He was charged as a convicted felon in possession of a firearm.", "prior_conviction"),  # ky_sp_2024_020
    ("Ashcombe was convicted in 1996 of indecent assault.", "prior_conviction"),        # doj_ceos_2010_010
])
def test_each_shape_is_its_kind(text, kind):
    assert _roles(text, 2010 if "1996" in text else 2024) == [kind]


@pytest.mark.parametrize("text", [
    "He has no prior convictions.",
    "Neither defendant has a prior conviction in Ohio.",
    "He faces 15 years if he has a prior conviction for a sex offense.",
    "The law sets enhanced penalties for defendants with prior convictions.",
    "He was sentenced to 20 years following his previous conviction for ten counts.",  # doj_safe_childhood_2024_091
    "Ashcombe was convicted in 2023 of the charges.",
])
def test_negated_hypothetical_and_own_case_phrases_are_not_prior(text):
    assert set(_roles(text)) <= {"not_prior"}


def test_records_are_per_masked_defendant_with_what_the_phrase_states():
    asr = A.collect_assertions(TWO, case_id="t", use_spacy=False, overrides={}, batch_year=2024,
                               ner_entities=_persons(TWO, "Corin Ashcombe", "Reese Thistlewood", "Ashcombe",
                                                     "Thistlewood"))
    stored = [a for a in asr if a["field"] == "prior_history"]
    assert stored and all("defendant_entity" not in (a.get("extras") or {}) for a in stored)  # names never stored
    res = A.resolve(asr, text=TWO)
    final = res["prior_history"]["final_value"]
    by_person = {r["person"]: r for r in final["records"]}
    ages = {e["person"]: e["age"] for e in res["age"]["final_value"]["perpetrator_entities"]}
    p_ash = next(p for p, a in ages.items() if a == 34)
    p_thi = next(p for p, a in ages.items() if a == 41)
    assert by_person[p_ash]["kinds"] == ["on_supervision", "prior_conviction"]
    assert by_person[p_ash]["count"] == 2 and by_person[p_ash]["sex_offense"] is True and by_person[p_ash]["age"] == 34
    assert by_person[p_thi]["kinds"] == ["prior_conviction", "registered_offender"]
    assert by_person[p_thi]["years"] == [2008]
    assert final["has_prior_conviction"] and final["registered"] and final["on_supervision"]


def test_without_ner_the_record_is_case_level():
    res = A.resolve(A.collect_assertions("He has two prior convictions.", case_id="t", use_spacy=False,
                                         overrides={}, batch_year=2024), text="He has two prior convictions.")
    [rec] = res["prior_history"]["final_value"]["records"]
    assert rec["person"] is None and rec["count"] == 2


def test_only_not_prior_phrases_resolve_empty_and_are_counted():
    text = "He has no prior convictions."
    res = A.resolve(A.collect_assertions(text, case_id="t", use_spacy=False, overrides={}), text=text)
    assert res["prior_history"]["status"] == "empty"
    assert res["prior_history"]["disagreement"] == {"not_prior": 1}


def test_the_span_gate_keeps_only_prior_history_phrases():
    good = {"field": "prior_history", "value": "prior_conviction", "role": "prior_conviction",
            "span_start": 7, "span_end": 24, "method": "regex", "confidence": 0.85}
    text = "He had prior convictions."
    assert A.gate_assertion(text, good)["span_ok"] == 1
    assert A.gate_assertion(text, {**good, "span_start": 0, "span_end": 6})["span_ok"] == 0


def test_reresolve_appends_prior_history_without_a_defendant():
    module = _load("reresolve_prior_history_under_test", REPO / "scripts" / "run" / "reresolve_assertions.py")
    fresh = [a for a in module._new_detected([], TWO) if a["field"] == "prior_history"]
    assert fresh and all("defendant_entity" not in (a.get("extras") or {}) for a in fresh)


def test_a_sentence_naming_no_one_keeps_its_record_on_the_case_not_on_a_person():
    res = A.resolve(A.collect_assertions(TWO, case_id="t", use_spacy=False, overrides={}, batch_year=2024,
                                         ner_entities=_persons(TWO, "Reese Thistlewood")), text=TWO)
    persons = {r["person"] for r in res["prior_history"]["final_value"]["records"]}
    assert None in persons  # unattributed phrases stay case-level; the mapper puts them on the case node
