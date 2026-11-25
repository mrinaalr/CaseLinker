"""Co-occurrence matrices without app-list boilerplate (section 10). Read-only; run after build_matrix.py.

  .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/cooc/build_variants.py

stated_clean / all_clean: matrix_stated / matrix_all without the edges (case, platform) whose every
sentence naming the platform matches a pattern in config/cooc_boilerplate_sentences.yaml. The
Facebook-in-Messenger correction is already applied when platform labels are loaded (afhq1/labels.py).
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir() / "cooc"
sys.path.insert(0, str(AI.AFH))
from afhq1 import pipeline as pl  # noqa: E402

CFG = yaml.safe_load((AI.AFH / "config" / "cooc_boilerplate_sentences.yaml").read_text())
PATTERNS = [(p["id"], re.compile(p["regex"], re.I)) for p in CFG["patterns"]]
pe = pl.evidence_module()
db = sqlite3.connect(f"file:{AI.DB}?mode=ro", uri=True)


def text_of(cid: str) -> str:
    row = db.execute("select json_extract(raw_data,'$.case_text') from cases where id=?", (cid,)).fetchone()
    return (row[0] if row else "") or ""


def boilerplate_only(cid: str, platform: str):
    """The matched pattern ids if every sentence naming the platform is boilerplate, else None."""
    sents = [s for s in (pe.sentences_with_platform(pe.repair_line_wraps(text_of(cid)).split("\n"), platform) or []) if s.strip()]
    if not sents:
        return None
    hits = []
    for s in sents:
        ids = [i for i, rx in PATTERNS if rx.search(s)]
        if not ids:
            return None
        hits += ids
    return sorted(set(hits))


def write(name, base):
    m = json.loads((OUT / f"matrix_{base}.json").read_text())
    kept, dropped = [], []
    for c, p in m["edges"]:
        why = boilerplate_only(c, p)
        (dropped if why else kept).append([c, p] + ([why] if why else []))
    edges = sorted([c, p] for c, p in kept)
    rows, cols = sorted({c for c, _ in edges}), sorted({p for _, p in edges})
    m.update(edge_set=name, rows=rows, cols=cols, edges=edges,
             case_source={c: m["case_source"][c] for c in rows},
             platform_default_on_classes={p: m["platform_default_on_classes"][p] for p in cols},
             platform_until={p: m["platform_until"][p] for p in cols},
             boilerplate_rule=CFG["version"], removed_edges=len(dropped),
             removed=sorted(dropped), afh_inputs=AI.inputs_label(OUT.parent))
    (OUT / f"matrix_{name}.json").write_text(json.dumps(m, indent=0) + "\n")
    return {"edges": len(edges), "removed_edges": len(dropped), "cases_touched": len({d[0] for d in dropped})}


print(json.dumps({"stated_clean": write("stated_clean", "stated"), "all_clean": write("all_clean", "all")}, indent=1))
