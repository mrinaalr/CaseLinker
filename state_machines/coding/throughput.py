"""Where coding time goes, and what the 30 real cases would cost under each strategy.

    python -m state_machines.coding.throughput [--bench local/bench] [--text-root local/pacer_text]

Reads the coder cache (per-call prompt and output tokens and seconds), the coverage logs of a
benchmark run, and the page routing of the real cases (no model calls). Reports, per model, the
time split between reading the prompt and writing the answer; the share of model pages where a
coder found no act; and projected hours for the real cases with both coders on every model page
(full) or with the second coder only on pages where the first found acts (selective). The
selective pass leaves the release unchanged (resolution publishes only acts both coders coded);
it changes what reliability is measured on.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from state_machines.evidence import evidence as E
from state_machines.coding import coder as C


def model_stats(cache: Path = C.CACHE) -> dict:
    db = sqlite3.connect(str(cache))
    out = {}
    for model, n, sec, pt, ps, ot, os_ in db.execute(
            "SELECT model, COUNT(*), AVG(seconds), AVG(prompt_tokens), AVG(prompt_seconds), AVG(output_tokens), AVG(output_seconds)"
            " FROM calls WHERE prompt_version=? AND output_tokens IS NOT NULL GROUP BY model", (C.PROMPT_VERSION,)):
        out[model] = {"calls": n, "seconds_per_page": round(sec, 1), "prompt_tokens": round(pt or 0), "prompt_seconds": round(ps or 0, 2),
                      "output_tokens": round(ot or 0), "output_seconds": round(os_ or 0, 1),
                      "output_tokens_per_second": round((ot or 0) / os_, 1) if os_ else None}
    return out


def zero_act_share(bench: Path) -> dict:
    out = {}
    for coder in ("coder_A", "coder_B"):
        c = Counter()
        for log in sorted((bench / coder).glob("*.log")):
            for line in log.read_text(encoding="utf-8").splitlines():
                m = re.match(r"page \S+ p\d+: model.*?, (\d+) acts$", line)
                if m:
                    c["model_pages"] += 1
                    c["zero_act_pages"] += int(m.group(1)) == 0
        out[coder] = dict(c, share=round(c["zero_act_pages"] / c["model_pages"], 3) if c["model_pages"] else None)
    return out


def real_routing(text_root: Path) -> dict:
    c = Counter()
    for case in sorted(p for p in text_root.iterdir() if (p / "sources.json").is_file()):
        sources = json.loads((case / "sources.json").read_text(encoding="utf-8"))
        for doc in sources["documents"]:
            for p in doc["pages"]:
                text = E.read_page(case.name, doc["doc_id"], p["pdf_page"], text_root) or ""
                c[C.route(doc, text) if text.strip() else "empty"] += 1
    return dict(c)


def project(stats: dict, zero: dict, routing: dict) -> dict:
    pages = routing.get("model", 0)
    spec = C.MODELS["coders"]
    a, b = stats.get(spec["coder_A"]["model"], {}), stats.get(spec["coder_B"]["model"], {})
    if not (a and b):
        return {}
    keep = 1 - (zero.get("coder_A", {}).get("share") or 0)
    full = pages * (a["seconds_per_page"] + b["seconds_per_page"]) / 3600
    selective = pages * (a["seconds_per_page"] + keep * b["seconds_per_page"]) / 3600
    return {"model_pages": pages, "hours_full": round(full, 1), "hours_selective": round(selective, 1),
            "second_coder_pages_selective": round(pages * keep)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bench", type=Path, default=E.REPO_ROOT / "local" / "bench")
    ap.add_argument("--text-root", type=Path, default=E.text_root())
    args = ap.parse_args(argv)
    stats, zero, routing = model_stats(), zero_act_share(args.bench), real_routing(args.text_root)
    print(json.dumps({"models": stats, "benchmark_zero_act_pages": zero, "real_page_routing": routing,
                      "projection_30_cases": project(stats, zero, routing)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
