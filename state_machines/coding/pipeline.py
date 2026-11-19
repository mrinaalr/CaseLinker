"""Automated coding, end to end: two local coders, machine resolution, benchmark and release.

    python -m state_machines.coding.pipeline code    <case_id> [...] [--text-root DIR] [--out DIR]
    python -m state_machines.coding.pipeline resolve <case_id> [...] [--out DIR]
    python -m state_machines.coding.pipeline bench   [--split dev|heldout|all]
    python -m state_machines.coding.pipeline release <release_id> <case_id> [...] [--out DIR] [--text-root DIR]

``code`` runs coder_A then coder_B on every case (each case is cached and resumable: a case whose
bundle exists is skipped). ``resolve`` applies ``resolve.resolve`` and writes the reliability report.
``bench`` runs both coders on the synthetic benchmark and scores each coder and the resolution
against the gold. ``release`` copies the resolved bundles into a release and builds it as
``machine``. A case that fails (no events, an unrepairable bundle, a model error) is recorded with
its reason and left out; it is never forced through.

Outputs (local, gitignored; they hold quotes and model output): ``<out>/coder_A``, ``<out>/coder_B``,
``<out>/resolved``, ``<out>/reports``.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional

from state_machines.evidence import evidence as E
from state_machines.coding import coder as C
from state_machines.coding.resolve import resolve
from state_machines.coding.workflow import agreement

OUT = E.REPO_ROOT / "local" / "auto"
BENCH = E.REPO_ROOT / "state_machines" / "benchmark" / "data"
DATA = E.REPO_ROOT / "state_machines" / "data"


def _deny(text_root: Path, case_id: str) -> List[str]:
    """The case's deny list (names from its captions), built from the page text when it is not there yet."""
    p = text_root / case_id / "deny.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    from state_machines.coding.workflow import build_deny
    return build_deny(case_id, text_root) if (text_root / case_id / "sources.json").is_file() and "benchmark" not in text_root.parts else []


def _same_documents(bundle_path: Path, text_root: Path, case_id: str) -> bool:
    """The coded bundle covers exactly the documents the text store now lists (by SHA-256)."""
    sources = text_root / case_id / "sources.json"
    if not sources.is_file():
        return True
    have = {d["sha256"] for d in json.loads(bundle_path.read_text(encoding="utf-8"))["documents"]}
    return have == {d["sha256"] for d in json.loads(sources.read_text(encoding="utf-8"))["documents"]}


def code(cases: List[str], text_root: Path, out: Path, selective: bool = False) -> dict:
    status = {}
    cache = C.Cache()
    for coder in ("coder_A", "coder_B"):
        for other in ("coder_A", "coder_B"):
            if other != coder:
                C.unload(other)                 # one model in memory at a time
        d = out / coder
        d.mkdir(parents=True, exist_ok=True)
        for case_id in cases:
            target = d / f"{case_id}.json"
            if target.is_file() and _same_documents(target, text_root, case_id):
                continue            # coded already, for these documents; a new filing recodes the case (old pages come from the cache)
            t = time.time()
            try:
                only = None
                if selective and coder == "coder_B":
                    first_log = out / "coder_A" / f"{case_id}.log"
                    only = C.pages_with_acts(first_log) if first_log.is_file() else None
                bundle, quotes, log = C.code_case(case_id, coder, text_root, cache, _deny(text_root, case_id), only_pages=only)
                target.write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                store = E.load_quotes(case_id, text_root)
                store.update(quotes)
                E.save_quotes(case_id, store, text_root)
                (d / f"{case_id}.log").write_text("\n".join(log) + "\n", encoding="utf-8")
                status[f"{coder}/{case_id}"] = {"events": len(bundle["events"]), "seconds": round(time.time() - t)}
                print(f"{coder} {case_id}: {len(bundle['events'])} events in {time.time() - t:.0f}s", flush=True)
            except BaseException as exc:            # noqa: BLE001 - a failed case is recorded, not fatal
                if isinstance(exc, KeyboardInterrupt):
                    raise
                (d / f"{case_id}.failed").write_text(f"{exc}\n{traceback.format_exc()}", encoding="utf-8")
                status[f"{coder}/{case_id}"] = {"failed": str(exc)[:300]}
                print(f"{coder} {case_id}: FAILED {exc}", flush=True)
    return status


def _model_coded(bundle: dict) -> dict:
    """The bundle without the docket parser's acts: reliability is measured on what the models coded."""
    keep = {e["event_id"] for e in bundle["events"] if e.get("notes") != "docket-parser"}
    return dict(bundle, events=[e for e in bundle["events"] if e["event_id"] in keep],
                relations=[r for r in bundle["relations"] if r["from_event"] in keep and r["to_event"] in keep])


def resolve_cases(cases: List[str], out: Path, text_root: Optional[Path] = None, settle_codes: bool = False,
                  sub: str = "resolved") -> dict:
    """Resolve each case's two codings into ``out/<sub>``; reports beside it. ``settle_codes`` turns on
    candidate rule 2b (``cues``), which a machine release does not use."""
    reports = "reports" if sub == "resolved" else f"reports_{sub}"
    (out / sub).mkdir(parents=True, exist_ok=True)
    (out / reports).mkdir(parents=True, exist_ok=True)
    summary = {}
    for case_id in cases:
        pa, pb = out / "coder_A" / f"{case_id}.json", out / "coder_B" / f"{case_id}.json"
        if not (pa.is_file() and pb.is_file()):
            summary[case_id] = {"failed": "a coder produced no bundle"}
            continue
        a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (pa, pb))
        bundle, report = resolve(a, b, text_root, settle_codes)
        if text_root is not None:
            from state_machines.coding.resolve import restate_order
            report["counts"]["published: stated order re-derived on agreed acts (5c)"] = restate_order(bundle, text_root)
        model_agree = agreement(_model_coded(a), _model_coded(b))
        report["agreement_model_coded"] = {k: v for k, v in model_agree.items() if k != "pairs"}
        report["parser_events"] = sum(e.get("notes") == "docket-parser" for e in bundle["events"])
        if not bundle["events"]:
            summary[case_id] = {"failed": "no event both coders coded", "report": report}
            continue
        (out / sub / f"{case_id}.json").write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        (out / reports / f"{case_id}.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        summary[case_id] = {"events": len(bundle["events"]), "parser_events": report["parser_events"],
                            "agreement_model_coded": report["agreement_model_coded"]}
    (out / reports / "SUMMARY.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def bench(split: str = "all", out: Path = E.REPO_ROOT / "local" / "bench", selective: bool = False) -> dict:
    from state_machines.benchmark.score import score_dir, split_of
    cases = [p.parent.name for p in sorted(BENCH.glob("synth_*/gold.json")) if split == "all" or split_of(p.parent.name) == split]
    code(cases, BENCH, out, selective)
    resolve_cases(cases, out, BENCH)
    resolve_cases(cases, out, BENCH, settle_codes=True, sub="resolved_2b")       # the candidate rule, scored beside the released one
    result = {name: score_dir(out / name, split) for name in ("coder_A", "coder_B", "resolved", "resolved_2b")}
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "reports" / f"benchmark.{split}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def bench_observations(split: str, out: Path, note: str = "", write: bool = False) -> dict:
    """Score the observation layer on a benchmark split. Observations need no model; supported
    relationships use the resolved bundles already in ``out`` (from ``bench``)."""
    from collections import Counter
    from state_machines.benchmark.score import score_observations, split_of, summarize_observations
    from state_machines.observations import observe as O
    total: Counter = Counter()
    cases = [p.parent.name for p in sorted(BENCH.glob("synth_*/gold.json")) if split_of(p.parent.name) == split]
    for case_id in cases:
        gold = json.loads((BENCH / case_id / "gold.json").read_text(encoding="utf-8"))
        doc = O.observe(case_id, BENCH)
        coded_path = out / "resolved" / f"{case_id}.json"
        coded = json.loads(coded_path.read_text(encoding="utf-8")) if coded_path.is_file() else None
        if coded:
            O.relate(doc, coded, BENCH)
        if O.check(doc, BENCH, coded):
            raise SystemExit(f"{case_id}: observations not sound")
        total += score_observations(gold, doc, coded)
    body = dict(summarize_observations(total), cases=len(cases), rule=O.RULE_VERSION)
    if note:
        body["_note"] = note
    if write:
        path = E.REPO_ROOT / "state_machines" / "benchmark" / "results" / f"{O.RULE_VERSION}.{split}.json"
        path.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    return body


def record(split: str, result: dict, note: str = "") -> Path:
    """Write a split's overall scores to the committed results folder, keyed by the rule version."""
    from state_machines.coding.resolve import RULE_VERSION
    path = E.REPO_ROOT / "state_machines" / "benchmark" / "results" / f"{RULE_VERSION}.{split}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {name: dict(r["overall"], cases=r["cases"], cases_without_output=r["missing"]) for name, r in result.items()}
    if note:
        body["_note"] = note
    path.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    return path


def release(release_id: str, cases: List[str], out: Path, text_root: Path, observations: bool = False) -> dict:
    from state_machines.graphs.release import build
    root = DATA / release_id / "cases"
    root.mkdir(parents=True, exist_ok=True)
    included = []
    for case_id in cases:
        src = out / "resolved" / f"{case_id}.json"
        if src.is_file():
            shutil.copy(src, root / f"{case_id}.json")
            included.append(case_id)
    manifest = build(release_id, text_root=text_root, deny_lists={c: _deny(text_root, c) for c in included}, mode="machine",
                     observations=observations, coders_root=out)
    return {"release": release_id, "cases": len(manifest["cases"]), "left_out": sorted(set(cases) - set(included))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("code", "resolve", "bench", "bench-observations", "release"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--text-root", type=Path, default=E.text_root())
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--split", choices=("dev", "heldout", "confirm", "all"), default="all")
    ap.add_argument("--selective", action="store_true", help="coder_B reads only pages where coder_A found acts")
    ap.add_argument("--observations", action="store_true",
                    help="release: also publish what each record names (platforms, feature phrases) as a third graph per case")
    ap.add_argument("--settle-codes", action="store_true",
                    help="resolve: candidate rule 2b, settle a differing action code from the sentence (not for a machine release)")
    ap.add_argument("--record", action="store_true", help="bench: write the split's scores to state_machines/benchmark/results")
    ap.add_argument("--note", default="", help="bench --record: one line stored with the scores")
    ap.add_argument("--bench-out", type=Path, default=E.REPO_ROOT / "local" / "bench")
    a = ap.parse_args(argv)
    if a.cmd == "code":
        print(json.dumps(code(a.args, a.text_root, a.out, a.selective), indent=1))
    elif a.cmd == "resolve":
        print(json.dumps(resolve_cases(a.args, a.out, a.text_root, a.settle_codes, "resolved_2b" if a.settle_codes else "resolved"), indent=1))
    elif a.cmd == "bench-observations":
        print(json.dumps(bench_observations(a.split, a.bench_out, a.note, a.record), indent=1))
    elif a.cmd == "bench":
        r = bench(a.split, a.bench_out, a.selective)
        if a.record:
            record(a.split, r, a.note)
        print(json.dumps({k: v["overall"] for k, v in r.items()}, indent=1))
    else:
        print(json.dumps(release(a.args[0], a.args[1:], a.out, a.text_root, a.observations), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
