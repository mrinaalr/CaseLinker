"""Stratified gold sample from a sealed frame. Nothing here draws on a real corpus.

    python -m state_machines.observations.gold_sample draw --population P --config C --sealed M --out DIR
    python -m state_machines.observations.gold_sample score --graded G --key K --draw D --sealed M

The population is a list of sentence units the researcher has already cut, each
with a case id, a stratum, the sentence, and at most two sentences of context
on either side. The sampler refuses a unit whose case is outside the sealed
gold frame, and it refuses a unit whose case is on the exclusion list. It never
reads a model score or an interestingness field. Stratum sizes and the seed
come from the config.

Each stratum is a simple random sample. The inclusion probability of a drawn
unit is n_h / N_h, and the sampling weight used for recall is N_h / n_h. The
SHA-256 of the drawn list (unit, stratum, inclusion probability) is computed
before the grading sheet. The sheet has the sentence and the clipped context.
Machine labels go only in the key.

``score`` checks the sealed manifest hash before it computes anything. Precision
is per stated unit (act, means tie, level C), with a Wilson interval. Recall
weights each gold-positive unit by N_h / n_h. Krippendorff's alpha (nominal)
and Cohen's kappa are computed across the human coders, with a percentile
bootstrap interval. The same rows, with the known probabilities, are emitted
for a design-based correction (DSL or prediction-powered inference). This
module does not run those estimators.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Optional, Sequence

from state_machines.observations.seal import refuse_store, verify_manifest
from state_machines.observations.validation import wilson

UNITS = ("act", "means_tie", "level_c")
_IGNORED = ("uncertainty", "interestingness", "model_score")


def _weight(row: dict) -> float:
    """N_h / n_h. Stored counts, so the weight is the inverse of n_h / N_h."""
    return row["stratum_population"] / row["stratum_drawn"]


def draw_sample(population: Sequence[dict], config: dict, *, sealed: dict) -> dict:
    """A stratified sample of the sealed gold frame.

    ``config`` is ``{"seed": int, "strata": {name: {"n": int}}}``. Selection uses
    the stratum name and the seed only.
    """
    verify_manifest(sealed)
    frame = set(sealed["gold_frame_ids"])
    banned = set(sealed.get("exclusion_ids") or [])
    outside = sorted({row["case_id"] for row in population if row["case_id"] not in frame})
    if outside:
        raise SystemExit("the gold sampler draws only from the sealed frame: " + ", ".join(outside))
    leaked = sorted({row["case_id"] for row in population if row["case_id"] in banned})
    if leaked:
        raise SystemExit("excluded ids cannot be drawn: " + ", ".join(leaked))
    if config.get("select") not in (None, "stratified_random"):
        raise SystemExit("selection is stratified random; model uncertainty is not a selection method")
    rng = random.Random(config["seed"])
    by = {}
    for row in population:
        by.setdefault(row["stratum"], []).append(row)
    drawn = []
    meta = {}
    for name, spec in config["strata"].items():
        pool = sorted(by.get(name, []), key=lambda row: row["unit_id"])
        size, asked = len(pool), spec["n"]
        if asked > size:
            raise SystemExit(f"{name}: asked for {asked} from a stratum of {size}")
        pi = (asked / size) if size else None
        meta[name] = {"population": size, "drawn": asked, "inclusion_probability": pi}
        picks = pool if asked == size else rng.sample(pool, asked)
        for row in picks:
            drawn.append({
                "unit_id": row["unit_id"],
                "case_id": row["case_id"],
                "stratum": name,
                "inclusion_probability": pi,
                "stratum_population": size,
                "stratum_drawn": asked,
                "sentence": row["sentence"],
                "context_before": list(row.get("context_before") or []),
                "context_after": list(row.get("context_after") or []),
                "machine": row.get("machine"),
            })
    return {"seed": config["seed"], "rows": drawn, "strata": meta}


def draw_sha256(sample: dict) -> str:
    """Hash of the drawn list: unit, stratum, inclusion probability. No labels."""
    payload = [{"unit_id": row["unit_id"], "stratum": row["stratum"],
                "inclusion_probability": row["inclusion_probability"]} for row in sample["rows"]]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _clip(rows: Sequence[str], window: int, last: bool) -> list:
    rows = list(rows)
    return rows[-window:] if last else rows[:window]


def grading_sheet(sample: dict, window: int = 2) -> dict:
    """The sentence and at most ``window`` sentences of context. No machine labels, no stratum."""
    units = []
    for row in sample["rows"]:
        units.append({
            "unit_id": row["unit_id"],
            "context_before": _clip(row.get("context_before") or [], window, last=True),
            "sentence": row["sentence"],
            "context_after": _clip(row.get("context_after") or [], window, last=False),
        })
    return {"units": units}


def key_file(sample: dict) -> dict:
    """Machine labels, stratum and inclusion probability, kept apart from the sheet."""
    return {"units": [{
        "unit_id": row["unit_id"],
        "case_id": row["case_id"],
        "stratum": row["stratum"],
        "inclusion_probability": row["inclusion_probability"],
        "stratum_population": row["stratum_population"],
        "stratum_drawn": row["stratum_drawn"],
        "machine": row["machine"],
    } for row in sample["rows"]]}


def _stated(unit: str, value) -> bool:
    if unit == "act":
        return value not in (None, "")
    return bool(value)


def _hit(unit: str, machine, gold) -> bool:
    if unit == "act":
        return machine not in (None, "") and machine == gold
    return bool(machine) and bool(gold)


def precision_unit(rows: Sequence[dict], unit: str) -> dict:
    """Unweighted precision among units the machine stated, with a Wilson interval."""
    tp = fp = 0
    for row in rows:
        machine, gold = row["machine"][unit], row["gold"][unit]
        if not _stated(unit, machine):
            continue
        if _hit(unit, machine, gold):
            tp += 1
        else:
            fp += 1
    stated = tp + fp
    return {"unit": unit, "tp": tp, "fp": fp, "stated": stated,
            "precision": (tp / stated) if stated else None,
            "interval_95": wilson(tp, stated) if stated else None}


def ipw_total(rows: Sequence[dict], include: Callable[[dict], bool]) -> float:
    """Horvitz-Thompson total: sum of N_h / n_h over the included sample rows."""
    return sum(_weight(row) for row in rows if include(row))


def ipw_recall(rows: Sequence[dict], unit: str) -> Optional[float]:
    """Weighted recall: HT true positives over HT gold positives."""
    gold = ipw_total(rows, lambda row: _stated(unit, row["gold"][unit]) if unit == "act" else bool(row["gold"][unit]))
    if gold == 0:
        return None
    hits = ipw_total(rows, lambda row: _hit(unit, row["machine"][unit], row["gold"][unit]))
    return hits / gold


def _recall_interval(rows: Sequence[dict], unit: str, replicates: int, seed: int) -> Optional[list]:
    """Percentile interval from resampling each stratum with replacement, at its drawn size."""
    if not rows:
        return None
    groups = {}
    for row in rows:
        groups.setdefault(row["stratum"], []).append(row)
    rng = random.Random(seed)
    stats = []
    for _ in range(replicates):
        sample = []
        for group in groups.values():
            sample.extend(group[rng.randrange(len(group))] for _ in group)
        value = ipw_recall(sample, unit)
        if value is not None:
            stats.append(value)
    if not stats:
        return None
    stats.sort()
    return [stats[int(0.025 * (len(stats) - 1))], stats[int(0.975 * (len(stats) - 1))]]


def krippendorff_alpha(units: Sequence[Sequence]) -> Optional[float]:
    """Nominal Krippendorff alpha from the coincidence matrix. None if it is undefined.

    A missing coder value is ``None`` and is left out of that unit. A unit with
    fewer than two values does not enter. Observed disagreement is the
    off-diagonal mass of the coincidence matrix; expected disagreement uses the
    category totals (Hayes and Krippendorff 2007).
    """
    counts = []
    for unit in units:
        values = [value for value in unit if value is not None]
        if len(values) >= 2:
            counts.append(Counter(values))
    if not counts:
        return None
    categories = sorted({label for counter in counts for label in counter}, key=str)
    observed = {c: {k: 0.0 for k in categories} for c in categories}
    for counter in counts:
        n_u = sum(counter.values())
        for left, n_left in counter.items():
            for right, n_right in counter.items():
                if left == right:
                    observed[left][right] += n_left * (n_left - 1) / (n_u - 1)
                else:
                    observed[left][right] += n_left * n_right / (n_u - 1)
    n = sum(observed[c][k] for c in categories for k in categories)
    if n <= 1:
        return None
    disagreement = sum(observed[c][k] for c in categories for k in categories if c != k) / n
    if disagreement == 0:
        return 1.0
    marginal = {c: sum(observed[c][k] for k in categories) for c in categories}
    expected = sum(marginal[c] * marginal[k] for c in categories for k in categories if c != k) / (n * (n - 1))
    if expected == 0:
        return None
    return 1 - disagreement / expected


def cohen_kappa(left: Sequence, right: Sequence) -> Optional[float]:
    """Cohen's kappa for two coders. None when there is nothing to score or chance is 1."""
    n = len(left)
    if n == 0 or n != len(right):
        return None
    observed = sum(a == b for a, b in zip(left, right)) / n
    cx, cy = Counter(left), Counter(right)
    chance = sum(cx[k] * cy[k] for k in set(cx) | set(cy)) / (n * n)
    if chance == 1:
        return None
    return (observed - chance) / (1 - chance)


def _bootstrap(values_of: Callable, units: Sequence, replicates: int, seed: int) -> Optional[list]:
    if len(units) < 2:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(replicates):
        sample = [units[rng.randrange(len(units))] for _ in units]
        value = values_of(sample)
        if value is not None:
            stats.append(value)
    if not stats:
        return None
    stats.sort()
    return [stats[int(0.025 * (len(stats) - 1))], stats[int(0.975 * (len(stats) - 1))]]


def _joined(graded: dict, key: dict) -> list:
    gold = {row["unit_id"]: row for row in graded["units"]}
    rows = []
    for item in key["units"]:
        human = gold[item["unit_id"]]
        rows.append({**item, "gold": human["gold"], "coders": human.get("coders") or {}})
    return rows


def _coder_units(rows: Sequence[dict], unit: str) -> list:
    names = sorted({name for row in rows for name in row["coders"]})
    return [[row["coders"].get(name, {}).get(unit) for name in names] for row in rows]


def score(graded: dict, key: dict, *, sealed: dict, replicates: int = 1000, seed: int = 0) -> dict:
    """Score a graded sheet against its key. The manifest hash is checked first."""
    digest = verify_manifest(sealed)
    rows = _joined(graded, key)
    precision = {unit: precision_unit(rows, unit) for unit in UNITS}
    recall = {}
    for unit in UNITS:
        point = ipw_recall(rows, unit)
        recall[unit] = {"recall": point, "interval_95": _recall_interval(rows, unit, replicates, seed) if point is not None else None}
    alpha = {}
    kappa = {}
    for unit in UNITS:
        coded = _coder_units(rows, unit)
        alpha_point = krippendorff_alpha(coded)
        alpha[unit] = {
            "alpha": alpha_point,
            "interval_95": _bootstrap(lambda sample: krippendorff_alpha(sample), coded, replicates, seed),
        }
        names = sorted({name for row in rows for name in row["coders"]})
        if len(names) >= 2:
            a = [row["coders"].get(names[0], {}).get(unit) for row in rows]
            b = [row["coders"].get(names[1], {}).get(unit) for row in rows]
            kappa_point = cohen_kappa(a, b)
            kappa[unit] = {
                "coders": names[:2],
                "kappa": kappa_point,
                "interval_95": _bootstrap(
                    lambda sample, n0=names[0], n1=names[1]: cohen_kappa(
                        [row["coders"].get(n0, {}).get(unit) for row in sample],
                        [row["coders"].get(n1, {}).get(unit) for row in sample]),
                    rows, replicates, seed),
            }
        else:
            kappa[unit] = {"coders": names, "kappa": None, "interval_95": None}
    ready = [{
        "unit_id": row["unit_id"],
        "stratum": row["stratum"],
        "inclusion_probability": row["inclusion_probability"],
        "sampling_weight": _weight(row),
        "gold": row["gold"],
        "machine": row["machine"],
    } for row in rows]
    return {
        "manifest_sha256": digest,
        "precision": precision,
        "recall": recall,
        "krippendorff_alpha": alpha,
        "cohen_kappa": kappa,
        "design_based": {
            "ready_for": ["DSL", "PPI"],
            "rows": ready,
            "note": "Each row carries its inclusion probability and the sampling weight N_h/n_h. "
                    "DSL (Egami, Hinck, Stewart and Wei 2023) and prediction-powered inference "
                    "(Angelopoulos, Bates, Fannjiang, Jordan and Zrnic, Science 382, 2023) both need those probabilities.",
        },
    }


def _population_counts(sample: dict) -> dict:
    return {name: spec["population"] for name, spec in sample["strata"].items()}


def score_drawn(graded: dict, key: dict, sample: dict, *, sealed: dict, replicates: int = 1000, seed: int = 0) -> dict:
    result = score(graded, key, sealed=sealed, replicates=replicates, seed=seed)
    result["design_based"]["population_by_stratum"] = _population_counts(sample)
    result["draw_sha256"] = draw_sha256(sample)
    return result


def write_draw(sample: dict, out_dir: Path) -> dict:
    """Write the hash, then the blind sheet and the key. The hash file is first."""
    refuse_store(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = draw_sha256(sample)
    (out_dir / "draw.sha256").write_text(digest + "\n", encoding="utf-8")
    (out_dir / "draw.json").write_text(json.dumps(sample, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    sheet = grading_sheet(sample)
    (out_dir / "grading_sheet.json").write_text(json.dumps(sheet, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "key.json").write_text(json.dumps(key_file(sample), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"sha256": digest, "units": len(sample["rows"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--population", type=Path, required=True)
    d.add_argument("--config", type=Path, required=True)
    d.add_argument("--sealed", type=Path, required=True)
    d.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--graded", type=Path, required=True)
    s.add_argument("--key", type=Path, required=True)
    s.add_argument("--draw", type=Path, required=True)
    s.add_argument("--sealed", type=Path, required=True)
    s.add_argument("--replicates", type=int, default=1000)
    s.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    for path in (getattr(args, "population", None), getattr(args, "config", None), args.sealed,
                 getattr(args, "graded", None), getattr(args, "key", None), getattr(args, "draw", None),
                 getattr(args, "out", None)):
        if path is not None:
            refuse_store(path)
    sealed = json.loads(args.sealed.read_text(encoding="utf-8"))
    if args.cmd == "draw":
        population = json.loads(args.population.read_text(encoding="utf-8"))
        config = json.loads(args.config.read_text(encoding="utf-8"))
        sample = draw_sample(population, config, sealed=sealed)
        print(json.dumps(write_draw(sample, args.out), indent=1))
    else:
        graded = json.loads(args.graded.read_text(encoding="utf-8"))
        key = json.loads(args.key.read_text(encoding="utf-8"))
        sample = json.loads(args.draw.read_text(encoding="utf-8"))
        print(json.dumps(score_drawn(graded, key, sample, sealed=sealed, replicates=args.replicates, seed=args.seed), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
