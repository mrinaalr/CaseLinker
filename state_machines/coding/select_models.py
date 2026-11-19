"""Choose the coder models on evidence: speed and accuracy on dev benchmark cases only.

    python -m state_machines.coding.select_models <model> [...] [--cases 8] [--out local/select]

Each candidate codes the first N dev cases on its own (held-out cases are never used here). For
each model: seconds per model page, output tokens per second, and its accuracy against the gold
(events, actions, actors, dates, order, level C, harms). Models run one at a time and are unloaded
after. The chosen pair is then pinned in ``models.json``.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from state_machines.benchmark.score import score_dir, split_of
from state_machines.coding import coder as C

BENCH = Path(__file__).resolve().parents[1] / "benchmark" / "data"


def run(model: str, cases, out: Path) -> dict:
    d = out / model.replace(":", "_")
    d.mkdir(parents=True, exist_ok=True)
    cache = C.Cache()
    t0 = time.time()
    for case_id in cases:
        target = d / f"{case_id}.json"
        if target.is_file():
            continue
        bundle, quotes, log = C.code_case(case_id, "model:" + model, BENCH, cache)
        target.write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        (d / f"{case_id}.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    spec = C.candidate_spec(model)
    db = sqlite3.connect(str(C.CACHE))
    row = db.execute("SELECT COUNT(*), AVG(seconds), AVG(output_tokens), SUM(output_tokens)/SUM(output_seconds), AVG(prompt_seconds)"
                     " FROM calls WHERE digest=? AND prompt_version=? AND output_tokens IS NOT NULL", (spec["digest"], C.PROMPT_VERSION)).fetchone()
    C.unload_model(model)
    s = score_dir(d, "dev")["overall"]
    return {"model": model, "digest": spec["digest"], "family": spec["family"], "parameters": spec["parameters"],
            "calls": row[0], "seconds_per_page": round(row[1] or 0, 1), "output_tokens": round(row[2] or 0),
            "output_tokens_per_second": round(row[3] or 0, 1), "prompt_seconds": round(row[4] or 0, 2),
            "wall_seconds_this_run": round(time.time() - t0),
            "events_f1": s["events"]["f1"], "events_recall": s["events"]["recall"], "events_precision": s["events"]["precision"],
            "action": s["action"], "actor": s["actor"], "dates": s["dates"], "order": s["order"], "level_c": s["level_c"],
            "harms": s["harms"], "standing": s["standing"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("models", nargs="+")
    ap.add_argument("--cases", type=int, default=8)
    ap.add_argument("--out", type=Path, default=C.E.REPO_ROOT / "local" / "select")
    a = ap.parse_args(argv)
    dev = [p.parent.name for p in sorted(BENCH.glob("synth_*/gold.json")) if split_of(p.parent.name) == "dev"][:a.cases]
    results = []
    for m in a.models:
        r = run(m, dev, a.out)
        results.append(r)
        print(json.dumps(r), flush=True)
    (a.out / "selection.json").write_text(json.dumps({"cases": dev, "results": results}, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
