"""The run report of a machine-coded release: what was coded, how well, and what was left out.

    python -m state_machines.coding.report <release_id> [--auto local/auto] [--pilot <dir of reference bundles>]

Writes ``state_machines/data/<release_id>/report.json`` (for tools and the review agent) and
``REPORT.md`` (for people). Numbers only: no quotes, no names, no coder text.

Sections: the pinned models and inference settings; per case, whether it was published, its
published acts and relations, its failures and reasons; page coverage by route (model, docket
parser, skipped form pages, skipped by the selective second pass); acts dropped and why;
inter-coder reliability on model-coded acts; benchmark accuracy per split and rule version (read
from ``state_machines/benchmark/results``); a comparison with reference coding of real cases where
one is given (``--pilot``); runtime per page. Reliability is agreement between the two coders on
the real cases; benchmark accuracy is on synthetic records; the reference comparison is agreement
with another coding of a few real cases. None of them is accuracy on the real cases.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from state_machines.evidence import evidence as E
from state_machines.coding import coder as C
from state_machines.coding.throughput import model_stats

DATA = E.REPO_ROOT / "state_machines" / "data"
RESULTS = E.REPO_ROOT / "state_machines" / "benchmark" / "results"


def benchmark_results() -> dict:
    """Committed benchmark scores, keyed ``<rule version>.<split>``: {system: overall scores}."""
    out = {}
    for path in sorted(RESULTS.glob("*.json")):
        out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return out


def reference_comparison(resolved: Path, pilot: Path) -> dict:
    """Published non-procedure acts of real cases against a reference coding of the same pages.

    For each published act: did the reference code an act in the same sentence (overlapping cited
    span), and did it give one there the same action code. The reference is another coding, not
    truth, and it does not code every act, so these are agreement counts, not accuracy."""
    from state_machines.coding.workflow import _spans
    from state_machines.evidence import vocab as V
    c: Counter = Counter()
    cases = []
    for ref_path in sorted(pilot.glob("*.json")):
        got = resolved / ref_path.name
        if not got.is_file():
            continue
        ref, r = (json.loads(x.read_text(encoding="utf-8")) for x in (ref_path, got))
        cases.append(r["case_id"])
        ref_spans = [(sp, e) for e in ref["events"] if V.FAMILY_OF[e["action"]] != "procedure" for sp in _spans(ref, e)]
        ours = [e for e in r["events"] if V.FAMILY_OF[e["action"]] != "procedure"]
        our_spans = [(sp, e) for e in ours for sp in _spans(r, e)]
        hit = lambda s, t: s[0] == t[0] and s[1] == t[1] and s[2] < t[3] and t[2] < s[3]
        for e in ours:
            near = [x for sp, x in ref_spans for s in _spans(r, e) if hit(s, sp)]
            tier = "settled" if "settled by cue rule" in e["review"].get("note", "") else "agreed"
            c[f"{tier}: published acts"] += 1
            c[f"{tier}: reference coded an act in the same sentence"] += bool(near)
            c[f"{tier}: reference gave the same action code there"] += any(x["action"] == e["action"] for x in near)
        ref_acts = {e["event_id"] for _, e in ref_spans}
        c["reference acts"] += len(ref_acts)
        c["reference acts in a sentence the release also cites"] += len({e["event_id"] for sp, e in ref_spans
                                                                          if any(hit(s, sp) for s, _ in our_spans)})
    return {"cases": cases, "counts": dict(sorted(c.items()))}


def _coverage(log: Path) -> Counter:
    c: Counter = Counter()
    if not log.is_file():
        return c
    for line in log.read_text(encoding="utf-8").splitlines():
        m = re.match(r"page \S+ p\d+: (.+?), (\d+) acts$", line)
        if m:
            route = m.group(1).split(" (")[0]
            c[f"pages: {route}"] += 1
            c[f"acts proposed: {route}"] += int(m.group(2))
        elif line.startswith("dropped by "):
            c["acts dropped: " + line.split(" at ")[0].replace("dropped by ", "rule ")] += 1
        elif line.startswith("dropped "):
            reason = line.split(": ", 1)[1] if ": " in line else line
            reason = re.sub(r"quote .*", "quote not located on the page", reason)
            reason = re.sub(r"actor role .*", "actor role cannot perform the action", reason)
            c["acts dropped: " + reason] += 1
    return c


def published_content(release_id: str) -> dict:
    """What the release's bundles hold, counted: acts by family, dated acts, relations, harms, level C."""
    from state_machines.evidence import vocab as V
    c: Counter = Counter()
    for path in sorted((DATA / release_id / "cases").glob("*.json")):
        b = json.loads(path.read_text(encoding="utf-8"))
        c["cases"] += 1
        c["cases with offender acts"] += any(V.FAMILY_OF[e["action"]] == "offender" for e in b["events"])
        for e in b["events"]:
            fam = V.FAMILY_OF[e["action"]]
            c["acts"] += 1
            c[f"acts: {fam}"] += 1
            c["acts with a cited date"] += bool(e["time"]["assertions"])
            if fam == "offender":
                c["offender acts naming a victim or an undercover persona"] += bool(e["targets"])
                c["offender acts with a documented platform"] += bool(e["platform_interactions"])
                c["level-C affordances (feature stated in the sentence)"] += len(e["affordances"])
            for h in e["harms"]:
                c[f"harms recorded: victim {h['victim_kind']}"] += 1
        for r in b["relations"]:
            c["relations: stated order" if r["type"] in V.ORDER_RELATIONS else "relations: possibly the same act"] += 1
    return dict(sorted(c.items()))


def observed_content(release_id: str, pilot: Path = None) -> dict:
    """The observation layer of a release, counted from its manifest, with the three level queries run
    on its graphs and, where reference bundles are given, the platforms those name per case."""
    manifest = json.loads((DATA / release_id / "manifest.json").read_text(encoding="utf-8"))
    cases = [c for c in manifest["cases"] if c.get("observations")]
    if not cases:
        return {}
    c: Counter = Counter()
    for case in cases:
        o = case["observations"]
        c["cases"] += 1
        c["observations"] += o["observations"]
        c["observations of a listed platform's name"] += o["platform_observations"]
        c["observations of a platform under a placeholder (name withheld)"] += o["withheld_platform_observations"]
        c["observations of a generic service description"] += o["service_description_observations"]
        c["feature observations"] += o["feature_observations"]
        c["cases naming at least one listed platform"] += bool(o["platforms"])
        c["cases with a platform whose name is withheld"] += bool(o["withheld_platforms"])
        c["cases with a generic service description"] += bool(o["service_terms"])
        c["cases with no listed platform, a withheld one"] += bool(o["withheld_platforms"]) and not o["platforms"]
        c["cases with neither, a generic service description"] += bool(o["service_terms"]) and not (o["platforms"] or o["withheld_platforms"])
        c["cases with none of the three"] += not (o["platforms"] or o["withheld_platforms"] or o["service_terms"])
        c["cases stating at least one feature phrase"] += bool(o["feature_classes"])
        c["distinct case and listed-platform pairs"] += len(o["platforms"])
        c["distinct case and withheld-platform pairs"] += len(o["withheld_platforms"])
        c["observations tied to a published act by a stated means"] += o["observations_tied_to_an_act"]
        c["cases with at least one such relationship"] += o["observations_tied_to_an_act"] > 0
        for k, v in o["by_standing"].items():
            c[f"observations in documents with standing {k}"] += v
    from state_machines.observations.queries import QUERIES, run
    out = {"counts": dict(c), "queries": {k: {"title": QUERIES[k]["title"], "columns": QUERIES[k]["columns"], "sparql": QUERIES[k]["sparql"], "rows": rows}
                                           for k, rows in run(release_id).items()}}
    if (DATA / release_id / "validation.json").is_file():
        out["validation"] = json.loads((DATA / release_id / "validation.json").read_text(encoding="utf-8"))
    if pilot is not None and pilot.is_dir():
        from state_machines.coding.enrich import known_platform
        ref: Counter = Counter()
        for path in sorted(pilot.glob("*.json")):
            case = next((x for x in cases if x["case_id"] == path.stem), None)
            if case is None:
                continue
            b = json.loads(path.read_text(encoding="utf-8"))
            raw = {x["platform_surface"] for e in b["events"] for k in ("platform_interactions", "platform_mentions") for x in e.get(k, [])}
            named = {known_platform(r) for r in raw if known_platform(r)}
            ref["cases"] += 1
            ref["listed platforms the reference coding names"] += len(named)
            ref["of which observed"] += len(named & set(case["observations"]["platforms"]))
            ref["platform surfaces in the reference that are not on the list"] += len({r for r in raw if not known_platform(r)})
            ref["listed platforms observed"] += len(case["observations"]["platforms"])
        out["reference"] = dict(ref)
    return out


def build(release_id: str, auto: Path, pilot: Path = None) -> dict:
    root = DATA / release_id
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    published = {c["case_id"]: c for c in manifest["cases"]}
    summary = json.loads((auto / "reports" / "SUMMARY.json").read_text(encoding="utf-8")) if (auto / "reports" / "SUMMARY.json").is_file() else {}
    cases, totals = {}, Counter()
    for case_id in sorted(set(summary) | set(published)):
        rep_path = auto / "reports" / f"{case_id}.json"
        rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.is_file() else {}
        cov = {coder: dict(_coverage(auto / coder / f"{case_id}.log")) for coder in ("coder_A", "coder_B")}
        failed = {coder: (auto / coder / f"{case_id}.failed").read_text(encoding="utf-8").splitlines()[0]
                  for coder in ("coder_A", "coder_B") if (auto / coder / f"{case_id}.failed").is_file()}
        entry = {"published": case_id in published, "failed": failed or summary.get(case_id, {}).get("failed"),
                 "resolution": rep.get("counts"), "agreement_model_coded": rep.get("agreement_model_coded"),
                 "parser_events": rep.get("parser_events"), "coverage": cov}
        if case_id in published:
            p = published[case_id]
            entry.update(shacl=p["shacl"]["conformance"], shacl_violations=p["shacl"]["violations"], review=p["review"],
                         passages=p.get("passages"))
            totals["cases published"] += 1
        else:
            totals["cases not published"] += 1
        for coder, c in cov.items():
            for k, v in c.items():
                totals[f"{coder} {k}"] += v
        cases[case_id] = entry
    ag = [c["agreement_model_coded"] for c in cases.values() if c.get("agreement_model_coded")]
    kappas = [a["action_code"]["kappa"] for a in ag if a.get("action_code", {}).get("kappa") is not None]
    reliability = {
        "cases": len(ag),
        "events_coder_A": sum(a["events"]["coder_a"] for a in ag), "events_coder_B": sum(a["events"]["coder_b"] for a in ag),
        "matched": sum(a["events"]["matched"] for a in ag),
        "mean_event_f1": round(sum(a["events"]["f1"] for a in ag) / len(ag), 3) if ag else None,
        "pooled_action_agreement": {"exact": sum(a["action_code"]["exact"] for a in ag), "of": sum(a["action_code"]["of"] for a in ag)},
        "mean_action_kappa": round(sum(kappas) / len(kappas), 3) if kappas else None,
        "note": "agreement on acts the models coded; the docket parser's acts are excluded",
    }
    reference = None
    if pilot is not None and pilot.is_dir():
        reference = {"released": reference_comparison(auto / "resolved", pilot)}
        if (auto / "resolved_2b").is_dir():
            reference["candidate_2b"] = reference_comparison(auto / "resolved_2b", pilot)
    from state_machines.graphs.release import privacy_scan
    privacy = privacy_scan(release_id, E.text_root())
    return {"release": release_id, "review_mode": manifest.get("review_mode"), "models": C.MODELS,
            "privacy_scan": {k: (len(v) if k == "hits" else v) for k, v in privacy.items()},
            "runtime_per_model": model_stats(), "totals": dict(sorted(totals.items())), "reliability_real_cases": reliability,
            "published": published_content(release_id), "observed": observed_content(release_id, pilot),
            "benchmark": benchmark_results(), "reference_real_cases": reference, "cases": cases}


_ROWS = [("gold acts found (recall)", lambda o: o["events"]["recall"]), ("coded acts that are gold acts (precision)", lambda o: o["events"]["precision"]),
         ("action code", lambda o: o["action"]), ("actor", lambda o: o["actor"]), ("legal standing", lambda o: o["standing"]),
         ("dates", lambda o: o["dates"]),
         ("order relations: correct against the documented order", lambda o: o.get("order_claims", {}).get("correct")),
         ("order relations: reversed", lambda o: o.get("order_claims", {}).get("reversed")),
         ("order relations: not documented", lambda o: o.get("order_claims", {}).get("not_documented")),
         ("gold sequence sentences recovered (stated order recall)", lambda o: o["order"]["recall"]),
         ("gold-ordered pairs also ordered, both acts coded", lambda o: o.get("order_pairs", {}).get("of_pairs_with_both_acts_coded")),
         ("gold-ordered pairs also ordered, all", lambda o: o.get("order_pairs", {}).get("of_all_gold_pairs")),
         ("level C found (recall)", lambda o: o["level_c"]["recall"]), ("level C correct (precision)", lambda o: o["level_c"]["precision"]),
         ("harms found (recall)", lambda o: o["harms"]["recall"]), ("harms correct (precision)", lambda o: o["harms"]["precision"]),
         ("possible retellings linked", lambda o: o["same_act"])]
_SPLITS = {"dev": "development cases (rules were tuned on these)", "heldout": "held-out cases",
           "confirm": "confirmation cases (wording written without sight of the rules; scored once)"}


def _cell(v) -> str:
    if v is None:
        return ""
    return f"{v['rate']} ({v['n']}/{v['of']})" if isinstance(v, dict) else str(v)


def _observed_md(ob: dict) -> list:
    if not ob:
        return []
    L = ["## What the records name (observation layer)", "",
         "Read by rule from every page except docket sheets, independent of the coders. An observation says that a cited sentence names a "
         "listed platform, refers to a service by a placeholder (\"Website A\", name withheld, a label that means nothing outside its "
         "case), uses a generic description of an online service (\"social media application\"), or states a codebook feature phrase. It "
         "does not say anyone used it, and a withheld name is not evidence of anonymity or of any feature. A relationship exists only "
         "where a published act's own sentence states the means; a generic description is never tied to an act.", "", "| Content | Count |", "|---|---:|"]
    L += [f"| {k} | {v} |" for k, v in ob["counts"].items()] + [""]
    v = ob.get("validation")
    if v:
        L += [f"**Reviewed on the real text** by {v['reviewer'] or 'the maintainer'} on {v['reviewed_on']} ({v['note']}):", "",
              "| Stratum | Reviewed | Term is in the sentence as cited | Meaning: yes / no / unclear | Meaning yes, 95% interval |", "|---|---:|---:|---:|---|"]
        L += [f"| {k} | {x['reviewed']} | {x['grounded']} | {x['meaning_yes']} / {x['meaning_no']} / {x['meaning_unclear']} | "
              f"{x['meaning_yes_interval_95'][0]} to {x['meaning_yes_interval_95'][1]} |" for k, x in v["strata"].items()] + [""]
    else:
        L += ["**Not yet reviewed on the real text.** A stratified local packet (`python -m state_machines.observations.validation packet`) "
              "covers every relationship, every feature observation and a sample of platform observations; its score is printed here once a "
              "reviewer has answered it.", ""]
    if ob.get("reference"):
        L += ["On the reference cases (another coding, not truth): " + "; ".join(f"{k} {v}" for k, v in ob["reference"].items()) + ".", ""]
    for q in ob["queries"].values():
        L += [f"### {q['title']}", "", "```sparql", q["sparql"], "```", "", "| " + " | ".join(q["columns"]) + " |", "|" + "---|" * len(q["columns"])]
        L += ["| " + " | ".join(row) + " |" for row in q["rows"][:40]]
        if len(q["rows"]) > 40:
            L.append(f"\n{len(q['rows']) - 40} more rows.")
        L.append("")
    return L


_OBS_ROWS = [("gold platform mentions found", "platform_mentions_found"), ("gold feature statements found", "feature_statements_found"),
             ("observed platforms the gold names in that sentence", "platform_observations_gold_names"),
             ("observed feature phrases the gold codes as an affordance there", "feature_observations_gold_codes_as_affordance"),
             ("relationships that the gold also holds", "relationships_correct"),
             ("relationships to the right platform, wrong kind", "relationships_right_platform_wrong_kind"),
             ("relationships to a platform the gold says is only named", "relationships_platform_only_named_in_gold"),
             ("relationships on an act that is not a gold act", "relationships_on_act_not_in_gold"),
             ("gold relationships found, on published acts", "gold_relationships_found_on_published_acts"),
             ("observations outside gold act sentences (not judged)", "observations_outside_gold_acts")]


def _benchmark_md(results: dict) -> list:
    L = []
    if not results:
        return L
    L += ["## Accuracy on the synthetic benchmark", "",
          "Scores per rule version and split. `resolved` is what a machine release publishes; `resolved_2b` is the candidate cue rule, "
          "not released. Synthetic pages are cleaner than real filings: none of this is accuracy on the real cases.", ""]
    observed = {k: v for k, v in results.items() if k.startswith("observe-")}
    results = {k: v for k, v in results.items() if k not in observed}
    if observed:
        splits = sorted(observed, key=lambda k: ["dev", "heldout", "confirm"].index(k.rsplit(".", 1)[1]))
        L += ["### Observation layer (" + ", ".join(sorted({k.rsplit('.', 1)[0] for k in observed})) + ")", "",
              "Platform names and feature terms are kept verbatim in every split, so these rates measure finding listed terms in new sentence "
              "constructions, not recognising unlisted wording.", "",
              "| Measure | " + " | ".join(_SPLITS.get(k.rsplit(".", 1)[1], k).split(" (")[0] for k in splits) + " |", "|---|" + "---:|" * len(splits)]
        L += [f"| {label} | " + " | ".join(_cell(observed[k].get(field)) for k in splits) + " |" for label, field in _OBS_ROWS] + [""]
    for key, systems in results.items():
        version, split = key.rsplit(".", 1)
        note = systems.get("_note")
        cols = [k for k in ("coder_A", "coder_B", "resolved", "resolved_2b") if k in systems]
        L += [f"### {version}, {_SPLITS.get(split, split)}", ""] + ([note, ""] if note else [])
        L += ["| Measure | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
        for label, get in _ROWS:
            cells = [_cell(get(systems[k])) for k in cols]
            if any(cells):
                L.append(f"| {label} | " + " | ".join(cells) + " |")
        tags = sorted({t for k in cols for t in systems[k].get("by_tag", {})})
        if tags and "resolved" in systems:
            L += ["", "Recall of the released coding by hard-case tag: " +
                  "; ".join(f"{t} {_cell(systems['resolved']['by_tag'][t])}" for t in tags if t in systems["resolved"]["by_tag"]) + ".", ""]
        L.append("")
    return L


def markdown(r: dict) -> str:
    t = r["totals"]
    L = [f"# Run report: {r['release']}", "",
         f"Review mode **{r['review_mode']}**: two local models coded every case independently; a fixed rule published what both coded. "
         "Nothing here is human-adjudicated. Reliability is agreement between the coders on these cases; benchmark accuracy is measured "
         "on synthetic records ([benchmark](../../benchmark/README.md)). Neither is accuracy on these cases.", "",
         "## What is published", "", "| Content | Count |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in (r.get("published") or {}).items()] + [
         "", "Order between acts comes mostly from cited dates; stated order is published only where a sentence names the earlier act "
         "or follows it directly. An act with no date and no stated order is unordered, not placed.", "",
         "## Models", "", "| Coder | Model | Digest | Quantization |", "|---|---|---|---|"]
    for name, spec in r["models"]["coders"].items():
        L.append(f"| {name} | `{spec['model']}` | `{spec['digest'][:19]}…` | {spec.get('quantization', '')} |")
    L += ["", f"Inference: `{json.dumps(r['models']['options'])}`; runtime `{json.dumps(r['models']['runtime'].get('env', {}))}`; prompt `{r['models'].get('prompt', {}).get('version')}`.", "",
          "## Cases", "", f"{t.get('cases published', 0)} published, {t.get('cases not published', 0)} not published.", "",
          "| Case | Published | Events | Relations | Coder A acts | Coder B acts | Matched | Action κ | SHACL |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for cid, c in r["cases"].items():
        res = c.get("resolution") or {}
        ev = (c.get("agreement_model_coded") or {}).get("events", {})
        kap = (c.get("agreement_model_coded") or {}).get("action_code", {}).get("kappa", "")
        L.append(f"| `{cid}` | {'yes' if c['published'] else 'no: ' + str(c.get('failed'))[:60]} | {res.get('published: events both coders coded', '')} | "
                 f"{res.get('published: relations both coders asserted', '')} | {ev.get('coder_a', '')} | {ev.get('coder_b', '')} | {ev.get('matched', '')} | "
                 f"{kap} | {c.get('shacl', '')} |")
    L += ["", "## Coverage and drops", "", "| Measure | Count |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in t.items() if k.startswith("coder_")]
    rel = r["reliability_real_cases"]
    L += ["", "## Reliability on the real cases", "", f"```json\n{json.dumps(rel, indent=1)}\n```", ""]
    L += _observed_md(r.get("observed") or {})
    L += _benchmark_md(r.get("benchmark") or {})
    ref = r.get("reference_real_cases")
    if ref:
        L += ["## Agreement with reference coding of real cases", "",
              f"Cases {', '.join('`' + c + '`' for c in ref['released']['cases'])} were coded earlier by two agent coders of a larger "
              "model (their agreed coding, not adjudicated). For each non-procedure act published here: did the reference code an act "
              "in the same sentence, and did it give the same action code there. The reference is another coding and does not code "
              "every act; this is agreement, not accuracy.", "", "| Measure | Released | Candidate 2b |", "|---|---:|---:|"]
        keys = sorted(set(ref["released"]["counts"]) | set(ref.get("candidate_2b", {}).get("counts", {})))
        for k in keys:
            L.append(f"| {k} | {ref['released']['counts'].get(k, 0)} | {ref.get('candidate_2b', {}).get('counts', {}).get(k, '')} |")
        L.append("")
    ps = r["privacy_scan"]
    L += ["## Privacy", "", f"{ps['files']} committed files checked against {ps['deny_terms']} deny-list terms (names from the case captions) "
          f"and {ps['quotes']} stored quotes; {ps.get('listed_values', 0)} platform names and feature words checked against the fixed lists they must "
          f"come from: **{ps['hits']} hits**.", ""]
    L += ["## Runtime", "", f"```json\n{json.dumps(r['runtime_per_model'], indent=1)}\n```", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("release_id")
    ap.add_argument("--auto", type=Path, default=E.REPO_ROOT / "local" / "auto")
    ap.add_argument("--pilot", type=Path, help="reference bundles of real cases (<case_id>.json) to compare the release with")
    a = ap.parse_args(argv)
    r = build(a.release_id, a.auto, a.pilot)
    (DATA / a.release_id / "report.json").write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8")
    (DATA / a.release_id / "REPORT.md").write_text(markdown(r) + "\n", encoding="utf-8")
    print(DATA / a.release_id / "REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
