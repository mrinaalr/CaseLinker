"""The run report of a machine-coded release: what was coded, how well, and what was left out.

    python -m state_machines.coding.report <release_id> [--auto local/auto] [--bench local/bench]

Writes ``state_machines/data/<release_id>/report.json`` (for tools and the review agent) and
``REPORT.md`` (for people). Numbers only: no quotes, no names, no coder text.

Sections: the pinned models and inference settings; per case, whether it was published, its
published acts and relations, its failures and reasons; page coverage by route (model, docket
parser, skipped form pages, skipped by the selective second pass); acts dropped and why;
inter-coder reliability on model-coded acts; held-out benchmark accuracy; runtime per page.
Reliability is agreement between the two coders on the real cases; benchmark accuracy is on
synthetic records. Neither is accuracy on the real cases.
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


def build(release_id: str, auto: Path, bench: Path) -> dict:
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
    bench_path = bench / "reports" / "benchmark.heldout.json"
    benchmark = {k: v["overall"] for k, v in json.loads(bench_path.read_text(encoding="utf-8")).items()} if bench_path.is_file() else None
    from state_machines.graphs.release import privacy_scan
    privacy = privacy_scan(release_id, E.text_root())
    return {"release": release_id, "review_mode": manifest.get("review_mode"), "models": C.MODELS,
            "privacy_scan": {k: (len(v) if k == "hits" else v) for k, v in privacy.items()},
            "runtime_per_model": model_stats(), "totals": dict(sorted(totals.items())), "reliability_real_cases": reliability,
            "benchmark_heldout": benchmark, "cases": cases}


def markdown(r: dict) -> str:
    t = r["totals"]
    L = [f"# Run report: {r['release']}", "",
         f"Review mode **{r['review_mode']}**: two local models coded every case independently; a fixed rule published what both coded. "
         "Nothing here is human-adjudicated. Reliability is agreement between the coders on these cases; benchmark accuracy is measured "
         "on synthetic records ([benchmark](../../benchmark/README.md)). Neither is accuracy on these cases.", "",
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
    if r["benchmark_heldout"]:
        L += ["## Accuracy on the held-out synthetic benchmark", ""]
        for who, s in r["benchmark_heldout"].items():
            L.append(f"- **{who}:** event F1 {s['events']['f1']}, recall {s['events']['recall']['rate']}, precision {s['events']['precision']['rate']}; "
                     f"action {s['action']['rate']}; actor {s['actor']['rate']}; dates {s['dates']['rate']}; order recall {s['order']['recall']['rate']}; "
                     f"level C recall {s['level_c']['recall']['rate']}; harms recall {s['harms']['recall']['rate']}; standing {s['standing']['rate']}")
        L.append("")
    ps = r["privacy_scan"]
    L += ["## Privacy", "", f"{ps['files']} committed files checked against {ps['deny_terms']} deny-list terms and {ps['quotes']} stored quotes: "
          f"**{ps['hits']} hits**.", ""]
    L += ["## Runtime", "", f"```json\n{json.dumps(r['runtime_per_model'], indent=1)}\n```", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("release_id")
    ap.add_argument("--auto", type=Path, default=E.REPO_ROOT / "local" / "auto")
    ap.add_argument("--bench", type=Path, default=E.REPO_ROOT / "local" / "bench")
    a = ap.parse_args(argv)
    r = build(a.release_id, a.auto, a.bench)
    (DATA / a.release_id / "report.json").write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8")
    (DATA / a.release_id / "REPORT.md").write_text(markdown(r) + "\n", encoding="utf-8")
    print(DATA / a.release_id / "REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
