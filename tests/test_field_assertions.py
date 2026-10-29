"""
Field assertions: known extraction failures as end-to-end regressions.

Every test runs real case text (verbatim excerpts from the public releases, cited by
case_id) through extraction → resolution → the legacy fields. None builds assertions
by hand. The hard-10 full-text test reads caselinker.db when present.
"""

from __future__ import annotations

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

A = processing.assertions_module
LLM = processing.llm_module

# --- verbatim excerpts ------------------------------------------------------

# doj_safe_childhood_2025_325
C325 = (
    "LEXINGTON, Ky. – A Lexington man, Casey Kendall Blackwillow, 30, was sentenced on Friday, by U.S. District\n"
    "Judge Karen Caldwell, to 50 years in prison, for production of child pornography.\n"
    "According to his plea agreement, in January 2022, law enforcement was contacted about a 12-year-old victim\n"
    "who was sexually exploited by an adult male. Further investigation revealed that Blackwillow, then 27 years-old,\n"
    "met the victim on Snapchat, where he initially claimed he was 17 years-old."
)
# doj_safe_childhood_2025_131
C131 = (
    "A man who sexually exploited children and distributed child pornography was sentenced September 3, 2025, to\n"
    "20 years in federal prison.\n"
    "Sawyer Kestrelson, 32, from Sioux City, Iowa, received the prison term after an April 7, 2025, guilty plea to sexual\n"
    "exploitation of a minor and distribution of child pornography.\n"
    "Evidence at the plea and sentencing hearings showed that from July 1, 2022, through July 2, 2024, Kestrelson used\n"
    "and coerced a minor under the age of 18 to engage in sexually explicit conduct for the purpose of producing\n"
    "visual depictions of such conduct. Kestrelson admitted to utilizing an app called Anonymous Chat to receive and\n"
    "send images of child pornography some included toddlers and sadistic and masochistic conduct. A forensic\n"
    "review of Kestrelson’s phone found he possessed 24 images of child sexual abuse material, including images of a\n"
    "known minor victim.\n"
    "Kestrelson was sentenced in Sioux City by United States District Court Judge Leonard T. Strand. Kestrelson was\n"
    "sentenced to 240 months’ imprisonment and was ordered to pay $1,200 in fines and assessments. He must also\n"
    "serve a 5-year term of supervised release after the prison term. There is no parole in the federal system.\n"
    "Kestrelson is being held in the United States Marshal’s custody until he can be transported to a federal prison."
)
# doj_safe_childhood_2025_327
C327 = (
    "ALBUQUERQUE – An Albuquerque man was sentenced to 25 years in prison for sexually exploiting a\n"
    "13-year-old girl and producing child pornography.\n"
    "There is no parole in the federal system.\n"
    "According to court records, Logan Foxglove , 41, was on supervised released after serving a sentence for first\n"
    "degree murder when he used the social media app, Telegram, to communicate with Jane Doe, a 13-year-old girl,\n"
    "while falsely claiming to be 16 years old.\n"
    "Foxglove was sentenced to an additional 30 months in prison for violating his supervision terms related to the\n"
    "murder charge, for a total of 27 and a half years."
)
# ncmec_2022_512
C512 = (
    "Skyler Riley Elderkin Jr., 56, of 871 Miller St., Luzerne, became the target of an\n"
    "investigation last month after Google reported he uploaded two videos depicting child\n"
    "sexual abuse.\n\n"
    "Police searched his computer and found photographs of naked, underage boys —\n"
    "many around 11 years old, authorities said — and evidence that he tried to delete\n"
    "them. Elderkin, who at the time was serving as an assistant pastor for the Diocese of\n"
    "Scranton in Pike County, pleaded guilty to 19 child porn charges and was sentenced to\n"
    "serve six to 72 months in state prison."
)
# ncmec_2024_1175
C1175 = (
    "SPOKANE, Wash. – A man was arrested for the second time after police caught him in a child sex sting operation\n"
    "posing as a 13-year-old girl.\n"
    "A Kittitas County Sheriff’s Deputy posed as 13-year-old ‘Avery’ who met Jamie Orrindale, 55, on the ‘MeetMe’ app.\n"
    "Orrindale was previously arrested in 2018, after a successful sting operation where he was sentenced to three\n"
    "months in prison.\n"
    "Orrindale was also found again on ‘Meet Me’ and was communicating with another agent from the Montana\n"
    "Bureau of Investigations who was posing as a 14-year-old girl.\n"
    "A cybertip from Facebook also aided police in their arrest after a user under the name of ‘Finley Dunmarrow’ uploaded\n"
    "child pornography material and sent it to another user.\n"
    "Police estimate that material to be of a child between the ages of 6 and 11."
)
# ncmec_2023_105
C105 = (
    "Law enforcement executed a search warrant at Rash’s residence on Friday,\n"
    "September 8th, after receiving a Cyber Tipline Report of suspected child porn.\n"
    "During the search, authorities looked through Rash’s phone and reportedly\n"
    "found evidence that he had sexually assaulted a child.\n"
    "According to the complaint, there were videos of Rash performing sex acts with\n"
    "the victim who was born in 2019. Police allegedly found that Rash would send\n"
    "the videos to other users on the social media platform KIK.\n"
    "When questioned about the content officers located, Rash reportedly said\n"
    "(quote) “it was one time” and “it was an accident.” The 23-year-old also\n"
    "allegedly said he was hoping that the victim was young enough not to\n"
    "remember.\n"
    "If convicted, Rash faces up to 125 years in prison. A preliminary hearing is\n"
    "scheduled for September 21st."
)
# illinois_ag_2023_015
C015 = (
    "Joshua G. Eastham, 38, of Jerseyville, was found guilty on Monday in Jersey County Circuit Court of four\n"
    "counts of disseminating child pornography involving victims under the age of 13, Class X felonies each\n"
    "punishable by six to 30 years in prison. Eastham is scheduled to be sentenced on Nov. 1.\n"
    "Raoul’s office charged Eastham after receiving a CyberTip from the mobile messaging application Kik and\n"
    "discovering evidence of child sexual abuse material during a search of Eastham’s home on Jan. 27, 2022."
)
C015_BOILERPLATE = (
    "The task force receives CyberTips, or online reports of child pornography, from the National Center for Missing\n"
    "and Exploited Children. Over the last several years, CyberTipline reports have steadily increased."
)
# doj_archives_2007_003
C2007 = (
    "Gary E. Jorandby, 57, of Upper Marlboro, Md., was arrested today on a federal indictment charging him with\n"
    "sexually exploiting a minor to produce child pornography and receipt of child pornography. According to the\n"
    "indictment, between approximately January 1990 and December 1999, Jorandby knowingly enticed and coerced a female\n"
    "child, who was approximately five years old at the time the crimes began, to engage in sexually explicit conduct."
)
# doj_safe_childhood_2026_001
C2026 = (
    "Hardy, Iowa, Man Sentenced to Over 7 Years in Federal Prison for\n"
    "Possession of Child Pornography\n"
    "September 11, 2026\n"
    "Publication date: 2026-09-11\n"
    "Source:\n"
    "Tatum Fenwright, 57, from Hardy, Iowa, was sentenced in federal court in Sioux City on September 11, 2026, to 90\n"
    "months’ imprisonment. Fenwright pled guilty April 20, 2026, to one count of possession of child pornography.\n"
    "States District Court Judge Leonard T. Strand sentenced Fenwright to 90 months’ imprisonment and 5\n"
    "years’ of supervised release following his imprisonment. There is no parole in the federal system. Fenwright must\n"
    "also pay restitution in the amount of $39,500 to the victims in the case. Fenwright remains in custody of the\n"
    "United States Marshal until he can be transported to a federal prison."
)
# azicac_2011_001 (full case text)
CAZ = (
    "In January 2011, a teen female high school\nstudent in Scottsdale, AZ contacted school\n"
    "officials and police when a 25 year old Scottsdale\nman stalked and followed the girl to her school\n"
    "and onto the school campus. She became\nfrightened not thinking this would happen or he\n"
    "would go to this extent, and made the contacts.\nAZICAC and Scottsdale Police arrested the man\n"
    "at the school which is when he said he had met\nthe girl online which led to him and the victim\n"
    "having an online and phone relationship. He said\nhe wanted to meet her in person. Apparently, the\n"
    "suspect and victim had exchanged pornographic\nimages because she had them on her person and\n"
    "provided the evidence to police. The unemployed\nScottsdale man was booked into Madison Street\n"
    "Jail and charged with luring a minor for sexual\nexploitation and furnishing harmful items to a\n"
    "minor via the Internet. This matter is being\nhandled by the Maricopa County Attorney’s\nOffice."
)
# ncis_2023_002 (sting: the "child" is an agent's persona)
CNCIS = (
    "Navy Sailor Sentenced To 10 Years In Federal Prison For Attempting To Entice And Meet A 13-Year-Old Child "
    "To Engage In Sexual Activity\n"
    "Jacksonville, Florida – United States District Judge Marcia Morales Howard has sentenced Riley Buck "
    "Brockway (40, Jacksonville) to 10 years in federal prison for using the internet and his cellphone to "
    "attempt to entice a 13-year-old child to engage in sexual activity. On July 17, 2023, an agent with the "
    "Naval Criminal Investigative Service (NCIS), posing as a 13-year-old child, began an undercover "
    "investigation designed to identify individuals who were seeking to sexually exploit children."
)
# azicac_2013_006 (full case text minus the PDF print header)
C2013 = (
    "In May 2013, during a proactive investigation by\nthe Arizona Crimes Against Children Task Force,\n"
    "identified the suspect’s residence as trafficking in\nvideos and images of young children (under 5)\n"
    "being sexually abused. During the forensic exam\nof the computers, numerous pictures and videos\n"
    "of an adult male and female were located\nmolesting a 3 year old boy and also using a dog\n"
    "to offend on the child. Detectives worked the\ncase and located the female and arrested her. In\n"
    "addition, the adult male was located three days\nlater and arrested. Detectives worked 25 hours\n"
    "straight trying to locate the victim. After 74\nhours of investigation, that covered three days,\n"
    "the victim was located and saved from the\noffender."
)
# ncmec_2023_279
C279 = (
    "Elliot Drew Rookhaven, 60, was sentenced to five years and three months in federal prison on charges of "
    "possession of child pornography during a hearing U.S. District Court in Cedar Rapids on Wednesday. "
    "Following prison, he will be on supervised release for five years."
)
# doj_safe_childhood_2023_453
C453 = (
    "Candeloro was previously convicted in two cases for a second-degree sex offense involving a 13-year-old "
    "victim in Howard County and Baltimore County Circuit Courts."
)
# ncmec_2025_821 ("believed to be" persona)
C821 = (
    "After communicating with the undercover officers online and arranging to purchase who he believed to be a "
    "14-year-old girl, Armstrong solicited and attempted to patronize the minor for sex."
)


def run(text: str, case_id: str = "test_case", year: str = "2025"):
    """Real pipeline path: pattern extraction → merge (3.0 collect + resolve) → comparison values."""
    raw = {"case_text": text, "case_id": case_id, "source": "TEST", "source_file": "test.pdf", "year": year}
    features = processing.extract_features(raw)
    case = processing.assign_comparison_values(processing.MergeProcessing().merge_features(features, None))
    return case, case["resolutions"]


def age_final(res):
    return res["age"]["final_value"] or {}


def sentence_final(res):
    return res["sentence"]["final_value"] or {}


def name_key_at_age(case, age):
    """The per-case name tokens a reader tied to this age (names are never stored)."""
    keys = [(a.get("extras") or {}).get("name_key") for a in case["assertions"] if a["field"] == "age" and a["value"] == age]
    return next((k for k in keys if k), "")


def excluded(res):
    return {(x["age"], x["role"]) for x in age_final(res).get("excluded") or []}


# --- ages ---------------------------------------------------------------------

def test_2019_birth_year_is_not_an_age():
    case, res = run(C105, "ncmec_2023_105")
    assert not any(a["field"] == "age" and a["value"] == 2019 for a in case["assertions"])
    assert age_final(res)["perpetrators"] == [23]
    assert age_final(res)["victims"] == []


def test_325_defendant_age_27_is_not_a_victim():
    case, res = run(C325, "doj_safe_childhood_2025_325")
    final = age_final(res)
    assert final["victims"] == [12]
    assert 27 not in final["victims"]
    assert final["perpetrators"] == [30]
    shepherd = final["perpetrator_entities"][0]
    assert shepherd["age"] == 30 and shepherd["other_ages"] == [27]
    assert (17, "claimed") in excluded(res)
    assert case["perpetrator_age"] == [30]
    assert case["case_demographics"]["ages"] == [12]


# A father "Porter Sr." and his son "Porter" are two defendants. The suffix is
# part of who they are. Stripping it and matching the surname collapses the son
# into the father and drops 24 from the perpetrator ages.
SR_AND_SON = (
    "PHOENIX – Samuel Porter Sr., 52, of Phoenix, was sentenced to 10 years in prison. "
    "His son, Samuel Porter, 24, of Phoenix, was sentenced to 5 years in prison."
)
# Two different people, neither named, same age. Value equality is not identity.
TWO_UNNAMED = (
    "Police arrested a 40-year-old man in Tulsa and a 40-year-old man in Omaha. "
    "Both men were charged with sexual exploitation of a minor."
)


def test_a_judges_suffix_does_not_become_the_defendants_name():
    text = (
        "Judge D.P. Marshall, Jr. Harper Riley Greywater, 34, of Little Rock, "
        "was sentenced to 10 years in prison."
    )
    case, res = run(text, "judge_suffix_leak")
    assert age_final(res)["perpetrator_entities"][0]["named"]
    # What the resolver reads from the stored tokens: three name tokens, no judge's suffix.
    key = A.resolution._entity_key({"extras": {"name_key": name_key_at_age(case, 34)}}) or ""
    assert len(key.split()) == 3
    assert "Jr" not in key.split()


def test_suffix_keeps_father_and_son_as_two_defendants():
    case, res = run(SR_AND_SON, "suffix_father_son")
    final = age_final(res)
    assert final["perpetrators"] == [24, 52]
    entities = final["perpetrator_entities"]
    assert len(entities) == 2
    assert all(e["named"] for e in entities)
    assert name_key_at_age(case, 52).split()[-1] == "Sr"
    assert "Sr" not in name_key_at_age(case, 24).split()


def test_unnamed_defendants_of_the_same_age_stay_separate():
    _, res = run(TWO_UNNAMED, "two_unnamed_40")
    entities = age_final(res)["perpetrator_entities"]
    assert len(entities) == 2
    assert [e["age"] for e in entities] == [40, 40]


def test_resolve_without_case_text_does_not_collapse_same_age_defendants():
    """Forgetting text= must not invent that two mentions are one person."""
    assertions = A.collect_assertions(TWO_UNNAMED, case_id="two_unnamed_no_text")
    without = age_final(A.resolve(assertions))
    with_text = age_final(A.resolve(assertions, text=TWO_UNNAMED))
    assert len(without["perpetrator_entities"]) == 2
    assert len(with_text["perpetrator_entities"]) == 2
    assert without["perpetrators"] == with_text["perpetrators"] == [40]


def test_a_repeated_nameless_age_is_one_defendant_unless_the_text_says_two():
    text = (
        "A 24-year-old Waterford man appeared in court charged with online child sexual exploitation. "
        "The 24-year-old was arrested and charged with one count of producing child pornography."
    )
    _, res = run(text, "repeated_nameless_24")
    entities = [e for e in age_final(res)["perpetrator_entities"] if e["age"] == 24]
    assert len(entities) == 1


def test_nameless_age_joins_the_only_named_defendant_of_that_age():
    text = (
        "A Celina man has been sentenced to four years. "
        "The 35-year-old man was indicted on 88 charges. "
        "Emerson Halloway, 35, of Celina, was sentenced to four years in prison."
    )
    _, res = run(text, "headline_and_name")
    entities = age_final(res)["perpetrator_entities"]
    named = [e for e in entities if e["named"] and e["age"] == 35]
    assert len(named) == 1
    assert not any(not e["named"] and e["age"] == 35 for e in entities)


def test_nameless_age_stays_apart_when_the_wording_is_plural():
    text = (
        "Investigators arrested two 40-year-old men in Tulsa. "
        "Jamie Dunmarrow, 40, of Tulsa, was charged with sexual exploitation of a minor."
    )
    _, res = run(text, "two_men_40")
    entities = age_final(res)["perpetrator_entities"]
    assert any(e["named"] and e["age"] == 40 for e in entities)
    assert any(not e["named"] and e["age"] == 40 for e in entities)


def test_nameless_age_stays_apart_when_the_place_is_different():
    text = (
        "Police arrested a 40-year-old man in Tulsa. "
        "Jamie Dunmarrow, 40, of Omaha, was arrested and charged with sexual exploitation of a minor."
    )
    _, res = run(text, "two_places_40")
    entities = age_final(res)["perpetrator_entities"]
    assert any(e["named"] and e["age"] == 40 for e in entities)
    assert any(not e["named"] and e["age"] == 40 for e in entities)


# Surface family asserts both a victim noun and a defendant cue on one mention.
# That family abstains and the age stays in review. The hold is a self-contradiction,
# not an unknown role.
SELF_CONTRADICTION = "The jailing of a 22-year-old student followed his arrest on the charge."


def test_self_contradiction_hold_is_not_labeled_unknown():
    _, res = run(SELF_CONTRADICTION, "self_contradiction_student")
    final = age_final(res)
    assert 22 not in (final.get("victims") or [])
    assert 22 not in (final.get("perpetrators") or [])
    reasons = [item["reason"] for item in res["age"]["review"]]
    assert reasons == ["self_contradiction"]


def test_imposed_sentence_attaches_to_the_person_sentenced_not_the_judge():
    text = (
        "U.S. District Judge Drew K. Bredar sentenced Parker Jordan Underhay, 38, of Parkville, "
        "to 15 years in prison. Jamie Quinn Quillfeather was sentenced to 27 years in prison."
    )
    case, _ = run(text, "judge_sentenced_defendant")
    imposed = [a for a in case["assertions"] if a["field"] == "sentence" and a.get("role") == "imposed"]
    by_value = {a["value"]: (a.get("extras") or {}).get("defendant_key") or "" for a in imposed}
    defendant = name_key_at_age(case, 38).split()  # the person sentenced, tokenized
    assert by_value.get("15 years", "").split()[-1:] == defendant[-1:]
    assert by_value.get("27 years") and by_value["27 years"].split()[-1] != defendant[-1]


def test_imposed_sentences_attach_to_the_subject_defendant():
    """Each imposed term keeps a defendant on the assertion. The legacy list stays strings."""
    case, res = run(SR_AND_SON, "suffix_father_son")
    assert sentence_final(res)["imposed"] == ["10 years", "5 years"]
    assert case["prosecution_outcome"]["sentences"] == ["10 years", "5 years"]
    imposed = [a for a in case["assertions"] if a["field"] == "sentence" and a.get("role") == "imposed"]
    by_value = {a["value"]: (a.get("extras") or {}).get("defendant_key") for a in imposed}
    father = (by_value.get("10 years") or "").split()
    son = (by_value.get("5 years") or "").split()
    assert father[-1:] == ["Sr"]
    assert son and son[-1] == father[-2] and "Sr" not in son  # same surname token, no suffix


def test_131_twenty_years_is_a_duration_not_an_age():
    case, res = run(C131, "doj_safe_childhood_2025_131")
    assert not any(a["field"] == "age" and a["value"] == 20 for a in case["assertions"])
    assert age_final(res)["perpetrators"] == [32]
    assert (18, "statutory_threshold") in excluded(res)
    assert case["perpetrator_age"] == [32]


def test_327_falsely_claimed_16_is_excluded():
    _, res = run(C327, "doj_safe_childhood_2025_327")
    assert age_final(res)["victims"] == [13]
    assert age_final(res)["perpetrators"] == [41]
    assert (16, "claimed") in excluded(res)
    # "a total of 27 and a half years" restates 25 years + 30 months; it is not a third term.
    assert sentence_final(res)["imposed"] == ["25 years", "30 months"]


def test_512_material_age_11_is_depicted_not_victim():
    case, res = run(C512, "ncmec_2022_512")
    assert age_final(res)["victims"] == []
    assert (11, "depicted_in_material") in excluded(res)
    assert age_final(res)["perpetrators"] == [56]
    # The 2009 term ("at the time …") never becomes this case's sentence.
    assert sentence_final(res)["imposed"] == []
    assert not any("72" in s for s in case["prosecution_outcome"]["sentences"])


def test_1175_decoys_need_the_persona_phrase():
    _, res = run(C1175, "ncmec_2024_1175")
    final = age_final(res)
    assert final["victims"] == []
    assert final["perpetrators"] == [55]  # 55 sits near "posed as" but is Orrindale's age
    assert {(13, "decoy"), (14, "decoy")} <= excluded(res)
    assert {(6, "depicted_in_material"), (11, "depicted_in_material")} <= excluded(res)
    assert sentence_final(res)["imposed"] == []  # the 2018 term is a prior case


def test_azicac_2011_001_perpetrator_25():
    case, res = run(CAZ, "azicac_2011_001", year="2011")
    assert age_final(res)["perpetrators"] == [25]
    assert case["perpetrator_age"] == [25]


def test_word_age_five():
    _, res = run(C2007, "doj_archives_2007_003", year="2007")
    assert age_final(res)["victims"] == [5]
    assert age_final(res)["perpetrators"] == [57]


def test_believed_persona_is_a_decoy():
    _, res = run(C821, "ncmec_2025_821")
    assert age_final(res)["victims"] == []
    assert (14, "decoy") in excluded(res)


def test_believed_father_of_undercover_child_is_not_a_victim():
    # doj_safe_childhood_2023_259: the nine-year-old is the child the undercover was posing as the father of.
    text = (
        "In August of 2021, Camero met an individual online whom he believed was the father of a "
        "nine-year-old boy. In reality, this individual was a law enforcement officer, acting in an "
        "undercover capacity."
    )
    _, res = run(text, "doj_safe_childhood_2023_259", year="2023")
    assert 9 not in (age_final(res).get("victims") or [])


def test_persona_echo_contests_victim_value():
    # The headline/body "13-year-old child" is the agent's persona.
    _, res = run(CNCIS, "ncis_2023_002", year="2023")
    assert 13 not in age_final(res)["victims"]
    assert (13, "decoy") in excluded(res)


def test_veto_needs_a_different_family():
    # regex: victim; temporal: prior-case victim → two families disagree → contested, not final.
    case, res = run(C453, "doj_safe_childhood_2023_453", year="2023")
    assert age_final(res)["victims"] == []
    contested = age_final(res)["contested"]
    assert any(c["value"] == 13 and set(c["roles"]) == {"victim", "prior_case"} for c in contested.values())


def test_pictured_child_who_was_later_found_stays_depicted():
    # azicac_2013_006. The boy is in the videos and was later found. The age on the
    # pictures stays depicted; finding him does not turn that mention into a victim age.
    _, res = run(C2013, "azicac_2013_006", year="2013")
    assert age_final(res)["victims"] == []
    assert (3, "depicted_in_material") in excluded(res)


def test_adult_crime_victim_is_not_a_csea_victim():
    # us_marshals_2025_016 class: "sexual assault of a 76-year-old woman"
    text = (
        "Jamie Wickersham, 32, wanted for the kidnapping and sexual assault of a 76-year-old woman in Camden County, "
        "was also charged with the attempted sexual assault of a 12-year-old female."
    )
    case, res = run(text, "us_marshals_adult_victim", year="2025")
    assert age_final(res)["victims"] == [12]
    assert 76 not in age_final(res)["victims"]
    assert (76, "adult_crime_victim") in excluded(res)
    assert case["case_demographics"]["ages"] == [12]


def test_victim_and_depicted_value_contests():
    # nca_2026_007 class: same age is a material depiction in one mention and a victim cue in another.
    text = (
        "Alexander, 42, asked for images of the girls aged nine and six posing in a certain way. "
        "He also messaged a facilitator about a nine-year-old girl he wanted to meet."
    )
    _, res = run(text, "nca_depicted_vs_victim", year="2026")
    assert 9 not in age_final(res)["victims"]
    contested = age_final(res)["contested"]
    assert any(c["value"] == 9 and "depicted_in_material" in c["roles"] for c in contested.values())
    assert (6, "depicted_in_material") in excluded(res)


# --- sentences -------------------------------------------------------------------

def test_up_to_125_years_is_exposure_never_imposed():
    case, res = run(C105, "ncmec_2023_105")
    assert "125 years" in sentence_final(res)["exposure"]
    assert sentence_final(res)["imposed"] == []
    assert not any("125" in s for s in (case.get("prosecution_outcome") or {}).get("sentences", []))


def test_exposure_is_killed_at_the_gate():
    case, res = run(C015, "illinois_ag_2023_015", year="2023")
    assert sentence_final(res)["exposure"] == ["six to 30 years"]
    assert sentence_final(res)["imposed"] == []
    assert (case.get("prosecution_outcome") or {}).get("sentences", []) == []


def test_curly_apostrophes_and_sub_kinds_populate():
    case, res = run(C131, "doj_safe_childhood_2025_131")
    final = sentence_final(res)
    assert final["imposed"] == ["240 months"]  # "20 years" in the lede is the same term
    assert final["supervised_release"] == ["5-year"]
    assert final["fine"] == ["$1,200"]
    assert final["custody"] and "custody" in final["custody"][0]
    assert case["prosecution_outcome"]["sentences"] == ["240 months", "5-year supervised release", "$1,200"]


def test_headline_approximation_and_curly_years_dedupe():
    _, res = run(C2026, "doj_safe_childhood_2026_001", year="2026")
    final = sentence_final(res)
    assert final["imposed"] == ["90 months"]  # "Over 7 Years" in the headline is the same term
    assert final["supervised_release"] == ["5 years"]
    assert final["fine"] == ["$39,500"]
    assert final["custody"] == ["remains in custody"]
    assert age_final(res)["perpetrators"] == [57]


def test_compound_term_is_one_sentence():
    _, res = run(C279, "ncmec_2023_279", year="2023")
    final = sentence_final(res)
    assert final["imposed"] == ["five years and three months"]
    assert final["supervised_release"] == ["five years"]


def test_life_without_parole_is_imposed_and_conduct_spans_are_not_terms():
    # ncmec_2022_067
    text = (
        "A South Bay man was sentenced Oct. 25, to life without parole in\n"
        "federal prison after admitting to producing thousands of sexually explicit images and\n"
        "videos of nearly three-dozen children – one of whom was exploited over the course of\n"
        "at least two years."
    )
    _, res = run(text, "ncmec_2022_067", year="2022")
    assert sentence_final(res)["imposed"] == ["to life without parole"]


def test_nz_starting_point_is_not_the_imposed_sentence():
    text = (
        "He was sentenced to 12 months home detention for distributing objectionable material. "
        "The sentencing Judge adopted a starting point of 4 years and 6 months imprisonment "
        "before applying discounts totalling 55%."
    )
    _, res = run(text, "nz_dia_2025_007", year="2025")
    assert sentence_final(res)["imposed"] == ["12 months"]


def test_nz_starting_point_for_sentencing_is_not_imposed():
    text = (
        "The court sentenced him to 12 months' imprisonment. "
        "The judge took as a starting point for sentencing, 18 months' imprisonment, "
        "reducing it to 12 after discounts."
    )
    _, res = run(text, "nz_dia_2006_001", year="2006")
    assert sentence_final(res)["imposed"] == ["12 months"]


def test_nz_recommended_starting_point_is_not_the_home_detention_term():
    text = (
        "He was sentenced to 8 months home detention and 300 hours of community work. "
        "The prosecutor recommended as a starting point\n"
        "that he be sentenced to four years' imprisonment with a discount for his guilty plea."
    )
    _, res = run(text, "nz_dia_2015_004", year="2015")
    assert sentence_final(res)["imposed"] == ["8 months"]


def test_nz_suggested_starting_point_does_not_replace_the_term():
    text = (
        "A former teacher was sentenced to two-and-a-half years prison after a jury found him guilty. "
        "The prosecutor suggested six years imprisonment as an appropriate sentencing starting point."
    )
    _, res = run(text, "nz_dia_2009_005", year="2009")
    assert "two-and-a-half years" in sentence_final(res)["imposed"]
    assert "six years" not in sentence_final(res)["imposed"]


def test_nz_minimum_period_of_imprisonment_is_not_imposed():
    text = (
        "He was sentenced to 8 years 7 months imprisonment with a minimum period of imprisonment "
        "of 5 years 8 months in the High Court today."
    )
    _, res = run(text, "nz_dia_2019_001", year="2019")
    assert sentence_final(res)["imposed"] == ["8 years 7 months"]


def test_aged_years_is_not_a_prison_term():
    text = (
        "A man has been jailed for 20 months after trading child sexual abuse images. "
        "They included the sexual abuse of girls aged six years or under."
    )
    _, res = run(text, "nz_dia_2009_011", year="2009")
    assert sentence_final(res)["imposed"] == ["20 months"]


def test_year_old_student_who_was_jailed_is_not_a_victim():
    text = (
        "The jailing of a 22-year-old student for possessing and distributing "
        "pictures of children being sexually abused sends a strong warning."
    )
    _, res = run(text, "nz_dia_2006_001", year="2006")
    # Defendant and victim cues both fire, so 22 is not stored as a victim final.
    assert age_final(res).get("victims") == []
    assert res["age"]["status"] == "needs_review"


def test_depicted_girls_aged_eight_and_12_are_not_perpetrators():
    text = (
        "A 42-year-old manager has been fined $2500 after pleading guilty to possessing "
        "objectionable movies involving girls, aged eight and 12."
    )
    _, res = run(text, "nz_dia_2007_001", year="2007")
    assert 8 not in age_final(res)["perpetrators"]
    assert 12 not in age_final(res)["perpetrators"]
    assert 8 not in age_final(res)["victims"]
    assert 12 not in age_final(res)["victims"]
    assert {(8, "depicted_in_material"), (12, "depicted_in_material")} <= excluded(res)


def test_not_less_than_is_statutory_exposure():
    # doj_safe_childhood_2026_074
    text = (
        "Gibbs’ conviction is punishable by a term of imprisonment of not less than five years and not more than twenty\n"
        "years, a fine of $250,000, or both."
    )
    _, res = run(text, "doj_safe_childhood_2026_074", year="2026")
    assert {"five years", "$250,000"} <= set(sentence_final(res)["exposure"])
    assert sentence_final(res)["imposed"] == []


def test_ordered_the_maximum_is_imposed_not_exposure():
    # doj_ceos_2013_092
    text = (
        "Tyler faced a maximum of 30 years for each count of production of child\n"
        "pornography and a maximum of 20 years for each count of distribution or receipt of child pornography. Judge\n"
        "Collier ordered the maximum sentence for each offense and then ordered the sentences to run partially\n"
        "consecutive to each other to reach the total sentence of 400 months."
    )
    _, res = run(text, "doj_ceos_2013_092", year="2013")
    assert sentence_final(res)["imposed"] == ["400 months"]
    assert "400 months" not in sentence_final(res)["exposure"]
    assert {"30 years", "20 years"} <= set(sentence_final(res)["exposure"])


# --- investigation type ------------------------------------------------------------

def test_cybertips_survive_casefolding_and_boilerplate_does_not_count():
    case, res = run(C105, "ncmec_2023_105")
    assert res["investigation_type"]["final_value"] == ["cybertip"]
    assert "cybertip" in case["investigation_types"]
    _, res = run(C015, "illinois_ag_2023_015", year="2023")
    assert res["investigation_type"]["final_value"] == ["cybertip"]
    case, res = run(C015_BOILERPLATE, "illinois_ag_boilerplate", year="2023")
    assert res["investigation_type"]["final_value"] == []
    assert "cybertip" not in case["investigation_types"]


# --- deterministic-only mode ---------------------------------------------------------

def test_runs_without_spacy_or_llm(monkeypatch):
    monkeypatch.setattr(A.spacy_patterns, "load_spacy", lambda: None)
    monkeypatch.delenv("CASELINKER_LLM", raising=False)
    case, res = run(C325, "doj_safe_childhood_2025_325")
    assert age_final(res)["victims"] == [12]
    assert age_final(res)["perpetrators"] == [30]
    assert not any(a["family"] in ("dependency", "llm") for a in case["assertions"])


# --- LLM layer (canned model output; the case text and gate are real) --------------------

def _llm_case():
    text = C1175 + "\nKCSO posed as ‘Avery’ for nearly three months while messaging Orrindale."
    assertions = A.collect_assertions(text, case_id="ncmec_2024_1175", use_spacy=False, overrides={})
    return text, assertions, A.resolve(assertions)


def test_llm_alone_never_finalizes_and_quotes_are_gated(monkeypatch, tmp_path):
    text, assertions, res = _llm_case()
    targets = LLM.targets_from(res, assertions)
    _prompt, _windows, cands = LLM.build_prompt(text, targets)
    messaging = next(c for c in cands if "nearly three months" in text[c["span"][0]:c["span"][1]])
    others = [c for c in cands if c is not messaging]
    reply = {"items": [{"id": messaging["id"], "role": "imposed", "quote": "posed as ‘Avery’ for nearly three months"}]}
    reply["items"] += [{"id": c["id"], "role": "imposed", "quote": "a quote that is not in the window"} for c in others]
    monkeypatch.setattr(LLM, "_generate", lambda cfg, prompt: (json.dumps(reply), 5, "ok"))
    cfg = {**LLM.llm_config(), "provider": "ollama", "model": "test-model"}
    cache = LLM.LLMCache(str(tmp_path / "cache.db"))
    out, meta = LLM.run_llm(text, res, assertions, A.gate_assertion, cfg=cfg, cache=cache, digest="sha256:test")
    assert meta["status"] == "ok"
    grounded = [a for a in out if a["span_ok"]]
    assert [(a["span_start"], a["family"]) for a in grounded] == [(messaging["span"][0], "llm")]
    assert all(a["extras"]["gate_reason"] == "missing" for a in out if not a["span_ok"])
    assert cache.conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 1
    final = A.resolve(assertions + out)
    assert "nearly three months" not in sentence_final(final)["imposed"]  # the LLM alone cannot finalize


def test_llm_cache_key_pins_digest_and_skips_truncated(monkeypatch, tmp_path):
    cfg = {**LLM.llm_config(), "provider": "ollama", "model": "m"}
    k1, _ = LLM.cache_key(cfg, "sha256:a", "prompt")
    k2, _ = LLM.cache_key(cfg, "sha256:b", "prompt")
    k3, _ = LLM.cache_key({**cfg, "model": "m2"}, "sha256:a", "prompt")
    assert len({k1, k2, k3}) == 3
    text, assertions, res = _llm_case()
    monkeypatch.setattr(LLM, "_generate", lambda cfg, prompt: (None, 9, "truncated"))
    cache = LLM.LLMCache(str(tmp_path / "cache.db"))
    out, meta = LLM.run_llm(text, res, assertions, A.gate_assertion, cfg=cfg, cache=cache, digest="sha256:a")
    assert out == [] and meta["status"] == "truncated"
    assert cache.conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 0


# --- storage: append-only assertions, resolutions, run pins, re-resolution -----------------

def test_resolution_only_run_is_still_the_current_run():
    """Empty extractions store resolutions and no assertion rows. That run is current."""
    import sqlite3

    from assertion_store import apply_assertion_schema, latest_run_id, read_case_assertions

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_assertion_schema(conn, "sqlite")
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO field_resolutions
           (run_id, case_id, field, rule_set_version, status, rule_id, final_json,
            winning_assertion_ids, disagreement_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("run_empty", "brazil_pf_2026_001", "age", "resolve_v3.0", "empty", "no_assertions", "null", "[]", "{}"),
    )
    conn.commit()
    assert latest_run_id(cur, "brazil_pf_2026_001", "sqlite") == "run_empty"
    payload = read_case_assertions(cur, "brazil_pf_2026_001", dialect="sqlite")
    assert payload["assertions"] == []
    assert payload["run_id"] == "run_empty"
    assert payload["resolutions"]["age"]["status"] == "empty"
    assert payload["resolutions"]["age"]["rule_id"] == "no_assertions"


def test_postgres_assertion_ddl_casts_the_timestamp_default():
    """Postgres rejects DEFAULT CURRENT_TIMESTAMP on a TEXT column. SQLite accepts it."""
    from assertion_store import apply_assertion_schema

    class _Cursor:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append(sql)

    sqlite, postgres = _Cursor(), _Cursor()
    apply_assertion_schema(sqlite, "sqlite")
    apply_assertion_schema(postgres, "postgres")
    sqlite_ddl = "\n".join(sqlite.sql)
    postgres_ddl = "\n".join(postgres.sql)
    assert "DEFAULT CURRENT_TIMESTAMP" in sqlite_ddl
    assert "::text" not in sqlite_ddl
    assert "DEFAULT (CURRENT_TIMESTAMP::text)" in postgres_ddl
    assert "field_assertions_append_only_update" in postgres_ddl
    assert "BIGSERIAL PRIMARY KEY" in postgres_ddl
    assert "AUTOINCREMENT" not in postgres_ddl




def test_storage_round_trip_append_only_and_reresolve(tmp_path):
    from storage import CaseStorage
    from provenance import attach_ingest_provenance

    case, _ = run(C325, "doj_safe_childhood_2025_325")
    storage = CaseStorage(str(tmp_path / "t.db"))
    attach_ingest_provenance(storage, [case], source_files=["test.pdf"], extractor_versions={
        "rule_set_version": "resolve_v3", "spacy_model": "en_core_web_sm:test", "extraction_mode": "deterministic",
    })
    assert storage.store_cases([case]) == 1

    out = storage.get_case_assertions("doj_safe_childhood_2025_325")
    assert out["resolutions"]["age"]["final_value"]["victims"] == [12]
    ids = {a["id"] for a in out["assertions"]}
    assert set(out["resolutions"]["age"]["winning_assertion_ids"]) <= ids

    conn = sqlite3.connect(tmp_path / "t.db")
    row = conn.execute("SELECT rule_set_version, spacy_model, extraction_mode FROM extraction_runs").fetchone()
    assert row == ("resolve_v3", "en_core_web_sm:test", "deterministic")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE field_assertions SET role = 'victim'")
    conn.rollback()
    blob = json.loads(conn.execute("SELECT extracted_features FROM cases").fetchone()[0])
    assert "assertions" not in blob and "resolutions" not in blob

    # Re-resolution reads stored rows (no re-extraction) and appends, never edits.
    run_id, stored = storage.load_case_assertions("doj_safe_childhood_2025_325")
    storage.append_resolutions("doj_safe_childhood_2025_325", run_id, A.resolve(stored))
    n = conn.execute("SELECT COUNT(*) FROM field_resolutions WHERE field = 'age'").fetchone()[0]
    assert n == 2
    assert storage.get_field_disagreements()["status_counts"]["age"]


# --- hard 10, full text from the local corpus -------------------------------------------------

# Phase 3 ids. Three rows moved when the corpus was re-split:
# ncmec_2024_1175 → ncmec_2024_1136, ncmec_2023_105 → ncmec_2023_104,
# ncmec_2022_512 → ncmec_2022_506. The 2007 DOJ release is still
# doj_archives_2007_003. The old doj_safe_childhood_2026_001 sentencing
# release is not in this corpus; south_florida_icac_2025_023 is the tenth real row.
HARD_EXPECTED = {
    "doj_safe_childhood_2025_131": {"victims": [], "perps": [32], "imposed": ["240 months"]},
    "doj_safe_childhood_2025_325": {"victims": [12], "perps": [30], "imposed": ["50 years"]},
    "ncmec_2024_1136": {"victims": [], "perps": [55], "imposed": [], "cybertip": True},
    "ncmec_2023_104": {"victims": [], "perps": [23], "imposed": [], "cybertip": True},
    "illinois_ag_2023_015": {"victims": [], "perps": [38], "imposed": [], "cybertip": True},
    "doj_archives_2007_003": {"victims": [5], "perps": [57], "imposed": []},
    "ncmec_2022_506": {"victims": [], "perps": [56], "imposed": [], "cybertip": True},
    "azicac_2011_001": {"victims": [], "perps": [25], "imposed": []},
    "doj_safe_childhood_2025_327": {"victims": [13], "perps": [41], "imposed": ["25 years", "30 months"]},
    "south_florida_icac_2025_023": {"victims": [10], "perps": [28], "imposed": []},
}
DB = REPO / "caselinker.db"


def test_hard_ten_lists_ten_cases():
    assert len(HARD_EXPECTED) == 10


@pytest.mark.skipif(not DB.exists(), reason="local caselinker.db not present")
@pytest.mark.parametrize("case_id", sorted(HARD_EXPECTED))
def test_hard_ten_full_text(case_id):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = conn.execute("SELECT raw_data FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        pytest.fail(f"{case_id} is not in caselinker.db")
    raw = json.loads(row[0])
    text = raw["case_text"]
    case, res = run(text, case_id, year=str(raw.get("year") or ""))
    want = HARD_EXPECTED[case_id]
    assert age_final(res)["victims"] == want["victims"]
    assert age_final(res)["perpetrators"] == want["perps"]
    assert sentence_final(res)["imposed"] == want["imposed"]
    assert (res["investigation_type"]["final_value"] == ["cybertip"]) == bool(want.get("cybertip"))


# --- document kinds and compiled rules ---------------------------------------

SCREEN_NAME = "Officer used screen name Jake, a 14-year-old from Boise, during the chat."
SCREEN_RULE = {
    "id": "screen_name_age",
    "field": "age",
    "role": "decoy",
    "regex": r"screen name\W+(?:\w+\W+){0,6}?(\d{1,2})-year-old",
    "group": 1,
    "confidence": 0.85,
    "document_kinds": ["press_release", "investigative_note"],
}


def test_year_old_name_of_city_is_the_defendant_and_publication_day_replaces_january_first():
    text = (
        "February 23, 2012\n"
        "Source: https://www.lapdonline.org/newsroom/example/\n"
        "Los Angeles: LA ICAC had received a cyber-tip about the suspect, "
        "34-year-old Rowan Zephyrine of Los Angeles, being involved with child pornography. "
        "Zephyrine was booked at Van Nuys Jail."
    )
    case, res = run(text, "lapd_year_old_name", year="2012")
    assert age_final(res)["perpetrators"] == [34]
    assert age_final(res)["victims"] == []
    assert case["date_range"]["start"] == "2012-02-23"
    assert case["date_range"]["end"] == "2012-02-23"
    assert case["prosecution_outcome"]["jail"] == "booked at Van Nuys Jail"
    assert "Van Nuys" not in " ".join(case["prosecution_outcome"]["sentences"])


def test_azicac_year_old_suspect_and_age_pair_finalize():
    text = (
        "After hours of interviews they discovered that the 40 year old dog groomer had images. "
        "The suspect had a 9 year old and a 10 year old daughter. "
        "The suspect was a resident and a 26 year old unemployed drug addict. "
        "Investigators arrested two men ages 34 and 35 for sexual exploitation of a minor. "
        "He was arrested when he was 16 years old and charged as a minor. "
        "A 21-year-old Thai national is due to appear in a West Australian court. "
        "The victims, ages 4 thru 10, were interviewed."
    )
    _, res = run(text, "azicac_year_old_suspect", year="2011")
    final = age_final(res)
    assert 40 in final["perpetrators"]
    assert 26 in final["perpetrators"]
    assert 34 in final["perpetrators"] and 35 in final["perpetrators"]
    assert 21 in final["perpetrators"]
    assert 16 not in final["perpetrators"]
    # "had a 9 year old and a 10 year old daughter" settles the first child.
    # "ages 4 thru 10" is a span, so 4 and that 10 do not become victims.
    assert final["victims"] == [9]


def test_stanza_most_mentioned_name_cannot_finalize_alone():
    text = "Jamie Dunmarrow met Jamie Dunmarrow, 35, yesterday."
    second = text.index("Jamie Dunmarrow, 35")
    persons = [
        (text.index("Jamie Dunmarrow"), text.index("Jamie Dunmarrow") + len("Jamie Dunmarrow"), "Jamie Dunmarrow"),
        (second, second + len("Jamie Dunmarrow"), "Jamie Dunmarrow"),
    ]
    start = text.index("35")
    ner = {
        "number_spans": [(start, start + 2, "CARDINAL")],
        "person_spans": persons,
        "_backend_version": "stanza-test",
    }
    raw = A._ner_assertions(text, ner, [(start, start + 2, 35, "name_comma")])
    assert len(raw) == 1
    assert raw[0]["role"] == "perpetrator"
    assert raw[0]["confidence"] == 0.65
    gated = A.gate_assertion(text, raw[0])
    assert gated["span_ok"] == 1
    alone = A.resolve([gated])
    assert 35 not in (age_final(alone)["perpetrators"] or [])
    regex = dict(gated)
    regex.update(method="regex", family="surface_pattern", confidence=0.9)
    agreed = A.resolve([gated, regex])
    assert age_final(agreed)["perpetrators"] == [35]


def test_year_old_name_with_initial_and_a_prior_arrest_is_still_this_defendant():
    initial = (
        "19-year-old Ronnie J. Alexander, of Eunice Drive in St. Martinville, "
        "was arrested on December 4, 2025, for possession of child sexual abuse material."
    )
    _, res = run(initial, "year_old_initial")
    assert age_final(res)["perpetrators"] == [19]

    prior = (
        "19-year-old Avery Yarrowby, of Tatum, was previously arrested in January. "
        "Yarrowby was arrested on April 1, 2026, on federal charges."
    )
    _, res = run(prior, "year_old_prior_arrest", year="2026")
    assert age_final(res)["perpetrators"] == [19]


def test_previously_jailed_term_is_not_todays_sentence_and_licence_is_not_prison():
    # nca_2026_011: the 14 years is the earlier term. Life is this case.
    prior = (
        "April 02, 2026\nPublication date: 2026-04-02\nSource: "
        "A man who was previously jailed for 14 years for child sexual abuse offences "
        "has today been sentenced to life, after pleading guilty to an additional 67 charges. "
        "He was jailed in August 2022 to 14 years, with five years on an extended licence."
    )
    _, res = run(prior, "nca_2026_011", year="2026")
    imposed = sentence_final(res)["imposed"]
    assert not any("14" in s for s in imposed)
    assert any("life" in s.lower() for s in imposed)
    # the extended licence belongs to the 2022 term, not to today's life sentence
    assert not any("five" in s for s in sentence_final(res)["supervised_release"])

    # nca_2026_001: "six years on licence" is not a second prison term.
    licence = (
        "He was sentenced at the same court today where he received a 21 year prison sentence, "
        "a further six years on licence."
    )
    _, res = run(licence, "nca_2026_001")
    assert any(s.startswith("21") for s in sentence_final(res)["imposed"])
    assert not any("six" in s for s in sentence_final(res)["imposed"])
    assert any("six" in s for s in sentence_final(res)["supervised_release"])


def test_abuse_lasted_for_over_five_years_is_not_the_sentence():
    text = "Riley Alderhouse was sentenced to 35 years for sexually abusing a minor for over 5 years."
    _, res = run(text, "abuse_duration_not_sentence")
    assert sentence_final(res)["imposed"] == ["35 years"]


def test_one_of_the_is_not_an_age_and_a_range_is_not_two_victims():
    one_of = (
        "Earlier this week, the lead administrator of Playpen, one of the world’s largest "
        "child sexual abuse websites, was sentenced to 30 years. The takedown led to "
        "Operation Pacifier, one of the largest investigations ever undertaken."
    )
    _, res = run(one_of, "europol_one_of")
    assert 1 not in (age_final(res).get("perpetrators") or [])
    assert 1 not in (age_final(res).get("victims") or [])

    ranged = (
        "The operation resulted in the safe recovery of 10 children and youth "
        "between the ages of 13 and 18. Several arrests were made."
    )
    _, res = run(ranged, "hi_ag_age_span")
    assert age_final(res)["victims"] == []
    assert age_final(res)["perpetrators"] == []

    named = "Jamie Dunmarrow, 32, of Phoenix, was arrested for possession of child pornography."
    _, res = run(named, "name_comma_still_age")
    assert age_final(res)["perpetrators"] == [32]


def test_closed_age_span_is_not_two_people():
    """thru / to / hyphen spans are one range. A list joined by and is still two people."""
    spans = [
        "The victims, ages 4 thru 10, were interviewed after the arrest.",
        "The victims, ages 4 through 10, were interviewed.",
        "The victims, ages 4-10, were interviewed.",
        "He abused children aged 6-9.",
        "He abused children aged 6 to 9.",
        "He abused children aged 4 - 6 years old.",
        "The victims were children 4-6 years old.",
        "He had sexual contact with children ages 11-13.",
    ]
    for text in spans:
        _, res = run(text, "closed_age_span")
        assert age_final(res)["victims"] == [], text
        assert age_final(res)["perpetrators"] == [], text

    _, res = run("The defendant, aged 25-30, was charged with the abuse.", "closed_age_span_defendant")
    assert age_final(res)["perpetrators"] == []
    assert age_final(res)["victims"] == []

    _, res = run("Men aged 30 to 40 were arrested for the abuse.", "closed_age_span_men")
    assert age_final(res)["perpetrators"] == []

    _, res = run(
        "Investigators arrested two men ages 34 and 35 for sexual exploitation of a minor.",
        "enumerated_ages",
    )
    assert age_final(res)["perpetrators"] == [34, 35]

    _, res = run("Police rescued two girls, ages 6 and 9, who had been abused.", "enumerated_victims")
    assert age_final(res)["victims"] == [6, 9]

    _, res = run("A 34-year-old man was arrested for possession.", "year_old_not_a_span")
    assert age_final(res)["perpetrators"] == [34]

    _, res = run("Police found images of girls ages 5 to 8.", "depicted_span")
    assert age_final(res)["victims"] == []
    assert {(x["age"], x["role"]) for x in age_final(res).get("excluded") or []} >= {
        (5, "depicted_in_material"),
        (8, "depicted_in_material"),
    }


def test_child_in_the_pictures_is_not_stored_as_a_victim_age():
    # azicac_2013_006 — the verb between "videos" and the age used to hide the material cue
    text = (
        "During the forensic exam of the computers, numerous pictures and videos "
        "of an adult male and female were located molesting a 3 year old boy and also using a dog "
        "to offend on the child. The victim was located and saved from the offender."
    )
    _, res = run(text, "azicac_2013_006")
    assert 3 not in age_final(res)["victims"]
    assert 3 not in (age_final(res)["perpetrators"] or [])
    assert (3, "depicted_in_material") in excluded(res)


def test_stated_attraction_age_is_not_a_victim():
    # azicac_2013_012 — "around 8" is who they said they were attracted to, not a child in the case
    text = (
        "Investigators arrested two men ages 34 and 35 for sexual exploitation of a minor. "
        "He asked an adult male to molest his two children ages 5 and 2 and send him the pictures. "
        "Both admitted they were sexually attracted to female girls around 8 years old."
    )
    _, res = run(text, "azicac_2013_012")
    final = age_final(res)
    assert final["perpetrators"] == [34, 35]
    assert 5 in final["victims"] and 2 in final["victims"]
    assert 8 not in final["victims"]


def test_sting_headline_and_the_next_article_title_do_not_finalize():
    # ncis_2023_001. The headline age is the persona described later. The "Ten Years"
    # is the next article's title glued on after "please visit".
    text = (
        "Jacksonville Sex Offender Indicted For Attempting To Meet A 13-Year-Old Child "
        "To Engage In Sexual Activity\nSource:\n"
        "charging Hayden Dakota Vantreece (36, Jacksonville) with using the internet to attempt to entice a child. "
        "If convicted, Vantreece faces a minimum penalty of 10 years, up to life, in federal prison.\n"
        "On June 16, 2023, an undercover FBI agent, posing as a minor child, was working online "
        "to identify individuals seeking to make contact with children. The agent engaged in online "
        "conversation with an app username who posted a notice in a public chat room. "
        "During this online conversation, the user was advised that the “child” was 13 years old.\n"
        "For more information about Project Safe Childhood, please visit Cloud Man Sentenced To Ten Years "
        "In Prison For Attempting To"
    )
    _, res = run(text, "ncis_2023_001", year="2023")
    assert 13 not in age_final(res)["victims"]
    assert 36 in age_final(res)["perpetrators"]
    imposed = sentence_final(res)["imposed"]
    assert "Ten Years" not in imposed
    assert "10 years" not in imposed


def test_charged_name_parenthetical_age_is_the_defendant():
    text = (
        "Attorney General Peter F. Neronha announced that a Providence man has been charged. "
        "The Office charged Morgan Blake Corbridge (age 20), by way of criminal information, with possession of child pornography. "
        "The Office charged Reese Pellowe (age 45) by way of criminal information, with solicitation of a minor "
        "following an undercover investigation posing as a 14-year-old female."
    )
    case, res = run(text, "ri_ag_paren_age", year="2024")
    assert age_final(res)["perpetrators"] == [20, 45]
    assert 14 not in age_final(res)["victims"]
    assert (14, "decoy") in excluded(res)


def test_press_detectors_do_not_run_on_pacer():
    text = "An undercover officer was posing as a 14-year-old girl."
    press = A.collect_assertions(text, use_spacy=False, overrides={}, doc_kind="press_release")
    pacer = A.collect_assertions(text, use_spacy=False, overrides={}, doc_kind="pacer")
    assert any(a["method"] == "regex" and a["role"] == "decoy" for a in press)
    assert not any(a["method"] == "regex" for a in pacer)


def test_a_pacer_detector_can_be_registered():
    text = "Dunmarrow, 40, was indicted."
    start = text.index("40")
    seen = []

    def pacer_only(ctx):
        seen.append(ctx.doc_kind)
        return [{
            "field": "age", "method": "pacer_test", "method_version": "t", "value": 40,
            "role": "perpetrator", "span_start": start, "span_end": start + 2,
            "confidence": 0.9, "extras": {},
        }]

    A.detectors.register_detector("test_pacer_only", ("pacer",), pacer_only, order=5)
    try:
        A.collect_assertions(text, use_spacy=False, overrides={}, doc_kind="press_release")
        assert seen == []
        out = A.collect_assertions(text, use_spacy=False, overrides={}, doc_kind="pacer")
        assert seen == ["pacer"]
        assert any(a["method"] == "pacer_test" and a["value"] == 40 and a["span_ok"] for a in out)
    finally:
        A.detectors.unregister_detector("test_pacer_only")


def test_compiled_rule_runs_only_after_it_is_passed_in():
    bare = A.collect_assertions(SCREEN_NAME, use_spacy=False, overrides={})
    assert not any(a["method"] == "compiled_rule" for a in bare)
    ruled = A.collect_assertions(
        SCREEN_NAME, use_spacy=False, overrides={}, compiled_rules_override=[SCREEN_RULE]
    )
    compiled = [a for a in ruled if a["method"] == "compiled_rule"]
    assert compiled and compiled[0]["role"] == "decoy" and compiled[0]["value"] == 14
    note = A.collect_assertions(
        SCREEN_NAME, use_spacy=False, overrides={}, doc_kind="investigative_note",
        compiled_rules_override=[SCREEN_RULE],
    )
    assert any(a["method"] == "compiled_rule" and a["role"] == "decoy" for a in note)
    pacer = A.collect_assertions(
        SCREEN_NAME, use_spacy=False, overrides={}, doc_kind="pacer",
        compiled_rules_override=[SCREEN_RULE],
    )
    assert not any(a["method"] == "compiled_rule" for a in pacer)


def test_llm_rule_draft_must_earn_the_quotes(tmp_path):
    positives = ["used screen name Jake, a 14-year-old from Boise"]
    negatives = ["a 14-year-old victim"]

    def draft(_prompt: str) -> str:
        return json.dumps({
            "id": "screen_name_age",
            "regex": SCREEN_RULE["regex"],
            "rationale": "The age is the persona attached to the screen name.",
        })

    proposal = A.compiled_rules.propose_rule(
        rule_id="screen_name_age", field="age", role="decoy",
        positives=positives, negatives=negatives, generate=draft,
    )
    assert proposal["ok"] is True
    path = A.compiled_rules.write_proposal(proposal, tmp_path)
    assert path.exists()
    assert json.loads(path.read_text())["approved"] is False
    assert A.compiled_rules.APPROVED == []

    too_wide = A.compiled_rules.propose_rule(
        rule_id="wide", field="age", role="decoy", positives=positives, negatives=negatives,
        regex=r"(\d{1,2})",
    )
    assert too_wide["ok"] is False
