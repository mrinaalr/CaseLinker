"""Prosecution status: a stage word counts only when it reports this case's own outcome.

Fixtures copy the wording of live releases, cited by case_id, with made-up people.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import processing  # noqa: E402

PP = processing.assertions_module.patterns._pp


def status(text: str):
    return PP._extract_prosecution_status(text)


# nj_ag_2017_001: an arrest announcement with the statutory penalty and the presumption of innocence.
ARREST_RELEASE = (
    "Attorney General today announced arrests of 79 alleged child predators. Thane Corbridge, 22, was arrested "
    "on Oct. 10 and charged with possession of child pornography. The defendants are charged with distributing "
    "25 items or more, and therefore are subject, if convicted, to a mandatory minimum sentence of five years "
    "in prison. Second-degree crimes carry a sentence of five to 10 years in state prison. The charges are "
    "merely accusations and the defendants are presumed innocent until proven guilty."
)


def test_if_convicted_is_not_a_conviction():
    assert status(ARREST_RELEASE) == "charged"


@pytest.mark.parametrize(
    "text, expected",
    [
        # ky_sp_2021_013, doj_ceos_2013_062: a label on the person, not this case's outcome
        ("He was charged with possession of a handgun by a convicted felon.", "charged"),
        ("Convicted Sex Offender Indicted For Production Of Child Pornography", "indicted"),
        # illinois_ag_2021_002, ncmec_2022_424: the earlier case
        ("Halloway was arrested Tuesday. Halloway was previously convicted on related charges in 2010.", "arrested"),
        ("He was arrested. State records showed he is a registered sex offender who was convicted in 2016 "
         "for possession of child pornography.", "arrested"),
        # ncmec_2024_324, doj_archives_2006_003: a class of people
        ("He was charged Monday. Sentences for those convicted of such felonies can range from probation to prison.",
         "charged"),
        ("He was indicted. That statute mandates a life sentence for any person who is convicted of a federal "
         "sex offense.", "indicted"),
        # doj_safe_childhood_2025_056, ohio_ag_2013_004: the plea happened, the sentencing has not
        ("Pellowe pleaded guilty today. Pellowe is scheduled to be sentenced on March 2, 2026.", "pleaded_guilty"),
        ("Pellowe pleaded guilty today and will be sentenced in the Court of Common Pleas next month.", "pleaded_guilty"),
        ("He was indicted and could be sentenced to as much as life in federal prison.", "indicted"),
    ],
)
def test_stage_words_that_are_not_this_cases_outcome(text, expected):
    assert status(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Rookhaven was convicted by a federal jury today of producing child pornography.", "convicted"),
        # doj_ceos_2013_050: the headline names him a registered sex offender and reports the verdict
        ("Lake Wales Registered Sex Offender Convicted Of Enticement Of A Minor", "convicted"),
        # de_ag_2025_002: a dated verdict in this case
        ("Publication date: 2025-01-08 On December 10, 2024, Tamberly, 19, was convicted of Rape Second Degree.",
         "convicted"),
        ("Underhay, a registered sex offender, was sentenced today to 20 years in prison.", "sentenced"),
        # scotland_police: "returned to be sentenced" reports the hearing
        ("He was jailed for 31 months when he returned to be sentenced on Tuesday.", "sentenced"),
        # ut_ag_2016_001: the plea in a sentencing release is this case's plea
        ("The judge ordered 1 to 15 years in prison. Vantreece had previously pleaded guilty to two counts.",
         "pleaded_guilty"),
        ("Local man pleads guilty to receiving child pornography", "pleaded_guilty"),
        # #61, nz_dia / scotland_police / nca: a term with no "sentenced"
        ("A Tauranga man was jailed yesterday for two years and two months after pleading guilty.", "sentenced"),
        ("He pleaded guilty and was jailed for three-and-a-half years.", "sentenced"),
        ("Halvorsen was convicted and imprisoned for 18 months.", "sentenced"),
        # A headline or a maximum penalty is not a term
        ("Man jailed for possessing child sex abuse images. He pleaded guilty in May.", "pleaded_guilty"),
        ("He pleaded guilty and could be jailed for 10 years.", "pleaded_guilty"),
    ],
)
def test_real_outcomes_are_kept(text, expected):
    assert status(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        # south_florida_icac_2024_017: the plea is the earlier case he was on probation for
        ("Publication date: 2024-11-18 Prosecutors upgraded charges Monday against a man who was arrested in "
         "October. Halvorsen was first arrested in 2020 and pleaded no contest in 2022 to the same crime.", "arrested"),
        # nj_ag_2018_024: a registered offender's 2011 plea in a 2018 arrest release
        ("Publication date: 2018-06-01 Marrowby was charged with endangering. Marrowby pleaded guilty in 2011 "
         "to attempted endangering.", "charged"),
        # nj_ag_2025_003: the next release's headline follows the presumption-of-innocence paragraph
        ("Thane Corbridge was charged with possession.\nCharges are merely accusations, and the defendant is "
         "presumed innocent unless and until proven guilty in a\ncourt of law.\n\nSecond Man Pleads Guilty to "
         "Distributing Child Pornography on\nthe Internet - Defendant", "charged"),
        # A plea dated last year is still this case's plea.
        ("Publication date: 2024-03-02 Underhay pleaded guilty in 2023 and awaits sentencing.", "pleaded_guilty"),
    ],
)
def test_a_plea_from_an_earlier_case_or_the_next_release_is_not_this_cases_plea(text, expected):
    assert status(text) == expected
