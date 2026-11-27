"""Sensitivity of the AfH 2.0 recurrence / persistence verdicts (numbers.md section 2) and level-A results.

  DATABASE_URL='' REDIS_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/afh_sensitivity.py

Run by run_all.sh after run_afh.py (it needs the analysis DB and harm_closed/). Each variant reruns
harm_release.build in a temporary folder with one change, and compares every verdict with the committed
harm_closed/ run. Nothing committed is modified; the primary rules are unchanged.

  unsourced_default_on   the registry rows that are default_on but cite no source (config/platforms.yaml,
                         sources == 0) are treated as not default_on. Also recomputes level-A prevalence
                         (build/records.csv) and the affordance x harm tables without them.
  thresholds             n_min (qualifying bin) in {20, 30, 50} x k (class present) in {2, 3, 5}.
  single_platform        each platform that contributes a stated-tier default-on row, left out in turn
                         (all its default_on rows off).

Not run here, because each needs a method decision first: re-auditing every default_on row under the
primary-interaction rule (README, Operational definitions) needs a per-row judgement of each platform's
primary interaction; "later-stage records" has no definition in this code.

Writes afh_sensitivity.json.
"""
import csv
import dataclasses
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
sys.path.insert(0, str(AI.AFH))
import yaml  # noqa: E402
from afhq1 import harm_release as hr  # noqa: E402
from afhq1 import pipeline as pl  # noqa: E402

J = lambda p: json.loads(Path(p).read_text())  # noqa: E731
hr.INPUTS = {k: v for k, v in AI.run_inputs(OUT).items() if k != "afh_2_0_reference"}
hr.CLOSE_AT_END = True
BASE = {n: J(OUT / "harm_closed" / n) for n in
        ("recurrence_by_generation.json", "affordance_harm_strict.json", "affordance_harm_broad.json")}
_registry = pl.platform_registry


def unsourced_rows() -> list:
    doc = yaml.safe_load((AI.AFH / "config" / "platforms.yaml").read_text())
    return sorted((p, c) for p, e in doc["platforms"].items() for c, v in (e.get("capabilities") or {}).items()
                  if v.get("default_on") and not v.get("sources"))


def patched(off: set):
    """platform_registry with default_on switched off for (platform, capability) pairs in `off`
    ((platform, None) switches off every class of that platform)."""
    def reg():
        out = {}
        for label, info in _registry().items():
            out[label] = dataclasses.replace(info, default_on={k: (v and (label, k) not in off and (label, None) not in off)
                                                               for k, v in info.default_on.items()})
        return out
    return reg


def run(off=frozenset(), n_min=hr.N_MIN, k=hr.K_PRESENT) -> dict:
    saved = (pl.platform_registry, hr.N_MIN, hr.K_PRESENT)
    pl.platform_registry, hr.N_MIN, hr.K_PRESENT = patched(set(off)), n_min, k
    try:
        with tempfile.TemporaryDirectory() as tmp:
            hr.OUT = Path(tmp)
            hr.build(AI.DB, log=lambda *_: None)
            return {n: J(Path(tmp) / n) for n in BASE}
    finally:
        pl.platform_registry, hr.N_MIN, hr.K_PRESENT = saved


def verdicts(res: dict) -> dict:
    """Every verdict and case count in numbers.md section 2."""
    out = {}
    for kind, key, bins_key, flag, n in (("cohort", "recurrence by launch cohort", "generations", "recurs", "stated_tier_default_on_cases"),
                                         ("era", "persistence by publication era", "eras", "persists", "cases")):
        r = res["recurrence_by_generation.json"][key]
        for g, b in r[bins_key].items():
            out[f"{kind}.{g}.coded_cases"] = b["coded_cases"]
            out[f"{kind}.{g}.qualifies"] = b["qualifies"]
        for c, row in r["classes"].items():
            out[f"{kind}.{c}.{flag}"] = row[flag]
            for g, cell in row[bins_key].items():
                out[f"{kind}.{c}.{g}.cases"] = cell[n]
                out[f"{kind}.{c}.{g}.present"] = cell["present"]
    return out


def is_verdict(key: str) -> bool:
    return key.endswith((".recurs", ".persists", ".present", ".qualifies"))


def diff(a: dict, b: dict) -> dict:
    changed = {k: [a[k], b.get(k)] for k in a if a[k] != b.get(k)}
    return {"verdicts_changed": {k: v for k, v in changed.items() if is_verdict(k)},
            "counts_changed": {k: v for k, v in changed.items() if not is_verdict(k)}}


base_v = verdicts(BASE)
report = {"afh_inputs": AI.inputs_label(OUT), "base": {"n_min": hr.N_MIN, "k": hr.K_PRESENT, "verdicts": {k: v for k, v in base_v.items() if is_verdict(k) and (".recurs" in k or ".persists" in k)}}}

# 0. control: an unchanged rerun must reproduce the committed run, or no variant below can be read
control = diff(base_v, verdicts(run()))
report["control_unchanged_rerun"] = {"reproduces_committed": not (control["verdicts_changed"] or control["counts_changed"]), **control}
if not report["control_unchanged_rerun"]["reproduces_committed"]:
    (OUT / "afh_sensitivity.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    sys.exit("control rerun does not reproduce harm_closed/: check AFH_DB is the analysis DB run_all.sh built")
print("control reproduces committed", flush=True)

# 1. unsourced default-on rows
rows = unsourced_rows()
res = run(off=frozenset(rows))
entry = {"rows_off": [f"{p}:{c}" for p, c in rows], "n_rows": len(rows), **diff(base_v, verdicts(res))}
for t in ("strict", "broad"):
    a, b = BASE[f"affordance_harm_{t}.json"]["counts"], res[f"affordance_harm_{t}.json"]["counts"]
    entry[f"harm_{t}_changed"] = {f"{c}.{h}": [v, b[c][h]] for c, row in a.items() for h, v in row.items() if v != b[c][h]}
recs = list(csv.DictReader(open(OUT / "build" / "records.csv")))
snake = lambda s: re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()  # noqa: E731
off = set(rows)
prev = {}
for col in sorted(k for k in recs[0] if k.endswith(".A")):
    cls = col.split(".")[0]
    before = sum(r[col] == "1" for r in recs)
    after = sum(r[col] == "1" and (r["platform"], snake(cls)) not in off for r in recs)
    prev[cls] = {"records_A_before": before, "records_A_after": after, "of_records": len(recs)}
entry["prevalence_level_A"] = prev
report["unsourced_default_on"] = entry
print("unsourced", len(entry["verdicts_changed"]), flush=True)

# 2. thresholds
grid = {}
for n_min in (20, 30, 50):
    for k in (2, 3, 5):
        if (n_min, k) == (hr.N_MIN, hr.K_PRESENT):
            continue
        grid[f"n_min={n_min},k={k}"] = diff(base_v, verdicts(run(n_min=n_min, k=k)))
        print("threshold", n_min, k, len(grid[f"n_min={n_min},k={k}"]["verdicts_changed"]), flush=True)
report["thresholds"] = grid

# 3. single-platform exclusions: platforms with a stated-tier record and a default_on class
reg = _registry()
contributing = sorted({r["platform"] for r in recs if r.get("tier_linewrap") == "stated"
                       and r["platform"] in reg and any(reg[r["platform"]].default_on.values())})
single = {}
for p in contributing:
    single[p] = diff(base_v, verdicts(run(off=frozenset({(p, None)}))))
    print("leave out", p, len(single[p]["verdicts_changed"]), flush=True)
report["single_platform"] = {"platforms_tested": len(contributing), "by_platform": single,
                             "platforms_whose_exclusion_changes_a_recurs_or_persists_verdict":
                                 sorted(p for p, d in single.items() if any(k.endswith((".recurs", ".persists")) for k in d["verdicts_changed"]))}
report["not_run"] = {
    "primary_interaction_reaudit": "needs a per-row classification of each platform's primary interaction under the README rule; a method decision, proposed, not run",
    "later_stage_records": "no definition of a stage record exists in this code; needs a definition before it can run",
}
(OUT / "afh_sensitivity.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
print(json.dumps({"unsourced_verdict_changes": len(report["unsourced_default_on"]["verdicts_changed"]),
                  "single_platform_tested": len(contributing),
                  "single_platform_changing_recurs_persists": report["single_platform"]["platforms_whose_exclusion_changes_a_recurs_or_persists_verdict"]}))
