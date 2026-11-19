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


@pytest.mark.parametrize("text, kind", [
    # doj_safe_childhood_2024_021: supervision after an earlier conviction, no sentencing verb
    ("At the time of his arrest he was on supervision following his prior conviction for possession.",
     {"on_supervision", "prior_conviction"}),
    # doj_safe_childhood_2024_307: a singular "offender with a previous conviction" is this defendant
    ("He is a registered sex offender with a previous conviction for possession.",
     {"registered_offender", "prior_conviction"}),
    # ncmec_2024_062: the charge names this defendant's earlier conviction
    ("He faces possession of child pornography by an individual with a previous conviction for possessing it.",
     {"prior_conviction"}),
])
def test_real_prior_history_the_first_exclusions_dropped(text, kind):
    assert set(_roles(text)) - {"not_prior"} == kind


def test_angel_watch_boilerplate_about_people_previously_convicted_is_not_prior():
    # doj_safe_childhood_2024_406
    text = "The program identifies individuals who have been previously convicted of sexual crimes against children."
    assert set(_roles(text)) <= {"not_prior"}


def test_a_sentencing_verb_before_an_abbreviation_still_makes_it_this_case():
    # doj_safe_childhood_2026_315, doj_safe_childhood_2026_392
    text = ("Corin Ashcombe, 60, was sentenced by U.S. District Judge Reese Thistlewood to 60 years in prison, "
            "following his previous conviction of five counts of production of child pornography.")
    assert set(_roles(text)) <= {"not_prior"}


@pytest.mark.parametrize("text, year", [
    # doj_ai_csam_2024_002: the date after the comma is this case's plea
    ("He has a prior federal felony conviction for possessing child pornography, pleaded guilty on Aug. 29, 2023.",
     None),
    # doj_safe_childhood_2024_322: the date dates this case's conduct
    ("Ashcombe was a registered sex offender in October of 2019, when he began messaging a girl.", None),
    ("Ashcombe is a registered sex offender from a 2013 conviction for indecent solicitation.", 2013),
    ("Ashcombe was previously convicted on August 23, 2019, of possession.", 2019),
])
def test_a_year_belongs_to_the_record_only_inside_its_clause(text, year):
    years = {(a.get("extras") or {}).get("year") for a in P.prior_history_assertions(text, 2024)
             if a["role"] != "not_prior"}
    assert years == {year}


@pytest.mark.parametrize("text", [
    # ncmec_2022_602
    "He doesn't appear to have any previous convictions, according to a records check.",
    # nj_ag_2017_013, nj_ag_2017_018, nj_ag_2018_003: statute boilerplate
    "The offense carries a presumptive sentence of three to five years in prison, whether or not the defendant "
    "has any prior felony conviction.",
    # vt_ag_2025_022: this case's suspended sentence
    "The Court sentenced the defendant to one to two years all suspended to be served while on probation supervision.",
    # vt_ag_2020_010: this case's probation conditions
    "Ashcombe was placed on probation for 10 years. While on probation, Ashcombe will be subject to special conditions.",
    # ncmec_2023_112
    "The judge sentenced Ashcombe to 2 years in jail but suspended all but 388 days while on probation.",
    # doj_archives_2006_007
    "His use of any computer will also be subject to monitoring while he is on supervised release.",
    # doj_safe_childhood_2022_324: registration as a term of this sentence
    "He will be sentenced to 10 to 12 years, followed by a term of lifetime supervision as a registered sex offender.",
])
def test_reviewer_round_one_cases_are_not_prior_history(text):
    assert set(_roles(text)) <= {"not_prior"}
    assert not (P._pp.extract_previous_conviction({"case_text": text, "year": "2024"}) or {}).get("has_prior_conviction")


def test_supervision_at_the_time_of_the_offense_still_counts():
    # doj_safe_childhood_2023_156
    text = ("At the time he possessed these images, Ashcombe was on federal supervised release for a prior federal "
            "conviction for possession of child pornography.")
    assert {"on_supervision", "prior_conviction"} <= set(_roles(text))


@pytest.mark.parametrize("text", [
    # doj_safe_childhood_2026_290
    "At the time of the offense, Ashcombe was on federal supervised release for a 2013 conviction of distribution.",
    # doj_safe_childhood_2024_036: this case's sentencing verb, earlier supervision
    "The judge sentenced a man who was caught with child pornography while on supervised release from a prior offense.",
    # doj_safe_childhood_2025_047
    "According to evidence presented at sentencing, Ashcombe, 55, was on federal supervised release for a conviction.",
])
def test_supervision_at_the_time_survives_this_cases_sentencing_words(text):
    assert "on_supervision" in _roles(text)


def test_conditions_in_the_sentence_before_do_not_make_supervision_this_cases():
    # doj_safe_childhood_2024_510, doj_safe_childhood_2022_100
    text = ("He had a phone he was prohibited from possessing under the conditions of his supervised release. "
            "Ashcombe was on federal supervision following a 2012 federal conviction for receipt.")
    assert "on_supervision" in _roles(text)
