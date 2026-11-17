"""Public adjudication summary: court-record wording never survives redaction."""
from __future__ import annotations

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
