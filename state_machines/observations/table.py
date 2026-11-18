"""The case-level research table of a release: one row per case, three kinds of evidence kept apart.

    python -m state_machines.observations.table <release_id> [--check]

Built from the committed release files only (``lifecycle.json`` and ``observations/<case>.json``),
so anyone with the repository can rebuild it; ``--check`` fails when the stored table differs.
Written to ``<release>/research_table.json`` and ``research_table.csv`` by the release build.

Per case the table keeps three things apart, and they must not be added together:

    platform named            the record mentions a listed service (a mention, not use)
    feature stated            the record states a codebook feature phrase (a mention, not use)
    used in an act            the cited sentence of an agreed act states the act was done by means
                              of that platform or feature (the only rows that tie technology to conduct)

The cases are a selected collection of prosecutions with available court records. Counts
describe these records; they are not rates of offending and not a sample of anything.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

MEANING = ("platforms and features are what the record names (mentions, not use); used_in_act lists the only places "
           "where an agreed act's own sentence states the act was done by means of one")
READING = [
    "platform_named, feature_stated and used_in_act are three kinds of evidence; do not add them together",
    "a case with platforms named and nothing in used_in_act documents mentions only, not platform-mediated acts",
    "acts are those two model coders agreed on; an absent act is not evidence the act did not happen",
    "the cases are a selected collection of prosecutions, not a sample of offending",
]
CSV_COLUMNS = ["case_id", "documents", "agreed_acts", "offender_acts", "dated_acts", "offender_action_codes", "harm_codes",
               "platforms_named", "platform_mentions", "feature_classes_stated", "feature_statements",
               "platforms_used_in_an_act", "features_used_in_an_act", "platforms_named_list", "features_stated_list", "used_in_act_list"]


def case_observed(doc: dict, actions: Dict[str, str] = None) -> dict:
    """A case's observations, grouped: who is named, what is stated, and what an act's sentence ties to the act."""
    platforms: Dict[str, dict] = {}
    features: Dict[str, Counter] = {}
    used: List[dict] = []
    for o in doc["observations"]:
        if o["kind"] == "platform":
            p = platforms.setdefault(o["platform"], {"mentions": 0, "standing": Counter()})
            p["mentions"] += 1
            p["standing"][o["source_status"]] += 1
        else:
            features.setdefault(o["feature_class"], Counter())[o["feature_term"]] += 1
        for r in o["relations"]:
            row = {"event_id": r["event_id"], "relationship": r["relationship"], "kind": o["kind"], "standing": o["source_status"],
                   **({"platform": o["platform"]} if o["kind"] == "platform" else
                      {"feature_class": o["feature_class"], "feature_term": o["feature_term"]})}
            if actions is not None:
                row["action"] = actions.get(r["event_id"])
            if row not in used:
                used.append(row)
    return {"meaning": MEANING,
            "platforms": {k: {"mentions": v["mentions"], "standing": dict(sorted(v["standing"].items()))} for k, v in sorted(platforms.items())},
            "features": {k: dict(sorted(v.items())) for k, v in sorted(features.items())},
            "used_in_act": sorted(used, key=lambda r: (r["event_id"], r["kind"], r.get("platform") or r.get("feature_class")))}


def build(root: Path) -> dict:
    """The research table of the release under ``root``, from its committed files."""
    payload = json.loads((root / "lifecycle.json").read_text(encoding="utf-8"))
    rows, rule = [], None
    for case in payload["cases"]:
        events = case["events"]
        path = root / "observations" / f"{case['case_id']}.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"observations": [], "rule": None}
        rule = rule or doc.get("rule")
        observed = case_observed(doc, {k: e["action"] for k, e in events.items()})
        offender = [e for e in events.values() if e["family"] == "offender"]
        rows.append({
            "case_id": case["case_id"],
            "documents": sum(1 for _ in case["documents"]),
            "acts": {"agreed": len(events), "offender": len(offender), "dated": sum(bool(e["time"]) for e in events.values()),
                     "offender_action_codes": dict(sorted(Counter(e["action"] for e in offender).items())),
                     "harm_codes": sorted({h["code"] for e in events.values() for h in e["harms"]})},
            "platform_named": observed["platforms"],
            "feature_stated": observed["features"],
            "used_in_act": observed["used_in_act"],
            "counts": {"platforms_named": len(observed["platforms"]),
                       "platform_mentions": sum(p["mentions"] for p in observed["platforms"].values()),
                       "feature_classes_stated": len(observed["features"]),
                       "feature_statements": sum(sum(t.values()) for t in observed["features"].values()),
                       "platforms_used_in_an_act": sum(r["kind"] == "platform" for r in observed["used_in_act"]),
                       "features_used_in_an_act": sum(r["kind"] == "feature" for r in observed["used_in_act"])},
        })
    totals: Counter = Counter()
    for r in rows:
        totals["cases"] += 1
        totals["cases naming a platform"] += bool(r["platform_named"])
        totals["cases stating a feature"] += bool(r["feature_stated"])
        totals["cases with a platform or feature used in an act"] += bool(r["used_in_act"])
        totals["agreed acts"] += r["acts"]["agreed"]
        totals["offender acts"] += r["acts"]["offender"]
        for k, v in r["counts"].items():
            totals[k] += v
    return {"release": payload["release"]["id"], "review_mode": payload["release"]["review_mode"], "observation_rule": rule,
            "reading": READING, "totals": dict(totals), "cases": rows}


def to_csv(table: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for r in table["cases"]:
        c = r["counts"]
        w.writerow([r["case_id"], r["documents"], r["acts"]["agreed"], r["acts"]["offender"], r["acts"]["dated"],
                    "; ".join(f"{k}={v}" for k, v in r["acts"]["offender_action_codes"].items()), "; ".join(r["acts"]["harm_codes"]),
                    c["platforms_named"], c["platform_mentions"], c["feature_classes_stated"], c["feature_statements"],
                    c["platforms_used_in_an_act"], c["features_used_in_an_act"],
                    "; ".join(f"{k}={v['mentions']}" for k, v in r["platform_named"].items()),
                    "; ".join(f"{cls}:{t}={n}" for cls, terms in r["feature_stated"].items() for t, n in terms.items()),
                    "; ".join(f"{x['action']} {x['relationship']} {x.get('platform') or x['feature_class'] + ':' + x['feature_term']} [{x['standing']}]"
                              for x in r["used_in_act"])])
    return out.getvalue()


def write(root: Path) -> dict:
    table = build(root)
    (root / "research_table.json").write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (root / "research_table.csv").write_text(to_csv(table), encoding="utf-8")
    return table


def main(argv=None) -> int:
    from state_machines.graphs.release import DATA
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("release_id")
    ap.add_argument("--check", action="store_true", help="fail if the stored table differs from one rebuilt from the release files")
    a = ap.parse_args(argv)
    root = DATA / a.release_id
    if a.check:
        same = (json.loads((root / "research_table.json").read_text(encoding="utf-8")) == json.loads(json.dumps(build(root), sort_keys=True))
                and (root / "research_table.csv").read_text(encoding="utf-8") == to_csv(build(root)))
        print("research table matches the release files" if same else "research table differs from the release files")
        return 0 if same else 1
    print(json.dumps(write(root)["totals"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
