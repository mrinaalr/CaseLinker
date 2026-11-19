"""Public adjudication summary: court-record wording never survives redaction."""
from __future__ import annotations

import pytest

from state_machines.coding.adjudication_packet import NGRAM, _redact


def _grams(*quotes):
    from state_machines.coding.adjudication_packet import _WORD
    out = set()
    for q in quotes:
        w = [x.lower() for x in _WORD.findall(q)]
        out |= {tuple(w[i:i + NGRAM]) for i in range(len(w) - NGRAM + 1)}
    return out


def test_quoted_and_unquoted_reuse_of_record_wording_is_redacted():
    grams = _grams("the defendant asked the minor to keep sending pictures")
    text = "Coder B's reading: he 'asked the minor to keep sending pictures' after the call. It's B's view."
    out = _redact(text, grams)
    assert "keep sending pictures" not in out and "[quote]" in out
    # possessive apostrophes do not pair up into a quoted span; ordinary words survive
    assert out.startswith("Coder B's reading:") and out.endswith("It's B's view.")


def test_short_overlap_below_threshold_is_kept():
    grams = _grams("the defendant asked the minor to keep sending pictures")
    assert _redact("the minor said no", grams) == "the minor said no"


def test_lookalikes_flag_unlinked_retellings():
    """Same offender action, overlapping dates, nothing linking them: flagged for adjudication."""
    import copy
    from state_machines.coding.adjudication import lookalikes
    from tests.pacer import fixtures as F
    bundle, _ = F.build()
    assert lookalikes(bundle) == []
    twin = copy.deepcopy(next(e for e in bundle["events"] if e["event_id"] == "e06"))
    twin["event_id"] = "e09"
    bundle["events"].append(twin)
    assert lookalikes(bundle) == [("e06", "e09")]
    bundle["relations"].append(F._rel("r09", "SAME_ACT", "e06", "e09", [F.S("p06", "time", "INFERRED")],
                                      basis="coder_inference", status="INFERRED"))
    assert lookalikes(bundle) == []


def _two_coders():
    """Coder A is the fixture; coder B disagrees on several points in known ways."""
    import copy
    from tests.pacer import fixtures as F
    pytest.importorskip("case_uco")
    from state_machines.coding.release_report import agreed_core
    from state_machines.coding.workflow import agreement
    a, _ = F.build()
    b = copy.deepcopy(a)
    eb = {e["event_id"]: e for e in b["events"]}
    eb["e02"]["status"] = "INFERRED"                      # status mismatch on e02
    eb["e03"]["action"] = "DIRECT_CONDUCT"                # action mismatch: e03 leaves the core
    b["events"] = [e for e in b["events"] if e["event_id"] != "e08"]   # only coder A has e08
    b["relations"] = [r for r in b["relations"] if r["relation_id"] != "r01"]   # only coder A orders e01 < e02
    b["tracks"] = [dict(t, event_ids=[x for x in t["event_ids"] if x != "e08"]) for t in b["tracks"]]
    core = agreed_core(a, b, agreement(a, b)["pairs"])
    return a, b, core


def _decide(items, choice):
    return {"reviewer": "maintainer", "decisions": {i["item_id"]: {"decision": choice(i), "note": ""} for i in items}}


def test_apply_refuses_undecided_and_deferred_items():
    from state_machines.coding.adjudication import apply_decisions, items_for
    a, b, core = _two_coders()
    items, _ = items_for("fictional_case_001", a, b, core)
    kinds = {i["kind"] for i in items}
    assert {"only_a", "action_mismatch", "status_mismatch", "order_only_a"} <= kinds
    decisions = _decide(items, lambda i: i["options"][0])
    decisions["decisions"][items[0]["item_id"]]["decision"] = "defer"
    del decisions["decisions"][items[1]["item_id"]]
    _, problems = apply_decisions("r", "fictional_case_001", decisions, a=a, b=b, core=core, items=items)
    assert any("deferred" in p for p in problems) and any("no valid decision" in p for p in problems)
    _, problems = apply_decisions("r", "fictional_case_001", dict(decisions, reviewer=""), a=a, b=b, core=core, items=items)
    assert "decisions.json names no reviewer" in problems


def test_apply_makes_each_decision_and_the_result_releases(tmp_path):
    from tests.pacer import fixtures as F
    from state_machines.coding.adjudication import apply_decisions, items_for
    from state_machines.evidence.validate import release_errors
    a, b, core = _two_coders()
    assert {e["event_id"] for e in core["events"]} == {"e01", "e02", "e04", "e05", "e06", "e07"}
    items, _ = items_for("fictional_case_001", a, b, core)

    def choose(i):
        return {"only_a": "include", "action_mismatch": "coder_b", "status_mismatch": "coder_a",
                "order_only_a": "include"}.get(i["kind"], "keep" if "keep" in i["options"] else i["options"][0])

    out, problems = apply_decisions("r", "fictional_case_001", _decide(items, choose), a=a, b=b, core=core, items=items)
    assert problems == []
    events = {e["event_id"]: e for e in out["events"]}
    assert "e08" in events                                       # only_a included, with its passages
    assert events["e03"]["action"] == "DIRECT_CONDUCT"           # coder B's action code
    assert events["e02"]["status"] == "DIRECT"                   # coder A's status, not the weaker
    assert any(r["from_event"] == "e01" and r["to_event"] == "e02" and r["type"] == "BEFORE" for r in out["relations"])
    assert all(e["review"]["status"] == "adjudicated" and e["review"]["adjudicator"] == "maintainer" for e in out["events"])
    assert all(r["review"]["status"] == "adjudicated" for r in out["relations"])
    F.write_pages(tmp_path)
    assert release_errors(out, text_root=tmp_path) == []          # releasable without allow_unreviewed


def test_same_act_and_role_decisions():
    import copy
    from state_machines.coding.adjudication import apply_decisions, items_for
    a, b, core = _two_coders()
    for bundle in (a, b, core):                                   # e06 retold as e09 in every coding
        twin = copy.deepcopy(next(e for e in bundle["events"] if e["event_id"] == "e06"))
        twin["event_id"] = "e09"
        twin["unresolved_participants"] = [{"participant_ref": "P3", "note": "present; role not stated", "passage_ids": ["p06"]}]
        bundle["events"].append(twin)
        bundle["tracks"][0]["event_ids"].append("e09")
    items, _ = items_for("fictional_case_001", a, b, core)
    same = [i for i in items if i["kind"] == "possible_same_act"]
    role = [i for i in items if i["kind"] == "unresolved_role"]
    assert [i["ref"] for i in same] == [{"x": "e06", "y": "e09"}] and len(role) == 1

    def choose(i):
        return {"possible_same_act": "same_act", "unresolved_role": "target:subject"}.get(
            i["kind"], "keep" if "keep" in i["options"] else i["options"][-1] if i["kind"] == "only_a" else i["options"][0])

    out, problems = apply_decisions("r", "fictional_case_001", _decide(items, choose), a=a, b=b, core=core, items=items)
    assert problems == []
    assert any(r["type"] == "SAME_ACT" and r["status"] == "INFERRED" and {r["from_event"], r["to_event"]} == {"e06", "e09"}
               for r in out["relations"])
    e09 = next(e for e in out["events"] if e["event_id"] == "e09")
    assert e09["unresolved_participants"] == [] and {"participant_ref": "P3", "role": "subject"} in e09["targets"]
