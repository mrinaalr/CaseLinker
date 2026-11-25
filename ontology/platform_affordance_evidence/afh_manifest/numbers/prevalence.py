"""Prevalence (section 11): class prevalence over Q1 records by evidence tier and level; 1 vs 2+ platforms per case.
Reads build/records.csv and cooc/matrix_*.json. Writes prevalence.json."""
import collections, csv, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
recs = list(csv.DictReader(open(OUT / "build/records.csv")))
CLASSES = ["Anonymity", "Ephemerality", "ContactDiscovery", "UnmonitoredCommunication", "DistributionInfrastructure", "GenerativeSynthesis"]
LEVELS = ["A", "B", "I", "C"]
TIERS = ["stated", "inferred", "named_only"]
tier_n = collections.Counter(r["tier_linewrap"] for r in recs)
named = [r for r in recs if r["status"] == "specific"]
out = {"records": len(recs), "records_by_tier": dict(tier_n), "named_platform_records": len(named),
       "levels": {"A": "registry default_on on the platform, window (since..ended) open at publication",
                  "A_any": "capability available on the platform at publication (registry window since..ended open), default_on or not; B, I and C nest within it", "B": "capability-relevant conduct", "I": "inferred facilitation (B on a default_on platform with its window open, or C)", "C": "instrumental (stated in the platform sentence)"},
       "classes": {}}
for c in CLASSES:
    row = {}
    for lv in LEVELS + ["A_any"]:
        hit = [r for r in recs if r.get(f"{c}.{lv}") in ("1", "True", "true")]   # records.csv carries A and A_any
        row[lv] = {"records": len(hit), "share_of_q1_records": round(len(hit) / len(recs), 4),
                   "by_tier": {t: {"records": sum(1 for r in hit if r["tier_linewrap"] == t),
                                   "share_of_tier": round(sum(1 for r in hit if r["tier_linewrap"] == t) / tier_n[t], 4)} for t in TIERS}}
    out["classes"][c] = row
cases = {}
for s in ("stated", "all"):
    m = json.loads((OUT / f"cooc/matrix_{s}.json").read_text())
    deg = collections.Counter(c for c, _ in m["edges"])
    cases[s] = {"cases": len(deg), "exactly_1": sum(1 for v in deg.values() if v == 1), "two_plus": sum(1 for v in deg.values() if v >= 2)}
out["named_platforms_per_case"] = cases
out["afh_inputs"] = AI.inputs_label(OUT)
(OUT / "prevalence.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({"records": out["records"], "by_tier": out["records_by_tier"], "per_case": cases}, indent=0))
for c, row in out["classes"].items():
    print(c, {lv: (row[lv]["records"], row[lv]["by_tier"]["stated"]["records"], row[lv]["by_tier"]["inferred"]["records"], row[lv]["by_tier"]["named_only"]["records"]) for lv in LEVELS})
