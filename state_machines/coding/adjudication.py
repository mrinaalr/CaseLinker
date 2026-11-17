"""Adjudication dossiers: every disagreement between two coders, enumerated in code.

    python -m state_machines.coding.adjudication <release> <case_id> [...]

Writes, per case, ``local/adjudication/<release>/<case>.dossier.json`` (internal: contains
quotes from the court record) listing every item a human must rule on:

  only_a / only_b        events one coder coded and the other did not match
  action_mismatch        matched events with different action codes
  status_mismatch        matched events with different assertion status
  actor_mismatch         matched events with different actor or actor role
  affordance_mismatch    matched events whose instrumental affordance sets differ
  harm_mismatch          matched events whose harm codes differ
  time_mismatch          matched events with different date intervals
  order_only_a/only_b    order relations between matched events asserted by one coder
  single_step            agreed trajectories of one step, with the evidence needed to say why
  possible_same_act      two agreed events with the same offender action and overlapping dates
                         that nothing links: one act told twice (add SAME_ACT), or two acts

Nothing here decides anything. Decisions are recorded separately (``decisions`` file) by a
named human reviewer; agent recommendations are labelled as such.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.trajectories.derive import derive, event_spans
from state_machines.coding.workflow import agreement

DATA = E.REPO_ROOT / "state_machines" / "data"
OUT = E.REPO_ROOT / "local" / "adjudication"


def _quotes(case_id: str, coder: str) -> Dict[str, str]:
    store = E.load_quotes(case_id)
    prefix = coder + ":"
    return {k[len(prefix):]: v for k, v in store.items() if k.startswith(prefix)}


def _cite(bundle: dict, quotes: Dict[str, str], pid: str) -> dict:
    p = next(p for p in bundle["passages"] if p["passage_id"] == pid)
    return {"passage_id": pid, "doc_id": p["doc_id"], "pdf_page": p["pdf_page"], "court_locator": p.get("court_locator"),
            "source_status": p["source_status"], "verification": p["verification"]["status"], "quote": quotes.get(pid, "")}


def _event_view(bundle: dict, quotes: Dict[str, str], e: dict) -> dict:
    pids = sorted({s["passage_id"] for s in e["support"]} | {p for a in e["time"]["assertions"] for p in a["passage_ids"]})
    return {
        "event_id": e["event_id"], "actor": f"{e['actor']['participant_ref']} ({e['actor']['role']})", "action": e["action"],
        "outcome": e["outcome"], "status": e["status"], "description": e["description"],
        "time": [{k: a.get(k) for k in ("earliest", "latest", "precision", "basis", "status")} for a in e["time"]["assertions"]],
        "affordances": sorted((a["affordance"], a["status"]) for a in e.get("affordances", [])),
        "harms": sorted((h["harm"], h["victim_ref"], h["status"]) for h in e.get("harms", [])),
        "platform_mentions": sorted(m["platform_surface"] for m in e.get("platform_mentions", [])),
        "tracks": sorted(t["track_id"] for t in bundle["tracks"] if e["event_id"] in t["event_ids"]),
        "notes": e.get("notes", ""),
        "passages": [_cite(bundle, quotes, pid) for pid in pids],
    }


def lookalikes(bundle: dict) -> List[tuple]:
    """Pairs of offender events with the same action and overlapping admitted dates that no
    relation joins. Often one act described in two documents (a finding and a sentencing memo)."""
    import itertools
    linked = {frozenset((r["from_event"], r["to_event"])) for r in bundle["relations"]}
    admitted = V.ADMISSIBLE["INFERRED"]
    out = []
    for a, b in itertools.combinations(sorted(bundle["events"], key=lambda e: e["event_id"]), 2):
        if a["action"] != b["action"] or V.FAMILY_OF[a["action"]] != "offender":
            continue
        if frozenset((a["event_id"], b["event_id"])) in linked:
            continue
        sa, sb = event_spans(a, admitted), event_spans(b, admitted)
        if any(x[0] <= y[1] and y[0] <= x[1] for x in sa for y in sb):
            out.append((a["event_id"], b["event_id"]))
    return out


def dossier(release: str, case_id: str) -> dict:
    base = DATA / release / "coded"
    a = json.loads((base / "coder_A" / f"{case_id}.json").read_text())
    b = json.loads((base / "coder_B" / f"{case_id}.json").read_text())
    core = json.loads((base / "agreed" / f"{case_id}.json").read_text())
    qa, qb = _quotes(case_id, "coder_A"), _quotes(case_id, "coder_B")
    agree = agreement(a, b)
    pairs = agree["pairs"]
    ea, eb = {e["event_id"]: e for e in a["events"]}, {e["event_id"]: e for e in b["events"]}

    items: List[dict] = []

    def add(kind: str, **data):
        items.append({"item_id": f"{case_id}.{kind}.{len([i for i in items if i['kind'] == kind]) + 1:03d}", "kind": kind, **data})

    matched_a, matched_b = {i for i, _ in pairs}, {j for _, j in pairs}
    for e in sorted(a["events"], key=lambda e: e["event_id"]):
        if e["event_id"] not in matched_a:
            add("only_a", coder_a=_event_view(a, qa, e))
    for e in sorted(b["events"], key=lambda e: e["event_id"]):
        if e["event_id"] not in matched_b:
            add("only_b", coder_b=_event_view(b, qb, e))
    for i, j in pairs:
        x, y = ea[i], eb[j]
        views = {"coder_a": _event_view(a, qa, x), "coder_b": _event_view(b, qb, y)}
        if x["action"] != y["action"]:
            add("action_mismatch", **views)
        if x["status"] != y["status"]:
            add("status_mismatch", **views)
        if x["actor"] != y["actor"]:
            add("actor_mismatch", **views)
        fa = {o["affordance"] for o in x.get("affordances", []) if o["status"] in ("DIRECT", "INFERRED")}
        fb = {o["affordance"] for o in y.get("affordances", []) if o["status"] in ("DIRECT", "INFERRED")}
        if fa != fb:
            add("affordance_mismatch", only_a=sorted(fa - fb), only_b=sorted(fb - fa), **views)
        if {h["harm"] for h in x.get("harms", [])} != {h["harm"] for h in y.get("harms", [])}:
            add("harm_mismatch", **views)
        ta = sorted((t["earliest"], t["latest"], t["status"]) for t in x["time"]["assertions"])
        tb = sorted((t["earliest"], t["latest"], t["status"]) for t in y["time"]["assertions"])
        if ta != tb:
            add("time_mismatch", **views)
    # three-level recoding: every event either coder tied to a platform or an affordance
    rev = {j: i for i, j in pairs}
    seen = set()
    for bundle, quotes, events, other in ((a, qa, ea, "a"), (b, qb, eb, "b")):
        for e in sorted(bundle["events"], key=lambda e: e["event_id"]):
            if not (e.get("platform_mentions") or e.get("affordances")):
                continue
            key = (e["event_id"], None) if other == "a" else (rev.get(e["event_id"]), e["event_id"])
            if other == "a":
                key = (e["event_id"], dict(pairs).get(e["event_id"]))
            if key in seen:
                continue
            seen.add(key)
            ia, ib = key
            add("platform_recode",
                coder_a=_event_view(a, qa, ea[ia]) if ia else None,
                coder_b=_event_view(b, qb, eb[ib]) if ib else None,
                question="For each platform: named only, or was the act carried out through it (platform_interactions)? "
                         "Is each affordance instrumental (level C: feature or mechanism stated and linked to the act)?")
    amap, bmap = dict(pairs), {j: i for i, j in pairs}
    order_a = {(r["from_event"], r["to_event"]): r for r in a["relations"] if r["type"] in V.ORDER_RELATIONS}
    order_b = {(bmap.get(r["from_event"]), bmap.get(r["to_event"])): r for r in b["relations"] if r["type"] in V.ORDER_RELATIONS}
    for (f, t), r in sorted(order_a.items()):
        if f in amap and t in amap and (f, t) not in order_b:
            add("order_only_a", relation=r, from_event=_event_view(a, qa, ea[f]), to_event=_event_view(a, qa, ea[t]),
                support=[_cite(a, qa, s["passage_id"]) for s in r["support"]])
    for (f, t), r in sorted(order_b.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if f and t and (f, t) not in order_a:
            add("order_only_b", relation=r, from_event=_event_view(a, qa, ea[f]), to_event=_event_view(a, qa, ea[t]),
                support=[_cite(b, qb, s["passage_id"]) for s in r["support"]])
    derived = derive(core, "INFERRED")
    core_events = {e["event_id"]: e for e in core["events"]}
    for t in derived["tracks"]:
        multi = {s["event_id"] for L in t["trajectories"] if len(L["steps"]) > 1 for s in L["steps"]}
        for L in t["trajectories"]:
            if len(L["steps"]) == 1:
                eid = L["steps"][0]["event_id"]
                partners = sorted({p for pair in t["unordered_pairs"] if eid in pair for p in pair if p != eid})
                add("single_step", track=t["track_id"], trajectory_id=L["trajectory_id"],
                    event=_event_view(core, qa, core_events[eid]),
                    unordered_with=[{"event_id": p, "action": core_events[p]["action"],
                                     "time": [{k: t.get(k) for k in ("earliest", "latest", "precision")} for t in core_events[p]["time"]["assertions"]],
                                     "in_multi_step_trajectory": p in multi} for p in partners],
                    coder_relations_touching=[r for r in a["relations"] + b["relations"]
                                              if eid in (r["from_event"], r["to_event"]) or amap.get(eid) in (r["from_event"], r["to_event"])][:12])
    for x, y in lookalikes(core):
        add("possible_same_act", reason=f"same action {core_events[x]['action']}, overlapping dates, no relation between them",
            event_a=_event_view(core, qa, core_events[x]), event_b=_event_view(core, qa, core_events[y]),
            question="The same act described twice (add SAME_ACT, INFERRED; keep both events), or two distinct acts?")
    counts: Dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {"case_id": case_id, "release": release, "counts": counts, "agreement": {k: v for k, v in agree.items() if k != "pairs"},
            "documents": [{"doc_id": d["doc_id"], "doc_type": d["doc_type"], "source_path": d["source_path"],
                           "page_count": d["page_count"]} for d in core["documents"]],
            "items": items}


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    release, cases = argv[0], argv[1:]
    out = OUT / release
    out.mkdir(parents=True, exist_ok=True)
    for c in cases:
        d = dossier(release, c)
        (out / f"{c}.dossier.json").write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(c, sum(d["counts"].values()), "items", d["counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
