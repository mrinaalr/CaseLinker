"""Machine resolution: two independent codings of a case become one bundle, with no human decisions.

    python -m state_machines.coding.resolve <coder_a.json> <coder_b.json> <out.json>

The rule, in full:

1. Events are matched across the coders by the overlap of the passages they cite
   (``workflow.match_events``), never by action code.
2. An event is published when both coders coded it with the same action code and the same
   actor. Participants are aligned across the two codings by the matched events they act in.
   A differing action code leaves the act out. (Candidate rule 2b, off by default: settle the
   code from the sentence's own words, ``cues.settle``; see ``cues`` for why it is not released.)
3. Its status is the weaker of the two. Affordances, candidate affordances, access and harms
   are kept only where both coders annotated them.
4. Dates keep every cited assertion of either coder (T1-T5). Assertions that do not overlap
   are kept and the event is flagged as a time conflict, so it gives no date order.
5. A relation is published when both coders asserted it between matched events. Rule 5c: the
   stated-order sentence rule (``enrich.stated_prior``) is then applied once more over the
   published acts (``restate_order``), because each coder could only link a sentence to acts in
   its own list. It links an act to the act its opening clause names, or to the act in the
   sentence just before it, and to nothing otherwise. Order the cited dates imply is derived
   later, whoever coded the dates.
6. Two published events with the same offender action and overlapping dates that nothing
   links are linked as possibly the same act (SAME_ACT, INFERRED). Both are kept (R05).
7. A participant whose role the source leaves open stays open.

Everything else (an event or relation only one coder coded, an action or actor the coders
disagree on, a harm or affordance only one coder found) is left out and counted in the
report. Every published event and relation carries ``review.status = agreed``: two coders
agreed, nobody adjudicated. Reliability is measured by ``workflow.agreement``; accuracy on
known truth by the synthetic benchmark (``state_machines/benchmark``).
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from state_machines.evidence import vocab as V
from state_machines.trajectories.derive import event_spans
from state_machines.coding.workflow import agreement
from state_machines.coding.cues import CUE_VERSION, settle

CODERS = ("coder_A", "coder_B")
RULE_VERSION = "resolve-1.1.0"
_RANK = {"DIRECT": 0, "INFERRED": 1, "UNSUPPORTED": 2, "CONTRADICTED": 3}


def _weaker(x: str, y: str) -> str:
    return x if _RANK[x] >= _RANK[y] else y


def align_participants(a: dict, b: dict, pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """Coder B participant ref -> coder A participant ref, by who acts in and is targeted by
    the matched events (greedy on co-occurrence, one to one, same kind only)."""
    ea, eb = {e["event_id"]: e for e in a["events"]}, {e["event_id"]: e for e in b["events"]}
    kind_a = {p["participant_ref"]: p["kind"] for p in a["participants"]}
    kind_b = {p["participant_ref"]: p["kind"] for p in b["participants"]}
    votes: Counter = Counter()
    for ia, ib in pairs:
        x, y = ea[ia], eb[ib]
        votes[(y["actor"]["participant_ref"], x["actor"]["participant_ref"])] += 3
        for role in V.TARGET_ROLES:
            tx = [t["participant_ref"] for t in x.get("targets", []) if t["role"] == role]
            ty = [t["participant_ref"] for t in y.get("targets", []) if t["role"] == role]
            for rb in ty:
                for ra in tx:
                    votes[(rb, ra)] += 2 if len(tx) == len(ty) == 1 else 1
        for cb in y.get("co_actors", []):
            for ca in x.get("co_actors", []):
                votes[(cb["participant_ref"], ca["participant_ref"])] += 1
    out, used = {}, set()
    for (rb, ra), _ in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0])):
        if rb in out or ra in used or kind_a.get(ra) != kind_b.get(rb):
            continue
        out[rb] = ra
        used.add(ra)
    return out


def _disjoint(x: dict, y: dict) -> bool:
    return x["latest"] < y["earliest"] or y["latest"] < x["earliest"]


def _import_passages(core: dict, src: dict, pids, prefix: str) -> Dict[str, str]:
    have = {p["passage_id"] for p in core["passages"]}
    by_id = {p["passage_id"]: p for p in src["passages"]}
    out = {}
    for pid in pids:
        new = prefix + pid
        if new not in have:
            core["passages"].append(dict(copy.deepcopy(by_id[pid]), passage_id=new))
            have.add(new)
        out[pid] = new
    return out


def lookalikes(bundle: dict) -> List[Tuple[str, str]]:
    """Offender events with the same action and overlapping admitted dates that no relation joins."""
    import itertools
    linked = {frozenset((r["from_event"], r["to_event"])) for r in bundle["relations"]}
    admitted = V.ADMISSIBLE["INFERRED"]
    out = []
    for x, y in itertools.combinations(sorted(bundle["events"], key=lambda e: e["event_id"]), 2):
        if x["action"] != y["action"] or V.FAMILY_OF[x["action"]] != "offender":
            continue
        if frozenset((x["event_id"], y["event_id"])) in linked:
            continue
        sx, sy = event_spans(x, admitted), event_spans(y, admitted)
        if any(p[0] <= q[1] and q[0] <= p[1] for p in sx for q in sy):
            out.append((x["event_id"], y["event_id"]))
    return out


def _sentence(bundle: dict, event: dict, text_root) -> str:
    """The cited sentence of an event's action, read from the page text store."""
    from state_machines.evidence import evidence as E
    from state_machines.coding.enrich import _HEADER
    P = {p["passage_id"]: p for p in bundle["passages"]}
    p = P[next(s["passage_id"] for s in event["support"] if s["facet"] == "action")]
    page = E.normalize(E.read_page(bundle["case_id"], p["doc_id"], p["pdf_page"], text_root) or "")
    return _HEADER.sub("", page[p["char_start"]:p["char_end"]]).strip()


def resolve(a: dict, b: dict, text_root=None, settle_codes: bool = False) -> Tuple[dict, dict]:
    """(bundle, report). The bundle is coder A's frame (ids, participants, passages) holding only
    what both coders coded; coder B's dated assertions are imported under a ``b.`` prefix.
    ``settle_codes`` turns on candidate rule 2b, which needs the page text (``text_root``)."""
    agree = agreement(a, b)
    pairs = agree["pairs"]
    pmap = align_participants(a, b, pairs)
    ea, eb = {e["event_id"]: e for e in a["events"]}, {e["event_id"]: e for e in b["events"]}
    report: Counter = Counter()
    matched_a, matched_b = {i for i, _ in pairs}, {j for _, j in pairs}
    for e in a["events"]:
        if e["event_id"] not in matched_a:
            report[f"left out: only coder A coded it ({V.FAMILY_OF[e['action']]})"] += 1
    for e in b["events"]:
        if e["event_id"] not in matched_b:
            report[f"left out: only coder B coded it ({V.FAMILY_OF[e['action']]})"] += 1

    core = copy.deepcopy(a)
    keep: Dict[str, dict] = {}
    for ia, ib in pairs:
        x, y = ea[ia], eb[ib]
        settled = None
        if x["action"] != y["action"]:
            same_actor = pmap.get(y["actor"]["participant_ref"]) == x["actor"]["participant_ref"]
            if settle_codes and text_root is not None and same_actor and V.FAMILY_OF[x["action"]] == V.FAMILY_OF[y["action"]]:
                settled = settle(_sentence(a, x, text_root), x["action"], y["action"])     # rule 2b
            if settled is None:
                report["left out: coders chose different action codes"] += 1
                continue
        if pmap.get(y["actor"]["participant_ref"]) != x["actor"]["participant_ref"]:
            report["left out: coders named different actors"] += 1
            continue
        e = copy.deepcopy(x)
        e["status"] = _weaker(x["status"], y["status"])
        yb = {o["affordance"]: o for o in y.get("affordances", [])}
        e["affordances"] = []
        for o in x.get("affordances", []):
            if o["affordance"] in yb:
                o = dict(copy.deepcopy(o), status=_weaker(o["status"], yb[o["affordance"]]["status"]))
                if o["status"] == "DIRECT" and not any(s["status"] == "DIRECT" and s["facet"] == "feature" for s in o["support"]):
                    o["status"] = "INFERRED"
                e["affordances"].append(o)
            else:
                report["left out: affordance only coder A annotated"] += 1
        report["left out: affordance only coder B annotated"] += len(set(yb) - {o["affordance"] for o in x.get("affordances", [])})
        yc = {c["candidate"] for c in y.get("candidate_affordances", [])}
        e["candidate_affordances"] = [c for c in x.get("candidate_affordances", []) if c["candidate"] in yc]
        yh = {h["harm"] for h in y.get("harms", [])}
        if settled is None:
            e["harms"] = [h for h in x.get("harms", []) if h["harm"] in yh]
            report["left out: harm only one coder recorded"] += len({h["harm"] for h in x.get("harms", [])} ^ yh)
        else:      # the harm follows from the action code (enrich.HARM_OF_ACTION): keep the settled code's
            e["action"] = settled
            e["description"] = e["description"].replace(x["action"].lower().replace("_", " "), settled.lower().replace("_", " "), 1)
            if settled == y["action"]:
                own = next(s["passage_id"] for s in x["support"] if s["facet"] == "action")
                e["harms"] = [dict(copy.deepcopy(h), victim_ref=pmap[h["victim_ref"]],
                                   support=[{"passage_id": own, "facet": "action", "status": h["status"]}])
                              for h in y.get("harms", []) if h["victim_ref"] in pmap]
            report["published: action code settled by cue rule (candidate 2b)"] += 1
        ya = {c["form"] for c in y.get("access", [])}
        e["access"] = [c for c in x.get("access", []) if c["form"] in ya]
        # T1-T5: every cited dated assertion of either coder is kept
        have = {(t["earliest"], t["latest"], t["basis"], t["status"]) for t in e["time"]["assertions"]}
        extra = [t for t in y["time"]["assertions"] if (t["earliest"], t["latest"], t["basis"], t["status"]) not in have]
        if extra:
            mapping = _import_passages(core, b, sorted({p for t in extra for p in t["passage_ids"]}), "b.")
            e["time"]["assertions"] += [dict(copy.deepcopy(t), passage_ids=[mapping[p] for p in t["passage_ids"]]) for t in extra]
            report["dates: coder B's cited assertions added"] += 1
        live = [t for t in e["time"]["assertions"] if t["status"] in ("DIRECT", "INFERRED")]
        if any(_disjoint(s, t) for i, s in enumerate(live) for t in live[i + 1:]):
            e["time"]["conflict_flagged"] = True
            report["dates: conflicting assertions kept and flagged"] += 1
        e["review"] = {"status": "agreed", "coders": list(CODERS), "adjudicator": None,
                       "note": f"coded by both coders; {RULE_VERSION}" if settled is None else
                       f"act and actor coded by both coders; action code settled by cue rule; {RULE_VERSION}, {CUE_VERSION}"}
        keep[ia] = e
    core["events"] = [keep[k] for k in sorted(keep)]
    report["published: events both coders coded"] = len(keep)

    a_to_b = dict(pairs)
    b_rel = {(r["type"], r["from_event"], r["to_event"]): r for r in b["relations"]}
    core["relations"] = []
    for r in a["relations"]:
        if r["from_event"] in keep and r["to_event"] in keep:
            other = b_rel.get((r["type"], a_to_b[r["from_event"]], a_to_b[r["to_event"]]))
            if other:
                core["relations"].append(dict(copy.deepcopy(r), status=_weaker(r["status"], other["status"]),
                                              review={"status": "agreed", "coders": list(CODERS), "adjudicator": None}))
            else:
                report["left out: relation only coder A asserted"] += 1
    report["published: relations both coders asserted"] = len(core["relations"])
    for x, y in lookalikes(core):
        sup = [{"passage_id": next(s["passage_id"] for s in ev["support"] if s["facet"] == "action"),
                "facet": "action", "status": "INFERRED"} for ev in (keep[x], keep[y])]
        core["relations"].append({"relation_id": f"same-{x}-{y}", "type": "SAME_ACT", "from_event": x, "to_event": y,
                                  "basis": "coder_inference", "status": "INFERRED", "support": sup,
                                  "note": "same action, overlapping dates: possibly one act told twice; both kept",
                                  "review": {"status": "agreed", "coders": list(CODERS), "adjudicator": None}})
        report["linked: possibly the same act (SAME_ACT)"] += 1
    report["open roles kept open"] = sum(len(e.get("unresolved_participants", [])) for e in core["events"])

    core["tracks"] = [dict(t, event_ids=[x for x in t["event_ids"] if x in keep]) for t in a["tracks"]]
    core["tracks"] = [t for t in core["tracks"] if t["event_ids"]]
    used = set()
    for e in core["events"]:
        for group in (e["support"], *[x["support"] for k in ("affordances", "candidate_affordances", "access", "harms",
                                                               "platform_interactions", "channels") for x in e.get(k, [])]):
            used |= {s["passage_id"] for s in group}
        used |= {p for t in e["time"]["assertions"] for p in t["passage_ids"]}
        used |= {p for m in e.get("platform_mentions", []) for p in m["passage_ids"]}
        used |= {p for u in e.get("unresolved_participants", []) for p in u["passage_ids"]}
        used |= set((e.get("repetition") or {}).get("passage_ids", []))
    used |= {s["passage_id"] for r in core["relations"] for s in r["support"]}
    for p in core["participants"]:
        used |= {s["passage_id"] for ls in p.get("legal_status", []) for s in ls["support"]}
        used |= {s["passage_id"] for s in (p.get("count") or {}).get("support", [])}
        used |= {s["passage_id"] for m in p.get("members", []) for s in m.get("support", [])}
    core["passages"] = [p for p in core["passages"] if p["passage_id"] in used]
    core["coding"] = dict(a["coding"], coder_id="coder_agreed",
                          note=f"machine resolution ({RULE_VERSION}) of two independent codings; not adjudicated")
    return core, {"rule": RULE_VERSION, "agreement": {k: v for k, v in agree.items() if k != "pairs"},
                  "participants_aligned": len(pmap), "counts": dict(sorted(report.items()))}


def restate_order(bundle: dict, text_root) -> int:
    """Rule 5c: apply the stated-order sentence rule (``enrich.stated_prior``) over the published acts.

    Each coder linked a sequence sentence to an act from its own list, often one the other coder
    did not code, so the relation was lost although both acts were agreed. The same deterministic
    rule runs here once on the resolved bundle, per document in reading order. It links a published
    act to the earlier published act its opening clause names ("After that first contact" -> the
    contact act) or to the act in the sentence immediately before it; where neither is published,
    it links nothing. Returns the number of relations added."""
    from state_machines.evidence import evidence as E
    from state_machines.coding.enrich import stated_prior
    P = {p["passage_id"]: p for p in bundle["passages"]}
    have = {(r["from_event"], r["to_event"]) for r in bundle["relations"] if r["type"] in V.ORDER_RELATIONS}
    by_doc: Dict[str, list] = {}
    for e in bundle["events"]:
        pid = next((s["passage_id"] for s in e["support"] if s["facet"] == "action"), None)
        if pid:
            by_doc.setdefault(P[pid]["doc_id"], []).append((P[pid]["pdf_page"], P[pid]["char_start"], P[pid]["char_end"], e, pid))
    added, pages = 0, {}
    for doc, acts in by_doc.items():
        acts.sort(key=lambda t: t[:3])
        for i, (page, start, end, e, pid) in enumerate(acts):
            if (doc, page) not in pages:
                pages[(doc, page)] = E.normalize(E.read_page(bundle["case_id"], doc, page, text_root) or "")
            earlier = [(x["event_id"], x["action"], e0, p0 == page) for p0, s0, e0, x, _ in acts[:i]
                       if p0 < page or e0 <= start]
            prior = stated_prior(pages[(doc, page)][start:end], start, earlier)
            if prior is None or (prior, e["event_id"]) in have or (e["event_id"], prior) in have:
                continue
            bundle["relations"].append({
                "relation_id": f"so-{prior}-{e['event_id']}", "type": "BEFORE", "from_event": prior, "to_event": e["event_id"],
                "basis": "explicit_sequence_language", "status": "DIRECT",
                "support": [{"passage_id": pid, "facet": "time", "status": "DIRECT"}],
                "note": "stated order, sentence rule applied to agreed acts",
                "review": {"status": "agreed", "coders": list(CODERS), "adjudicator": None}})
            have.add((prior, e["event_id"]))
            added += 1
    return added


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in argv[:2])
    bundle, report = resolve(a, b)
    Path(argv[2]).write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
