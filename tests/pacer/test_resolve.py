"""Machine resolution of two codings, and the three release modes."""
from __future__ import annotations

import copy

import pytest

from state_machines.coding.resolve import align_participants, resolve, restate_order
from state_machines.coding.workflow import agreement
from state_machines.evidence.validate import release_errors
from tests.pacer import fixtures as F


def _renumber(bundle: dict, mapping: dict) -> dict:
    """The same coding with participants numbered differently, as an independent coder would."""
    text = __import__("json").dumps(bundle)
    for old, new in mapping.items():
        text = text.replace(f'"{old}"', f'"__{new}"')
    return __import__("json").loads(text.replace('"__', '"'))


def _coders():
    a, _ = F.build()
    b = _renumber(copy.deepcopy(a), {"P1": "P3", "P2": "P1", "P3": "P2"})
    eb = {e["event_id"]: e for e in b["events"]}
    eb["e03"]["action"] = "DIRECT_CONDUCT"                                   # action disagreement
    b["events"] = [e for e in b["events"] if e["event_id"] != "e08"]       # only coder A has e08
    b["tracks"] = [dict(t, event_ids=[x for x in t["event_ids"] if x != "e08"]) for t in b["tracks"]]
    eb["e02"]["time"] = {"assertions": [{"expression": "late March 2024", "precision": "range", "earliest": "2024-03-20",
                                         "latest": "2024-03-31", "basis": "relative_statement", "status": "INFERRED",
                                         "passage_ids": ["p09"]}]}         # a date only coder B cites
    return a, b


def test_participants_are_aligned_across_numberings():
    a, b = _coders()
    pmap = align_participants(a, b, agreement(a, b)["pairs"])
    assert pmap == {"P3": "P1", "P1": "P2", "P2": "P3"}


def test_resolution_publishes_only_what_both_coders_coded(tmp_path):
    a, b = _coders()
    out, report = resolve(a, b)
    ids = {e["event_id"] for e in out["events"]}
    assert "e08" not in ids and "e03" not in ids                          # only one coder / different action
    assert {"e01", "e02", "e04", "e05", "e06", "e07"} <= ids               # renumbering is not a disagreement
    counts = report["counts"]
    assert counts["left out: only coder A coded it (offender)"] == 1
    assert counts["left out: coders chose different action codes"] == 1
    assert "left out: coders named different actors" not in counts
    e02 = next(e for e in out["events"] if e["event_id"] == "e02")
    assert any(t["basis"] == "relative_statement" for t in e02["time"]["assertions"])   # coder B's date kept
    assert all(e["review"]["status"] == "agreed" for e in out["events"])
    made = [r for r in out["relations"] if "made by the resolution rule" in r.get("note", "")]
    assert all(r["review"] == {"status": "rule_derived", "coders": [], "adjudicator": None} for r in made)     # no coder asserted these
    assert all(r["review"]["status"] == "agreed" and r["review"]["coders"] for r in out["relations"] if r not in made)
    # an affordance only one coder annotated on an act both coded is left out and counted
    a2, b2 = _coders()
    shared = next(e for e in a2["events"] if e["event_id"] in ids and e.get("affordances"))
    twin = next(e for e in b2["events"] if e["affordances"] and e["affordances"][0]["affordance"] == shared["affordances"][0]["affordance"]
                and e["action"] == shared["action"])
    twin["affordances"] = []
    out2, report2 = resolve(a2, b2)
    assert sum(len(e["affordances"]) for e in out2["events"]) == sum(len(e["affordances"]) for e in out["events"]) - 1
    assert report2["counts"]["left out: affordance only coder A annotated"] == counts.get("left out: affordance only coder A annotated", 0) + 1
    F.write_pages(tmp_path)
    assert release_errors(out, text_root=tmp_path, mode="machine") == []
    assert any("not adjudicated" in p for p in release_errors(out, text_root=tmp_path, mode="adjudicated"))
    # a relation the rule made is published by a machine release under its own status; an act can never carry that status
    ruled = copy.deepcopy(out)
    pair = [e["event_id"] for e in ruled["events"]][:2]
    ruled["relations"].append({"relation_id": "same-x", "type": "SAME_ACT", "from_event": pair[0], "to_event": pair[1], "basis": "coder_inference",
                               "status": "INFERRED", "support": [dict(s, status="INFERRED") for s in ruled["events"][0]["support"][:1]],
                               "note": "made by the resolution rule", "review": {"status": "rule_derived", "coders": [], "adjudicator": None}})
    assert not any("not adjudicated or agreed" in p for p in release_errors(ruled, text_root=tmp_path, mode="machine"))
    assert any("not adjudicated" in p for p in release_errors(ruled, text_root=tmp_path, mode="adjudicated"))
    ruled["events"][0]["review"] = {"status": "rule_derived", "coders": [], "adjudicator": None}
    assert any("not adjudicated or agreed" in p for p in release_errors(ruled, text_root=tmp_path, mode="machine"))


def test_actor_disagreement_and_date_conflict():
    a, b = _coders()
    eb = {e["event_id"]: e for e in b["events"]}
    eb["e05"]["actor"] = {"participant_ref": "P1", "role": "offender"}    # coder B: a different person (P2 in A)
    eb["e06"]["time"]["assertions"][0].update(earliest="2023-01-01", latest="2023-01-31")   # disjoint from A's date
    out, report = resolve(a, b)
    ids = {e["event_id"] for e in out["events"]}
    assert "e05" not in ids and report["counts"]["left out: coders named different actors"] == 1
    e06 = next(e for e in out["events"] if e["event_id"] == "e06")
    assert e06["time"]["conflict_flagged"] is True and len(e06["time"]["assertions"]) == 2


def test_candidate_rule_settles_a_differing_code_only_from_the_sentence_and_only_when_asked(tmp_path):
    F.write_pages(tmp_path)
    a, b = _coders()                                       # coder B coded e03 DIRECT_CONDUCT; the sentence says "asked ... to send ... images"
    out, report = resolve(a, b, tmp_path)                  # off by default: a machine release holds only agreed codes
    assert "e03" not in {e["event_id"] for e in out["events"]} and report["counts"]["left out: coders chose different action codes"] == 1
    out, report = resolve(a, b, tmp_path, settle_codes=True)
    e03 = next(e for e in out["events"] if e["event_id"] == "e03")
    assert e03["action"] == "SOLICIT_IMAGERY" and "settled by cue rule" in e03["review"]["note"]
    assert report["counts"]["published: action code settled by cue rule (candidate 2b)"] == 1
    assert "left out: coders chose different action codes" not in report["counts"]
    assert release_errors(out, text_root=tmp_path, mode="machine") == []
    # the other way round: coder A has the code the sentence does not support
    a, b = _coders()
    next(e for e in a["events"] if e["event_id"] == "e03")["action"] = "DIRECT_CONDUCT"
    next(e for e in b["events"] if e["event_id"] == "e03")["action"] = "SOLICIT_IMAGERY"
    out, _ = resolve(a, b, tmp_path, settle_codes=True)
    e03 = next(e for e in out["events"] if e["event_id"] == "e03")
    assert e03["action"] == "SOLICIT_IMAGERY" and [h["victim_ref"] for h in e03["harms"]] == ["P2"]   # in coder A's frame
    assert release_errors(out, text_root=tmp_path, mode="machine") == []
    # a sentence with no cue for either code, or a different actor, stays out
    a, b = _coders()
    next(e for e in a["events"] if e["event_id"] == "e03")["action"] = "BUILD_RAPPORT"
    out, report = resolve(a, b, tmp_path, settle_codes=True)
    assert "e03" not in {e["event_id"] for e in out["events"]}
    a, b = _coders()
    next(e for e in b["events"] if e["event_id"] == "e03")["actor"] = {"participant_ref": "P1", "role": "offender"}
    out, report = resolve(a, b, tmp_path, settle_codes=True)
    assert "e03" not in {e["event_id"] for e in out["events"]}


def test_stated_order_is_restated_on_agreed_acts_and_never_guessed(tmp_path):
    F.write_pages(tmp_path)
    a, b = _coders()
    for bundle in (a, b):                                  # whole sentences, as the automated coder cites them
        for p in bundle["passages"]:
            page = F.PAGES[(p["doc_id"], p["pdf_page"])]
            if p["passage_id"] == "p02":
                p["char_start"] = page.index("After that first contact")
            if p["passage_id"] == "p05":
                p["char_start"] = page.index("Within a day of being blocked")
        bundle["relations"] = []
    out, _ = resolve(a, b)
    assert restate_order(out, tmp_path) == 2
    assert sorted((r["from_event"], r["to_event"], r["basis"]) for r in out["relations"] if r["type"] == "BEFORE") == [
        ("e01", "e02", "explicit_sequence_language"),     # "After that first contact" names the contact act
        ("e04", "e05", "explicit_sequence_language")]     # "Within a day ..." follows the sentence just before it
    # the named act is not published: nothing is linked to it, and the nearest earlier act is not a stand-in
    a2, b2 = copy.deepcopy(a), copy.deepcopy(b)
    for bundle in (a2, b2):
        next(e for e in bundle["events"] if e["event_id"] == "e01")["action"] = "SEEK_TARGETS"
    out, _ = resolve(a2, b2)
    assert restate_order(out, tmp_path) == 1
    assert [(r["from_event"], r["to_event"]) for r in out["relations"] if r["type"] == "BEFORE"] == [("e04", "e05")]


def test_possible_retellings_are_linked_not_merged():
    a, b = _coders()
    for bundle in (a, b):
        twin = copy.deepcopy(next(e for e in bundle["events"] if e["event_id"] == "e06"))
        twin["event_id"] = "e09"
        twin["support"] = [dict(s, passage_id="p10") for s in twin["support"]]
        bundle["events"].append(twin)
        bundle["tracks"][0]["event_ids"].append("e09")
    out, report = resolve(a, b)
    assert {"e06", "e09"} <= {e["event_id"] for e in out["events"]}
    same = [r for r in out["relations"] if r["type"] == "SAME_ACT"]
    assert len(same) == 1 and same[0]["status"] == "INFERRED"
    assert report["counts"]["linked: possibly the same act (SAME_ACT)"] == 1


@pytest.mark.parametrize("mode,review,open_role,ok", [
    ("adjudicated", "adjudicated", False, True),
    ("adjudicated", "agreed", False, False),
    ("adjudicated", "adjudicated", True, False),
    ("machine", "agreed", True, True),
    ("machine", "single_coder", False, False),
    ("preview", "single_coder", True, True),
])
def test_release_modes(mode, review, open_role, ok, tmp_path):
    b, _ = F.build()
    for e in b["events"]:
        e["review"] = {"status": review, "coders": ["coder_A", "coder_B"], "adjudicator": "x" if review == "adjudicated" else None}
    if open_role:
        b["events"][0]["unresolved_participants"] = [{"participant_ref": "P3", "note": "present; role not stated", "passage_ids": ["p01"]}]
    F.write_pages(tmp_path)
    assert (release_errors(b, text_root=tmp_path, mode=mode) == []) is ok
