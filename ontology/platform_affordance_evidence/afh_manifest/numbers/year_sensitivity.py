"""Sensitivity of every year-dependent result to the publication-year flags (year_evidence.json).

  DATABASE_URL='' REDIS_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/year_sensitivity.py

Reruns the harm release (launch-cohort recurrence, publication-era persistence, affordance x harm tables closed
at registry end dates) with every flagged record left out, and recomputes prevalence by class and level and the
Q1 size from build/records.csv without them. Writes year_sensitivity.json: both values side by side, and every
verdict (recurs / persists / present / qualifies) that differs. Read-only; outputs go to a temporary folder.
"""
import csv
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
sys.path.insert(0, str(AI.AFH))
from afhq1 import harm_release as hr  # noqa: E402

J = lambda p: json.loads(Path(p).read_text())  # noqa: E731
flagged = frozenset(f["case_id"] for f in J(OUT / "year_evidence.json")["flags"])

hr.INPUTS = {k: v for k, v in AI.run_inputs(OUT).items() if k != "afh_2_0_reference"}
hr.CLOSE_AT_END = True
hr.EXCLUDE_CASES = flagged
with tempfile.TemporaryDirectory() as tmp:
    hr.OUT = Path(tmp)
    hr.build(AI.DB, log=lambda *_: None)
    without = {name: J(Path(tmp) / name) for name in
               ("recurrence_by_generation.json", "affordance_harm_strict.json", "affordance_harm_broad.json")}
hr.EXCLUDE_CASES = frozenset()
with_ = {name: J(OUT / "harm_closed" / name) for name in without}

changes, side = [], {}


def compare(label, a, b, verdict=False):
    side[label] = [a, b]
    if verdict and a != b:
        changes.append({"result": label, "with_flagged": a, "without_flagged": b})


for kind, key, bins_key, flag in (("launch_cohort", "recurrence by launch cohort", "generations", "recurs"),
                                  ("publication_era", "persistence by publication era", "eras", "persists")):
    a, b = with_["recurrence_by_generation.json"][key], without["recurrence_by_generation.json"][key]
    for g in a[bins_key]:
        compare(f"{kind}.{g}.coded_cases", a[bins_key][g]["coded_cases"], b[bins_key][g]["coded_cases"])
        compare(f"{kind}.{g}.qualifies", a[bins_key][g]["qualifies"], b[bins_key][g]["qualifies"], verdict=True)
    for c in a["classes"]:
        compare(f"{kind}.{c}.{flag}", a["classes"][c][flag], b["classes"][c][flag], verdict=True)
        for g, cell in a["classes"][c][bins_key].items():
            other = b["classes"][c][bins_key][g]
            n = "stated_tier_default_on_cases" if kind == "launch_cohort" else "cases"
            compare(f"{kind}.{c}.{g}.cases", cell[n], other[n])
            compare(f"{kind}.{c}.{g}.present", cell["present"], other["present"], verdict=True)

for t in ("strict", "broad"):
    a, b = with_[f"affordance_harm_{t}.json"], without[f"affordance_harm_{t}.json"]
    for c, row in a["counts"].items():
        for h, v in row.items():
            compare(f"harm_{t}.{c}.{h}", v, b["counts"][c][h])

recs = list(csv.DictReader(open(OUT / "build" / "records.csv")))
kept = [r for r in recs if r["case_id"] not in flagged]
compare("q1.cases", len({r["case_id"] for r in recs}), len({r["case_id"] for r in kept}))
compare("q1.records", len(recs), len(kept))
classes = sorted({k.split(".")[0] for k in recs[0] if k.endswith(".A_any")})
for c in classes:
    for lv in ("A", "A_any", "B", "I", "C"):
        compare(f"prevalence.{c}.{lv}", sum(r[f"{c}.{lv}"] == "1" for r in recs), sum(r[f"{c}.{lv}"] == "1" for r in kept))

(OUT / "year_sensitivity.json").write_text(json.dumps({
    "flagged_left_out": len(flagged),
    "flagged_in_q1": len({r["case_id"] for r in recs} & flagged),
    "verdict_changes": changes,
    "values_with_and_without_flagged": side,
    "afh_inputs": AI.inputs_label(OUT),
}, indent=1, sort_keys=True) + "\n")
print(json.dumps({"flagged_left_out": len(flagged), "verdict_changes": len(changes)}))
