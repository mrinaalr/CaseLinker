"""Export contested acts and actors for a person to adjudicate.

Both resolution modes feed the same sheet: case id, passage id, the sentence
span, each coder's frame, and blank columns for the human decision. Nothing
here decides. A count taken from events a reviewer has already marked
``adjudicated`` is labelled ``adjudicated``. It is refused if a caller asks to
label that count ``machine``.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List, Optional, Sequence

from state_machines.coding.workflow import match_events

COLUMNS = (
    "case_id", "passage_id", "sentence_start", "sentence_end",
    "coder_a_frame", "coder_b_frame",
    "human_decision", "human_reason", "human_adjudicator",
)
_BLANK = {"human_decision": "", "human_reason": "", "human_adjudicator": ""}


def refuse_store(path: Path) -> None:
    """Refuse a path inside the committed release, the local store, or Oxigraph.

    The check looks at path parts only. It does not open the file.
    """
    parts = set(Path(path).resolve().parts)
    if {"state_machines", "data"} <= parts or "caselinker_oxigraph" in parts or "local" in parts:
        raise SystemExit(f"refusing to read or write {path}: that store is not for this command")


def _span(bundle: dict, event: dict):
    passages = {p["passage_id"]: p for p in bundle["passages"]}
    for support in event.get("support", []):
        if support.get("facet") == "action" and support.get("passage_id") in passages:
            p = passages[support["passage_id"]]
            return p["passage_id"], p.get("char_start"), p.get("char_end")
    return None, None, None


def _frame(event: dict, bundle: dict) -> dict:
    pid, start, end = _span(bundle, event)
    return {"event_id": event["event_id"], "action": event.get("action"),
            "actor": (event.get("actor") or {}).get("role"), "passage_id": pid,
            "sentence_start": start, "sentence_end": end}


def _row(case_id: str, passage_id, start, end, a_frame, b_frame) -> dict:
    return {"case_id": case_id, "passage_id": passage_id or "", "sentence_start": start if start is not None else "",
            "sentence_end": end if end is not None else "",
            "coder_a_frame": json.dumps(a_frame, sort_keys=True) if a_frame else "",
            "coder_b_frame": json.dumps(b_frame, sort_keys=True) if b_frame else "", **_BLANK}


def rows_from_intersection(case_id: str, a: dict, b: dict) -> List[dict]:
    """Contested events under intersection: only one coder, or different action or actor."""
    pairs = match_events(a, b)
    ea = {e["event_id"]: e for e in a["events"]}
    eb = {e["event_id"]: e for e in b["events"]}
    matched_a = {i for i, _ in pairs}
    matched_b = {j for _, j in pairs}
    rows = []
    for eid, event in ea.items():
        if eid in matched_a:
            continue
        pid, start, end = _span(a, event)
        rows.append(_row(case_id, pid, start, end, _frame(event, a), None))
    for eid, event in eb.items():
        if eid in matched_b:
            continue
        pid, start, end = _span(b, event)
        rows.append(_row(case_id, pid, start, end, None, _frame(event, b)))
    for ia, ib in pairs:
        x, y = ea[ia], eb[ib]
        same_action = x.get("action") == y.get("action")
        same_actor = (x.get("actor") or {}).get("role") == (y.get("actor") or {}).get("role")
        if same_action and same_actor:
            continue
        pid, start, end = _span(a, x)
        rows.append(_row(case_id, pid, start, end, _frame(x, a), _frame(y, b)))
    return rows


def rows_from_propose_verify(case_id: str, result: dict) -> List[dict]:
    """Rejected and corrected frames. Accepted frames are not contested."""
    rows = []
    for frame in list(result.get("rejected", [])) + list(result.get("corrected", [])):
        rows.append(_row(
            case_id, frame.get("passage_id"), frame.get("sentence_start"), frame.get("sentence_end"),
            {"frame_id": frame.get("frame_id"), "act": frame.get("act"), "actor": frame.get("actor"),
             "decision": frame.get("decision"), "reason_code": frame.get("reason_code")},
            None,
        ))
    return rows


def write_sheet(rows: Sequence[dict], dest: Path) -> tuple:
    """Write ``dest/disagreements.csv`` and ``dest/disagreements.jsonl``. Human columns stay blank."""
    refuse_store(dest)
    dest.mkdir(parents=True, exist_ok=True)
    csv_path, jsonl_path = dest / "disagreements.csv", dest / "disagreements.jsonl"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in COLUMNS})
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({k: row.get(k, "") for k in COLUMNS}, sort_keys=True) + "\n")
    return csv_path, jsonl_path


def count_label(events: Sequence[dict], requested: Optional[str] = None) -> str:
    """The label a published count must carry.

    Events whose review status is ``adjudicated`` are ``adjudicated``. Asking
    for ``machine`` on those events raises. Anything else stays the requested
    label, or ``machine`` when the caller does not name one.
    """
    statuses = {(e.get("review") or {}).get("status") for e in events}
    adjudicated = bool(events) and statuses <= {"adjudicated"}
    if adjudicated and requested == "machine":
        raise ValueError("published counts from adjudication are labelled adjudicated, never machine")
    if adjudicated:
        return "adjudicated"
    return requested or "machine"
