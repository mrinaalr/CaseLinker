"""Program-history dates are not case events; case events carry a kind.

Regression: "Project Safe Childhood, a nationwide initiative launched in May
2006" was stored as role=event in 2,358 of 10,802 cases.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "temporal_tags", ROOT / "src" / "Processing Layer" / "Pattern Processing Layer" / "temporal_tags.py")
tt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tt)


def roles(text: str):
    return [(a["value"], a["role"], a["extras"].get("event_kind"))
            for a in tt.temporal_assertions(text, [], 2024) if a["field"] == "date"]


HEAD = "Synthetic Town Man Sentenced\nMarch 3, 2024\n\n"

BOILERPLATE = [
    "This case was brought as part of Project Safe Childhood, a nationwide initiative launched in May 2006 by the Department of Justice to combat the growing epidemic of child sexual exploitation and abuse.",
    "This case is part of Project Safe Childhood, a nationwide initiative launched by the Department of Justice in May 2006 to combat child sexual exploitation.",
    "The case is brought as part of Project Safe Childhood. In 2006, the Department of Justice created Project Safe Childhood, a nationwide initiative designed to protect children.",
    "Since 2006, the Attorney General's ICAC Task Force has been involved in more than 1,840 arrests of sexual predators.",
    "Since 2019, the Attorney General's ICAC Task Force has received more than 24,100 CyberTips.",
    "Since the launch of Operation Predator in 2003, HSI has arrested more than 10,000 individuals for crimes against children.",
    "There have been 650 arrests in the state by the ICAC Task Force since it was established in 2002.",
]


def test_program_history_dates_are_boilerplate():
    for sentence in BOILERPLATE:
        got = roles(HEAD + sentence)
        program = [r for r in got if r[0][:4] in ("2002", "2003", "2006", "2019")]
        assert program and all(r[1] == "program_boilerplate" for r in program), (sentence, got)


def test_case_events_next_to_program_names_stay_events():
    text = HEAD + (
        "Between November 2021 and November 2023, the defendant received child pornography. "
        "He was arrested in January 2024 after an investigation by the ICAC Task Force. "
        "This case was brought as part of Project Safe Childhood, a nationwide initiative launched in May 2006."
    )
    got = {v: (r, k) for v, r, k in roles(text)}
    assert got["2021-11"] == ("event", "offense")
    assert got["2023-11"][0] == "event"
    assert got["2024-01"] == ("event", "arrest")
    assert got["2006-05"][0] == "program_boilerplate"


def test_began_communicating_is_offense_not_program():
    text = HEAD + "In June 2021, the defendant began communicating with a 13-year-old girl on a messaging app."
    assert roles(text)[-1] == ("2021-06", "event", "offense")


def test_operation_arrest_is_an_event():
    text = HEAD + "Agents with Operation Synthetic Sweep arrested the defendant in October 2023 at his home."
    assert roles(text)[-1] == ("2023-10", "event", "arrest")


def test_event_kinds():
    cases = {
        "A federal grand jury indicted him in August 2022 on two counts.": "prosecution",
        "Investigators executed a search warrant in February 2023 at the residence.": "investigation",
        "He uploaded the files in July 2020 according to the complaint.": "offense",
        "Something happened in April 2019 that the release does not describe.": "unknown",
    }
    for sentence, kind in cases.items():
        assert roles(HEAD + sentence)[-1][2] == kind, sentence


def test_publication_dates_untouched():
    got = roles(HEAD + "The defendant pleaded guilty.")
    assert got[0] == ("2024-03-03", "publication", None)


def test_this_cases_investigation_and_operation_dates_stay_events():
    for sentence, value in {
        "The investigation began in February 2017 as the result of a proactive initiative by police.": "2017-02",
        "The agency began its investigation in January 2018 when the unit received a referral.": "2018-01",
        "Operation Synthetic Nest, launched in February 2008, targeted 26 defendants charged in the district.": "2008-02",
        "Evidence at the hearing established that between August 2020 and August 2021 he used a peer-to-peer network.": "2020-08",
    }.items():
        got = [r for r in roles(HEAD + sentence) if r[0] == value]
        assert got and got[0][1] == "event", (sentence, got)


def test_other_program_foundings_are_boilerplate():
    for sentence, value in {
        "The Synthetic County Child Predator Task Force, which the Attorney General established in 2007, investigated.": "2007",
        "Formed in November 2004, the goals of the Synthetic Human Trafficking Task Force are to identify victims.": "2004-11",
        "In 2021, the office launched a community-based educational outreach initiative for parents.": "2021",
    }.items():
        got = [r for r in roles(HEAD + sentence) if r[0] == value]
        assert got and got[0][1] == "program_boilerplate", (sentence, got)
