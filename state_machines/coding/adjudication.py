"""Adjudication: every open item in a case, decided by a named reviewer, applied in code.

    python -m state_machines.coding.adjudication dossier <release> <case_id> [...]
    python -m state_machines.coding.adjudication apply <release> <case_id> <decisions.json>

Inputs, all local (they hold coder text and court quotes):

    local/adjudication/<release>/coded/coder_A|coder_B/<case>.json   each coder's bundle (schema 2.0)
    local/adjudication/<release>/agreed/<case>.json                  the agreed core, frozen when the
                                                                     first dossier is written; "edit"
                                                                     decisions are made in this file
    local/adjudication/<release>/<case>.dossier.json                 the items, with quotes
    decisions.json                                                   exported from the packet

``apply`` rebuilds ``state_machines/data/<release>/cases/<case>.json`` from the frozen core and
the decisions, every time, so it can be rerun. It refuses while any item is undecided or
deferred, applies each decision, marks every event and relation ``adjudicated`` with the
reviewer's name, and validates the result.

Item kinds and the decisions each accepts (``OPTIONS``):

  only_a / only_b          an event only one coder coded
  action_mismatch          matched events with different action codes (not in the core)
  status_mismatch          matched events with different assertion status
  actor_mismatch           matched events with different actor or actor role
  affordance_mismatch      matched events whose instrumental affordances differ
  harm_mismatch            matched events whose harm codes differ
  time_mismatch            matched events with different dated assertions
  order_only_a/only_b      an order relation between matched events only one coder asserted
  platform_recode          an event either coder tied to a platform or an affordance
  single_step              an agreed trajectory of one step
  possible_same_act        same action, overlapping dates, nothing linking them
  unresolved_role          a participant in an event whose role the source leaves open
  single_coder_relation    a relation in the core that only one coder asserted

Coder A's ids, participants and passages are the core's own; coder B's passages are imported
under a ``b.`` prefix. Anything that needs coder B's participants is an ``edit``. Nothing here
decides anything: a decision exists only when a named reviewer records it.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.trajectories.derive import derive, event_spans
from state_machines.coding.workflow import agreement

DATA = E.REPO_ROOT / "state_machines" / "data"
OUT = E.REPO_ROOT / "local" / "adjudication"

_ROLE_OPTIONS = tuple(f"target:{r}" for r in V.TARGET_ROLES) + tuple(f"co_actor:{m}" for m in V.PARTICIPATION_MODES)
OPTIONS: Dict[str, Tuple[str, ...]] = {
    "only_a": ("include", "exclude"),
    "only_b": ("exclude", "edit"),
    "action_mismatch": ("coder_a", "coder_b", "exclude", "edit"),
    "status_mismatch": ("keep", "coder_a", "coder_b", "edit"),
    "actor_mismatch": ("keep", "edit"),
    "affordance_mismatch": ("keep", "coder_a", "coder_b", "edit"),
    "harm_mismatch": ("keep", "coder_a", "edit"),
    "time_mismatch": ("keep", "coder_b", "edit"),
    "order_only_a": ("include", "exclude"),
    "order_only_b": ("include", "exclude"),
    "platform_recode": ("keep", "edit"),
    "single_step": ("keep", "edit"),
    "possible_same_act": ("same_act", "distinct"),
    "unresolved_role": _ROLE_OPTIONS + ("not_involved", "edit"),
    "single_coder_relation": ("include", "exclude"),
}
KIND_ORDER = list(OPTIONS)
QUESTIONS = {
    "only_a": "Coder A coded this event; coder B did not. Include it (with coder A's relations to included events), or exclude it?",
    "only_b": "Coder B coded this event; coder A did not. Exclude it, or add it by hand to the agreed bundle (edit)?",
    "action_mismatch": "The coders chose different action codes, so the event is not in the agreed core. Include it with coder A's code, with coder B's code, exclude it, or edit?",
    "status_mismatch": "Different assertion status. Keep the weaker (as agreed), take coder A's, take coder B's, or edit?",
    "actor_mismatch": "Different actor or actor role. Keep coder A's, or edit?",
    "affordance_mismatch": "Different instrumental affordances (level C). Keep the intersection (as agreed), take coder A's, take coder B's, or edit?",
    "harm_mismatch": "Different harm codes. Keep the intersection (as agreed), take coder A's, or edit?",
    "time_mismatch": "Different dated assertions. Keep coder A's (as agreed), take coder B's, or edit?",
    "order_only_a": "Only coder A asserted this order. Include it, or exclude it?",
    "order_only_b": "Only coder B asserted this order. Include it, or exclude it?",
    "platform_recode": "For each platform: named only, or was the act carried out through it? Is each affordance instrumental (feature or mechanism stated and tied to the act)? Keep, or edit?",
    "single_step": "This agreed trajectory has one step. Is the act genuinely unordered with the others (keep), or does a passage order it (edit: add the relation)?",
    "possible_same_act": "The same act described twice (add SAME_ACT, INFERRED; both events kept), or two distinct acts?",
    "unresolved_role": "What does the source support about this participant's part in the act?",
    "single_coder_relation": "Only one coder asserted this relation. Include it, or exclude it?",
}


def _quotes(case_id: str, coder: str) -> Dict[str, str]:
    store = E.load_quotes(case_id)
    prefix = coder + ":"
    return {k[len(prefix):]: v for k, v in store.items() if k.startswith(prefix)}


def _cite(bundle: dict, quotes: Dict[str, str], pid: str) -> dict:
    p = next(p for p in bundle["passages"] if p["passage_id"] == pid)
    return {"passage_id": pid, "doc_id": p["doc_id"], "pdf_page": p["pdf_page"], "court_locator": p.get("court_locator"),
            "source_status": p["source_status"], "verification": p["verification"]["status"], "quote": quotes.get(pid, "")}


def _event_pids(e: dict) -> List[str]:
    groups = [e["support"], *[x["support"] for k in ("affordances", "candidate_affordances", "access", "harms",
                                                       "platform_interactions", "channels") for x in e.get(k, [])]]
    pids = {s["passage_id"] for g in groups for s in g}
    pids |= {pid for a in e["time"]["assertions"] for pid in a["passage_ids"]}
    pids |= {pid for m in e.get("platform_mentions", []) for pid in m["passage_ids"]}
    pids |= {pid for u in e.get("unresolved_participants", []) for pid in u["passage_ids"]}
    pids |= set((e.get("repetition") or {}).get("passage_ids", []))
    return sorted(pids)


def _event_view(bundle: dict, quotes: Dict[str, str], e: dict) -> dict:
    return {
        "event_id": e["event_id"], "actor": f"{e['actor']['participant_ref']} ({e['actor']['role']})", "action": e["action"],
        "co_actors": [f"{c['participant_ref']} ({c['role']}, {c['mode']})" for c in e.get("co_actors", [])],
        "targets": [f"{t['participant_ref']} ({t['role']})" for t in e.get("targets", [])],
        "unresolved": [f"{u['participant_ref']}: {u['note']}" for u in e.get("unresolved_participants", [])],
        "outcome": e["outcome"], "status": e["status"], "description": e["description"],
        "time": [{k: a.get(k) for k in ("expression", "earliest", "latest", "precision", "basis", "status")} for a in e["time"]["assertions"]],
        "affordances": sorted((a["affordance"], a["status"]) for a in e.get("affordances", [])),
        "harms": sorted((h["harm"], h["victim_ref"], h["status"]) for h in e.get("harms", [])),
        "platforms": sorted(f"{i['platform_key']} ({i['mode']})" for i in e.get("platform_interactions", [])),
        "platform_mentions": sorted(m["platform_surface"] for m in e.get("platform_mentions", [])),
        "tracks": sorted(t["track_id"] for t in bundle["tracks"] if e["event_id"] in t["event_ids"]),
        "notes": e.get("notes", ""),
        "passages": [_cite(bundle, quotes, pid) for pid in _event_pids(e)],
    }


def _relation_view(bundle: dict, quotes: Dict[str, str], r: dict) -> dict:
    return {"relation_id": r["relation_id"], "type": r["type"], "from": r["from_event"], "to": r["to_event"],
            "status": r["status"], "basis": r["basis"], "passages": [_cite(bundle, quotes, s["passage_id"]) for s in r["support"]]}


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


def _local(release: str) -> Path:
    return OUT / release


def load_inputs(release: str, case_id: str, *, refresh_core: bool = False) -> Tuple[dict, dict, dict]:
    """(coder A, coder B, frozen agreed core). The core is copied from the release on first use."""
    root = _local(release)
    a = json.loads((root / "coded" / "coder_A" / f"{case_id}.json").read_text(encoding="utf-8"))
    b = json.loads((root / "coded" / "coder_B" / f"{case_id}.json").read_text(encoding="utf-8"))
    frozen = root / "agreed" / f"{case_id}.json"
    if refresh_core or not frozen.is_file():
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_text((DATA / release / "cases" / f"{case_id}.json").read_text(encoding="utf-8"), encoding="utf-8")
    core = json.loads(frozen.read_text(encoding="utf-8"))
    return a, b, core


def items_for(case_id: str, a: dict, b: dict, core: dict, qa: Optional[Dict[str, str]] = None,
              qb: Optional[Dict[str, str]] = None) -> Tuple[List[dict], dict]:
    """Every open item for one case, each with its kind, references, question and options."""
    qa, qb = qa or {}, qb or {}
    agree = agreement(a, b)
    pairs = agree["pairs"]
    ea, eb = {e["event_id"]: e for e in a["events"]}, {e["event_id"]: e for e in b["events"]}
    core_events = {e["event_id"]: e for e in core["events"]}
    items: List[dict] = []

    def add(kind: str, ref: dict, **views):
        n = len([i for i in items if i["kind"] == kind]) + 1
        items.append({"item_id": f"{case_id}.{kind}.{n:03d}", "kind": kind, "ref": ref,
                      "question": QUESTIONS[kind], "options": list(OPTIONS[kind]), **views})

    matched_a, matched_b = {i for i, _ in pairs}, {j for _, j in pairs}
    for e in sorted(a["events"], key=lambda e: e["event_id"]):
        if e["event_id"] not in matched_a and e["event_id"] not in core_events:
            add("only_a", {"a": e["event_id"]}, coder_a=_event_view(a, qa, e))
    for e in sorted(b["events"], key=lambda e: e["event_id"]):
        if e["event_id"] not in matched_b:
            add("only_b", {"b": e["event_id"]}, coder_b=_event_view(b, qb, e))
    for ia, ib in pairs:
        x, y = ea[ia], eb[ib]
        views = {"coder_a": _event_view(a, qa, x), "coder_b": _event_view(b, qb, y)}
        if x["action"] != y["action"]:
            if ia not in core_events:
                add("action_mismatch", {"a": ia, "b": ib}, **views)
            continue                       # the event's other fields are decided with the action
        if ia not in core_events:
            continue
        if x["status"] != y["status"]:
            add("status_mismatch", {"a": ia, "b": ib}, **views)
        if x["actor"] != y["actor"]:
            add("actor_mismatch", {"a": ia, "b": ib}, **views)
        live = ("DIRECT", "INFERRED")
        if {o["affordance"] for o in x.get("affordances", []) if o["status"] in live} != \
                {o["affordance"] for o in y.get("affordances", []) if o["status"] in live}:
            add("affordance_mismatch", {"a": ia, "b": ib}, **views)
        if {h["harm"] for h in x.get("harms", [])} != {h["harm"] for h in y.get("harms", [])}:
            add("harm_mismatch", {"a": ia, "b": ib}, **views)
        ta = sorted((t["earliest"], t["latest"], t["status"]) for t in x["time"]["assertions"])
        tb = sorted((t["earliest"], t["latest"], t["status"]) for t in y["time"]["assertions"])
        if ta != tb:
            add("time_mismatch", {"a": ia, "b": ib}, **views)
    for e in sorted(core["events"], key=lambda e: e["event_id"]):
        if e.get("platform_interactions") or e.get("platform_mentions") or e.get("affordances"):
            other = dict(pairs).get(e["event_id"])
            add("platform_recode", {"event": e["event_id"]}, agreed=_event_view(core, qa, e),
                coder_b=_event_view(b, qb, eb[other]) if other else None)
    amap, bmap = dict(pairs), {j: i for i, j in pairs}
    order_a = {(r["from_event"], r["to_event"]): r for r in a["relations"] if r["type"] in V.ORDER_RELATIONS}
    order_b = {(bmap.get(r["from_event"]), bmap.get(r["to_event"])): r for r in b["relations"] if r["type"] in V.ORDER_RELATIONS}
    core_rel = {(r["from_event"], r["to_event"]) for r in core["relations"]}
    for (f, t), r in sorted(order_a.items()):
        if f in amap and t in amap and (f, t) not in order_b and (f, t) not in core_rel:
            add("order_only_a", {"relation": r["relation_id"]}, relation=_relation_view(a, qa, r),
                from_event=_event_view(a, qa, ea[f]), to_event=_event_view(a, qa, ea[t]))
    for (f, t), r in sorted(order_b.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if f and t and (f, t) not in order_a and (f, t) not in core_rel:
            add("order_only_b", {"relation": r["relation_id"], "from": f, "to": t}, relation=_relation_view(b, qb, r),
                from_event=_event_view(a, qa, ea[f]), to_event=_event_view(a, qa, ea[t]))
    for r in sorted(core["relations"], key=lambda r: r["relation_id"]):
        if (r.get("review") or {}).get("status") == "single_coder":
            add("single_coder_relation", {"relation": r["relation_id"]}, relation=_relation_view(core, qa, r))
    for e in sorted(core["events"], key=lambda e: e["event_id"]):
        for u in e.get("unresolved_participants", []):
            add("unresolved_role", {"event": e["event_id"], "participant": u["participant_ref"]}, agreed=_event_view(core, qa, e))
    derived = derive(core, "INFERRED")
    for t in derived["tracks"]:
        for L in t["trajectories"]:
            if len(L["steps"]) == 1:
                eid = L["steps"][0]["event_id"]
                partners = sorted({p for pair in t["unordered_pairs"] if eid in pair for p in pair if p != eid})
                add("single_step", {"event": eid, "track": t["track_id"]}, agreed=_event_view(core, qa, core_events[eid]),
                    unordered_with=[{"event_id": p, "action": core_events[p]["action"],
                                     "time": [{k: x.get(k) for k in ("earliest", "latest", "precision")} for x in core_events[p]["time"]["assertions"]]}
                                    for p in partners])
    for x, y in lookalikes(core):
        add("possible_same_act", {"x": x, "y": y},
            reason=f"same action {core_events[x]['action']}, overlapping dates, no relation between them",
            event_x=_event_view(core, qa, core_events[x]), event_y=_event_view(core, qa, core_events[y]))
    return items, agree


def dossier(release: str, case_id: str, *, refresh_core: bool = False) -> dict:
    a, b, core = load_inputs(release, case_id, refresh_core=refresh_core)
    items, agree = items_for(case_id, a, b, core, _quotes(case_id, "coder_A"), _quotes(case_id, "coder_B"))
    counts: Dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {"case_id": case_id, "release": release, "counts": counts,
            "agreement": {k: v for k, v in agree.items() if k != "pairs"},
            "documents": [{"doc_id": d["doc_id"], "doc_type": d["doc_type"], "source_path": d["source_path"],
                           "page_count": d["page_count"]} for d in core["documents"]],
            "items": items}


# --- applying decisions ----------------------------------------------------------------------

def _import_passages(core: dict, src: dict, pids, prefix: str) -> Dict[str, str]:
    """Copy passages from a coder bundle into the core; returns old id -> core id."""
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


def _remap(obj, mapping: Dict[str, str]):
    """Rewrite passage ids inside supports, time assertions and mentions."""
    if isinstance(obj, dict):
        o = {}
        for k, v in obj.items():
            if k == "passage_id" and v in mapping:
                o[k] = mapping[v]
            elif k == "passage_ids":
                o[k] = [mapping.get(x, x) for x in v]
            else:
                o[k] = _remap(v, mapping)
        return o
    if isinstance(obj, list):
        return [_remap(x, mapping) for x in obj]
    return obj


def _add_event_from_a(core: dict, a: dict, eid: str) -> None:
    e = next(x for x in a["events"] if x["event_id"] == eid)
    _import_passages(core, a, _event_pids(e), "")
    core["events"].append(copy.deepcopy(e))
    for t in a["tracks"]:
        if eid in t["event_ids"]:
            ct = next((x for x in core["tracks"] if x["track_id"] == t["track_id"]), None)
            if ct is None:
                core["tracks"].append(dict(copy.deepcopy(t), event_ids=[eid]))
            elif eid not in ct["event_ids"]:
                ct["event_ids"] = sorted(ct["event_ids"] + [eid])


def _add_relation(core: dict, src: dict, r: dict, *, prefix: str, ends: Tuple[str, str]) -> None:
    mapping = _import_passages(core, src, [s["passage_id"] for s in r["support"]], prefix)
    rid = prefix + r["relation_id"]
    if any(x["relation_id"] == rid for x in core["relations"]):
        return
    core["relations"].append(dict(_remap(copy.deepcopy(r), mapping), relation_id=rid, from_event=ends[0], to_event=ends[1]))


def apply_decisions(release: str, case_id: str, decisions: dict, *, a: Optional[dict] = None, b: Optional[dict] = None,
                    core: Optional[dict] = None, items: Optional[List[dict]] = None) -> Tuple[dict, List[str]]:
    """(adjudicated bundle, problems). Problems name undecided, deferred or invalid items; the
    bundle is only meaningful when there are none."""
    if core is None:
        a, b, core = load_inputs(release, case_id)
    if items is None:
        items, _ = items_for(case_id, a, b, core)
    reviewer = (decisions.get("reviewer") or "").strip()
    chosen = decisions.get("decisions", {})
    problems = [] if reviewer else ["decisions.json names no reviewer"]
    for it in items:
        d = (chosen.get(it["item_id"]) or {}).get("decision", "")
        if d not in it["options"]:
            problems.append(f"{it['item_id']}: " + ("deferred" if d == "defer" else f"no valid decision ({d or 'none'}; options: {', '.join(it['options'])})"))
    if problems:
        return core, problems

    out = copy.deepcopy(core)
    ea, eb = {e["event_id"]: e for e in a["events"]}, {e["event_id"]: e for e in b["events"]}
    ev = lambda eid: next(e for e in out["events"] if e["event_id"] == eid)   # noqa: E731
    included_a = set()
    for it in items:
        d, ref, kind = chosen[it["item_id"]]["decision"], it["ref"], it["kind"]
        if d in ("keep", "edit", "exclude", "distinct", "not_involved") and kind not in ("unresolved_role", "single_coder_relation"):
            continue
        if kind == "only_a" and d == "include":
            _add_event_from_a(out, a, ref["a"]); included_a.add(ref["a"])
        elif kind == "action_mismatch" and d in ("coder_a", "coder_b"):
            _add_event_from_a(out, a, ref["a"]); included_a.add(ref["a"])
            if d == "coder_b":
                ev(ref["a"])["action"] = eb[ref["b"]]["action"]
        elif kind == "status_mismatch":
            ev(ref["a"])["status"] = (ea[ref["a"]] if d == "coder_a" else eb[ref["b"]])["status"]
        elif kind == "affordance_mismatch":
            src, prefix = (a, "") if d == "coder_a" else (b, "b.")
            affs = copy.deepcopy((ea[ref["a"]] if d == "coder_a" else eb[ref["b"]]).get("affordances", []))
            mapping = _import_passages(out, src, sorted({s["passage_id"] for x in affs for s in x["support"]}), prefix)
            ev(ref["a"])["affordances"] = _remap(affs, mapping)
        elif kind == "harm_mismatch" and d == "coder_a":
            harms = copy.deepcopy(ea[ref["a"]].get("harms", []))
            _import_passages(out, a, sorted({s["passage_id"] for x in harms for s in x["support"]}), "")
            ev(ref["a"])["harms"] = harms
        elif kind == "time_mismatch" and d == "coder_b":
            t = copy.deepcopy(eb[ref["b"]]["time"])
            mapping = _import_passages(out, b, sorted({p for x in t["assertions"] for p in x["passage_ids"]}), "b.")
            ev(ref["a"])["time"] = _remap(t, mapping)
        elif kind == "order_only_a" and d == "include":
            r = next(x for x in a["relations"] if x["relation_id"] == ref["relation"])
            _add_relation(out, a, r, prefix="", ends=(r["from_event"], r["to_event"]))
        elif kind == "order_only_b" and d == "include":
            r = next(x for x in b["relations"] if x["relation_id"] == ref["relation"])
            _add_relation(out, b, r, prefix="b.", ends=(ref["from"], ref["to"]))
        elif kind == "possible_same_act" and d == "same_act":
            x, y = ev(ref["x"]), ev(ref["y"])
            sup = [{"passage_id": next(s["passage_id"] for s in e["support"] if s["facet"] == "action"),
                    "facet": "action", "status": "INFERRED"} for e in (x, y)]
            out["relations"].append({"relation_id": f"same-{ref['x']}-{ref['y']}", "type": "SAME_ACT",
                                     "from_event": ref["x"], "to_event": ref["y"], "basis": "coder_inference",
                                     "status": "INFERRED", "support": sup,
                                     "note": "possibly the same act described in two documents; both events kept"})
        elif kind == "unresolved_role" and d not in ("edit",):
            e, pref = ev(ref["event"]), ref["participant"]
            u = next(x for x in e["unresolved_participants"] if x["participant_ref"] == pref)
            e["unresolved_participants"] = [x for x in e["unresolved_participants"] if x is not u]
            where, _, value = d.partition(":")
            if where == "target":
                e.setdefault("targets", []).append({"participant_ref": pref, "role": value})
            elif where == "co_actor":
                e.setdefault("co_actors", []).append({"participant_ref": pref, "role": e["actor"]["role"], "mode": value})
        elif kind == "single_coder_relation" and d == "exclude":
            out["relations"] = [r for r in out["relations"] if r["relation_id"] != ref["relation"]]
    # coder A's relations between an included event and the rest of the core come with it
    if included_a:
        present = {e["event_id"] for e in out["events"]}
        for r in a["relations"]:
            if (r["from_event"] in included_a or r["to_event"] in included_a) and r["from_event"] in present and r["to_event"] in present:
                _add_relation(out, a, r, prefix="", ends=(r["from_event"], r["to_event"]))
    review = {"status": "adjudicated", "coders": ["coder_A", "coder_B"], "adjudicator": reviewer}
    for e in out["events"]:
        e["review"] = dict(review, note=e["review"].get("note", ""))
    for r in out["relations"]:
        r["review"] = dict(review)
    out["events"].sort(key=lambda e: e["event_id"])
    out["coding"]["note"] = (f"adjudicated by {reviewer} on {date.today().isoformat()} from the agreed core of two agent coders; "
                             f"{len(items)} items decided")[:300]
    return out, []


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    from state_machines.evidence.validate import release_errors
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dossier"); d.add_argument("release"); d.add_argument("cases", nargs="+")
    d.add_argument("--refresh-core", action="store_true", help="recopy the agreed core from the release (drops edits)")
    p = sub.add_parser("apply"); p.add_argument("release"); p.add_argument("case"); p.add_argument("decisions", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "dossier":
        out = _local(args.release)
        for c in args.cases:
            dz = dossier(args.release, c, refresh_core=args.refresh_core)
            (out / f"{c}.dossier.json").write_text(json.dumps(dz, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(c, sum(dz["counts"].values()), "items", dz["counts"])
        return 0
    bundle, problems = apply_decisions(args.release, args.case, json.loads(args.decisions.read_text(encoding="utf-8")))
    if problems:
        print(f"{args.case}: not applied, {len(problems)} items open:\n  " + "\n  ".join(problems[:40]), file=sys.stderr)
        return 1
    errors = release_errors(bundle, text_root=E.text_root(), deny_list=_deny(args.case))
    if errors:
        print(f"{args.case}: adjudicated bundle does not validate:\n  " + "\n  ".join(errors[:40]), file=sys.stderr)
        return 1
    (DATA / args.release / "cases" / f"{args.case}.json").write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{args.case}: adjudicated ({len(bundle['events'])} events, {len(bundle['relations'])} relations)")
    return 0


def _deny(case_id: str) -> List[str]:
    from state_machines.coding.workflow import deny_list
    return deny_list(case_id)


if __name__ == "__main__":
    sys.exit(main())
