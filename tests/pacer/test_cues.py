"""The codebook cue table that settles a differing action code (state_machines/coding/cues.py)."""
from __future__ import annotations

from state_machines.coding import coder as C
from state_machines.coding.cues import CUES, RESIDUAL, settle


def test_every_specific_code_the_models_can_give_has_cues():
    assert {a for a in C.ACTIONS if a not in RESIDUAL} <= set(CUES)
    assert not RESIDUAL & set(CUES)


def test_exactly_one_cued_code_settles_it():
    asked = "The defendant asked Minor Victim 1 to send sexually explicit images of herself."
    assert settle(asked, "SOLICIT_IMAGERY", "INITIATE_CONTACT") == "SOLICIT_IMAGERY"
    assert settle(asked, "INITIATE_CONTACT", "SOLICIT_IMAGERY") == "SOLICIT_IMAGERY"       # order of the coders is irrelevant
    exam = "A forensic examination of the defendant's phone found the application installed."
    assert settle(exam, "LE_SURVEIL", "LE_FORENSIC_EXAM") == "LE_FORENSIC_EXAM"


def test_no_cue_or_cues_for_both_leaves_it_unsettled():
    both = "The defendant threatened to send the images to her friends and then sent them to her mother."
    assert settle(both, "THREATEN_EXPOSURE", "EXPOSE_TO_VICTIM_NETWORK") is None           # one sentence, two acts
    neither = "The defendant and Minor Victim 1 exchanged messages for several weeks."
    assert settle(neither, "BUILD_RAPPORT", "SOLICIT_IMAGERY") is None
    assert settle(neither, "BUILD_RAPPORT", "NOT_A_CODE") is None


def test_a_residual_code_yields_only_to_a_cued_specific_code():
    moved = "The defendant told Minor Victim 1 to continue their conversation on Kitebox."
    assert settle(moved, "COMMUNICATE", "MOVE_CHANNEL") == "MOVE_CHANNEL"
    assert settle("The defendant wrote to Minor Victim 1 every day.", "COMMUNICATE", "MOVE_CHANNEL") is None
