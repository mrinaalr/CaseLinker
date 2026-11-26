"""Platform map data for one AfH release: the page's records, from the frozen build. Read-only on the DB.

  DATABASE_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/platform_map.py

One record per Q1 case and platform label from build/records.csv, with the primary tier (`tier_linewrap`)
as `stated_vs_inferred`, so the page counts what numbers.md counts. Case ids only: no quotes, no text.
`platform_type` (the page's lane and surface) is carried from the published evidence file.

On the AfH 2.0 inputs this writes ontology/platform_affordance_evidence/platform_affordance_evidence_afh-2.0.json,
the file /visualization loads by default (?release=afh2.0). Any other inputs write platform_map.json into the
run's output folder, so they cannot replace the pinned release file.
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()

PUBLISHED = AI.REPO / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence.json"
PINNED = AI.REPO / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence_afh-2.0.json"


def build() -> dict:
    inventory = json.loads((OUT / "build" / "inventory.json").read_text())
    rows = list(csv.DictReader(open(OUT / "build" / "records.csv", newline="")))
    types = {}
    for rec in json.loads(PUBLISHED.read_text())["records"]:
        types.setdefault(rec["platform"], rec.get("platform_type") or "Unknown")
    records = [{"case_id": r["case_id"], "platform": r["platform"], "platform_type": types.get(r["platform"], "Unknown"),
                "stated_vs_inferred": r["tier_linewrap"]}
               for r in sorted(rows, key=lambda r: (r["platform"], r["case_id"]))]
    label = AI.inputs_label(OUT)
    return {
        "_meta": {
            "release": "afh2.0" if label.get("afh_2_0_snapshot") else "other inputs",
            "afh_inputs": label,
            "cases_processed": len({r["case_id"] for r in rows}),
            "case_platform_pairs": len(records),
            "tier_field": "stated_vs_inferred holds the primary tier (tier_linewrap), as numbers.md counts it",
            "named_platforms": len(inventory["labels"]["specific"]),
            "label_status": inventory["labels"],
            "ids_only": True,
            "source": "numbers/build/records.csv, numbers/build/inventory.json (numbers/platform_map.py)",
        },
        "records": records,
    }


if __name__ == "__main__":
    data = build()
    dest = PINNED if data["_meta"]["afh_inputs"].get("afh_2_0_snapshot") else OUT / "platform_map.json"
    dest.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"written": dest.name, "records": len(data["records"]), "named_platforms": data["_meta"]["named_platforms"]}))
