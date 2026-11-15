#!/usr/bin/env python3
"""Phase 3 vs 2.x passage check on the same 200 cases.

The sample is case ids stored in both the 2.x baseline and the live Postgres
corpus. One seat comes from each shared source. The remaining seats follow the
number of paired cases in that source. Seed 20261017.

Pass ``--ids scripts/verify/phase_3/phase3_paired_sample_ids.txt`` to judge that frozen
draw. With no id file, the script draws a fresh sample.

A stored age or sentence is wrong when the passage check rejects it. Uncertain
values stay in the stored count and out of the wrong count. ``reading`` on a
rejected row is a separate look at the passage: ``real_wrong`` or ``false_flag``.

Usage:
  python3 scripts/verify/phase_3/phase3_paired_results.py
  python3 scripts/verify/phase_3/phase3_paired_results.py --ids scripts/verify/phase_3/phase3_paired_sample_ids.txt
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras

REPO = Path(__file__).resolve().parents[3]
BASELINE = REPO / "caselinker_v25_baseline.db"
SAMPLE_IDS = Path(__file__).with_name("phase3_paired_sample_ids.txt")
SEED = 20261017
N = 200
_NUMBER_WORDS = {
    "5": "five", "8": "eight", "9": "nine", "13": "thirteen",
    "15": "fifteen", "30": "thirty",
}
# Passage readings for the frozen draw. Key is side, case id, kind, value.
# real_wrong: the stored final does not match the passage.
# false_flag: the passage check rejected a final the passage supports.
READINGS = {
    ("phase3", "doj_archives_2007_003", "age", "5"): "false_flag",
    ("phase3", "doj_ceos_2013_138", "age", "15"): "false_flag",
    ("phase3", "doj_safe_childhood_2024_251", "age", "30"): "false_flag",
    ("phase3", "doj_safe_childhood_2025_397", "sentence", "five years supervised release"): "false_flag",
    ("phase3", "doj_safe_childhood_2023_259", "age", "9"): "real_wrong",
    ("phase3", "doj_safe_childhood_2022_308", "age", "8"): "false_flag",
    ("phase3", "doj_safe_childhood_2025_278", "sentence", "ten-year supervised release"): "false_flag",
    ("phase3", "doj_safe_childhood_2024_179", "age", "13"): "false_flag",
    ("v2", "doj_ceos_2013_138", "age", "15"): "false_flag",
    ("v2", "doj_safe_childhood_2024_251", "age", "30"): "false_flag",
    # Holdout, seed 20261018. Readings only. No extractor change was made from these.
    ("phase3", "doj_ceos_2010_022", "sentence", "five years supervised release"): "false_flag",
    ("phase3", "doj_safe_childhood_2026_047", "sentence", "ten years supervised release"): "false_flag",
    ("phase3", "doj_safe_childhood_2022_129", "sentence", "lifetime term supervised release"): "false_flag",
    ("phase3", "doj_safe_childhood_2025_036", "sentence", "life term supervised release"): "false_flag",
    ("phase3", "illinois_ag_2025_007", "sentence", "three and a half years"): "false_flag",
    ("phase3", "pa_ag_2026_025", "sentence", "six years probation"): "false_flag",
    ("phase3", "ohio_ag_2015_005", "age", "6"): "false_flag",
    ("phase3", "texas_ag_2018_004", "age", "61"): "false_flag",
    ("phase3", "svicac_2021_002", "age", "10"): "false_flag",
    ("phase3", "doj_safe_childhood_2024_264", "age", "4"): "real_wrong",
    ("phase3", "doj_safe_childhood_2024_264", "age", "6"): "real_wrong",
    ("phase3", "pa_ag_2025_026", "sentence", "30 Years"): "real_wrong",
    ("v2", "svicac_2021_002", "age", "10"): "false_flag",
    ("v2", "de_ag_2017_006", "age", "35"): "real_wrong",
    ("v2", "pa_ag_2025_026", "sentence", "30 Years"): "real_wrong",
}
# 2.x sentence flags read as statutory exposure, a fine, or a bare
# "supervised release" fragment that does not state the imposed term.
REAL_WRONG = {
    ("v2", "doj_ceos_2013_032", "sentence", "mandatory minimum"),
    ("v2", "doj_ceos_2013_032", "sentence", "15 years"),
    ("v2", "doj_ceos_2013_032", "sentence", "30 years"),
    ("v2", "doj_ceos_2025_038", "sentence", "15 years"),
    ("v2", "doj_safe_childhood_2026_253", "sentence", "20 years"),
    ("v2", "doj_safe_childhood_2026_121", "sentence", "40 years"),
    ("v2", "doj_safe_childhood_2025_397", "sentence", "supervised release"),
    ("v2", "doj_safe_childhood_2023_525", "sentence", "20 years"),
    ("v2", "doj_safe_childhood_2025_278", "sentence", "supervised release"),
    ("v2", "doj_safe_childhood_2026_012", "sentence", "supervised release"),
    ("v2", "doj_safe_childhood_2024_420", "sentence", "mandatory minimum"),
    ("v2", "doj_safe_childhood_2024_420", "sentence", "15 years"),
    ("v2", "doj_safe_childhood_2024_420", "sentence", "30 years"),
    ("v2", "doj_safe_childhood_2024_420", "sentence", "supervised release"),
    ("v2", "ncmec_2024_1061", "sentence", "10 years"),
    ("v2", "nj_ag_2023_001", "sentence", "$15,000"),
    ("v2", "nj_ag_2023_001", "sentence", "18 months"),
    ("v2", "nj_ag_2023_001", "sentence", "$10,000"),
    ("v2", "nj_ag_2026_001", "sentence", "$15,000"),
    ("v2", "nj_ag_2026_001", "sentence", "18 months"),
    ("v2", "nj_ag_2026_001", "sentence", "$10,000"),
    ("v2", "scag_icac_2023_045", "sentence", "10 years"),
    ("v2", "scag_icac_2021_030", "sentence", "10 years"),
    ("v2", "scag_icac_2022_057", "sentence", "10 years"),
    ("v2", "scag_icac_2025_116", "sentence", "10 years"),
    ("v2", "scag_icac_2021_035", "sentence", "10 years"),
    ("v2", "scag_icac_2021_002", "sentence", "10 years"),
    ("v2", "scag_icac_2025_031", "sentence", "10 years"),
    ("v2", "svicac_2022_016", "sentence", "20 years"),
    ("v2", "svicac_2022_016", "sentence", "$250,000"),
    ("v2", "usss_2016_002", "sentence", "mandatory minimum sentence"),
    ("v2", "wy_dci_2024_004", "sentence", "264 years"),
    ("v2", "wy_dci_2024_004", "sentence", "$240,000"),
    # Holdout 2.x sentences: exposure, a statutory ceiling, a bond, or a fragment.
    ("v2", "doj_archives_2007_030", "sentence", "mandatory minimum sentence"),
    ("v2", "doj_archives_2008_010", "sentence", "15 years"),
    ("v2", "doj_archives_2008_010", "sentence", "10 years"),
    ("v2", "doj_archives_2008_010", "sentence", "20 years"),
    ("v2", "doj_archives_2005_025", "sentence", "mandatory minimum sentence"),
    ("v2", "doj_ceos_2013_090", "sentence", "15 years"),
    ("v2", "doj_ceos_2013_090", "sentence", "supervised release"),
    ("v2", "doj_ceos_2013_068", "sentence", "mandatory minimum"),
    ("v2", "doj_ceos_2013_068", "sentence", "25 years"),
    ("v2", "doj_ceos_2013_068", "sentence", "50 years"),
    ("v2", "doj_ceos_2013_068", "sentence", "$250,000"),
    ("v2", "doj_safe_childhood_2022_553", "sentence", "10 years"),
    ("v2", "doj_safe_childhood_2022_553", "sentence", "20 years"),
    ("v2", "doj_safe_childhood_2022_553", "sentence", "supervised release"),
    ("v2", "doj_safe_childhood_2024_519", "sentence", "15 years"),
    ("v2", "doj_safe_childhood_2024_519", "sentence", "30 years"),
    ("v2", "doj_safe_childhood_2026_284", "sentence", "mandatory minimum"),
    ("v2", "doj_safe_childhood_2026_284", "sentence", "15 years"),
    ("v2", "doj_safe_childhood_2026_284", "sentence", "40 years"),
    ("v2", "doj_safe_childhood_2026_041", "sentence", "10 years"),
    ("v2", "doj_safe_childhood_2026_041", "sentence", "20 years"),
    ("v2", "doj_safe_childhood_2026_041", "sentence", "supervised release"),
    ("v2", "doj_safe_childhood_2026_041", "sentence", "15 years"),
    ("v2", "doj_safe_childhood_2026_258", "sentence", "20 years"),
    ("v2", "doj_safe_childhood_2026_258", "sentence", "$250,000"),
    ("v2", "doj_safe_childhood_2026_258", "sentence", "$17,000"),
    ("v2", "doj_safe_childhood_2025_036", "sentence", "supervised release"),
    ("v2", "hi_ag_2024_001", "sentence", "10 years"),
    ("v2", "illinois_ag_2018_001", "sentence", "30 years"),
    ("v2", "illinois_ag_2018_001", "sentence", "$400,000"),
    ("v2", "illinois_ag_2015_004", "sentence", "30 years"),
    ("v2", "illinois_ag_2015_004", "sentence", "15 years"),
    ("v2", "illinois_ag_2015_004", "sentence", "$750,000"),
    ("v2", "illinois_ag_2023_007", "sentence", "30 years"),
    ("v2", "illinois_ag_2014_008", "sentence", "30 years"),
    ("v2", "ncmec_2023_202", "sentence", "150 years"),
    ("v2", "ncmec_2023_027", "sentence", "15 years"),
    ("v2", "ncmec_2025_863", "sentence", "10 years"),
    ("v2", "scag_icac_2026_043", "sentence", "10 years"),
    ("v2", "scag_icac_2021_078", "sentence", "10 years"),
    ("v2", "scag_icac_2021_022", "sentence", "10 years"),
    ("v2", "scag_icac_2024_064", "sentence", "20 years"),
    ("v2", "scag_icac_2024_064", "sentence", "10 years"),
    ("v2", "scag_icac_2024_002", "sentence", "20 years"),
    ("v2", "scag_icac_2024_002", "sentence", "10 years"),
    ("v2", "scag_icac_2024_067", "sentence", "10 years"),
    ("v2", "scag_icac_2022_032", "sentence", "10 years"),
    ("v2", "scag_icac_2022_004", "sentence", "10 years"),
    ("v2", "scag_icac_2021_057", "sentence", "10 years"),
    ("v2", "texas_ag_2018_004", "sentence", "10 years"),
    ("v2", "texas_ag_2018_004", "sentence", "60 years"),
    ("v2", "vt_ag_2024_025", "sentence", "5 years"),
    ("v2", "wy_dci_2023_001", "sentence", "10 years"),
    ("v2", "wy_dci_2023_001", "sentence", "$5,000"),
}

EXPOSURE = re.compile(
    r"faces?\s+up\s+to|punishable\s+by|maximum\s+of|could\s+face|"
    r"carries?\s+a\s+(?:maximum|sentence)|up\s+to\s+\d",
    re.I,
)
IMPOSED = re.compile(
    r"sentenced\s+to|was\s+sentenced|received\s+a\s+sentence|"
    r"ordered\s+to\s+serve|pleaded\s+guilty\s+and\s+was",
    re.I,
)
PRIOR = re.compile(
    r"previously\s+(?:sentenced|jailed|convicted)|"
    r"in\s+\d{4}\b.{0,40}sentenced|prior\s+conviction",
    re.I,
)


def database_url() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DATABASE_URL is not set in .env")


def loads(raw):
    if raw is None or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


def ages_of(features) -> dict[str, list[str]]:
    features = loads(features) or {}
    perps = features.get("perpetrator_age") or []
    victims = (features.get("case_demographics") or {}).get("ages") or []
    if isinstance(perps, str):
        perps = [perps]
    if isinstance(victims, str):
        victims = [victims]
    return {
        "perpetrators": [str(value) for value in perps],
        "victims": [str(value) for value in victims],
    }


def sentences_of(features) -> list[str]:
    features = loads(features) or {}
    outcome = features.get("prosecution_outcome") or {}
    sentences = (outcome or {}).get("sentences") or []
    if isinstance(sentences, str):
        sentences = loads(sentences) or []
    if not isinstance(sentences, list):
        return []
    return [str(value) for value in sentences if str(value).strip()]


def case_text(raw) -> str:
    raw = loads(raw) or {}
    if not isinstance(raw, dict):
        return ""
    return raw.get("case_text") or ""


def window(text: str, needle: str, radius: int = 140) -> str:
    if not text or not needle:
        return ""
    low = text.lower()
    token = needle.lower()
    index = low.find(token)
    if index < 0:
        match = re.search(r"\d+", needle)
        if not match:
            return ""
        index = low.find(match.group(0))
        if index < 0:
            return ""
        token = match.group(0)
    start = max(0, index - radius)
    end = min(len(text), index + len(token) + radius)
    return " ".join(text[start:end].split())


def _age_snippet(value: str, text: str) -> str:
    escaped = re.escape(value)
    pattern = re.compile(
        rf".{{0,90}}(?:{escaped}[- ]year[- ]old|{escaped}\s+years?\s+old|"
        rf"aged?\s+{escaped}\b|age[:\s]+{escaped}\b|,"
        rf"?\s*{escaped},?\s+of\b|{escaped}\s+years?\b).{{0,90}}",
        re.I,
    )
    match = pattern.search(text)
    return " ".join(match.group(0).split()) if match else ""


def judge_age(value: str, text: str) -> str:
    if not text:
        return "uncertain"
    snippet = _age_snippet(value, text)
    if snippet:
        if re.search(rf"\b{re.escape(value)}\s+years?\b", snippet, re.I) and not re.search(
            r"year[- ]old|years old|aged|age[:\s]", snippet, re.I
        ):
            if re.search(r"prison|sentence|probation|supervised", snippet, re.I):
                return "wrong"
        if re.search(rf"under\s+{re.escape(value)}\s+years\s+of\s+age", snippet, re.I):
            return "wrong"
        if re.search(rf"as young as {re.escape(value)}", snippet, re.I):
            return "wrong"
        return "ok"
    if not re.search(rf"\b{re.escape(value)}\b", text):
        return "wrong"
    years = re.findall(r"\b(?:19|20)\d{2}\b", text)
    if value in years and not _age_snippet(value, text):
        stripped = re.sub(r"\b(?:19|20)\d{2}\b", "", text)
        if not re.search(rf"(?<!\d){re.escape(value)}(?!\d)", stripped):
            return "wrong"
    return "uncertain"


def _loose_in(text: str, value: str) -> str:
    parts = [part for part in re.split(r"[\s\-]+", value.lower()) if part and part not in {"of", "a", "the"}]
    if not parts:
        return ""
    pattern = r".{0,40}".join(re.escape(part) for part in parts)
    match = re.search(pattern, text, re.I)
    if not match:
        return ""
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 80)
    return " ".join(text[start:end].split())


def judge_sentence(value: str, text: str) -> str:
    if not text:
        return "uncertain"
    context = _loose_in(text, value) or window(text, value, 180)
    if not context:
        return "wrong"
    if EXPOSURE.search(context) and not IMPOSED.search(context):
        return "wrong"
    if PRIOR.search(context) and not IMPOSED.search(context):
        return "wrong"
    return "ok"


def paired_ids(baseline: sqlite3.Connection, postgres) -> dict[str, list[str]]:
    baseline_ids = {row[0] for row in baseline.execute("SELECT id FROM cases")}
    cursor = postgres.cursor()
    cursor.execute("SELECT id, source FROM cases")
    by_source: dict[str, list[str]] = defaultdict(list)
    for case_id, source in cursor.fetchall():
        if case_id in baseline_ids and source:
            by_source[source].append(case_id)
    cursor.close()
    return by_source


def allocate(by_source: dict[str, list[str]]) -> dict[str, int]:
    sources = sorted(by_source)
    if len(sources) > N:
        raise SystemExit(f"{len(sources)} shared sources is more than {N} seats")
    alloc = {source: 1 for source in sources}
    left = N - len(sources)
    weights = {source: len(by_source[source]) for source in sources}
    total = sum(weights.values())
    raw = {source: left * weights[source] / total for source in sources}
    floors = {source: int(raw[source]) for source in sources}
    for source in sources:
        alloc[source] += floors[source]
    remain = left - sum(floors.values())
    ranked = sorted(sources, key=lambda source: raw[source] - floors[source], reverse=True)
    for source in ranked:
        if remain <= 0:
            break
        if alloc[source] >= len(by_source[source]):
            continue
        alloc[source] += 1
        remain -= 1
    if remain:
        raise SystemExit(f"could not fill {remain} seats from paired cases")
    if sum(alloc.values()) != N:
        raise SystemExit(f"allocation summed to {sum(alloc.values())}")
    return alloc


def sample_ids(by_source: dict[str, list[str]], alloc: dict[str, int], seed: int = SEED) -> list[str]:
    rng = random.Random(seed)
    chosen: list[str] = []
    for source in sorted(by_source):
        ids = by_source[source][:]
        rng.shuffle(ids)
        take = alloc[source]
        if take > len(ids):
            raise SystemExit(f"{source} has {len(ids)} paired cases and was given {take} seats")
        chosen.extend(ids[:take])
    if len(chosen) != N or len(set(chosen)) != N:
        raise SystemExit("sample is not 200 distinct cases")
    return chosen


def _paired_sqlite(baseline: sqlite3.Connection, phase3: sqlite3.Connection) -> dict[str, list[str]]:
    baseline_ids = {row[0] for row in baseline.execute("SELECT id FROM cases")}
    by_source: dict[str, list[str]] = defaultdict(list)
    for case_id, source in phase3.execute("SELECT id, source FROM cases"):
        if case_id in baseline_ids and source:
            by_source[source].append(case_id)
    return by_source


def fetch_sqlite_cases(conn: sqlite3.Connection, ids: list[str]) -> dict[str, sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    found = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        marks = ",".join("?" for _ in chunk)
        for row in conn.execute(
            f"SELECT id, source, extracted_features, raw_data FROM cases WHERE id IN ({marks})",
            chunk,
        ):
            found[row["id"]] = row
    missing = [case_id for case_id in ids if case_id not in found]
    if missing:
        raise SystemExit(f"phase3 sqlite is missing {len(missing)} sampled ids")
    return found


def fetch_postgres(postgres, ids: list[str]) -> dict[str, dict]:
    cursor = postgres.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        "SELECT id, source, extracted_features, raw_data FROM cases WHERE id = ANY(%s)",
        (ids,),
    )
    rows = {row["id"]: row for row in cursor.fetchall()}
    cursor.close()
    missing = [case_id for case_id in ids if case_id not in rows]
    if missing:
        raise SystemExit(f"Postgres is missing {len(missing)} sampled ids")
    return rows


def fetch_baseline(baseline: sqlite3.Connection, ids: list[str]) -> dict[str, sqlite3.Row]:
    baseline.row_factory = sqlite3.Row
    found = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        marks = ",".join("?" for _ in chunk)
        for row in baseline.execute(
            f"SELECT id, extracted_features, raw_data FROM cases WHERE id IN ({marks})",
            chunk,
        ):
            found[row["id"]] = row
    missing = [case_id for case_id in ids if case_id not in found]
    if missing:
        raise SystemExit(f"baseline is missing {len(missing)} sampled ids")
    return found


def load_id_file(path: Path) -> list[str]:
    ids = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(line)
    if len(ids) != N or len(set(ids)) != N:
        raise SystemExit(f"{path} must list {N} distinct case ids, found {len(ids)}")
    return ids


def require_present(label: str, ids: list[str], found: set[str]) -> None:
    missing = [case_id for case_id in ids if case_id not in found]
    if missing:
        raise SystemExit(f"{label} is missing {len(missing)} sampled ids, first {missing[0]}")


def evidence_passage(kind: str, value: str, text: str) -> str:
    # Line breaks sit inside phrases ("supervised\\nrelease"). The check still
    # sees the raw text. The stored passage is the readable window.
    flat = " ".join(text.split())
    if kind == "age":
        passage = _age_snippet(value, flat) or window(flat, value, 180)
        word = _NUMBER_WORDS.get(value)
        if word:
            spelled = window(flat, word, 140)
            if spelled and (not passage or "year" not in passage.lower()):
                return spelled
        return passage
    return _loose_in(flat, value) or window(flat, value, 180)


def value_rows(kind: str, features, text: str) -> list[dict]:
    rows = []
    if kind == "age":
        pairs = [(role, value) for role, values in ages_of(features).items() for value in values]
        judge = judge_age
    else:
        pairs = [("imposed", value) for value in sentences_of(features)]
        judge = judge_sentence
    for role, value in pairs:
        rows.append({
            "kind": kind,
            "role": role,
            "value": value,
            "check": judge(value, text),
            "passage": evidence_passage(kind, value, text),
        })
    return rows


def attach_readings(side: str, case_id: str, rows: list[dict]) -> list[str]:
    unread = []
    for row in rows:
        if row["check"] != "wrong":
            continue
        key = (side, case_id, row["kind"], row["value"])
        reading = READINGS.get(key)
        if reading is None and key in REAL_WRONG:
            reading = "real_wrong"
        if reading is None:
            unread.append(f"{side} {case_id} {row['kind']} {row['role']} {row['value']}")
            continue
        row["reading"] = reading
    return unread


# 95% normal quantile. Wilson's score interval for k errors in n stored finals.
WILSON_Z = 1.959963984540054


def wilson_interval(errors: int, stored: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    """Wilson 95% interval for an error rate. None when nothing was stored."""
    if stored <= 0:
        return None
    if errors < 0 or errors > stored:
        raise ValueError(f"{errors} errors is outside 0..{stored}")
    proportion = errors / stored
    z2 = z * z
    denom = 1 + z2 / stored
    center = (proportion + z2 / (2 * stored)) / denom
    margin = z * math.sqrt(proportion * (1 - proportion) / stored + z2 / (4 * stored * stored)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _fmt_wilson(interval: tuple[float, float] | None) -> str:
    if interval is None:
        return "n/a"
    low, high = interval
    return f"[{low:.4f}, {high:.4f}]"


def summarize(rows: list[dict]) -> dict[str, int]:
    return {
        "age_stored": sum(1 for row in rows if row["kind"] == "age"),
        "age_wrong": sum(1 for row in rows if row["kind"] == "age" and row["check"] == "wrong"),
        "age_real_wrong": sum(1 for row in rows if row["kind"] == "age" and row.get("reading") == "real_wrong"),
        "sentence_stored": sum(1 for row in rows if row["kind"] == "sentence"),
        "sentence_wrong": sum(1 for row in rows if row["kind"] == "sentence" and row["check"] == "wrong"),
        "sentence_real_wrong": sum(
            1 for row in rows if row["kind"] == "sentence" and row.get("reading") == "real_wrong"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase3-sqlite", type=Path,
                        help="read Phase 3 from this sqlite file instead of DATABASE_URL")
    parser.add_argument("--ids", type=Path, help="judge these case ids in file order")
    parser.add_argument("--exclude", type=Path, help="case ids a fresh draw must not use")
    parser.add_argument("--seed", type=int, default=SEED, help="seed for a fresh draw")
    parser.add_argument("--write-ids", type=Path, help="write the draw, one id per line")
    parser.add_argument("--write-results", type=Path, help="write one JSON object per case")
    args = parser.parse_args()

    baseline = sqlite3.connect(f"file:{BASELINE}?mode=ro", uri=True)
    phase3_conn = None
    postgres = None
    if args.phase3_sqlite:
        phase3_conn = sqlite3.connect(f"file:{args.phase3_sqlite}?mode=ro", uri=True)
        by_source = _paired_sqlite(baseline, phase3_conn)
    else:
        postgres = psycopg2.connect(database_url())
        by_source = paired_ids(baseline, postgres)
    if args.ids:
        chosen = load_id_file(args.ids)
        paired = {case_id for ids in by_source.values() for case_id in ids}
        require_present("paired corpus", chosen, paired)
    else:
        if args.exclude:
            banned = {
                line.strip() for line in args.exclude.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            }
            by_source = {
                source: [case_id for case_id in ids if case_id not in banned]
                for source, ids in by_source.items()
            }
            by_source = {source: ids for source, ids in by_source.items() if ids}
        chosen = sample_ids(by_source, allocate(by_source), seed=args.seed)
    if phase3_conn is not None:
        phase3 = fetch_sqlite_cases(phase3_conn, chosen)
        phase3_conn.close()
    else:
        phase3 = fetch_postgres(postgres, chosen)
        postgres.close()
    prior = fetch_baseline(baseline, chosen)

    if args.write_ids:
        args.write_ids.write_text("\n".join(chosen) + "\n", encoding="utf-8")

    totals = {
        "phase3": {
            "age_stored": 0, "age_wrong": 0, "age_real_wrong": 0,
            "sentence_stored": 0, "sentence_wrong": 0, "sentence_real_wrong": 0,
        },
        "v2": {
            "age_stored": 0, "age_wrong": 0, "age_real_wrong": 0,
            "sentence_stored": 0, "sentence_wrong": 0, "sentence_real_wrong": 0,
        },
    }
    records = []
    unread = []
    for order, case_id in enumerate(chosen, start=1):
        current = phase3[case_id]
        current_text = case_text(current["raw_data"])
        old = prior[case_id]
        old_text = case_text(old["raw_data"]) or current_text
        sides = {
            "v2": value_rows("age", old["extracted_features"], old_text) + value_rows("sentence", old["extracted_features"], old_text),
            "phase3": value_rows("age", current["extracted_features"], current_text) + value_rows("sentence", current["extracted_features"], current_text),
        }
        for side, rows in sides.items():
            unread.extend(attach_readings(side, case_id, rows))
            add(totals[side], summarize(rows))
        records.append({
            "order": order,
            "case_id": case_id,
            "source": current["source"],
            "v2": sides["v2"],
            "phase3": sides["phase3"],
        })

    print(f"paired_cases {len(chosen)}")
    print(f"shared_sources {len(by_source)}")
    print(f"sources_in_sample {len({phase3[case_id]['source'] for case_id in chosen})}")
    print(f"ids {'file' if args.ids else 'fresh'} seed {args.seed if not args.ids else 'frozen'}")
    print("side\tkind\tstored\tpassage_wrong\tpassage_rate\tpassage_wilson95\treal_wrong\terror_rate\terror_wilson95")
    for side in ("v2", "phase3"):
        row = totals[side]
        for kind in ("age", "sentence"):
            stored = row[f"{kind}_stored"]
            passage = row[f"{kind}_wrong"]
            real = row[f"{kind}_real_wrong"]
            passage_rate = f"{passage / stored:.4f}" if stored else "n/a"
            error_rate = f"{real / stored:.4f}" if stored else "n/a"
            print(
                f"{side}\t{kind}\t{stored}\t{passage}\t{passage_rate}\t"
                f"{_fmt_wilson(wilson_interval(passage, stored))}\t"
                f"{real}\t{error_rate}\t{_fmt_wilson(wilson_interval(real, stored))}"
            )
    if unread:
        print("UNREAD")
        print("\n".join(unread))
    if args.write_results:
        if unread:
            raise SystemExit("refusing to write results until every rejected final has a reading")
        args.write_results.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
            encoding="utf-8",
        )
    baseline.close()


def add(total: dict[str, int], part: dict[str, int]) -> None:
    for key, value in part.items():
        total[key] += value


if __name__ == "__main__":
    main()
