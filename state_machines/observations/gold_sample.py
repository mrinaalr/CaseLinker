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
unit is n_h / N_h, and the sampling weight is N_h / n_h. Precision and recall
both use that weight. The SHA-256 of the drawn list (unit, stratum, inclusion
probability) is computed before the grading sheet. The sheet has the sentence
and the clipped context. Machine labels go only in the key.

``score`` checks the sealed manifest hash before it computes anything. Precision
is the Horvitz-Thompson ratio of true positives to machine statements. Its
interval, and the intervals on recall and on agreement, resample whole cases
from the frame. A drawn case brings every sentence it has, in every stratum.
A Wilson interval is also reported inside each stratum.
Recall weights each gold-positive unit by N_h / n_h and reports how many gold
positives each stratum contributed. A second grader marks a fixed seeded
subset; Krippendorff's alpha (nominal) and Cohen's kappa are computed on the
rows that have two grades. The same rows,
with the known probabilities, are emitted for a design-based correction (DSL or
prediction-powered inference). This module does not run those estimators.
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


def _gold_positive(unit: str, row: dict) -> bool:
    value = row["gold"][unit]
    if unit == "act":
        return value not in (None, "")
    return bool(value)


def gold_positive_counts(rows: Sequence[dict], unit: str) -> dict:
    """How many sampled rows in each stratum the gold marks positive."""
    counts = {}
    for row in rows:
        counts.setdefault(row["stratum"], 0)
        if _gold_positive(unit, row):
            counts[row["stratum"]] += 1
    return counts


def _stratum_statements(rows: Sequence[dict], unit: str) -> dict:
    """Per stratum: true positives, false positives, and the weight N_h / n_h."""
    by = {}
    for row in rows:
        bucket = by.setdefault(row["stratum"], [0, 0, _weight(row)])
        machine = row["machine"][unit]
        if not _stated(unit, machine):
            continue
        if _hit(unit, machine, row["gold"][unit]):
            bucket[0] += 1
        else:
            bucket[1] += 1
    return by


def ipw_precision(rows: Sequence[dict], unit: str) -> Optional[float]:
    """Horvitz-Thompson precision: sum w_h*TP_h / sum w_h*(TP_h+FP_h)."""
    num = den = 0.0
    for tp, fp, weight in _stratum_statements(rows, unit).values():
        num += weight * tp
        den += weight * (tp + fp)
    if den == 0:
        return None
    return num / den


def unweighted_recall(rows: Sequence[dict], unit: str) -> Optional[float]:
    """Pooled hits over gold positives, ignoring the sampling weights."""
    gold = hits = 0
    for row in rows:
        if not _gold_positive(unit, row):
            continue
        gold += 1
        if _hit(unit, row["machine"][unit], row["gold"][unit]):
            hits += 1
    if gold == 0:
        return None
    return hits / gold


def unweighted_precision(rows: Sequence[dict], unit: str) -> Optional[float]:
    """Pooled TP / (TP+FP), ignoring the sampling weights. For the contrast test."""
    tp = fp = 0
    for stp, sfp, _weight_h in _stratum_statements(rows, unit).values():
        tp += stp
        fp += sfp
    stated = tp + fp
    if stated == 0:
        return None
    return tp / stated


def precision_unit(rows: Sequence[dict], unit: str) -> dict:
    """Weighted precision, plus a Wilson interval inside each stratum."""
    by = _stratum_statements(rows, unit)
    tp = fp = 0
    strata = {}
    for name, (stp, sfp, weight) in by.items():
        tp += stp
        fp += sfp
        stated = stp + sfp
        strata[name] = {
            "tp": stp,
            "fp": sfp,
            "stated": stated,
            "weight": weight,
            "wilson_95": wilson(stp, stated) if stated else None,
        }
    stated = tp + fp
    return {"unit": unit, "tp": tp, "fp": fp, "stated": stated,
            "precision": ipw_precision(rows, unit),
            "by_stratum": strata}


def _clusters(group: Sequence[dict]) -> list:
    """One list of rows per case, in the order the cases first appear."""
    order = []
    buckets = {}
    for row in group:
        key = row["case_id"]
        if key not in buckets:
            order.append(key)
            buckets[key] = []
        buckets[key].append(row)
    return [buckets[key] for key in order]


def cluster_resample(rows: Sequence[dict], rng: random.Random) -> list:
    """Draw cases with replacement from every case in the frame.

    Every sentence of a drawn case comes along, in every stratum that case has
    rows in. Each row keeps its ``N_h / n_h`` weight. Rows are not drawn one by one.
    """
    clusters = _clusters(rows)
    sample = []
    for _ in range(len(clusters)):
        sample.extend(clusters[rng.randrange(len(clusters))])
    return sample


def _percentile(stats: list) -> Optional[list]:
    if not stats:
        return None
    stats.sort()
    return [stats[int(0.025 * (len(stats) - 1))], stats[int(0.975 * (len(stats) - 1))]]


def _cluster_interval(rows: Sequence[dict], statistic: Callable, replicates: int, seed: int) -> Optional[list]:
    """Percentile interval from a whole-case bootstrap. None with fewer than two cases."""
    if not rows:
        return None
    n_cases = len({row["case_id"] for row in rows})
    if n_cases < 2:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(replicates):
        value = statistic(cluster_resample(rows, rng))
        if value is not None:
            stats.append(value)
    return _percentile(stats)


def _precision_interval(rows: Sequence[dict], unit: str, replicates: int, seed: int) -> Optional[list]:
    return _cluster_interval(rows, lambda sample: ipw_precision(sample, unit), replicates, seed)


def recall_report(rows: Sequence[dict], unit: str, replicates: int, seed: int) -> dict:
    """Weighted recall, its interval, gold-positive counts, and a thin-stratum warning."""
    counts = gold_positive_counts(rows, unit)
    warnings = [
        f"{name}: fewer than 5 gold positives; its bootstrap interval is unreliable"
        for name, count in sorted(counts.items()) if count < 5
    ]
    point = ipw_recall(rows, unit)
    return {
        "recall": point,
        "interval_95": _recall_interval(rows, unit, replicates, seed) if point is not None else None,
        "gold_positives_by_stratum": counts,
        "warnings": warnings,
    }


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
    return _cluster_interval(rows, lambda sample: ipw_recall(sample, unit), replicates, seed)


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


def score(graded: dict, key: dict, *, sealed: dict, replicates: int = 2000, seed: int = 0) -> dict:
    """Score a graded sheet against its key. The manifest hash is checked first."""
    digest = verify_manifest(sealed)
    rows = _joined(graded, key)
    precision = {}
    for unit in UNITS:
        block = precision_unit(rows, unit)
        block["interval_95"] = _precision_interval(rows, unit, replicates, seed) if block["precision"] is not None else None
        precision[unit] = block
    recall = {unit: recall_report(rows, unit, replicates, seed) for unit in UNITS}
    alpha = {}
    kappa = {}
    for unit in UNITS:
        names = sorted({name for row in rows for name in row["coders"]})
        paired = [row for row in rows if len(names) >= 2 and names[0] in row["coders"] and names[1] in row["coders"]]
        coded = _coder_units(paired, unit)
        alpha_point = krippendorff_alpha(coded)
        alpha[unit] = {
            "alpha": alpha_point,
            "interval_95": _cluster_interval(
                paired, lambda sample: krippendorff_alpha(_coder_units(sample, unit)), replicates, seed),
        }
        if len(names) >= 2 and paired:
            a = [row["coders"][names[0]].get(unit) for row in paired]
            b = [row["coders"][names[1]].get(unit) for row in paired]
            kappa_point = cohen_kappa(a, b)
            kappa[unit] = {
                "coders": names[:2],
                "kappa": kappa_point,
                "interval_95": _cluster_interval(
                    paired, lambda sample, n0=names[0], n1=names[1]: cohen_kappa(
                        [row["coders"][n0].get(unit) for row in sample],
                        [row["coders"][n1].get(unit) for row in sample]),
                    replicates, seed),
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


def score_drawn(graded: dict, key: dict, sample: dict, *, sealed: dict, replicates: int = 2000, seed: int = 0) -> dict:
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
    s.add_argument("--replicates", type=int, default=2000)
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
