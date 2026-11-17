"""Deterministic coding of an act's sentence (state_machines/coding/enrich.py)."""
from __future__ import annotations

import pytest

from state_machines.coding import enrich as N


@pytest.mark.parametrize("sentence,expected", [
    ("On or about July 1, 2020, the defendant asked MV-1 for images.", ("On or about July 1, 2020", "2020-07-01", "2020-07-01", "day")),
    ("In June 2020, the defendant first contacted Minor Victim 1.", ("In June 2020", "2020-06-01", "2020-06-30", "month")),
    ("05/02/2021 the defendant was arrested.", ("05/02/2021", "2021-05-02", "2021-05-02", "day")),
    ("The defendant violated 18 U.S.C. § 2422 in 2251 ways.", None),
    ("The defendant told Minor Victim 1 that he was seventeen.", None),
])
def test_dates_keep_their_words_and_real_bounds(sentence, expected):
    d = N.find_date(sentence)
    assert (None if d is None else (d["x"], d["from"], d["to"], d["p"])) == expected


def test_targets_from_role_mentions():
    assert N.targets("The defendant asked MV-2 for images.", "offender") == [{"who": "minor victim 2", "role": "victim"}]
    assert N.targets("He asked an undercover agent for images.", "offender") == [{"who": "an undercover agent", "role": "counterparty"}]
    assert N.targets("Agents arrested him.", "law_enforcement") == [{"who": "the defendant", "role": "subject"}]


def test_level_c_needs_the_feature_words_in_the_sentence():
    assert N.feature("He used the disappearing-message feature on Vellum Chat.") == ("ephemerality", "disappearing-message")
    assert N.feature("He created a new account under a different name to hide.")[0] == "anonymity"
    assert N.feature("He messaged her on Snapwire.") is None                  # a platform name alone is never level C (B0)


def test_platforms_are_named_services_never_places_or_dates():
    assert N.platform("He first contacted her through the Chirpline application.")["n"] == "Chirpline"
    assert N.platform("He posted the images in a Kitebox group chat.") == {"n": "Kitebox", "m": "through", "au": "group"}
    assert N.platform("He lived in Anchorage on June 3.") is None


def test_harm_follows_the_act_only_with_a_minor_target():
    a = N.enrich({"action": "RECEIVE_SELF_GENERATED"}, "Minor Victim 1 sent the defendant two images.", "offender")
    assert a["harm"] == "HARM_COERCED_SELF_GENERATED_IMAGERY"
    b = N.enrich({"action": "SOLICIT_IMAGERY"}, "He asked an undercover agent for images.", "offender")
    assert "harm" not in b and b["outcome"] == "attempted_not_completed"


def test_sequence_words_mark_order_and_channels_are_not_platforms():
    a = N.enrich({"action": "RECREATE_ACCOUNT"}, "After Minor Victim 1 blocked him, the defendant made a new account.", "offender")
    assert a["after"] == "__previous__"
    c = N.enrich({"action": "COMMUNICATE"}, "The defendant sent Minor Victim 1 text messages every day.", "offender")
    assert c["platform"]["name"] == "text message"                            # becomes a channel in assemble (I3)
