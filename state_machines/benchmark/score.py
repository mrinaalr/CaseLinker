"""Score coded bundles against the synthetic gold.

    python -m state_machines.benchmark.score <coded_dir> [--split dev|heldout|all] [--json out.json]

``coded_dir`` holds ``<case_id>.json`` bundles (a coder's output, or a resolved bundle). Events are
matched to gold events by the overlap of the passages they cite (``workflow.match_events``),
participants by the matched events they act in (``resolve.align_participants``). Reported:

    events        recall (gold acts found), precision (coded acts that are gold acts), F1
    action        share of matched acts with the gold action code
    actor         share of matched acts whose actor is the gold actor (after alignment)
    standing      share of matched acts whose cited passage has the gold legal standing
    dates         share of dated gold acts whose coded dates include the gold date exactly
    order         recall and precision of gold BEFORE/MEETS relations between matched acts
    level_c       recall and precision of gold level-C affordances on matched acts
    harms         recall and precision of gold H0 harms on matched acts
    same_act      share of gold SAME_ACT pairs the coded bundle links
    by_tag        recall of gold acts per hard-case tag (explicit_order, retelling, allegation_only, ...)

Every rate comes with its numerator and denominator. Nothing here is a claim about real cases.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.evidence import vocab as V
from state_machines.coding.resolve import align_participants
from state_machines.coding.workflow import match_events

DATA = Path(__file__).resolve().parent / "data"


def _rate(n: int, d: int) -> dict:
    return {"rate": round(n / d, 3) if d else None, "n": n, "of": d}


def _passage_standing(bundle: dict, e: dict) -> Optional[str]:
    P = {p["passage_id"]: p for p in bundle["passages"]}
    st = [P[s["passage_id"]]["source_status"] for s in e["support"] if s["facet"] == "action" and s["passage_id"] in P]
    return st[0] if st else None


def score_case(gold: dict, coded: dict) -> Counter:
    c: Counter = Counter()
    pairs = match_events(gold, coded)
    pmap = {v: k for k, v in align_participants(gold, coded, pairs).items()}   # gold ref -> coded ref
    eg, ec = {e["event_id"]: e for e in gold["events"]}, {e["event_id"]: e for e in coded["events"]}
    g2c = dict(pairs)
    c["gold_events"] += len(eg)
    c["coded_events"] += len(ec)
    c["matched"] += len(pairs)
    for ig, ic in pairs:
        g, k = eg[ig], ec[ic]
        c["action_ok"] += g["action"] == k["action"]
        c["actor_ok"] += pmap.get(g["actor"]["participant_ref"]) == k["actor"]["participant_ref"]
        c["standing_ok"] += _passage_standing(gold, g) == _passage_standing(coded, k)
        if g["time"]["assertions"]:
            c["dated"] += 1
            gd = {(t["earliest"], t["latest"]) for t in g["time"]["assertions"]}
            kd = {(t["earliest"], t["latest"]) for t in k["time"]["assertions"]}
            c["dates_ok"] += bool(gd & kd)
        ga = {a["affordance"] for a in g.get("affordances", [])}
        ka = {a["affordance"] for a in k.get("affordances", []) if a["status"] in ("DIRECT", "INFERRED")}
        c["aff_gold"] += len(ga)
        c["aff_coded"] += len(ka)
        c["aff_hit"] += len(ga & ka)
        gh = {V.HARM_H0[h["harm"]] for h in g.get("harms", []) if V.HARM_H0[h["harm"]]}
        kh = {V.HARM_H0[h["harm"]] for h in k.get("harms", []) if V.HARM_H0[h["harm"]]}
        c["harm_gold"] += len(gh)
        c["harm_coded"] += len(kh)
        c["harm_hit"] += len(gh & kh)
    # order: gold relations between matched acts, mapped into the coded ids
    coded_order = {(r["from_event"], r["to_event"]) for r in coded["relations"] if r["type"] in V.ORDER_RELATIONS}
    gold_order = [(r["from_event"], r["to_event"]) for r in gold["relations"] if r["type"] in V.ORDER_RELATIONS]
    c["order_gold"] += len(gold_order)
    c["order_found"] += sum((g2c.get(a), g2c.get(b)) in coded_order for a, b in gold_order)
    c2g = {v: k for k, v in g2c.items()}
    c["order_coded"] += len(coded_order)
    c["order_correct"] += sum((c2g.get(a), c2g.get(b)) in set(gold_order) for a, b in coded_order)
    same = {frozenset((r["from_event"], r["to_event"])) for r in coded["relations"] if r["type"] == "SAME_ACT"}
    gs = [(r["from_event"], r["to_event"]) for r in gold["relations"] if r["type"] == "SAME_ACT"]
    c["same_gold"] += len(gs)
    c["same_found"] += sum(frozenset((g2c.get(a), g2c.get(b))) in same for a, b in gs)
    for e in gold["events"]:
        for tag in e.get("notes", "").split():
            c[f"tag_gold:{tag}"] += 1
            c[f"tag_found:{tag}"] += e["event_id"] in g2c
    return c


def summarize(c: Counter) -> dict:
    p = c["matched"] / c["coded_events"] if c["coded_events"] else 0
    r = c["matched"] / c["gold_events"] if c["gold_events"] else 0
    return {
        "events": {"recall": _rate(c["matched"], c["gold_events"]), "precision": _rate(c["matched"], c["coded_events"]),
                   "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0},
        "action": _rate(c["action_ok"], c["matched"]), "actor": _rate(c["actor_ok"], c["matched"]),
        "standing": _rate(c["standing_ok"], c["matched"]), "dates": _rate(c["dates_ok"], c["dated"]),
        "order": {"recall": _rate(c["order_found"], c["order_gold"]), "precision": _rate(c["order_correct"], c["order_coded"])},
        "level_c": {"recall": _rate(c["aff_hit"], c["aff_gold"]), "precision": _rate(c["aff_hit"], c["aff_coded"])},
        "harms": {"recall": _rate(c["harm_hit"], c["harm_gold"]), "precision": _rate(c["harm_hit"], c["harm_coded"])},
        "same_act": _rate(c["same_found"], c["same_gold"]),
        "by_tag": {k.split(":", 1)[1]: _rate(c[f"tag_found:{k.split(':', 1)[1]}"], v)
                   for k, v in sorted(c.items()) if k.startswith("tag_gold:")},
    }


def split_of(case_id: str, data: Path = DATA) -> str:
    m = json.loads((data / "MANIFEST.json").read_text(encoding="utf-8"))
    return m.get("splits", {}).get(case_id, "dev")


def score_dir(coded_dir: Path, split: str = "all", data: Path = DATA) -> dict:
    total, per_case, missing = Counter(), {}, []
    for gold_path in sorted(data.glob("synth_*/gold.json")):
        case_id = gold_path.parent.name
        if split != "all" and split_of(case_id, data) != split:
            continue
        coded_path = coded_dir / f"{case_id}.json"
        if not coded_path.is_file():
            missing.append(case_id)
            continue
        c = score_case(json.loads(gold_path.read_text(encoding="utf-8")), json.loads(coded_path.read_text(encoding="utf-8")))
        per_case[case_id] = summarize(c)["events"]
        total += c
    return {"split": split, "cases": len(per_case), "missing": missing, "overall": summarize(total), "per_case": per_case}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("coded_dir", type=Path)
    ap.add_argument("--split", choices=("dev", "heldout", "all"), default="all")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    out = score_dir(args.coded_dir, args.split)
    if args.json:
        args.json.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["overall"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
