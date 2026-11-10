"""Platform names that are also ordinary words or people's names.

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


def platforms(text: str) -> list[str]:
    return PP.extract_platforms({"case_text": text})


# nj_ag_2017_001
DOG = (
    "The Division of Criminal Justice exhibited its new cyber forensics van, and the State Police showcased "
    "its new electronics detection dog, Mega, both of which contributed greatly to the success of the "
    "operation. Detectives allegedly found over 10 nude images of an underage girl on his phone."
)


def test_mega_the_dog_is_not_a_platform():
    assert "Mega.nz" not in platforms(DOG)


def test_mega_as_an_adjective_or_surname_is_not_a_platform():
    # ncmec_2025_239, nj_ag_2013_011
    assert "Mega.nz" not in platforms("A former youth pastor from a mega church was arrested on child abuse charges.")
    assert "Mega.nz" not in platforms("Orrin Mega pleaded guilty on Aug. 14 to second-degree distribution of child pornography.")


@pytest.mark.parametrize(
    "text",
    [
        "He used file-hosting service Mega to download child pornography.",  # doj_safe_childhood_2024_302
        "He kept them in his encrypted cloud storage account held by Mega LTD.",  # doj_safe_childhood_2024_435
        "He admitted using apps such as TamTam, ICQ, Mega, and Telegram.",  # doj_safe_childhood_2026_345
        "He shared these files through various online platforms including Telegram and Mega.",  # doj_safe_childhood_2026_232
        "He stored the videos on MEGA.",
        "Investigators traced the upload to mega.nz.",
    ],
)
def test_mega_the_service_is_still_a_platform(text):
    assert "Mega.nz" in platforms(text)


def test_facetime_is_a_platform():
    # nj_ag_2017_001
    got = platforms("He allegedly engaged multiple underage girls in conversations on FaceTime, which he recorded.")
    assert "FaceTime" in got


def test_facetime_reaches_the_case_graph_as_a_messaging_service():
    sys.path.insert(0, str(REPO / "ontology"))
    from features_to_cac import PLATFORM_MAP

    assert PLATFORM_MAP["FaceTime"][0] == PLATFORM_MAP["Skype"][0] == "MessagingService"
