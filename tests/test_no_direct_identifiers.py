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
            if surname.isupper():
                surname = surname.capitalize()  # older releases print defendants in capitals
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


def test_a_small_town_ner_calls_a_person_stays_unmasked():
    text = ("Troopers arrest Hollow Brook man for possession. Rowan Quinn Brambleton,25, of Hollow Brook, NY, "
            "was arraigned in the Hollow Brook Town Court.")
    ner = [[text.index("Hollow"), text.index(" man")], [text.index("Rowan"), text.index(",25")]]
    public = PK.public_text(text, PK.person_spans(text, ner))
    assert public.count("Hollow Brook") == 3 and "Brambleton" not in public


# --- names NER found that the masker used to let through -------------------------
# Wording copied from live releases (nj_ag_2017_001, doj_ceos_2012_007 and others), names made up.

def _public(text: str, *names: str, not_people=()) -> str:
    """Public text when NER reports each of ``names`` as a PERSON span."""
    ner = []
    for name in names:
        for m in re.finditer(re.escape(name), text):
            ner.append([m.start(), m.end()])
    return PK.public_text(text, PK.person_spans(text, ner, not_people))


def test_a_title_before_a_name_is_not_an_organization():
    text = ("TRENTON – Attorney General Corin Ashcombe today announced arrests. Sheriff Reese Thistlewood and "
            "U.S. Marshal Hollis K. Wexley assisted. Suspects told police Ashcombe had been notified.")
    public = _public(text, "Corin Ashcombe", "Reese Thistlewood", "Hollis K. Wexley")
    assert public == ("TRENTON – Attorney General [PERSON] today announced arrests. Sheriff [PERSON] and "
                      "U.S. Marshal [PERSON] assisted. Suspects told police [PERSON] had been notified.")


def test_an_agency_named_with_of_or_a_possessive_is_still_not_a_person():
    text = ("The Department of Internal Affairs and the Attorney General's Child Predator Unit worked "
            "Operation Broken Heart with Corin Ashcombe.")
    public = _public(text, "Internal Affairs", "Child Predator", "Broken Heart", "Corin Ashcombe")
    assert public == text.replace("Corin Ashcombe", "[PERSON]")


def test_a_name_wrapped_across_two_lines_is_masked_whole():
    text = "He thanked Detectives Corin Ashcombe, Reese\nThistlewood, and Hollis K.\nWexley for their work."
    public = _public(text, "Corin Ashcombe", "Reese\nThistlewood", "Hollis K.\nWexley")
    assert public == "He thanked Detectives [PERSON], [PERSON], and [PERSON] for their work."


def test_a_name_ends_with_its_line_when_the_next_line_is_a_label():
    text = "Contact Reese Thistlewood\nSource:\nNASHVILLE – An investigation led to an arrest."
    public = _public(text, "Reese Thistlewood\nSource")
    assert public == "Contact [PERSON]\nSource:\nNASHVILLE – An investigation led to an arrest."


def test_a_suffix_or_office_after_a_name_is_not_a_state():
    text = "Hollis K. Wexley, II, United States Attorney, and Reese Thistlewood, EU Commissioner, spoke."
    public = _public(text, "Hollis K. Wexley", "Reese Thistlewood")
    assert public == "[PERSON], II, United States Attorney, and [PERSON], EU Commissioner, spoke."


def test_a_surname_that_is_also_a_town_is_masked_where_it_is_a_person():
    # "Hartwell" is on the map (Hartwell, Georgia) and is also this official's surname.
    person = "On July 21, Governor Hartwell signed a new law. Hartwell said it takes effect in February."
    assert _public(person, "Hartwell") == ("On July 21, Governor [PERSON] signed a new law. "
                                           "[PERSON] said it takes effect in February.")
    town = "A Hartwell man was arrested Tuesday by Hartwell police, officials in Hartwell said."
    assert _public(town, "Hartwell") == town


def test_the_sentence_after_a_name_does_not_make_it_an_organization():
    text = ("“We will find you,” said Director Corin Ashcombe. “Operation Broken Heart proves it.” "
            "Ashcombe’s office, with a federal grant, runs the task force.")
    public = _public(text, "Corin Ashcombe", "Ashcombe’s")
    assert public.startswith("“We will find you,” said Director [PERSON]. “Operation Broken Heart proves it.” [PERSON]")
    assert "Ashcombe" not in public


def test_all_caps_defendant_names_are_masked_and_headlines_are_not():
    text = ("PINECREST MAN ARRESTED ON CHILD PORNOGRAPHY CHARGES\nINDIANAPOLIS – A grand jury returned an indictment "
            "charging ROWAN BRAMBLETON, age 27, of Pinecrest. BRAMBLETON was arrested by ICAC agents.")
    public = _public(text, "PINECREST MAN", "INDIANAPOLIS", "ROWAN BRAMBLETON", "BRAMBLETON", "ICAC")
    assert public == ("PINECREST MAN ARRESTED ON CHILD PORNOGRAPHY CHARGES\nINDIANAPOLIS – A grand jury returned an "
                      "indictment charging [PERSON], age 27, of Pinecrest. [PERSON] was arrested by ICAC agents.")


def test_the_defendant_block_is_masked_without_ner():
    text = "Assistant U.S. Attorneys are in charge of the prosecution.\nThe Defendant:\nROWAN BRAMBLETON Age: 39 Springfield"
    assert PK.public_text(text, PK.person_spans(text, ())).endswith("The Defendant:\n[PERSON] Age: 39 Springfield")


def test_a_title_ner_took_with_the_name_stays_readable():
    text = ("Former church Pastor Reese Thistlewood was indicted, said Special Agent in Charge Corin Ashcombe. "
            "Contact Detective Wexley #4576 of the police department.")
    public = _public(text, "Pastor Reese Thistlewood", "Charge Corin Ashcombe", "Wexley #4576")
    assert public == ("Former church Pastor [PERSON] was indicted, said Special Agent in Charge [PERSON]. "
                      "Contact Detective [PERSON] of the police department.")


def test_initials_nicknames_and_particles_stay_inside_the_name():
    text = ("Chief Judge R.L. Wexley. Wexley sentenced Reese “Rocky” Thistlewood, 33. "
            "His lawyer, van Ashcombe added, will appeal.")
    public = _public(text, "R.L. Wexley", "Reese “Rocky", "van Ashcombe")
    assert "Wexley" not in public and "Reese" not in public and "Rocky" not in public and "Ashcombe" not in public
    assert public.startswith("Chief Judge [PERSON]. [PERSON] sentenced [PERSON]")


def test_placeholders_and_non_names_ner_calls_people_stay_readable():
    text = ("Jane Doe 1 confided in a teacher. He was read his Miranda rights and gave up his Kik account. "
            "Corin Ashcombe, 41, was charged.")
    public = _public(text, "Jane Doe 1", "Miranda", "Kik", "Corin Ashcombe")
    assert public == text.replace("Corin Ashcombe", "[PERSON]")


def test_a_name_inside_an_email_address_is_masked_and_the_agency_domain_is_kept():
    text = "Contact Public Affairs Officer Corin Ashcombe at corin.ashcombe@usdoj.gov or tips@usdoj.gov."
    public = _public(text, "Corin Ashcombe")
    assert public == "Contact Public Affairs Officer [PERSON] at [PERSON]@usdoj.gov or tips@usdoj.gov."
