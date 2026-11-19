"""Convert schema 1.x coded bundles to schema 2.0, mechanically, and list what needs a person.

What is mechanical:
  actors -> participants P1..Pn (role-neutral). The old ref is kept in the description
  ("coded as D1 in schema 1") so a reviewer can trace it. An undercover actor becomes a
  persona; a platform actor becomes an organization; everyone else a person.
  Each event's actor, co-actors and targets get the role the old actor table gave them;
  a target's role is victim when the old actor was a victim, counterparty when it was an
  undercover persona, subject otherwise.
  One time interval -> one dated assertion with real calendar bounds (precision kept).
  Harms take the old actor's victim kind.

What is NOT mechanical, and is listed in the report for adjudication:
  legal status (never inferred from a coded role), people who may hold different roles in
  different events (R04), groups that need a collective (R10), possible identity (R05),
  dates that came from an enclosing window (T2), and platform interactions (I1-I3).

    python -m state_machines.evidence.migrate <in.json> <out.json>
"""
from __future__ import annotations

import calendar
import copy
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from state_machines.evidence import vocab as V


def _bounds(value: str, end: bool) -> str:
    parts = value.split("-")
    y = int(parts[0])
    if len(parts) == 1:
        return f"{y}-12-31" if end else f"{y}-01-01"
    m = int(parts[1])
    if len(parts) == 2:
        return f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}" if end else f"{y}-{m:02d}-01"
    return value


def _time(old: dict) -> dict:
    lo, hi = old.get("earliest"), old.get("latest")
    if not (lo or hi) or not old.get("passage_ids"):
        return {"assertions": []}
    lo, hi = lo or hi, hi or lo
    precision = old.get("precision") if old.get("precision") in V.TIME_PRECISION else "range"
    basis = old.get("basis") if old.get("basis") in V.TIME_BASIS else "explicit_date"
    return {"assertions": [{"precision": precision, "earliest": _bounds(lo, False), "latest": _bounds(hi, True),
                            "basis": basis, "status": "DIRECT", "passage_ids": list(old["passage_ids"])}]}


def migrate(bundle: dict) -> Tuple[dict, List[str]]:
    if bundle.get("schema_version", "").startswith("2."):
        return copy.deepcopy(bundle), []
    b = copy.deepcopy(bundle)
    review: List[str] = []
    actors = {a["actor_ref"]: a for a in b.pop("actors")}
    refs: Dict[str, str] = {}
    participants = []
    for i, ref in enumerate(sorted(actors, key=lambda r: (r.rstrip("0123456789"), int("0" + r[len(r.rstrip("0123456789")):]))), 1):
        a, new = actors[ref], f"P{i}"
        refs[ref] = new
        kind = {"undercover": "persona", "platform": "organization"}.get(a["role"], "person")
        p = {"participant_ref": new, "kind": kind, "description": f"coded as {ref} ({a['role']}) in schema 1",
             "legal_status": []}
        if a.get("age_band") and kind == "person":
            p["age_band"] = a["age_band"]
        participants.append(p)
        review.append(f"{new} ({ref}): legal status not recorded; add it with a supporting passage")
    roles = {ref: a["role"] for ref, a in actors.items()}
    target_role = lambda ref: {"victim": "victim", "undercover": "counterparty"}.get(roles[ref], "subject")  # noqa: E731
    as_target: Dict[str, set] = {}
    for e in b["events"]:
        old_actor = e.pop("actor_ref")
        e["actor"] = {"participant_ref": refs[old_actor], "role": roles[old_actor]}
        e["co_actors"], e["targets"] = [], [{"participant_ref": refs[r], "role": target_role(r)} for r in e.pop("target_refs", [])]
        allowed = V.FAMILY_ROLES[V.FAMILY_OF[e["action"]]]
        for r in e.pop("co_actor_refs", []):
            if roles[r] in allowed:
                e["co_actors"].append({"participant_ref": refs[r], "role": roles[r], "mode": "assisting"})
            else:   # tied to the act by the record, but no role can be claimed without adjudication
                pids = sorted({s["passage_id"] for s in e["support"]})
                e.setdefault("unresolved_participants", []).append({
                    "participant_ref": refs[r], "passage_ids": pids,
                    "note": f"coded as co-actor {r} ({roles[r]}) of an {V.FAMILY_OF[e['action']]} action in schema 1"})
                review.append(f"{e['event_id']}: {refs[r]} ({r}, {roles[r]}) was a co-actor of an {V.FAMILY_OF[e['action']]} action; "
                              f"role unresolved; read passages {', '.join(pids)} and decide it (R04)")
        for r in [t["participant_ref"] for t in e["targets"]]:
            as_target.setdefault(r, set()).add(e["event_id"])
        e["time"] = _time(e["time"])
        if e["time"]["assertions"] and e["time"]["assertions"][0]["basis"] in ("count_window", "date_range"):
            review.append(f"{e['event_id']}: date basis {e['time']['assertions'][0]['basis']}; if it comes from an enclosing window, mark it enclosing_window and INFERRED (T2)")
        for h in e.get("harms", []):
            h["victim_kind"] = actors[h["victim_ref"]].get("victim_kind") or "unknown"
            h["victim_ref"] = refs[h["victim_ref"]]
            if h["victim_ref"] not in {t["participant_ref"] for t in e["targets"] if t["role"] == "victim"}:
                e["targets"].append({"participant_ref": h["victim_ref"], "role": "victim"})
        for a in e.get("access", []):
            a["target_ref"] = refs[a["target_ref"]]
        for i in e.get("platform_interactions", []):
            i.setdefault("platform_key", i["platform_surface"])
            i.setdefault("mode", "through")
            i.setdefault("audience", "unknown")
        if e.get("platform_mentions"):
            review.append(f"{e['event_id']}: platform mentioned; decide whether the act went through it (platform_interactions, mode, audience)")
    for t in b["tracks"]:
        if t.get("anchor_ref"):
            t["anchor_ref"] = refs[t["anchor_ref"]]
    for old, new in refs.items():
        acting_roles = {e["actor"]["role"] for e in b["events"] if e["actor"]["participant_ref"] == new}
        if roles[old] in ("offender", "co_offender") and new in as_target:
            review.append(f"{new} ({old}): coded as {roles[old]} and also a target of other acts; check each event's role (R04)")
    b["participants"] = participants
    b["schema_version"] = V.SCHEMA_VERSION
    b["codebook_version"] = V.CODEBOOK_VERSION
    b["notes"] = (b.get("notes", "") + f" Migrated mechanically from schema {bundle.get('schema_version')}.").strip()[:2000]
    return b, review


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    src, dst = Path(argv[0]), Path(argv[1])
    out, review = migrate(json.loads(src.read_text(encoding="utf-8")))
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{dst}: {len(review)} items need review")
    for line in review:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
