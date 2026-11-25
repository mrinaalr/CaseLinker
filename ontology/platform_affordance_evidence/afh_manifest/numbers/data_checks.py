"""Data checks: boilerplate app lists, the Facebook-in-Messenger double tag, BiCM power. Read-only.

  DATABASE_URL='' REDIS_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/data_checks.py
Writes data_checks.json.
"""
import collections
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
sys.path.insert(0, str(AI.AFH))
from afhq1 import pipeline as pl  # noqa: E402

pe = pl.evidence_module()
db = sqlite3.connect(f"file:{AI.DB}?mode=ro", uri=True)
text = {i: re.sub(r"[ \t]+", " ", t or "") for i, t in db.execute("select id, json_extract(raw_data,'$.case_text') from cases")}
recs = list(csv.DictReader(open(OUT / "build/records.csv")))
manifest = json.loads((OUT / "build/manifest.json").read_text())["platforms"]
out = {}

# ---- 1. boilerplate-only platform tags
def boiler_only(cid: str, platform: str) -> bool:
    sents = pe.sentences_with_platform(pe.repair_line_wraps(text[cid]).split("\n"), platform) or []
    sents = [s for s in sents if s.strip()]
    if not sents:
        return False                      # never named in a sentence (alias / metadata only): not this question
    names = [r["platform"] for r in by_case_all[cid]]
    def is_list(s):
        k = sum(1 for n in set(names) if re.search(r"\b" + re.escape(n.split(" / ")[0]) + r"\b", s, re.I))
        return pe.is_awareness_or_list_framing(s) or (k >= 3 and pe.is_enumeration_only(s, platform))
    return all(is_list(s) for s in sents)


by_case_all = collections.defaultdict(list)
for r in recs:
    by_case_all[r["case_id"]].append(r)
flag = {(r["case_id"], r["platform"]): boiler_only(r["case_id"], r["platform"]) for r in recs}
by_case = collections.defaultdict(list)
for r in recs:
    by_case[r["case_id"]].append(r)
only = sorted(c for c, rs in by_case.items() if all(flag[(r["case_id"], r["platform"])] for r in rs))
named_only_cases = sorted(c for c, rs in by_case.items()
                          if [r for r in rs if r["status"] == "specific"]
                          and all(flag[(r["case_id"], r["platform"])] for r in rs if r["status"] == "specific"))
brecs = [r for r in recs if flag[(r["case_id"], r["platform"])]]
man_hit = collections.Counter()
for r in brecs:
    if r["platform"] in manifest and r["tier_linewrap"] in ("stated", "inferred"):
        man_hit[r["platform"]] += 1
out["1_boilerplate"] = {
    "rule": "every sentence naming the platform is awareness/list framing (is_awareness_or_list_framing), or names 3+ of the case's platforms and is a bare enumeration (is_enumeration_only)",
    "records_boilerplate_only": len(brecs),
    "records_by_tier_linewrap": dict(collections.Counter(r["tier_linewrap"] for r in brecs)),
    "records_by_tier1": dict(collections.Counter(r["tier"] for r in brecs)),
    "q1_cases_all_tags_boilerplate": len(only),
    "q1_cases_all_named_platform_tags_boilerplate": len(named_only_cases),
    "manifest_platforms_with_boilerplate_use_documented_records": dict(man_hit),
    "sources_of_all_boilerplate_cases": dict(collections.Counter(r["source"] for c in only for r in by_case[c][:1]).most_common()),
}

# ---- 2. Facebook inside "Facebook Messenger" (corrected at load by afhq1/labels.py; counted here from the raw DB labels)
from afhq1.labels import facebook_only_inside_messenger  # noqa: E402
raw_text = {i: t or "" for i, t in db.execute("select id, json_extract(raw_data,'$.case_text') from cases")}
raw_labels = {i: json.loads(p or "[]") for i, p in db.execute("select id, platforms_used from cases")}
corpus_fb = [i for i, ls in raw_labels.items() if "Facebook" in ls]
corpus_dbl = sorted(i for i in corpus_fb if facebook_only_inside_messenger(raw_labels[i], raw_text[i]))
q1_ids = set(by_case)
mf = manifest.get("Facebook", {})
out["2_facebook"] = {
    "rule": "a 'Facebook' tag whose only textual source is the phrase 'Facebook Messenger' becomes 'Facebook Messenger' (afhq1/labels.py)",
    "applied": "at load, in every AfH output (snapshot cases, Q1 records, manifest, harm tables, co-occurrence); the DB is unchanged",
    "corpus_cases_tagged_facebook_raw": len(corpus_fb), "corpus_double_tags": len(corpus_dbl),
    "corpus_cases_tagged_facebook_corrected": len(corpus_fb) - len(corpus_dbl),
    "q1_double_tags": len(set(corpus_dbl) & q1_ids),
    "manifest_facebook_total_cases": mf.get("cases"), "manifest_facebook_stated_cases": mf.get("cases_by_tier", {}).get("stated"),
    "double_tag_case_ids": corpus_dbl,
}

# ---- 3. BiCM power: cases naming 2+ platforms
power = {}
for s in ("stated", "all"):
    m = json.loads((OUT / f"cooc/matrix_{s}.json").read_text())
    deg = collections.Counter(c for c, _ in m["edges"])
    power[s] = {"cases": len(deg), "cases_2plus": sum(1 for v in deg.values() if v >= 2),
                "cases_3plus": sum(1 for v in deg.values() if v >= 3),
                "degree_distribution": dict(sorted(collections.Counter(deg.values()).items()))}
out["3_bicm_power"] = power
out["afh_inputs"] = AI.inputs_label(OUT)
(OUT / "data_checks.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "double_tag_case_ids"} for k, v in out.items()}, indent=1))
