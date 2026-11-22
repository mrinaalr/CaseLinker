"""Propose-then-verify resolution, selected by setting ``CASELINKER_ACT_POLICY``.

``CASELINKER_ACT_POLICY=propose-verify-1.0`` selects it. The default is
``intersection-1.0``, and ``pipeline.resolve_cases`` then calls
``coding.resolve.resolve``. That function is not modified.

Coder 1 proposes frames. Coder 2 accepts a frame, rejects it with a reason
code, or corrects one slot. A third pass looks only at sentences neither coder
framed where the caller says the means rule fired, and may recover an act.
Every published act records ``produced_by`` as this mode. Recovered and
corrected acts are machine products, not adjudicated ones.
"""
from __future__ import annotations

import os
from typing import Callable, Iterable, List, Optional, Sequence

POLICY_ID = "propose-verify-1.0"
INTERSECTION_ID = "intersection-1.0"
REASON_CODES = (
    "not_an_act", "wrong_actor", "wrong_action", "wrong_span", "wrong_means",
    "slot_correction", "missed_act", "not_reviewed",
)


def selected_policy() -> str:
    return os.environ.get("CASELINKER_ACT_POLICY", INTERSECTION_ID)


def _stamp(frame: dict, decision: str, reason_code: str) -> dict:
    out = dict(frame)
    out["decision"] = decision
    out["reason_code"] = reason_code
    out["produced_by"] = POLICY_ID
    out["review"] = {"status": "machine", "label": "machine"}
    return out


def propose_verify(proposals: Sequence[dict], reviews: Sequence[dict], *,
                   missed: Sequence[dict] = (), means_sentence_ids: Iterable[str] = (),
                   recover: Optional[Callable] = None) -> dict:
    """Apply coder 2's reviews to coder 1's frames, then the missed-act pass.

    ``reviews`` are dicts with ``frame_id``, ``decision`` (``accept``, ``reject``
    or ``correct``), a ``reason_code`` for a rejection or a correction, and for
    a correction the ``slot`` name and the ``corrected`` slot value.
    ``recover(sentence)`` returns frames for a sentence neither coder framed.
    It is called only for sentence ids in ``means_sentence_ids``.
    """
    by_id = {r["frame_id"]: r for r in reviews}
    published: List[dict] = []
    rejected: List[dict] = []
    corrected: List[dict] = []
    for frame in proposals:
        review = by_id.get(frame["frame_id"])
        if review is None:
            rejected.append(_stamp(frame, "reject", "not_reviewed"))
            continue
        decision = review["decision"]
        if decision == "accept":
            published.append(_stamp(frame, "accept", review.get("reason_code") or ""))
        elif decision == "reject":
            if review.get("reason_code") not in REASON_CODES:
                raise ValueError("a rejection needs a reason code")
            rejected.append(_stamp(frame, "reject", review["reason_code"]))
        elif decision == "correct":
            if review.get("reason_code") not in REASON_CODES or "slot" not in review or "corrected" not in review:
                raise ValueError("a correction needs a reason code and the corrected slot")
            updated = dict(frame)
            updated[review["slot"]] = review["corrected"]
            stamped = _stamp(updated, "correct", review["reason_code"])
            corrected.append(stamped)
            published.append(stamped)
        else:
            raise ValueError(f"unknown decision {decision}")
    recovered: List[dict] = []
    if recover is not None:
        covered = {f.get("sentence_id") for f in proposals}
        wanted = set(means_sentence_ids)
        for sent in missed:
            sid = sent["sentence_id"]
            if sid in covered or sid not in wanted:
                continue
            for frame in recover(sent):
                item = _stamp(dict(frame, sentence_id=sid), "recovered", "missed_act")
                recovered.append(item)
                published.append(item)
    return {"act_policy": POLICY_ID, "published": published, "rejected": rejected,
            "corrected": corrected, "recovered": recovered}


def _span(bundle: dict, event: dict):
    passages = {p["passage_id"]: p for p in bundle["passages"]}
    for support in event["support"]:
        if support["facet"] == "action" and support["passage_id"] in passages:
            p = passages[support["passage_id"]]
            return p["passage_id"], p["char_start"], p["char_end"]
    return None


def _missed_on_pages(pages: Sequence[str], covered: Sequence[tuple]) -> tuple:
    """Sentences the means rule ties and neither coder framed."""
    from state_machines.coding.cues import CUES
    from state_machines.evidence import vocab as V
    from state_machines.observations.observe import _means, features_in, sentences
    missed, means_ids = [], []
    earlier = ""
    for page in pages:
        for start, end in sentences(page):
            if any(s < end and start < e for _pid, s, e in covered):
                continue
            sentence = page[start:end]
            if not any(_means("feature", sentence, {"feature_term": phrase}) for _cls, phrase, _a, _b in features_in(sentence)):
                continue
            sid = f"page:{start}:{end}"
            codes = sorted(c for c in CUES if V.FAMILY_OF.get(c) == "offender" and CUES[c].search(sentence))
            means_ids.append(sid)
            missed.append({"sentence_id": sid, "text": sentence, "codes": codes,
                           "prior": earlier + page[:start]})
        earlier += page + "\n"
    return missed, means_ids


def from_bundles(a: dict, b: dict, pages: Optional[Sequence[str]] = None,
                 case_id: Optional[str] = None, text_root=None) -> dict:
    """Run propose-then-verify on two coder bundles.

    Coder 1's events are the proposals. Coder 2 accepts an overlapping sentence
    with the same action and the same actor role, corrects the action when the
    sentence overlaps and the action differs, and a proposal with no overlap
    is rejected. When ``pages`` is given, a sentence neither coder framed where
    the means rule fires is recovered. ``pipeline.resolve_cases`` passes the
    pages. Without them the missed-act pass does not run.
    """
    proposals = []
    for event in a["events"]:
        span = _span(a, event)
        if span is None:
            continue
        pid, start, end = span
        proposals.append({
            "frame_id": event["event_id"],
            "sentence_id": f"{pid}:{start}:{end}",
            "passage_id": pid,
            "sentence_start": start,
            "sentence_end": end,
            "act": {"code": event["action"]},
            "actor": {"id": event["actor"]["role"], "participant": event["actor"].get("participant_ref")},
        })
    b_events = []
    for event in b["events"]:
        span = _span(b, event)
        if span is None:
            continue
        pid, start, end = span
        b_events.append((pid, start, end, event))
    reviews = []
    for frame in proposals:
        overlap = [e for (pid, start, end, e) in b_events
                   if pid == frame["passage_id"] and start < frame["sentence_end"] and frame["sentence_start"] < end]
        if not overlap:
            reviews.append({"frame_id": frame["frame_id"], "decision": "reject", "reason_code": "not_an_act"})
            continue
        other = overlap[0]
        same_who = other["actor"].get("participant_ref") == frame["actor"].get("participant")
        if frame["actor"].get("participant") and not same_who:
            reviews.append({"frame_id": frame["frame_id"], "decision": "reject", "reason_code": "wrong_actor"})
        elif other["actor"]["role"] != frame["actor"]["id"]:
            reviews.append({"frame_id": frame["frame_id"], "decision": "reject", "reason_code": "wrong_actor"})
        elif other["action"] != frame["act"]["code"]:
            reviews.append({"frame_id": frame["frame_id"], "decision": "correct", "reason_code": "slot_correction",
                            "slot": "act", "corrected": {"code": other["action"]}})
        else:
            reviews.append({"frame_id": frame["frame_id"], "decision": "accept"})
    if not pages:
        return propose_verify(proposals, reviews)
    covered = [(f["passage_id"], f["sentence_start"], f["sentence_end"]) for f in proposals]
    covered += [(pid, start, end) for pid, start, end, _event in b_events]
    missed, means_ids = _missed_on_pages(pages, covered)

    from state_machines.coding.workflow import case_defendants, clause_subject, decide_actor
    if case_id is not None and text_root is not None:
        info = case_defendants(case_id, text_root)
    else:
        info = {"records": [], "generic": "no_defendant_record"}
    records = info["records"]
    generic = info["generic"]

    def recover(sent):
        text = sent.get("text") or ""
        found, reason = decide_actor(text, clause_subject(text), records, generic=generic)
        if reason or not found or "canonical" not in found:
            return []
        return [{"frame_id": f"recovered:{sent['sentence_id']}:{code}", "act": {"code": code},
                 "actor": {"id": "defendant", "text": found["canonical"]}} for code in sent.get("codes") or []]

    return propose_verify(proposals, reviews, missed=missed, means_sentence_ids=means_ids, recover=recover)


