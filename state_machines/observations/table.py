"""The case-level research table of a release: one row per case, the kinds of evidence kept apart.

    python -m state_machines.observations.table <release_id> [--check]

Built from the committed release files only (``lifecycle.json`` and ``observations/<case>.json``),
so anyone with the repository can rebuild it; ``--check`` fails when the stored table differs.
Written to ``<release>/research_table.json`` and ``research_table.csv`` by the release build.

Per case the table keeps these apart, and they must not be added together:

    platform named            the record mentions a listed service (a mention, not use)
    platform withheld         the record refers to a service by a placeholder ("Website A")
    service described         a generic description of an online service; not a platform
    feature stated            the record states a codebook feature phrase (a mention, not use)
    used in an act            the cited sentence of an agreed act states the act was done by means
                              of that platform or feature (the only rows that tie technology to conduct)
    means stated, act disputed   the sentence states a means and each coder gave an offender act there to an
                              identified offender, but they differ on the act; a disputed machine reading
    means stated, actor conflict the same where the coders do not both name an identified offender; never
                              counted as offender use

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

MEANING = ("platforms, service descriptions and features are what the record names (mentions, not use); used_in_act lists the "
           "only places where the observation rule found an agreed act's own sentence stating the act was done by means of one")
READING = [
    "platform_named, feature_stated and used_in_act are three kinds of evidence; do not add them together",
    "platform_withheld holds services the record refers to by a placeholder (\"Website A\"); the label is the record's and means nothing outside its case; a withheld name is not evidence of anonymity or of any feature",
    "means_stated_act_disputed is a fourth kind, counted in observations (two platforms in one sentence are two rows): the sentence states the platform or feature as a means, each coder gave an offender act in that sentence to an identified offender (the defendant, named so, named by a caption name, or not named, which the coder's prompt defines as the defendant; a co-defendant; a co-conspirator), and they differ on which act or which offender; both coders' action codes and actor categories are kept, no act is published there and nothing is tied to one. It is a disputed machine reading, not established conduct, and it never enters an agreed-act count or a trajectory",
    "means_stated_actor_conflict holds the observations where the coders do not both name an identified offender: one gives the act to an investigator, the court, a victim or an undercover persona, or to a label the coder did not recognise. Whose conduct it was is in dispute, so it is not counted as offender use anywhere",
    "service_described holds generic descriptions (\"social media application\"): cited phrases, not platforms, never tied to an act",
    "a case with platforms named and nothing in used_in_act documents mentions only, not platform-mediated acts",
    "acts are those two model coders agreed on; an absent act is not evidence the act did not happen",
    "the cases are a selected collection of prosecutions, not a sample of offending",
]
CSV_COLUMNS = ["case_id", "documents", "agreed_acts", "offender_acts", "dated_acts", "offender_action_codes", "harm_codes",
               "platforms_named", "platform_mentions", "platforms_withheld", "withheld_platform_mentions", "service_description_mentions", "feature_classes_stated", "feature_statements",
               "platforms_used_in_an_act", "features_used_in_an_act", "platform_means_stated_act_disputed", "feature_means_stated_act_disputed",
               "sentences_means_stated_act_disputed", "platforms_named_list", "platforms_withheld_list", "service_descriptions_list", "features_stated_list", "used_in_act_list", "means_stated_act_disputed_list", "means_stated_actor_conflict"]


def _where(r: dict) -> tuple:
    return (r["doc_id"], r["pdf_page"], r["char_start"], r["kind"], r.get("platform") or r.get("feature_class"))


def case_observed(doc: dict, actions: Dict[str, str] = None) -> dict:
    """A case's observations, grouped: who is named, what is stated, and what an act's sentence ties to the act."""
    platforms: Dict[str, dict] = {}
    features: Dict[str, Counter] = {}
    described: Counter = Counter()
    used: List[dict] = []
    disputed: List[dict] = []
    conflicts: List[dict] = []
    for o in doc["observations"]:
        for field, rows in (("contested_act", disputed), ("actor_conflict", conflicts)):
            c = o.get(field)
            if not c:
                continue
            row = {"relationship": c["relationship"], "kind": o["kind"], "standing": o["source_status"],
                   "doc_id": o["doc_id"], "pdf_page": o["pdf_page"], "char_start": o["char_start"], "char_end": o["char_end"],
                   "action_codes": c["action_codes"], "actors": c["actors"], "dispute": c["dispute"],
                   **({"platform": o["platform"]} if o["kind"] == "platform" else {"feature_class": o["feature_class"], "feature_term": o["feature_term"]})}
            if row not in rows:
                rows.append(row)
        if o["kind"] == "platform":
            p = platforms.setdefault(o["platform"], {"mentions": 0, "standing": Counter(), "withheld": bool(o.get("withheld"))})
            p["mentions"] += 1
            p["standing"][o["source_status"]] += 1
        elif o["kind"] == "service_description":
            described[o["service_term"]] += 1
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
            "platforms": {k: {"mentions": v["mentions"], "standing": dict(sorted(v["standing"].items())), **({"withheld": True} if v["withheld"] else {})}
                          for k, v in sorted(platforms.items())},
            "features": {k: dict(sorted(v.items())) for k, v in sorted(features.items())},
            "service_descriptions": dict(sorted(described.items())),
            "used_in_act": sorted(used, key=lambda r: (r["event_id"], r["kind"], r.get("platform") or r.get("feature_class"))),
            "means_stated_act_disputed": sorted(disputed, key=_where),
            "means_stated_actor_conflict": sorted(conflicts, key=_where)}


def build(root: Path) -> dict:
    """The research table of the release under ``root``, from its committed files."""
    payload = json.loads((root / "lifecycle.json").read_text(encoding="utf-8"))
    listed = {c["case_id"] for c in json.loads((root / "manifest.json").read_text(encoding="utf-8"))["cases"] if "observations" in c["graphs"]}
    rows, rule = [], None
    for case in payload["cases"]:
        events = case["events"]
        path = root / "observations" / f"{case['case_id']}.json"
        doc = (json.loads(path.read_text(encoding="utf-8")) if case["case_id"] in listed and path.is_file()
               else {"observations": [], "rule": None})
        rule = rule or doc.get("rule")
        observed = case_observed(doc, {k: e["action"] for k, e in events.items()})
        offender = [e for e in events.values() if e["family"] == "offender"]
        rows.append({
            "case_id": case["case_id"],
            "documents": sum(1 for _ in case["documents"]),
            "acts": {"agreed": len(events), "offender": len(offender), "dated": sum(bool(e["time"]) for e in events.values()),
                     "offender_action_codes": dict(sorted(Counter(e["action"] for e in offender).items())),
                     "harm_codes": sorted({h["code"] for e in events.values() for h in e["harms"]})},
            "platform_named": {k: v for k, v in observed["platforms"].items() if not v.get("withheld")},
            "platform_withheld": {k: v for k, v in observed["platforms"].items() if v.get("withheld")},
            "service_described": observed["service_descriptions"],
            "feature_stated": observed["features"],
            "used_in_act": observed["used_in_act"],
            "means_stated_act_disputed": observed["means_stated_act_disputed"],
            "means_stated_actor_conflict": observed["means_stated_actor_conflict"],
            "counts": {"platforms_named": sum(not p.get("withheld") for p in observed["platforms"].values()),
                       "platforms_withheld": sum(bool(p.get("withheld")) for p in observed["platforms"].values()),
                       "platform_mentions": sum(p["mentions"] for p in observed["platforms"].values() if not p.get("withheld")),
                       "withheld_platform_mentions": sum(p["mentions"] for p in observed["platforms"].values() if p.get("withheld")),
                       "service_description_mentions": sum(observed["service_descriptions"].values()),
                       "feature_classes_stated": len(observed["features"]),
                       "feature_statements": sum(sum(t.values()) for t in observed["features"].values()),
                       "platforms_used_in_an_act": sum(r["kind"] == "platform" for r in observed["used_in_act"]),
                       "features_used_in_an_act": sum(r["kind"] == "feature" for r in observed["used_in_act"]),
                       "platform_means_stated_act_disputed": sum(r["kind"] == "platform" for r in observed["means_stated_act_disputed"]),
                       "feature_means_stated_act_disputed": sum(r["kind"] == "feature" for r in observed["means_stated_act_disputed"]),
                       "sentences_means_stated_act_disputed": len({(r["doc_id"], r["pdf_page"], r["char_start"]) for r in observed["means_stated_act_disputed"]}),
                       "means_stated_actor_conflict": len(observed["means_stated_actor_conflict"])},
        })
    totals: Counter = Counter()
    for r in rows:
        totals["cases"] += 1
        totals["cases naming a platform"] += bool(r["platform_named"])
        totals["cases with a platform whose name is withheld"] += bool(r["platform_withheld"])
        totals["cases with a generic service description"] += bool(r["service_described"])
        totals["cases with no listed platform, a withheld one"] += bool(r["platform_withheld"]) and not r["platform_named"]
        totals["cases with no listed or withheld platform, a generic description"] += bool(r["service_described"]) and not (r["platform_named"] or r["platform_withheld"])
        totals["cases with none of the three"] += not (r["platform_named"] or r["platform_withheld"] or r["service_described"])
        totals["cases stating a feature"] += bool(r["feature_stated"])
        totals["cases with a platform or feature used in an act"] += bool(r["used_in_act"])
        totals["cases with a means stated where the coders dispute the act"] += bool(r["means_stated_act_disputed"])
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
                    c["platforms_named"], c["platform_mentions"], c["platforms_withheld"], c["withheld_platform_mentions"],
                    c["service_description_mentions"], c["feature_classes_stated"], c["feature_statements"],
                    c["platforms_used_in_an_act"], c["features_used_in_an_act"], c["platform_means_stated_act_disputed"], c["feature_means_stated_act_disputed"], c["sentences_means_stated_act_disputed"],
                    "; ".join(f"{k}={v['mentions']}" for k, v in r["platform_named"].items()),
                    "; ".join(f"{k}={v['mentions']}" for k, v in r["platform_withheld"].items()),
                    "; ".join(f"{k}={v}" for k, v in r["service_described"].items()),
                    "; ".join(f"{cls}:{t}={n}" for cls, terms in r["feature_stated"].items() for t, n in terms.items()),
                    "; ".join(f"{x['action']} {x['relationship']} {x.get('platform') or x['feature_class'] + ':' + x['feature_term']} [{x['standing']}]"
                              for x in r["used_in_act"]),
                    " | ".join(f"{x['relationship']} {x.get('platform') or x['feature_class'] + ':' + x['feature_term']} "
                               f"[{x['standing']}, A {'/'.join(x['action_codes']['coder_A'])} by {'/'.join(x['actors']['coder_A'])}, "
                               f"B {'/'.join(x['action_codes']['coder_B'])} by {'/'.join(x['actors']['coder_B'])}, differ on {' and '.join(x['dispute'])}]"
                              for x in r["means_stated_act_disputed"]),
                    len(r["means_stated_actor_conflict"])])
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
