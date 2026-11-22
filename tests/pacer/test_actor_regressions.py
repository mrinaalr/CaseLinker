"""One table of caption and actor probes from the v2 reviews.

Each row is a caption or a sentence. The expected value is the defendant
surnames, the canonical actor, or the counted drop reason.
"""
from __future__ import annotations

import json

import pytest

from state_machines.coding import coder as C
from state_machines.coding.frames import locate_span
from state_machines.coding.workflow import (
    case_defendants, clause_subject, decide_actor, defendant_records_in,
)
from state_machines.evidence import evidence as E

from tests.pacer.test_pipeline_flags import _ask_frames, _clear, _page, _plain_frame, _store


def _parser_up() -> bool:
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


def _surnames(text: str):
    return [record["surname"] for record in defendant_records_in(text)]


def _expect(value):
    if isinstance(value, dict):
        return value["spacy"] if _parser_up() else value["none"]
    return value


def _store_docs(tmp, case, docs):
    listed = []
    for doc_id, doc_type, pages in docs:
        page_rows = []
        for number, text in enumerate(pages, 1):
            E.write_page(case, doc_id, number, text, tmp)
            page_rows.append({"pdf_page": number, "text_method": "text_layer",
                              "page_text_sha256": E.sha256_text(E.normalize(text)),
                              "court_page_label": None, "ocr_engine": None,
                              "ocr_mean_confidence": None, "image_checked": False, "limitations": []})
        listed.append({"doc_id": doc_id, "doc_type": doc_type, "source_path": f"FICTIONAL/{case}.pdf",
                       "sha256": E.sha256_text(doc_id), "ecf_document_number": None, "filed_date": None,
                       "page_count": len(pages), "pages": page_rows})
    (tmp / case / "sources.json").write_text(
        json.dumps({"case_id": case, "documents": listed}), encoding="utf-8")


# (name, kind, payload, expected)
# kind records: caption text -> surnames
# kind subject: sentence -> clause_subject
# kind actor: (caption, sentence, actor) -> canonical or drop reason
# kind case: documents -> generic status and surnames
# kind locate: (page, needle) -> found
# kind frame: (page, quote, actor) -> event action or drop reason
PROBES = [
    ("middle-initial", "records", "UNITED STATES v. MICHAEL A. SMITH, Defendant.", ["SMITH"]),
    ("single-initial", "records", "UNITED STATES v. M. SMITH, Defendant.", ["SMITH"]),
    ("middle-q", "records", "United States v. MICHAEL Q. SMITH, Defendant.", ["SMITH"]),
    ("middle-j", "records", "United States v. Michael J. Smith, Defendant.", ["Smith"]),
    ("surname-first", "records", "UNITED STATES v. SMITH, MICHAEL, Defendant.", ["SMITH"]),
    ("suffix-between", "records", "United States v. SMITH, JR., MICHAEL, Defendant.", ["SMITH"]),
    ("suffix-after", "records", "United States v. John Smith Jr., Defendant.", ["Smith"]),
    ("entity-and", "records", "United States v. ACME WIDGETS AND HOLDINGS LLC, Defendant.", ["LLC"]),
    ("comma-three", "records",
     "United States v. Michael Smith, Robert Brown, and Alan Price, Defendants.",
     ["Smith", "Brown", "Price"]),
    ("comma-two", "records", "United States v. MICHAEL SMITH, ROBERT BROWN, Defendant.", ["SMITH", "BROWN"]),
    ("semicolons", "records", "United States v. SMITH; JONES; and PRICE, Defendants.", ["SMITH", "JONES", "PRICE"]),
    ("surname-and-initial", "records",
     "United States v. SMITH, MICHAEL A. and JONES, ROBERT, Defendants.", ["SMITH", "JONES"]),
    ("alias-one", "records",
     "UNITED STATES v. Jordan Example a/k/a Jay Sample, Defendant.", ["Example"]),
    ("blank-lines", "records",
     "UNITED STATES OF AMERICA,\n\nv.\n\nMICHAEL SMITH,\n\nDefendant.", ["SMITH"]),
    ("booker-same-page", "records",
     "United States v. Michael Smith, Defendant. " + ("The statute describes an offense. " * 8)
     + "See United States v. Booker, 543 U.S. 220 (2005). Gall v. United States, 552 U.S. 38 (2007).",
     ["Smith"]),
    ("subject-smith", "subject", "Smith sent the files to other users via an encrypted channel.", "Smith"),
    ("subject-defendant-name", "subject",
     "Defendant Smith sent the files to other users via an encrypted channel.", "Defendant Smith"),
    ("subject-date", "subject",
     "On May 1, 2020, Smith sent the files to other users via an encrypted channel.", "Smith"),
    ("subject-the-defendant", "subject",
     "On May 2, 2021, the defendant sent the files to other users via an encrypted channel.", "the defendant"),
    ("lead-on-or-about", "subject",
     "On or about May 2, 2020, Smith sent the files.", "Smith"),
    ("lead-between-months", "subject",
     "Between May and June 2021, Smith sent the files.", "Smith"),
    ("lead-between-days", "subject",
     "Between May 1 and June 3, 2020, Smith sent the files.", "Smith"),
    ("lead-then", "subject", "Then, Smith sent the files.", "Smith"),
    ("lead-later", "subject", "Later, Smith sent the files.", "Smith"),
    ("lead-however", "subject", "However, Smith sent the files.", "Smith"),
    ("lead-thereafter", "subject", "Thereafter, Smith sent the files.", "Smith"),
    ("lead-around", "subject", "In or around 2019, the defendant sent the files.", "the defendant"),
    ("lead-clock", "subject", "At 3:00 p.m., the defendant sent the files.", "the defendant"),
    ("young-people", "actor",
     ("United States v. ROBERT YOUNG, Defendant.",
      "Young people sent the files to other users via an encrypted channel.", "Young"),
     {"spacy": "actor_rejected", "none": "no_parser"}),
    ("brown-packages", "actor",
     ("United States v. BROWN, Defendant.",
      "Brown packages were sent to other users via an encrypted channel.", "Brown"),
     {"spacy": "actor_rejected", "none": "no_parser"}),
    ("white-emailed", "actor",
     ("United States v. White, Defendant.",
      "White emailed the files to other users via an encrypted channel.", "White"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("long-texted", "actor",
     ("United States v. Long, Defendant.",
      "Long texted the files to other users via an encrypted channel.", "Long"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("price-messaged", "actor",
     ("United States v. Price, Defendant.",
      "Price messaged the files to other users via an encrypted channel.", "Price"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("price-traded", "actor",
     ("United States v. Price, Defendant.",
      "Price traded the files to other users via an encrypted channel.", "Price"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("long-repeatedly", "actor",
     ("United States v. Long, Defendant.",
      "Long repeatedly sent the files to other users via an encrypted channel.", "Long"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("smith-from-middle-initial", "actor",
     ("United States v. MICHAEL Q. SMITH, Defendant.",
      "Smith sent the files to other users via an encrypted channel.", "Smith"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("smith-from-surname-first", "actor",
     ("United States v. SMITH, MICHAEL, Defendant.",
      "Smith sent the files to other users via an encrypted channel.", "Smith"),
     {"spacy": "the defendant", "none": "no_parser"}),
    ("given-name-only", "actor",
     ("United States v. Michael Smith, Defendant.",
      "Michael uploaded the files using an encrypted app.", "Michael"),
     "surname_not_established"),
    ("lowercase-surname", "actor",
     ("United States v. ROBERT YOUNG, Defendant.",
      "The young victim sent nothing.", "young"),
     "actor_rejected"),
    ("possessive-mother", "actor",
     ("United States v. Michael Smith, Defendant.",
      "The defendant's mother distributed the files to other users via an encrypted channel.",
      "The defendant's mother"),
     "actor_rejected"),
    ("possessive-smith", "actor",
     ("United States v. Michael Smith, Defendant.",
      "Smith's mother sent the files to other users via an encrypted channel.", "Smith's mother"),
     "actor_rejected"),
    ("agent-not-subject", "actor",
     ("United States v. Michael Smith, Defendant.",
      "Agent Porter sent the files to the defendant via an encrypted channel.", "the defendant"),
     "actor_rejected"),
    ("passive", "actor",
     ("United States v. Michael Smith, Defendant.",
      "The files were sent by Smith to other users via an encrypted channel.", "Smith"),
     "passive_subject"),
    ("generic-one", "actor",
     ("United States v. Michael Smith, Defendant.",
      "The defendant sent the files to other users via an encrypted channel.", "the defendant"),
     "the defendant"),
    ("generic-two", "actor",
     ("United States v. Michael Smith and Robert Porter, Defendants.",
      "The defendant sent the files to other users via an encrypted channel.", "the defendant"),
     "ambiguous"),
    ("no-caption", "actor",
     ("The files moved through an encrypted channel.",
      "The defendant sent the files to other users via an encrypted channel.", "the defendant"),
     "no_defendant_record"),
    ("defendant-smith-case", "actor",
     ("United States v. Michael Smith, Defendant.",
      "defendant smith sent the files to other users via an encrypted channel.", "defendant smith"),
     "the defendant"),
    ("hyphen", "locate",
     ("The defendant sent the files via a peer-to-\npeer channel.", "peer-to-peer"), True),
    ("hyphen-both", "locate",
     ("The defendant sent the files via a peer-to-\npeer-based channel.", "peer-to-peer-based"), True),
    ("page-two-surname", "case_actor",
     {"docs": [("sof", "statement_of_facts",
                ["United States v. Michael Smith, Defendant. The caption is here.",
                 "Smith sent the files to other users via an encrypted channel."])],
      "sentence": "Smith sent the files to other users via an encrypted channel.",
      "actor": "Smith"},
     {"spacy": "the defendant", "none": "no_parser"}),
    ("other-document-surname", "case_actor",
     {"docs": [("exhibit", "other", ["A photograph of a phone."]),
               ("sof", "statement_of_facts",
                ["United States v. Michael Smith, Defendant. Smith sent the files to other users via an encrypted channel."])],
      "sentence": "Smith sent the files to other users via an encrypted channel.",
      "actor": "Smith"},
     {"spacy": "the defendant", "none": "no_parser"}),
    ("et-al-first", "case",
     [("docket", "docket", ["USA v. Smith et al, Defendants."]),
      ("sof", "statement_of_facts",
       ["United States v. Michael Smith and Robert Porter, Defendants. The defendant sent the files."])],
     ("ambiguous", ["Smith", "Smith", "Porter"])),
    ("charging-preferred", "case",
     [("exhibit", "other", ["No caption on this cover page."]),
      ("indictment", "indictment", ["United States v. Michael Smith, Defendant."]),
      ("sof", "statement_of_facts",
       ["United States v. Michael Smith and Robert Porter, Defendants."])],
     ("one", ["Smith"])),
    ("booker-other-page", "case",
     [("sof", "statement_of_facts",
       ["United States v. Michael Smith, Defendant. The defendant sent the files.",
        "A middle page.",
        "See United States v. Booker, 543 U.S. 220 (2005)."])],
     ("one", ["Smith"])),
    ("agreeing-copies", "frame",
     (_page("The defendant sent the files to other users via an encrypted channel. "
            "The defendant sent the files to other users via an encrypted channel."),
      "The defendant sent the files to other users via an encrypted channel.",
      "The defendant"),
     "DISTRIBUTE_MATERIAL"),
    ("young-people-frame", "frame",
     (_page("Young people sent the files to other users via an encrypted channel.", "Robert Young"),
      "Young people sent the files to other users via an encrypted channel.", "Young"),
     {"spacy": "actor_rejected", "none": "no_parser"}),
]


def _outcome(found, reason):
    return reason or (found or {}).get("canonical")


_MODEL_XFAIL = {
    "long-texted": "en_core_web_sm 3.8.0 labels Long as advmod of texted, not nsubj",
    "long-repeatedly": "en_core_web_sm 3.8.0 labels Long as advmod of sent, not nsubj",
}


def _check(name, got, expected):
    want = _expect(expected)
    if got != want and name in _MODEL_XFAIL and _parser_up():
        pytest.xfail(f"{_MODEL_XFAIL[name]}; got {got}")
    assert got == want, name


@pytest.mark.parametrize("name,kind,payload,expected", PROBES, ids=[row[0] for row in PROBES])
def test_v2_caption_and_actor_regressions(name, kind, payload, expected, tmp_path, monkeypatch):
    if kind == "records":
        assert _surnames(payload) == expected
        if name == "alias-one":
            assert defendant_records_in(payload)[0]["aliases"] == ["Jay Sample"]
    elif kind == "subject":
        assert clause_subject(payload) == expected
    elif kind == "actor":
        caption, sentence, actor = payload
        records = defendant_records_in(caption)
        generic = "no_defendant_record" if not records else ("one" if len(records) == 1 else "ambiguous")
        found, reason = decide_actor(sentence, actor, records, generic=generic)
        _check(name, _outcome(found, reason), expected)
    elif kind == "locate":
        page, needle = payload
        assert bool(locate_span(page, needle)) is expected
    elif kind == "case":
        _store_docs(tmp_path, name.replace("-", "_"), payload)
        info = case_defendants(name.replace("-", "_"), tmp_path)
        status, surnames = expected
        assert info["generic"] == status
        assert [record["surname"] for record in info["records"]] == surnames
    elif kind == "case_actor":
        _store_docs(tmp_path, name.replace("-", "_"), payload["docs"])
        info = case_defendants(name.replace("-", "_"), tmp_path)
        found, reason = decide_actor(payload["sentence"], payload["actor"], info["records"], generic=info["generic"])
        _check(name, _outcome(found, reason), expected)
    elif kind == "frame":
        page, quote, actor = payload
        _clear(monkeypatch)
        monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
        _ask_frames(monkeypatch, [_plain_frame(quote, "DISTRIBUTE_MATERIAL", actor)])
        case = name.replace("-", "_")
        _store(tmp_path, case, page)
        from state_machines.coding.workflow import build_deny
        bundle, _, log = C.code_case(case, "coder_A", tmp_path, deny=build_deny(case, tmp_path))
        want = _expect(expected)
        if want == "DISTRIBUTE_MATERIAL":
            assert [event["action"] for event in bundle["events"]] == ["DISTRIBUTE_MATERIAL"]
            assert C.drops_from_log(log)["duplicate_sentence"] == 0
        else:
            assert bundle["events"] == []
            assert C.drops_from_log(log)[want] >= 1
    else:
        raise AssertionError(kind)
