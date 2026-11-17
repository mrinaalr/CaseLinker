"""Machine resolution of two codings, and the three release modes."""
from __future__ import annotations

import copy

import pytest

from state_machines.coding.resolve import align_participants, resolve
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
    assert all(r["review"]["status"] == "agreed" for r in out["relations"])
    F.write_pages(tmp_path)
    assert release_errors(out, text_root=tmp_path, mode="machine") == []
    assert any("not adjudicated" in p for p in release_errors(out, text_root=tmp_path, mode="adjudicated"))


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
