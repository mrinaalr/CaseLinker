"""Case vs awareness vs roundup. No network and no real narratives."""

from collector.case_release_filter import classify_release


def test_arrest_release_is_kept():
    title = "Man charged with child sexual offences"
    body = "He was charged with possession of child abuse material and remanded."
    assert classify_release(title, body) == "keep"


def test_awareness_is_skipped():
    title = "Tips for parents during awareness month"
    body = "The ICAC task force shared statistics and guidance for parents."
    assert classify_release(title, body) == "skip"


def test_footer_boilerplate_does_not_qualify_another_crime():
    title = "Man charged after a burglary"
    body = (
        "He was charged with burglary.\n\n"
        "About the ICAC\n"
        "The Internet Crimes Against Children task force investigates child exploitation."
    )
    assert classify_release(title, body) == "skip"


def test_child_porn_arrest_title_is_kept():
    assert classify_release(
        "Man arrested for child porn offences",
        "Details of the arrest were released.",
    ) == "keep"


def test_child_luring_charge_is_kept():
    assert classify_release(
        "Charges laid for child luring",
        "He was charged after the investigation.",
    ) == "keep"


def test_numbered_group_is_a_roundup():
    assert classify_release(
        "26 people charged in online child sexual exploitation investigations",
        "Police announced the results of the investigation.",
    ) == "roundup"


def test_one_person_with_repeated_charge_words_is_kept():
    assert classify_release(
        "Man arrested for child pornography offences",
        "He was arrested. He was charged with possession. He was charged with distribution.",
    ) == "keep"


def test_three_charged_people_is_a_roundup():
    title = "Operation example"
    body = (
        "A was charged with child pornography. "
        "B was charged with child pornography. "
        "C was charged with child pornography."
    )
    assert classify_release(title, body) == "roundup"


def test_word_number_group_is_a_roundup():
    assert classify_release(
        "Eleven adults arrested over alleged sexual exploitation of children",
        "Gardaí charged the group after the investigation.",
    ) == "roundup"


def test_policy_title_is_skipped():
    assert classify_release(
        "Publication of policy on the investigation of sexual crime and crimes against children",
        "The investigation policy sets out how reports are handled.",
    ) == "skip"
