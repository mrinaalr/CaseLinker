"""CaseLinker processes names but never stores or serves them.

Readers may use a name in memory. Stored assertions and resolutions carry
per-case tokens, extraction records where people are (offsets, not names), and
every public surface redacts from those offsets.

Every name in this file is made up. Fixtures must never use a real person's name
(see ``test_fixtures_use_made_up_names``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_field_assertions import A, run  # noqa: E402

import people_mask as PK  # noqa: E402  (on sys.path via processing)

# Shapes the readers latch onto: appositive, "N-year-old Name", a judge's suffix,
# father/son suffixes, a sentencing subject.
TEXTS = {
    "appositive": "PHOENIX – Corin Ashcombe Sr., 52, of Phoenix, was sentenced to 10 years in prison. "
                  "His son, Corin Ashcombe, 24, of Phoenix, was sentenced to 5 years in prison.",
    "year_old_name": "Police arrested 34-year-old Reese Thistlewood of Los Angeles on Tuesday.",
    "judge": "Judge D.P. Larkspur, Jr. Finley Jordan Penhallow, 34, of Little Rock, was sentenced to 10 years in prison.",
    "sentenced_by": "U.S. District Judge Hollis K. Wexley sentenced Harper Emerson Marrowby, 38, of Parkville, "
                    "to 15 years in prison. Rowan Quinn Brambleton was sentenced to 27 years in prison.",
}
NAMES = ["Ashcombe", "Thistlewood", "Larkspur", "Penhallow", "Wexley", "Marrowby", "Brambleton", "Reese", "Harper"]


def _stored(case):
    """What storage writes: assertions and resolutions (never the source text)."""
    return json.dumps({"assertions": case["assertions"], "resolutions": case["resolutions"]})


def test_no_name_reaches_assertions_or_resolutions():
    for key, text in TEXTS.items():
        case, _ = run(text, f"no_names_{key}")
        stored = _stored(case)
        leaked = [n for n in NAMES if n in stored]
        assert not leaked, (key, leaked)


def test_no_name_shaped_entity_survives():
    for key, text in TEXTS.items():
        case, _ = run(text, f"no_entity_{key}")
        for a in case["assertions"]:
            extras = a.get("extras") or {}
            assert not A.resolution._parse_entity(extras.get("entity") or ""), (key, a["method"])
            assert "defendant_entity" not in extras and "sentence_subject" not in extras


def test_tokens_are_consistent_within_a_case_and_keep_suffixes():
    items = [
        {"span_start": 10, "extras": {"entity": "Corin Ashcombe Sr."}},
        {"span_start": 50, "extras": {"entity": "Corin Ashcombe"}},
        {"span_start": 90, "extras": {"defendant_entity": "Ashcombe"}},
        {"span_start": 95, "extras": {"entity": "man"}},
    ]
    PK.pseudonymize(items)
    assert items[0]["extras"] == {"name_key": "N1 N2 Sr"}
    assert items[1]["extras"] == {"name_key": "N1 N2"}
    assert items[2]["extras"] == {"defendant_key": "N2"}
    assert items[3]["extras"] == {"entity": "man"}  # a role noun is not a name


def test_resolution_output_has_person_index_not_name():
    case, res = run(TEXTS["appositive"], "person_index")
    entities = res["age"]["final_value"]["perpetrator_entities"]
    assert [e["person"] for e in entities] == ["p1", "p2"]
    assert all("entity" not in e for e in entities)


# --- where people are: offsets, and the redacted release -----------------------

RELEASE = (
    "LITTLE ROCK – Rowan Quinn Brambleton, 38, of Little Rock pleaded guilty to possession of child pornography. "
    "Brambleton told agents he had downloaded the files. The Minnesota Bureau of Criminal Apprehension, "
    "the Pulaski County Sheriff's Office and Homeland Security Investigations assisted."
)
ADMISSION = {
    "quote": "he had downloaded the files",
    "context": "Brambleton told agents he had downloaded the files",
    "frame": "told_investigators", "themes": ["possession"], "confidence": "high", "quote_type": "paraphrase",
}
NER_PERSON = [[RELEASE.index("Rowan"), RELEASE.index(", 38")]]  # what Stanza reports for this release


def test_person_spans_are_offsets_and_cover_repeat_mentions():
    spans = PK.person_spans(RELEASE, NER_PERSON)
    assert all(isinstance(s, int) and isinstance(e, int) for s, e in spans)
    covered = [RELEASE[s:e] for s, e in spans]
    assert "Rowan Quinn Brambleton" in covered and "Brambleton" in covered  # the later bare surname too


def test_redacted_release_keeps_places_agencies_and_facts():
    public = PK.public_text(RELEASE, PK.person_spans(RELEASE, NER_PERSON))
    assert "Brambleton" not in public and public.count("[PERSON]") == 2
    for kept in ("Little Rock", "Minnesota Bureau of Criminal Apprehension", "Pulaski County Sheriff's Office",
                 "Homeland Security Investigations", "38", "possession of child pornography"):
        assert kept in public


def test_admission_quotes_are_masked_but_kept_otherwise():
    [pub] = PK.mask_admissions([ADMISSION], RELEASE, PK.person_spans(RELEASE, NER_PERSON))
    assert "Brambleton" not in pub["context"] and pub["context"].startswith("[PERSON] told agents")
    assert pub["quote"] == ADMISSION["quote"]
    assert pub["themes"] == ["possession"] and pub["frame"] == "told_investigators"
    assert ADMISSION["context"].startswith("Brambleton")  # stored record untouched


def test_agencies_places_and_charges_are_not_masked():
    feats = {
        "person_spans": PK.person_spans(RELEASE, NER_PERSON),
        "agencies_involved": ["Minnesota Bureau of Criminal Apprehension", "Homeland Security Investigations"],
        "locations": ["Little Rock"],
        "organizations": ["Rowan Quinn Brambleton"],  # a reader filed the defendant as an organization
        "case_topics": ["Possession of Child Pornography"],
    }
    pub = PK.mask_feature_strings(feats, RELEASE)
    assert pub["agencies_involved"] == feats["agencies_involved"]
    assert pub["locations"] == ["Little Rock"]
    assert pub["case_topics"] == feats["case_topics"]
    assert pub["organizations"] == ["[PERSON]"]
    assert "person_spans" not in pub  # offsets are internal


def test_public_case_payload_serves_redacted_text_only():
    import importlib.util
    spec = importlib.util.spec_from_file_location("caselinker_run_main_nopii", ROOT / "run" / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["caselinker_run_main_nopii"] = main
    spec.loader.exec_module(main)
    case = {"id": "c1", "raw_data": {"case_text": RELEASE},
            "extracted_features": {"perpetrator_admissions": [dict(ADMISSION)], "case_text": RELEASE,
                                   "person_spans": PK.person_spans(RELEASE, NER_PERSON)}}
    out = main._sanitize_case_for_public(case)
    blob = json.dumps(out)
    assert "Brambleton" not in blob
    assert "raw_data" not in out and "case_text" not in out and "case_text" not in out["extracted_features"]
    assert out["case_text_redacted"].startswith("LITTLE ROCK – [PERSON], 38, of Little Rock")


def test_case_graph_holds_no_person_names():
    sys.path.insert(0, str(ROOT / "ontology"))
    import features_to_cac as F
    case = {"id": "graph_no_names", "source": "TEST", "case_text": RELEASE,
            "perpetrator_admissions": [dict(ADMISSION)], "organizations": ["Rowan Quinn Brambleton"],
            "extracted_features": {"perpetrator_admissions": [dict(ADMISSION)]}}
    graph, _ = F.CaseToCAC().map_case(case)
    assert "Brambleton" not in graph.serialize(format="trig")


# --- the public assistant never reads source text ------------------------------

def test_public_sql_cannot_read_source_text():
    import importlib.util
    spec = importlib.util.spec_from_file_location("caselinker_run_main_sql", ROOT / "run" / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["caselinker_run_main_sql"] = main
    spec.loader.exec_module(main)
    blocked = [
        "SELECT substr(raw_data, 1, 400) AS t FROM cases",
        "SELECT extracted_features FROM cases",
        "SELECT substr(extracted_features, 1, 200) FROM cases",
        "SELECT * FROM cases",
        "SELECT id FROM cases UNION SELECT extracted_features FROM cases",
        "SELECT (SELECT extracted_features FROM cases LIMIT 1) FROM cases",
    ]
    for q in blocked:
        try:
            main._nl_validate_select_sql(q)
        except ValueError:
            continue
        raise AssertionError(f"allowed: {q}")
    main._nl_validate_select_sql("SELECT count(*) FROM cases WHERE extracted_features LIKE '%sextortion%'")
    rows = main._nl_sanitize_rows([{"t": "Rowan Quinn Brambleton, 38, pleaded guilty."}])
    assert "Brambleton" not in rows[0]["t"]


# --- fixtures never carry a real person's name --------------------------------

# Made-up surnames fixtures may use. A test that needs a person's name picks from here
# (or adds a clearly fictional one). Real names copied from releases are not allowed.
FICTIONAL_SURNAMES = {
    "Ashcombe", "Thistlewood", "Larkspur", "Penhallow", "Wexley", "Marrowby", "Brambleton", "Quillfeather",
    "Kestrelson", "Orrindale", "Fenwright", "Halloway", "Corbridge", "Pellowe", "Rookhaven", "Tamberly",
    "Underhay", "Vantreece", "Wickersham", "Yarrowby", "Zephyrine", "Alderhouse", "Blackwillow", "Dunmarrow",
    "Elderkin", "Foxglove", "Greywater", "Hartwell", "Ivorydale", "Juniperton", "Kingsmere", "Lindqvast",
    "Moorcroft", "Northcote", "Oakhollow", "Pinecrest", "Quarrington", "Ravensworth", "Silverbirch", "Thornbury",
    "Umberfield", "Valemont", "Westerly",
    # Generic placeholders, never a full name from a release (checked against the corpus when added).
    # The father/son sentencing test needs a surname spaCy parses as a person.
    "Porter", "Smith", "Doe",
}


def test_fixtures_use_made_up_names():
    """Every person a test's text marks as a person (age / defendant-verb cues) has a made-up surname."""
    offenders = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for s, e in PK.person_spans(text, ()):
            surname = text[s:e].split()[-1].strip(".,’'")
            if len(surname) > 2 and surname[:1].isupper() and surname not in FICTIONAL_SURNAMES:
                offenders[path.name] = offenders.get(path.name, 0) + 1
    # Counts only: the failure message must not print the names it is guarding against.
    assert not offenders, f"fixtures with names not in FICTIONAL_SURNAMES (file: count): {offenders}"


def test_two_people_are_both_masked_and_an_agency_is_not():
    text = ("Corin Ashcombe and Reese Thistlewood, 41, were charged. Ashcombe said nothing. "
            "The Department of Internal Affairs said it helped, and Operation Broken Heart continues.")
    ner = [[text.index("Corin"), text.index(" and")], [text.index("Reese"), text.index(", 41")]]
    public = PK.public_text(text, PK.person_spans(text, ner))
    assert public.startswith("[PERSON] and [PERSON], 41, were charged. [PERSON] said nothing.")
    assert "Department of Internal Affairs" in public and "Operation Broken Heart" in public


def test_org_name_parts_are_not_people():
    text = "Agents with the Department of Labor and Workforce Development said the Kik Corporation cooperated."
    assert PK.person_spans(text, [[text.index("Workforce"), text.index(" said")]]) == []


def test_possessive_person_entries_are_dropped():
    text = "Corin Ashcombe Jr., 33, was charged. Agents searched Corin Ashcombe Jr.’s phone."
    spans = PK.person_spans(text, [[0, text.index(", 33")]])
    full, sur = PK.case_people(text, [text[a:b] for a, b in spans])
    out = PK.scrub_people({"organizations": ["Corin Ashcombe Jr.’s", "Kik"], "locations": ["Corin Ashcombe's"]}, full, sur)
    assert out == {"organizations": ["Kik"], "locations": []}


def test_two_letter_surname_is_masked_even_when_the_excerpt_is_not_in_the_text():
    # A short surname ("Wu"-length) and an excerpt from a differently normalized copy of the release.
    text = "From the United States Attorney’s Office, Reese Qo, 42, of Tulsa, pleaded guilty."
    excerpt = "from the United States Attorney’s Office,  Reese Qo, 42, of Tulsa, pleaded"  # not in text
    spans = PK.person_spans(text, [[text.index("Reese"), text.index(", 42")]])
    assert PK.public_text(text, spans).startswith("From the United States Attorney’s Office, [PERSON], 42")
    [pub] = PK.mask_admissions([{"quote": "he shared the files", "context": excerpt}], text, spans)
    assert "Qo" not in pub["context"] and "Reese" not in pub["context"]


def test_surname_with_suffix_label_is_a_person_but_a_county_abbreviation_is_not():
    text = "Corin Ashcombe Jr., 29, of Boyd Co., was arrested. Ashcombe Jr. was lodged in the Boyd County Detention Center."
    spans = PK.person_spans(text, [[0, text.index(", 29")]])
    assert not any(text[a:b].startswith("Boyd") for a, b in spans)  # "Boyd Co." is a county
    feats = {"person_spans": spans, "organizations": ["Ashcombe Jr.’s", "Boyd County Detention Center"]}
    assert PK.mask_feature_strings(feats, text)["organizations"] == ["[PERSON]", "Boyd County Detention Center"]
    assert "Boyd County Detention Center" in PK.public_text(text, spans)


def test_repeats_after_a_comma_and_glued_words_are_masked_and_agency_places_are_not():
    text = ("Rowan Quinn Brambleton, 38, was arraigned. According to the complaint filed against Rowan Quinn Brambleton, "
            "police pursued leads. Brambletonhas been released. Spring Grove officers assisted.")
    ner = [[0, text.index(", 38")], [text.index("Spring"), text.index(" officers")]]
    public = PK.public_text(text, PK.person_spans(text, ner, ["Spring Grove Police Department"]))
    assert "Brambleton" not in public and "Rowan" not in public
    assert "Spring Grove officers" in public  # a place this case's agencies are named after


def test_a_town_in_possessive_form_is_not_masked_when_agencies_are_named_after_it():
    text = "Spring Grove’s police department led the case. Rowan Quinn Brambleton, 61, was charged."
    ner = [[0, text.index("’s")], [text.index("Rowan"), text.index(", 61")]]
    public = PK.public_text(text, PK.person_spans(text, ner, ["Spring Grove Police Department"]))
    assert public.startswith("Spring Grove’s police department") and "Brambleton" not in public
