"""A fictional coded case for the trajectory tests. Every word of page text is invented.

Shape of the fictional record:
  e01 contact in a public group -> e02 move to private messages -> e03 solicitation
  -> e04 victim blocks (response) -> e05 new account -> {e06 threat, e08 distribution} (unordered)
  e07 arrest interrupts e06. e06 rests on an indictment allegation only.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Dict, List, Tuple

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V

CASE = "fictional_case_001"

PAGES: Dict[Tuple[str, int], str] = {
    ("sof", 1): (
        "STATEMENT OF FACTS. In March 2024 the defendant first contacted Minor Victim 1 in a public group "
        "on a messaging application. After that first contact, the defendant told Minor Victim 1 to continue "
        "in private direct messages on the same application. In those private direct messages the defendant "
        "asked Minor Victim 1 to send sexually explicit images, and Minor Victim 1 sent two images."
    ),
    ("sof", 2): (
        "Minor Victim 1 then blocked the defendant's account. Within a day of being blocked, the defendant "
        "created a new account under a different name and contacted Minor Victim 1 again. Afterwards the "
        "defendant sent the images to at least three other users of the application."
    ),
    ("ind", 1): (
        "INDICTMENT. COUNT TWO. On or about April 2, 2024, the defendant threatened to send the images "
        "to the friends of Minor Victim 1 unless more images were produced."
    ),
    ("jdg", 1): (
        "JUDGMENT IN A CRIMINAL CASE. The defendant was arrested on April 3, 2024 and pleaded guilty to Count One."
    ),
}


def _passage(pid: str, doc: str, page: int, quote: str, status: str, reason: str = "") -> Tuple[dict, str]:
    start, end, q = E.locate(PAGES[(doc, page)], quote)
    p = {"passage_id": pid, "doc_id": doc, "pdf_page": page, "court_locator": None, "char_start": start,
         "char_end": end, "quote_sha256": E.sha256_text(q), "quote_word_count": len(q.split()),
         "source_status": status,
         "verification": {"status": "VERIFIED",
                          "method": "ocr_plus_page_image" if doc == "jdg" else "text_layer_exact", "checked_by": "coder_A"}}
    if reason:
        p["source_status_reason"] = reason
    return p, q


def _doc(doc_id: str, doc_type: str, n_pages: int, method: str = "text_layer") -> dict:
    return {"doc_id": doc_id, "doc_type": doc_type, "source_path": f"FICTIONAL/{CASE} -- {doc_type}.pdf",
            "sha256": E.sha256_text(doc_id + "-pdf"), "ecf_document_number": None, "filed_date": None,
            "page_count": n_pages,
            "pages": [{"pdf_page": i, "text_method": method, "page_text_sha256": E.sha256_text(E.normalize(PAGES[(doc_id, i)])),
                       "court_page_label": None, "ocr_engine": "tesseract 5" if method == "ocr" else None,
                       "ocr_mean_confidence": 91.0 if method == "ocr" else None, "image_checked": method == "ocr",
                       "limitations": []} for i in range(1, n_pages + 1)]}


def S(pid: str, facet: str = "action", status: str = "DIRECT") -> dict:
    return {"passage_id": pid, "facet": facet, "status": status}


ROLE = {"P1": "offender", "P2": "victim", "P3": "law_enforcement"}


def _when(day_or_month: str, pid: str, precision: str, expression: str, basis: str = "explicit_date",
          status: str = "DIRECT") -> dict:
    import calendar
    if precision == "month":
        y, m = map(int, day_or_month.split("-"))
        lo, hi = f"{day_or_month}-01", f"{day_or_month}-{calendar.monthrange(y, m)[1]:02d}"
    else:
        lo = hi = day_or_month
    return {"assertions": [{"expression": expression, "precision": precision, "earliest": lo, "latest": hi,
                            "basis": basis, "status": status, "passage_ids": [pid]}]}


def _event(eid, actor, action, desc, support, *, targets=(("P2", "victim"),), affordances=(), harms=(), time=None,
           status="DIRECT", outcome="completed") -> dict:
    return {"event_id": eid, "actor": {"participant_ref": actor, "role": ROLE[actor]}, "co_actors": [],
            "targets": [{"participant_ref": r, "role": role} for r, role in targets], "action": action,
            "outcome": outcome, "description": desc, "support": list(support), "status": status,
            "time": time or {"assertions": []},
            "repetition": {"kind": "single"}, "platform_mentions": [], "affordances": list(affordances),
            "candidate_affordances": [], "access": [], "harms": list(harms),
            "review": {"status": "single_coder", "coders": ["coder_A"]}}


def _aff(name, pid, basis="feature_stated", status="DIRECT", term="") -> dict:
    return {"affordance": name, "basis": basis, "feature_term": term or name, "platform_surface": "messaging application",
            "status": status, "support": [S(pid, "feature", status)]}


def _rel(rid, typ, a, b, support=(), basis="explicit_sequence_language", status="DIRECT") -> dict:
    return {"relation_id": rid, "type": typ, "from_event": a, "to_event": b, "basis": basis, "status": status,
            "support": list(support)}


def build() -> Tuple[dict, Dict[str, str]]:
    """(bundle, quotes) for the fictional case."""
    specs = [
        ("p01", "sof", 1, "the defendant first contacted Minor Victim 1 in a public group", "ADMITTED"),
        ("p02", "sof", 1, "told Minor Victim 1 to continue in private direct messages", "ADMITTED"),
        ("p03", "sof", 1, "asked Minor Victim 1 to send sexually explicit images, and Minor Victim 1 sent two images", "ADMITTED"),
        ("p04", "sof", 2, "Minor Victim 1 then blocked the defendant's account", "ADMITTED"),
        ("p05", "sof", 2, "created a new account under a different name and contacted Minor Victim 1 again", "ADMITTED"),
        ("p06", "ind", 1, "threatened to send the images to the friends of Minor Victim 1", "ALLEGATION"),
        ("p07", "jdg", 1, "The defendant was arrested on April 3, 2024", "COURT_RECORD"),
        ("p08", "sof", 2, "Afterwards the defendant sent the images to at least three other users", "ADMITTED"),
        ("p09", "sof", 1, "In March 2024", "ADMITTED"),
        ("p10", "ind", 1, "On or about April 2, 2024", "ALLEGATION"),
        ("p11", "sof", 1, "After that first contact", "ADMITTED"),
    ]
    passages, quotes = [], {}
    for pid, doc, page, quote, status in specs:
        p, q = _passage(pid, doc, page, quote, status)
        passages.append(p)
        quotes[pid] = q
    events = [
        _event("e01", "P1", "INITIATE_CONTACT", "Defendant first contacts the minor in a public group.", [S("p01")],
               affordances=[_aff("contact_discovery", "p01", term="public group")],
               time=_when("2024-03", "p09", "month", "March 2024")),
        _event("e02", "P1", "MOVE_CHANNEL", "Defendant moves the conversation to private direct messages.", [S("p02")],
               affordances=[_aff("unmonitored_communication", "p02", term="private direct messages")]),
        _event("e03", "P1", "SOLICIT_IMAGERY", "Defendant asks for explicit images; two are sent.", [S("p03")],
               harms=[{"harm": "HARM_COERCED_SELF_GENERATED_IMAGERY", "victim_ref": "P2", "victim_kind": "minor", "status": "DIRECT", "support": [S("p03")]}]),
        _event("e04", "P2", "RESP_BLOCK", "Minor blocks the defendant's account.", [S("p04")], targets=(("P1", "subject"),)),
        _event("e05", "P1", "RECREATE_ACCOUNT", "Defendant creates a new account and recontacts the minor.", [S("p05")],
               affordances=[_aff("anonymity", "p05", term="new account under a different name")]),
        _event("e06", "P1", "THREATEN_EXPOSURE", "Alleged threat to send the images to the minor's friends.", [S("p06")],
               harms=[{"harm": "HARM_EXPOSURE_THREAT", "victim_ref": "P2", "victim_kind": "minor", "status": "DIRECT", "support": [S("p06")]}],
               time=_when("2024-04-02", "p10", "day", "on or about April 2, 2024")),
        _event("e07", "P3", "LE_ARREST", "Defendant is arrested.", [S("p07")], targets=(("P1", "subject"),),
               time=_when("2024-04-03", "p07", "day", "April 3, 2024")),
        _event("e08", "P1", "DISTRIBUTE_MATERIAL", "Defendant sends the images to other users.", [S("p08")],
               affordances=[_aff("distribution_infrastructure", "p08", status="INFERRED", term="sent to other users")],
               harms=[{"harm": "HARM_DISTRIBUTION_RECIRCULATION", "victim_ref": "P2", "victim_kind": "minor", "status": "DIRECT", "support": [S("p08")]}]),
    ]
    events[7]["affordances"][0]["support"] = [S("p08", "feature", "INFERRED")]
    relations = [
        _rel("r01", "BEFORE", "e01", "e02", [S("p11", "time")]),
        _rel("r02", "BEFORE", "e02", "e03", [S("p03", "time", "INFERRED")], basis="coder_inference", status="INFERRED"),
        _rel("r03", "BEFORE", "e03", "e04", [S("p04", "time")]),
        _rel("r04", "MEETS", "e04", "e05", [S("p05", "time")]),
        _rel("r05", "RESPONDS_TO", "e05", "e04", [S("p05", "time")]),
        _rel("r06", "BEFORE", "e05", "e06", [S("p06", "time", "INFERRED")], basis="coder_inference", status="INFERRED"),
        _rel("r07", "BEFORE", "e05", "e08", [S("p08", "time")]),
        _rel("r08", "INTERRUPTS", "e07", "e06", [S("p07", "time", "INFERRED")], basis="coder_inference", status="INFERRED"),
    ]
    bundle = {
        "schema_version": V.SCHEMA_VERSION, "codebook_version": V.CODEBOOK_VERSION, "case_id": CASE,
        "coding": {"coder_id": "coder_A", "method": "human", "model": None, "coded_on": "2026-11-16", "blind_to": [], "note": "fictional"},
        "documents": [_doc("sof", "statement_of_facts", 2), _doc("ind", "indictment", 1), _doc("jdg", "judgment", 1, "ocr")],
        "passages": passages,
        "participants": [
            {"participant_ref": "P1", "kind": "person",
             "legal_status": [{"status": "charged_defendant", "support": [S("p06", "legal_status")]}]},
            {"participant_ref": "P2", "kind": "person", "age_band": "13-15",
             "legal_status": [{"status": "named_victim", "support": [S("p01", "legal_status")]}]},
            {"participant_ref": "P3", "kind": "person",
             "legal_status": [{"status": "law_enforcement", "support": [S("p07", "legal_status")]}]}],
        "events": events, "relations": relations,
        "tracks": [{"track_id": "v1", "kind": "victim", "anchor_ref": "P2", "event_ids": [e["event_id"] for e in events]}],
    }
    return bundle, quotes


def write_pages(root: Path) -> None:
    for (doc, page), text in PAGES.items():
        E.write_page(CASE, doc, page, text, root)


def fresh(tmp_path: Path) -> dict:
    write_pages(tmp_path)
    bundle, _ = build()
    return copy.deepcopy(bundle)


def codes(findings: List) -> List[str]:
    return sorted({f.code for f in findings if f.severity == "error"})


SYNTHESIS_DEFECT = "https://cacontology.projectvic.org/synthesis/shapes#ActionSemanticsShape"


def with_synthesis_fix(monkeypatch):
    """Simulate the proposed upstream fix (U3): ActionSemanticsShape no longer targets every
    uco-action:Action. Only for tests that check the full/partial logic itself; the
    published shape set is what validation_report uses everywhere else."""
    import rdflib
    from rdflib.namespace import SH
    from state_machines.graphs import shacl

    patched = rdflib.Graph()
    for t in shacl.shapes_graph():      # shapes_graph() is cached: never mutate it in place
        patched.add(t)
    patched.remove((rdflib.URIRef(SYNTHESIS_DEFECT), SH.targetClass, None))
    monkeypatch.setattr(shacl, "shapes_graph", lambda: patched)
