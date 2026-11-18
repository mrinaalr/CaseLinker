"""The affordance evidence matrix of a release: for each affordance class of the codebook, what the
court records hold, with the kinds of evidence side by side and never added together.

    python -m state_machines.observations.affordance_matrix <release_id> [--check]

Computed only from committed release files (``lifecycle.json``, ``observations/*.json``).

1. ``phrase_stated``: a listed feature phrase of the class is stated in a cited sentence. A mention.
2. ``in_agreed_act_sentence``: the phrase stands in a sentence that an agreed offender act cites.
   Co-occurrence only: the sentence need not say the feature was used, or by whom.
3. ``means_stated_in_act_sentence``: an agreed act's own sentence states the act was done by means of
   that phrase (the stated-means rule; this is level C, and it is the same rule in the act layer and
   the observation layer).

Platform observations are never read here, whether named, under a placeholder or generic: a platform
name, a withheld name or a description is not evidence of an affordance. Each case and class gets one
mechanical reading: ``means_stated``, ``in_act_sentence_only``, ``stated_only`` or ``none``.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Tuple

from state_machines.evidence import vocab as V
from state_machines.observations.observe import FEATURES

KINDS = ("phrase_stated", "in_agreed_act_sentence", "means_stated_in_act_sentence")
READING = [
    "rows are affordance classes in codebook order; there is no total row and no percentage, because the classes have phrase lists of different sizes and the cases are a selected collection, not a sample",
    "phrase_stated, in_agreed_act_sentence and means_stated_in_act_sentence are three kinds of evidence; do not add them together",
    "in_agreed_act_sentence is co-occurrence: the phrase and an agreed act share a sentence; the sentence may describe the technology, another person's use, or a denial",
    "needs_researcher_interpretation is mechanical: in some case the class is stated, with or without an act in the same sentence, and no act's sentence states it as the means",
    "no_evidence_in_these_records means no listed phrase in the cases read; it is not evidence the affordance played no part",
    "a case whose narrative filings are sealed or were not collected reads none for the same reason as a case where nothing happened; the grid cannot tell them apart",
    "cases_by_standing can exceed cases stating, since a case can state a phrase in documents of several standings",
]
CLASS_COLUMNS = ["affordance_class", "listed_phrases", "statements", "cases_stating", "statements_by_standing", "cases_by_standing",
                 "acts_with_phrase_in_sentence", "cases_with_phrase_in_act_sentence", "acts_means_stated", "cases_means_stated",
                 "cases_stated_only", "cases_in_act_sentence_only", "needs_researcher_interpretation", "no_evidence_in_these_records"]


def _cell(doc: dict, events: dict, cls: str) -> dict:
    """One case and one class: the three kinds of evidence, side by side."""
    stated = [o for o in doc["observations"] if o["kind"] == "feature" and o["feature_class"] == cls]
    beside = sorted({e for o in stated for e in o.get("in_act_sentence", [])})
    means = sorted({r["event_id"] for o in stated for r in o["relations"]}
                   | {k for k, e in events.items() if any(a["class"] == cls for a in e["affordances"])})
    reading = "means_stated" if means else "in_act_sentence_only" if beside else "stated_only" if stated else "none"
    return {"statements": len(stated), "by_standing": dict(sorted(Counter(o["source_status"] for o in stated).items())),
            "terms": dict(sorted(Counter(o["feature_term"] for o in stated).items())),
            "acts_with_phrase_in_sentence": beside, "acts_means_stated": means, "reading": reading}


def build(root: Path) -> dict:
    payload = json.loads((root / "lifecycle.json").read_text(encoding="utf-8"))
    grid, rule = [], None
    for case in payload["cases"]:
        path = root / "observations" / f"{case['case_id']}.json"
        if not path.is_file():
            grid.append({"case_id": case["case_id"], "observations_read": False, "cells": {}})
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        rule = rule or doc.get("rule")
        grid.append({"case_id": case["case_id"], "observations_read": True,
                     "cells": {cls: _cell(doc, case["events"], cls) for cls in V.AFFORDANCE_CLASSES}})
    classes = []
    for cls in V.AFFORDANCE_CLASSES:
        cells = {g["case_id"]: g["cells"][cls] for g in grid if g["observations_read"]}
        standing, standing_cases = Counter(), Counter()
        for c in cells.values():
            standing.update(c["by_standing"])
            standing_cases.update(c["by_standing"].keys())
        with_ = lambda key: sorted(k for k, c in cells.items() if c[key])
        by_reading = {r: sorted(k for k, c in cells.items() if c["reading"] == r) for r in ("means_stated", "in_act_sentence_only", "stated_only")}
        classes.append({
            "affordance_class": cls, "cac_class": V.AFFORDANCE_CLASSES[cls], "listed_phrases": len(FEATURES[cls]),
            "phrase_stated": {"statements": sum(c["statements"] for c in cells.values()), "cases": with_("statements"),
                              "statements_by_standing": dict(sorted(standing.items())), "cases_by_standing": dict(sorted(standing_cases.items()))},
            "in_agreed_act_sentence": {"acts": sum(len(c["acts_with_phrase_in_sentence"]) for c in cells.values()), "cases": with_("acts_with_phrase_in_sentence")},
            "means_stated_in_act_sentence": {"acts": sum(len(c["acts_means_stated"]) for c in cells.values()), "cases": with_("acts_means_stated")},
            "cases_by_reading": by_reading,
            "needs_researcher_interpretation": bool(by_reading["stated_only"] or by_reading["in_act_sentence_only"]),
            "no_evidence_in_these_records": not any(by_reading.values()),
        })
    return {"release": payload["release"]["id"], "review_mode": payload["release"]["review_mode"], "codebook_version": payload["release"]["codebook_version"],
            "observation_rule": rule, "cases_read": sum(g["observations_read"] for g in grid), "reading": READING, "classes": classes, "grid": grid}


def to_csv(matrix: dict) -> Tuple[str, str]:
    """(one row per class, one row per case with one column per class)."""
    a, b = io.StringIO(), io.StringIO()
    w = csv.writer(a, lineterminator="\n")
    w.writerow(CLASS_COLUMNS)
    kv = lambda d: "; ".join(f"{k}={v}" for k, v in d.items())
    for r in matrix["classes"]:
        s, i, m, by = r["phrase_stated"], r["in_agreed_act_sentence"], r["means_stated_in_act_sentence"], r["cases_by_reading"]
        w.writerow([r["affordance_class"], r["listed_phrases"], s["statements"], len(s["cases"]), kv(s["statements_by_standing"]), kv(s["cases_by_standing"]),
                    i["acts"], len(i["cases"]), m["acts"], len(m["cases"]), len(by["stated_only"]), len(by["in_act_sentence_only"]),
                    "yes" if r["needs_researcher_interpretation"] else "no", "yes" if r["no_evidence_in_these_records"] else "no"])
    w = csv.writer(b, lineterminator="\n")
    w.writerow(["case_id"] + list(V.AFFORDANCE_CLASSES))
    for g in matrix["grid"]:
        w.writerow([g["case_id"]] + [f"stated={x['statements']} in_act_sentence={len(x['acts_with_phrase_in_sentence'])} means_stated={len(x['acts_means_stated'])}"
                                     if g["observations_read"] else "not_read" for x in (g["cells"].get(k) for k in V.AFFORDANCE_CLASSES)])
    return a.getvalue(), b.getvalue()


FILES = ("affordance_matrix.json", "affordance_matrix.csv", "affordance_case_grid.csv")


def rendered(root: Path) -> dict:
    m = build(root)
    a, b = to_csv(m)
    return {FILES[0]: json.dumps(m, indent=1, sort_keys=True) + "\n", FILES[1]: a, FILES[2]: b}


def write(root: Path) -> dict:
    for name, text in rendered(root).items():
        (root / name).write_text(text, encoding="utf-8")
    return build(root)


def main(argv=None) -> int:
    import argparse
    from state_machines.graphs.release import DATA
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("release_id")
    ap.add_argument("--check", action="store_true", help="fail if the committed files differ from what the release files give")
    a = ap.parse_args(argv)
    root = DATA / a.release_id
    if a.check:
        stale = [n for n, text in rendered(root).items() if not (root / n).is_file() or (root / n).read_text(encoding="utf-8") != text]
        print("affordance matrix matches the release files" if not stale else f"affordance matrix differs from the release files: {stale}")
        return 1 if stale else 0
    write(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
