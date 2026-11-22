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
positives each stratum contributed. When a second grader has marked rows,
Krippendorff's alpha (nominal) and Cohen's kappa are computed on the rows that
have two grades. Those rows, with their inclusion probabilities, are emitted
for a design-based correction (Egami, Hinck, Stewart and Wei 2023). This module
does not run that estimator.
"""
from __future__ import annotations

import argparse
import csv
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


def _copy_id(row: dict):
    """Which copy of a filing this row belongs to. The duplicate check is the sha256 alone."""
    ident = row.get("doc_id") or row.get("document_id")
    if ident:
        return (row.get("case_id"), ident)
    return (row.get("case_id"), row.get("document_sha256") or row.get("unit_id"))


def merge_dockets(rows: Sequence[dict]) -> list:
    """One case per court and case number. A repeated document is dropped whole.

    Every sentence of the first copy is kept. A later document with the same
    sha256 is dropped, sentences and all. Rows without a court and case number
    stay on their own case id. The merged id is the first case id in the group,
    so a sealed frame id is unchanged when that case is the first copy.
    """
    seen_digest = {}
    dropped = set()
    kept = []
    for row in rows:
        key = _copy_id(row)
        digest = row.get("document_sha256")
        if digest:
            owner = seen_digest.setdefault(digest, key)
            if owner != key:
                dropped.add(key)
        if key in dropped:
            continue
        kept.append(row)
    canonical = {}
    merged = []
    for row in kept:
        court, number = row.get("court"), row.get("docket_number")
        if court and number:
            key = (str(court), str(number))
            canonical.setdefault(key, row["case_id"])
            row = {**row, "case_id": canonical[key]}
        merged.append(row)
    return merged


_STAMPED = ("court", "docket_number", "document_sha256", "doc_id")


def _observations_file(directory, case_id: str) -> dict:
    """The release file ``observations/{case}.json``. A missing file is an error."""
    if directory is None:
        raise SystemExit("an observations file is required")
    path = Path(directory)
    if path.is_dir():
        path = path / f"{case_id}.json"
    if not path.is_file():
        raise SystemExit(f"observations file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_file(directory, case_id: str) -> dict:
    """The head's case bundle. A missing file is an error."""
    if directory is None:
        raise SystemExit("a decision file is required")
    path = Path(directory)
    if path.is_dir():
        path = path / f"{case_id}.json"
    if not path.is_file():
        raise SystemExit(f"decision file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _covers(spans, doc_id, page, start, end) -> bool:
    return any(doc == doc_id and pg == page and a < end and start < b for doc, pg, a, b, *_rest in spans)


def _act_spans(bundle: dict) -> list:
    passages = {p["passage_id"]: p for p in bundle.get("passages") or []}
    spans = []
    for event in bundle.get("events") or []:
        for support in event.get("support") or []:
            if support.get("facet") != "action":
                continue
            passage = passages.get(support.get("passage_id"))
            if not passage:
                continue
            spans.append((passage["doc_id"], passage["pdf_page"], passage["char_start"], passage["char_end"],
                          event.get("action") or ""))
    return spans


def _tied_spans(document: dict, kind: str) -> list:
    """Means ties from ``observations/{case}.json``, not from the decision bundle."""
    spans = []
    for obs in document.get("observations") or []:
        if obs.get("kind") != kind or not obs.get("relations"):
            continue
        spans.append((obs["doc_id"], obs["pdf_page"], obs["char_start"], obs["char_end"]))
    return spans


def _machine_labels(act_spans, platform_spans, feature_spans, doc_id, page, start, end) -> dict:
    act = next((code for doc, pg, a, b, code in act_spans
                if doc == doc_id and pg == page and a < end and start < b), "")
    return {
        "act": act,
        "means_tie": _covers(platform_spans, doc_id, page, start, end),
        "level_c": _covers(feature_spans, doc_id, page, start, end),
    }


def population_from_case(case_id: str, text_root, decisions=None, observations=None,
                         decisions_v2=None, observations_v2=None) -> list:
    """Every sentence on every filed page.

    ``{case_id}:act`` when the flags-off bundle published an act there.
    ``level_c`` when ``observations/{case}.json`` tied a feature means and no act
    was published there. ``{case_id}:other`` otherwise. A platform name alone is
    not an act. The v2 bundle and v2 observations file are required and supply
    ``machine_v2``. A missing file is an error.
    """
    from state_machines.evidence import evidence as E
    from state_machines.observations.observe import sentences

    bundle = _decision_file(decisions, case_id)
    observed = _observations_file(observations, case_id)
    v2 = _decision_file(decisions_v2, case_id)
    observed_v2 = _observations_file(observations_v2, case_id)
    act_spans = _act_spans(bundle)
    feature_spans = _tied_spans(observed, "feature")
    platform_spans = _tied_spans(observed, "platform")
    v2_acts = _act_spans(v2)
    v2_features = _tied_spans(observed_v2, "feature")
    v2_platforms = _tied_spans(observed_v2, "platform")
    root = Path(text_root) / case_id
    sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    key_path = root / "case_key.json"
    key = json.loads(key_path.read_text(encoding="utf-8")) if key_path.is_file() else {}
    court = key.get("court") or sources.get("court") or ""
    docket = key.get("docket_number") or sources.get("docket_number") or ""
    rows = []
    for doc in sources.get("documents") or []:
        sha = doc.get("sha256") or ""
        doc_id = doc.get("doc_id") or ""
        for page in doc.get("pages") or []:
            text = E.read_page(case_id, doc_id, page["pdf_page"], text_root) or ""
            spans = list(sentences(E.normalize(text)))
            texts = [E.normalize(text)[start:end].strip() for start, end in spans]
            for index, ((start, end), sentence) in enumerate(zip(spans, texts)):
                if not sentence:
                    continue
                page_no = page["pdf_page"]
                acted = _covers(act_spans, doc_id, page_no, start, end)
                level = _covers(feature_spans, doc_id, page_no, start, end)
                if acted:
                    stratum = f"{case_id}:act"
                elif level:
                    stratum = "level_c"
                else:
                    stratum = f"{case_id}:other"
                row = {
                    "unit_id": f"{case_id}:{doc_id}:{page_no}:{index}",
                    "case_id": case_id,
                    "doc_id": doc_id,
                    "court": court,
                    "docket_number": docket,
                    "document_sha256": sha,
                    "pdf_page": page_no,
                    "char_start": start,
                    "char_end": end,
                    "stratum": stratum,
                    "sentence": sentence,
                    "context_before": texts[max(0, index - 2):index],
                    "context_after": texts[index + 1:index + 3],
                    "machine": _machine_labels(act_spans, platform_spans, feature_spans, doc_id, page_no, start, end),
                    "machine_v2": _machine_labels(v2_acts, v2_platforms, v2_features, doc_id, page_no, start, end),
                }
                rows.append(row)
    return rows


def _order_key(seed, row: dict) -> str:
    blob = f"{seed}‖{row['case_id']}‖{row['unit_id']}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _v15_plan(by: dict, frame_ids, *, cap: int = 43) -> tuple:
    """Up to two act sentences per case, the rest of three from other, and level C up to 43.

    A case in the frame with no sentences is logged. An empty or short stratum
    does not stop the draw.
    """
    strata = {}
    shortfalls = []
    present = {name[:name.rfind(":")] for name in by if name.endswith(":act") or name.endswith(":other")}
    for case_id in sorted(set(frame_ids) | present):
        act_name, other_name = f"{case_id}:act", f"{case_id}:other"
        n_act_pop, n_other_pop = len(by.get(act_name, [])), len(by.get(other_name, []))
        if n_act_pop == 0 and n_other_pop == 0:
            shortfalls.append({"stratum": case_id, "population": 0, "asked": 3, "drawn": 0})
            continue
        n_act, n_other = min(2, n_act_pop), min(3 - min(2, n_act_pop), n_other_pop)
        if n_act < 2:
            shortfalls.append({"stratum": act_name, "population": n_act_pop, "asked": 2, "drawn": n_act})
        if n_other < 3 - n_act:
            shortfalls.append({"stratum": other_name, "population": n_other_pop, "asked": 3 - n_act, "drawn": n_other})
        if n_act:
            strata[act_name] = {"n": n_act}
        if n_other:
            strata[other_name] = {"n": n_other}
    level_pop = len(by.get("level_c", []))
    n_level = min(cap, level_pop)
    if level_pop == 0 or n_level < level_pop:
        shortfalls.append({"stratum": "level_c", "population": level_pop, "asked": min(cap, level_pop), "drawn": n_level})
    if n_level:
        strata["level_c"] = {"n": n_level}
    return strata, shortfalls


def draw_sample(population: Sequence[dict], config: dict, *, sealed: dict) -> dict:
    """The per-case draw. ``config`` is ``{"seed": int}``.

    Rows that share a court and case number are one case before the draw.
    """
    verify_manifest(sealed)
    population = merge_dockets(population)
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
    by = {}
    for row in population:
        by.setdefault(row["stratum"], []).append(row)
    strata, shortfalls = _v15_plan(by, frame, cap=int(config.get("level_c_cap", 43)))
    drawn = []
    meta = {}
    for name, spec in strata.items():
        pool = list(by.get(name, []))
        size, asked = len(pool), spec["n"]
        if asked > size:
            raise SystemExit(f"{name}: asked for {asked} from a stratum of {size}")
        pi = (asked / size) if size else None
        meta[name] = {"population": size, "drawn": asked, "inclusion_probability": pi}
        picks = sorted(pool, key=lambda row: _order_key(config["seed"], row))[:asked]
        for row in picks:
            drawn_row = {
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
            }
            if row.get("machine_v2") is not None:
                drawn_row["machine_v2"] = row["machine_v2"]
            for field in _STAMPED:
                if row.get(field):
                    drawn_row[field] = row[field]
            drawn.append(drawn_row)
    sample = {"seed": config["seed"], "rows": drawn, "strata": meta, "shortfalls": shortfalls}
    return sample


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
        units.append(_stamp(row, {
            "unit_id": row["unit_id"],
            "context_before": _clip(row.get("context_before") or [], window, last=True),
            "sentence": row["sentence"],
            "context_after": _clip(row.get("context_after") or [], window, last=False),
        }))
    random.Random(sample["seed"]).shuffle(units)
    return {"seed": sample["seed"], "units": units}


def _stamp(row: dict, base: dict) -> dict:
    for field in _STAMPED:
        if row.get(field):
            base[field] = row[field]
    return base


def key_file(sample: dict) -> dict:
    """Machine labels, stratum and inclusion probability, kept apart from the sheet."""
    units = []
    for row in sample["rows"]:
        units.append(_stamp(row, {
            "unit_id": row["unit_id"],
            "case_id": row["case_id"],
            "stratum": row["stratum"],
            "inclusion_probability": row["inclusion_probability"],
            "stratum_population": row["stratum_population"],
            "stratum_drawn": row["stratum_drawn"],
            "machine": row["machine"],
        }))
        if row.get("machine_v2") is not None:
            units[-1]["machine_v2"] = row["machine_v2"]
    return {"units": units}


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
    rows = merge_dockets(_joined(graded, key))
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
    ready = []
    for row in rows:
        stamped = {
            "unit_id": row["unit_id"],
            "stratum": row["stratum"],
            "inclusion_probability": row["inclusion_probability"],
            "sampling_weight": _weight(row),
            "gold": row["gold"],
            "machine": row["machine"],
        }
        for field in _STAMPED:
            if row.get(field):
                stamped[field] = row[field]
        ready.append(stamped)
    result = {
        "manifest_sha256": digest,
        "precision": precision,
        "recall": recall,
        "krippendorff_alpha": alpha,
        "cohen_kappa": kappa,
        "design_based": {
            "ready_for": ["DSL"],
            "rows": ready,
            "note": "Each row carries its inclusion probability and the sampling weight N_h/n_h. "
                    "DSL (Egami, Hinck, Stewart and Wei 2023) needs those probabilities.",
        },
    }
    if rows and all(row.get("machine_v2") is not None for row in rows):
        alt = [{**row, "machine": row["machine_v2"]} for row in rows]
        v2_precision = {}
        for unit in UNITS:
            block = precision_unit(alt, unit)
            block["interval_95"] = _precision_interval(alt, unit, replicates, seed) if block["precision"] is not None else None
            v2_precision[unit] = block
        result["machine_v2"] = {
            "precision": v2_precision,
            "recall": {unit: recall_report(alt, unit, replicates, seed) for unit in UNITS},
        }
    return result


def _population_counts(sample: dict) -> dict:
    return {name: spec["population"] for name, spec in sample["strata"].items()}


def score_drawn(graded: dict, key: dict, sample: dict, *, sealed: dict, replicates: int = 2000, seed: int = 0) -> dict:
    result = score(graded, key, sealed=sealed, replicates=replicates, seed=seed)
    result["design_based"]["population_by_stratum"] = _population_counts(sample)
    result["draw_sha256"] = draw_sha256(sample)
    return result


def label_rows(rows: Sequence[dict], decisions, observations, decisions_v2, observations_v2) -> list:
    """Machine labels from the decision and observations files. Labels in ``rows`` are ignored."""
    labelled = []
    cache = {}
    for row in rows:
        case_id = row["case_id"]
        if case_id not in cache:
            cache[case_id] = (
                _act_spans(_decision_file(decisions, case_id)),
                _tied_spans(_observations_file(observations, case_id), "platform"),
                _tied_spans(_observations_file(observations, case_id), "feature"),
                _act_spans(_decision_file(decisions_v2, case_id)),
                _tied_spans(_observations_file(observations_v2, case_id), "platform"),
                _tied_spans(_observations_file(observations_v2, case_id), "feature"),
            )
        acts, platforms, features, v2_acts, v2_platforms, v2_features = cache[case_id]
        clean = {key: value for key, value in row.items() if key not in {"machine", "machine_v2"}}
        clean["machine"] = _machine_labels(acts, platforms, features, row["doc_id"], row["pdf_page"], row["char_start"], row["char_end"])
        clean["machine_v2"] = _machine_labels(v2_acts, v2_platforms, v2_features, row["doc_id"], row["pdf_page"], row["char_start"], row["char_end"])
        labelled.append(clean)
    return labelled


def write_population(case_ids: Sequence[str], text_root: Path, out: Path, decisions, observations,
                     decisions_v2, observations_v2) -> int:
    """Write the sentence units ``draw --population`` reads. Machine labels are not in the file."""
    refuse_store(out)
    rows = []
    for case_id in case_ids:
        rows.extend(population_from_case(
            case_id, text_root, decisions, observations, decisions_v2, observations_v2))
    out.parent.mkdir(parents=True, exist_ok=True)
    public = [{key: value for key, value in row.items() if key not in {"machine", "machine_v2"}} for row in rows]
    out.write_text(json.dumps(public, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return len(rows)


_GRADE_COLUMNS = (
    "unit_id", "context_before", "sentence", "context_after",
    "act", "act_code", "actor",
    "platform_means", "platform",
    "feature_means", "feature",
)


def _yes(value: str) -> bool:
    return (value or "").strip().lower() in {"y", "yes", "1", "true"}


def export_grading_csv(sheet: dict, out: Path) -> int:
    """Blind CSV. The machine key is not an input and is not a column."""
    refuse_store(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_GRADE_COLUMNS)
        writer.writeheader()
        for unit in sheet["units"]:
            writer.writerow({
                "unit_id": unit["unit_id"],
                "context_before": " | ".join(unit.get("context_before") or []),
                "sentence": unit.get("sentence") or "",
                "context_after": " | ".join(unit.get("context_after") or []),
                "act": "",
                "act_code": "",
                "actor": "",
                "platform_means": "",
                "platform": "",
                "feature_means": "",
                "feature": "",
            })
    return len(sheet["units"])


def import_graded_csv(path: Path) -> dict:
    """Filled CSV back into the graded JSON ``score`` reads.

    ``act`` yes uses ``act_code`` as ``gold.act``. ``platform_means`` yes is
    ``gold.means_tie``. ``feature_means`` yes is ``gold.level_c``. The platform
    and feature names are kept on the unit and are not scoring units.
    """
    units = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            act = (row.get("act_code") or "").strip() if _yes(row.get("act") or "") else ""
            units.append({
                "unit_id": row["unit_id"],
                "gold": {
                    "act": act,
                    "means_tie": _yes(row.get("platform_means") or ""),
                    "level_c": _yes(row.get("feature_means") or ""),
                },
                "actor": (row.get("actor") or "").strip(),
                "platform": (row.get("platform") or "").strip(),
                "feature": (row.get("feature") or "").strip(),
            })
    return {"units": units}


def write_draw(sample: dict, sheet_dir: Path, record_dir: Path) -> dict:
    """The sheet folder gets the blind sheet and CSV. The record folder gets the draw and the key."""
    refuse_store(sheet_dir)
    refuse_store(record_dir)
    if sheet_dir.resolve() == record_dir.resolve():
        raise SystemExit("the draw record is kept out of the sheet folder")
    sheet_dir.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)
    digest = draw_sha256(sample)
    (record_dir / "draw.sha256").write_text(digest + "\n", encoding="utf-8")
    (record_dir / "draw.json").write_text(json.dumps(sample, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    sheet = grading_sheet(sample)
    (sheet_dir / "grading_sheet.json").write_text(json.dumps(sheet, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    export_grading_csv(sheet, sheet_dir / "grading_sheet.csv")
    (record_dir / "key.json").write_text(json.dumps(key_file(sample), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"sha256": digest, "units": len(sample["rows"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--population", type=Path, required=True)
    d.add_argument("--config", type=Path, required=True)
    d.add_argument("--sealed", type=Path, required=True)
    d.add_argument("--sheet-out", type=Path, required=True)
    d.add_argument("--record-out", type=Path, required=True)
    d.add_argument("--decisions", type=Path, required=True)
    d.add_argument("--observations", type=Path, required=True)
    d.add_argument("--decisions-v2", type=Path, required=True)
    d.add_argument("--observations-v2", type=Path, required=True)
    p = sub.add_parser("population")
    p.add_argument("--text-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--decisions", type=Path, required=True)
    p.add_argument("--observations", type=Path, required=True)
    p.add_argument("--decisions-v2", type=Path, required=True)
    p.add_argument("--observations-v2", type=Path, required=True)
    p.add_argument("cases", nargs="+")
    e = sub.add_parser("export-csv")
    e.add_argument("--sheet", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    i = sub.add_parser("import-csv")
    i.add_argument("--csv", type=Path, required=True)
    i.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    s.add_argument("--graded", type=Path, required=True)
    s.add_argument("--key", type=Path, required=True)
    s.add_argument("--draw", type=Path, required=True)
    s.add_argument("--sealed", type=Path, required=True)
    s.add_argument("--replicates", type=int, default=2000, help="bootstrap replicates (default: 2000)")
    s.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    for path in (getattr(args, "population", None), getattr(args, "config", None),
                 getattr(args, "sealed", None), getattr(args, "graded", None),
                 getattr(args, "key", None), getattr(args, "draw", None),
                 getattr(args, "sheet", None), getattr(args, "csv", None),
                 getattr(args, "out", None), getattr(args, "text_root", None)):
        if path is not None:
            refuse_store(path)
    if args.cmd == "population":
        print(write_population(args.cases, args.text_root, args.out, args.decisions, args.observations,
                               args.decisions_v2, args.observations_v2))
        return 0
    if args.cmd == "export-csv":
        sheet = json.loads(args.sheet.read_text(encoding="utf-8"))
        print(export_grading_csv(sheet, args.out))
        return 0
    if args.cmd == "import-csv":
        graded = import_graded_csv(args.csv)
        args.out.write_text(json.dumps(graded, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(len(graded["units"]))
        return 0
    sealed = json.loads(args.sealed.read_text(encoding="utf-8"))
    if args.cmd == "draw":
        population = label_rows(
            json.loads(args.population.read_text(encoding="utf-8")),
            args.decisions, args.observations, args.decisions_v2, args.observations_v2)
        config = json.loads(args.config.read_text(encoding="utf-8"))
        sample = draw_sample(population, config, sealed=sealed)
        print(json.dumps(write_draw(sample, args.sheet_out, args.record_out), indent=1))
    else:
        graded = json.loads(args.graded.read_text(encoding="utf-8"))
        key = json.loads(args.key.read_text(encoding="utf-8"))
        sample = json.loads(args.draw.read_text(encoding="utf-8"))
        print(json.dumps(score_drawn(graded, key, sample, sealed=sealed, replicates=args.replicates, seed=args.seed), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
