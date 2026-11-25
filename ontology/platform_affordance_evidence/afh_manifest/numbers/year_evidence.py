"""Publication-year evidence: the corrections table and the flag list. Read-only; text-free output.

  DATABASE_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/year_evidence.py

Corrections: afhq1/labels.year_corrections (>= 2 of a record's own publication evidence fields agree on
another year and none supports the stored one). Flags: records whose stored year conflicts with their own
fields by any of four signals, whether or not they are corrected:
  A  the stored year is a biography date's year and no event or publication date's year
  B  an event or publication date is 2+ years after the stored year (the release predates its own events)
  C  every stated publication date is 2+ years from the stored year
  D  the case-id year is 2+ years from the stored year
Writes year_evidence.json: ids, years and signal letters only.
"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
sys.path.insert(0, str(AI.AFH))
from afhq1.labels import dated_assertions, year_corrections, year_evidence  # noqa: E402

db = sqlite3.connect(f"file:{AI.DB}?mode=ro", uri=True)
dated = dated_assertions(db)
fixes = year_corrections(db)
flags = []
for cid, year, source_file in db.execute(
        "select id, cast(json_extract(raw_data,'$.year') as int), json_extract(raw_data,'$.source_file') from cases order by id"):
    if year is None:
        continue
    ev = year_evidence(cid, source_file, dated.get(cid, {}))
    happened = set(ev["event"]) | set(ev["publication"])
    signals = [s for s, hit in (
        ("A", year in ev["biography"] and year not in happened),
        ("B", bool(happened) and max(happened) > year + 1),
        ("C", bool(ev["publication"]) and min(abs(p - year) for p in ev["publication"]) > 1),
        ("D", ev["id"] is not None and abs(ev["id"] - year) > 1),
    ) if hit]
    if signals:
        flags.append({"case_id": cid, "stored_year": year,
                      "corrected_year": fixes[cid]["corrected"] if cid in fixes else None, "signals": signals})

(OUT / "year_evidence.json").write_text(json.dumps({
    "rule": ("a stored publication year is corrected when >= 2 of the record's publication evidence fields (case-id year, "
             "compilation-file year, stated publication dates) agree on another year and none supports the stored one; "
             "an event date supports the stored year only when no publication date is stated"),
    "corrections": fixes,
    "corrected_n": len(fixes),
    "flags": flags,
    "flagged_n": len(flags),
    "flagged_still_uncorrected_n": sum(1 for f in flags if f["corrected_year"] is None),
    "afh_inputs": AI.inputs_label(OUT),
}, indent=1, sort_keys=True) + "\n")
print(json.dumps({"corrected": len(fixes), "flagged": len(flags)}))
