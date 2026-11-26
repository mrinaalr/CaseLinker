"""Case x named-platform biadjacency matrices for the BiCM run (section 10). Read-only.

  .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/cooc/build_matrix.py

Input: ../build/records.csv (the committed AfH build's Q1 records, fresh corpus) and the registry.
Edge: a Q1 record whose status is `specific` (a named platform), kept only while the platform is
open: dropped when the case's publication year is after the registry `until` year.
Two edge sets: `stated` (line-wrap primary tier = stated) and `all` (stated, inferred, named-only).
Writes matrix_<set>.json: rows (case ids), cols (platforms), edges, case sources, platform classes.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir() / "cooc"
OUT.mkdir(parents=True, exist_ok=True)
REPO = AI.REPO
reg = yaml.safe_load((REPO / "ontology/platform_affordance_evidence/afh_manifest/config/platforms.yaml").read_text())["platforms"]
cb = yaml.safe_load((REPO / "ontology/platform_affordance_evidence/afh_manifest/config/codebook.yaml").read_text())


def find(node, key):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            r = find(v, key)
            if r is not None:
                return r
    return None


CLASS_OF_CAP = {spec["capability"]: name for name, spec in find(cb, "classes").items()}
recs = list(csv.DictReader(open(OUT.parent / "build/records.csv")))
log = Counter()
for edge_set, tiers in (("stated", {"stated"}), ("all", {"stated", "inferred", "named_only"})):
    edges, source = set(), {}
    for r in recs:
        if r["status"] != "specific":
            continue
        log[f"{edge_set}:specific_records"] += 1
        if r["tier_linewrap"] not in tiers:
            continue
        until = (reg.get(r["platform"]) or {}).get("until")
        if until is not None and int(r["pub_year"]) > int(until):
            log[f"{edge_set}:closed_after_until"] += 1
            continue
        edges.add((r["case_id"], r["platform"]))
        source[r["case_id"]] = r["source"]
    rows = sorted({c for c, _ in edges})
    cols = sorted({p for _, p in edges})
    classes = {}
    for p in cols:
        caps = (reg.get(p) or {}).get("capabilities") or {}
        classes[p] = sorted(CLASS_OF_CAP[c] for c, m in caps.items()
                            if isinstance(m, dict) and m.get("default_on") and c in CLASS_OF_CAP)
    (OUT / f"matrix_{edge_set}.json").write_text(json.dumps({
        "afh_inputs": AI.inputs_label(OUT.parent),
        "edge_set": edge_set, "rows": rows, "cols": cols, "edges": sorted(edges),
        "case_source": {c: source[c] for c in rows}, "platform_default_on_classes": classes,
        "platform_until": {p: (reg.get(p) or {}).get("until") for p in cols},
    }, indent=0) + "\n")
    log[f"{edge_set}:cases"] = len(rows)
    log[f"{edge_set}:platforms"] = len(cols)
    log[f"{edge_set}:edges"] = len(edges)
print(json.dumps(dict(log), indent=1))
