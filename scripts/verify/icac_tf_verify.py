#!/usr/bin/env python3
"""
ICAC task-force text hits vs CaseLinker ``source`` (explicit ingest pipeline).

Same needle list as the historical ``icac_tf_text_hits.py`` (inlined here so this
script runs standalone).

Usage:
  python3 scripts/verify/icac_tf_verify.py --db caselinker.db
  python3 scripts/verify/icac_tf_verify.py --db caselinker.db --cross-csv /tmp/tf_cross.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# 61 geographic ICAC contact “lead” rows + 1 military row = 62.
TF_ROWS: List[Tuple[str, Sequence[str | re.Pattern]]] = [
    ("AL — Alabama Law Enforcement Agency", ("alabama law enforcement agency", re.compile(r"\balea\b", re.I))),
    ("AK — Anchorage Police Department", ("anchorage police department", re.compile(r"\bapd\b.*anchorage|anchorage.*\bapd\b", re.I))),
    ("AZ — Phoenix Police Department", ("phoenix police department", "phoenix police", re.compile(r"\bppd\b.*phoenix|phoenix.*\bppd\b", re.I))),
    ("AR — Arkansas State Police", ("arkansas state police", re.compile(r"\basp\b.*arkansas|arkansas state patrol", re.I))),
    ("CA — Fresno County Sheriff's Office", ("fresno county sheriff", "fresno sheriff")),
    ("CA — Los Angeles Police Department", ("los angeles police department", re.compile(r"\blapd\b", re.I))),
    ("CA — Sacramento County Sheriff's Office", ("sacramento county sheriff", "sacramento sheriff")),
    ("CA — San Diego Police Department", ("san diego police department", re.compile(r"\bsdpd\b", re.I))),
    ("CA — San Jose Police Department", ("san jose police department", re.compile(r"\bsjpd\b", re.I))),
    ("CO — Colorado Springs Police Department", ("colorado springs police department", re.compile(r"\bcspd\b.*colorado springs", re.I))),
    ("CT — Connecticut State Police", ("connecticut state police", re.compile(r"\bcsp\b.*connecticut", re.I))),
    ("DE — Delaware Department of Justice", ("delaware department of justice",)),
    ("FL — Central (Osceola County Sheriff's Office)", ("osceola county sheriff",)),
    ("FL — Northern (Gainesville Police Department)", ("gainesville police department", re.compile(r"\bgpd\b.*gainesville", re.I))),
    ("FL — Southern (Broward County Sheriff's Office)", ("broward county sheriff", "broward sheriff's office", "broward sheriff")),
    ("GA — Georgia Bureau of Investigation", ("georgia bureau of investigation", re.compile(r"\bgbi\b", re.I))),
    (
        "HI — Hawaii Department of the Attorney General",
        (
            "hawaii department of the attorney general",
            "hawaii attorney general",
            "operation keiki shield",
            re.compile(r"\bhicac\b", re.I),
        ),
    ),
    ("ID — Idaho Office of Attorney General", ("idaho office of the attorney general", "idaho attorney general")),
    ("IL — Illinois Office of the Attorney General", ("illinois attorney general", "illinois office of the attorney general")),
    (
        "IL — Cook County State's Attorney's Office",
        (
            "cook county state's attorney",
            "cook county state attorney",
            re.compile(r"\bccsao\b", re.I),
            re.compile(r"cook county.{0,60}state'?s attorney", re.I),
        ),
    ),
    ("IN — Indiana State Police", ("indiana state police", re.compile(r"\bisp\b.*indiana", re.I))),
    ("IA — Iowa Division of Criminal Investigation", ("iowa division of criminal investigation", "iowa dci")),
    ("KS — Sedgwick County Sheriff's Office", ("sedgwick county sheriff", "wichita.*sheriff", "sedgwick county district attorney")),
    ("KY — Kentucky State Police", ("kentucky state police", re.compile(r"\bksp\b", re.I))),
    ("LA — Louisiana Department of Justice", ("louisiana department of justice", "louisiana attorney general")),
    ("ME — Maine State Police", ("maine state police",)),
    ("MD — Maryland State Police", ("maryland state police", re.compile(r"\bmsp\b.*maryland", re.I))),
    ("MA — Massachusetts State Police", ("massachusetts state police",)),
    ("MI — Michigan State Police", ("michigan state police", re.compile(r"\bmsp\b.*michigan|michigan.*\bmsp\b", re.I))),
    ("MN — Minnesota Bureau of Criminal Apprehension", ("minnesota bureau of criminal apprehension", re.compile(r"\bbca\b.*minnesota", re.I))),
    ("MS — Mississippi Office of the Attorney General", ("mississippi attorney general", "mississippi office of the attorney general")),
    ("MO — St. Charles County Police Department", ("st. charles county police", "st charles county police")),
    ("MT — Montana Division of Criminal Investigation", ("montana division of criminal investigation", "montana dci", "montana department of justice")),
    ("NE — Nebraska State Patrol", ("nebraska state patrol",)),
    ("NV — Las Vegas Metropolitan Police Department", ("las vegas metropolitan police", "las vegas metro police", re.compile(r"\blvmpd\b", re.I))),
    ("NH — Portsmouth Police Department", ("portsmouth police department", re.compile(r"\bppd\b.*portsmouth", re.I))),
    ("NJ — New Jersey State Police", ("new jersey state police", re.compile(r"\bnjsp\b", re.I))),
    ("NM — New Mexico Attorney General's Office", ("new mexico attorney general", "new mexico department of justice")),
    ("NY — New York State Police", ("new york state police", re.compile(r"\bnysp\b", re.I))),
    ("NY — New York City Police Department", ("new york city police department", re.compile(r"\bnypd\b", re.I))),
    ("NC — North Carolina State Bureau of Investigation", ("north carolina state bureau of investigation", "north carolina sbi", re.compile(r"\bncsbi\b", re.I))),
    ("ND — North Dakota Bureau of Criminal Investigation", ("north dakota bureau of criminal investigation", "north dakota bci")),
    ("OH — Cuyahoga County Prosecuting Attorney's Office", ("cuyahoga county prosecuting attorney", "cuyahoga county prosecutor")),
    ("OK — Oklahoma State Bureau of Investigation", ("oklahoma state bureau of investigation", "oklahoma osbi", re.compile(r"\bosbi\b.*oklahoma", re.I))),
    ("OR — Oregon Department of Justice", ("oregon department of justice", "oregon attorney general")),
    ("PA — Delaware County District Attorney's Office", ("delaware county district attorney", "delaware county prosecutor")),
    ("RI — Rhode Island State Police", ("rhode island state police", re.compile(r"\brisp\b", re.I))),
    ("SC — South Carolina Attorney General's Office", ("south carolina attorney general",)),
    ("SD — South Dakota Division of Criminal Investigation", ("south dakota division of criminal investigation", "south dakota dci")),
    ("TN — Knoxville Police Department", ("knoxville police department", re.compile(r"\bkpd\b.*knoxville", re.I))),
    ("TX — Office of the Attorney General of Texas", ("office of the attorney general of texas", "texas attorney general")),
    ("TX — Dallas Police Department", ("dallas police department", re.compile(r"\bdpd\b.*dallas", re.I))),
    ("TX — Houston Police Department", ("houston police department", re.compile(r"\bhpd\b.*houston", re.I))),
    ("UT — Utah Office of the Attorney General", ("utah attorney general", "utah office of the attorney general")),
    ("VT — Vermont Office of the Attorney General", ("vermont attorney general", "vermont office of the attorney general")),
    ("VA — Virginia State Police", ("virginia state police", re.compile(r"\bvsp\b.*virginia", re.I))),
    ("VA — Bedford County Sheriff's Office", ("bedford county sheriff",)),
    ("WA — Seattle Police Department", ("seattle police department", re.compile(r"\bspd\b.*seattle|seattle.*\bspd\b", re.I))),
    ("WV — West Virginia State Police", ("west virginia state police",)),
    ("WI — Wisconsin Department of Justice", ("wisconsin department of justice", "wisconsin attorney general")),
    ("WY — Wyoming Division of Criminal Investigation", ("wyoming division of criminal investigation", "wyoming dci")),
    ("U.S. — Armed Forces / military investigative agencies", ("army criminal investigation", "ncis", "air force office of special investigations", "afosi", "coast guard investig", "military criminal investigative")),
]

GEOGRAPHIC_TF_LABELS: List[str] = [
    label for label, _ in TF_ROWS if not label.startswith("U.S. —")
]
ICAC_TF_ROSTER_GEOGRAPHIC = 61


# Curly/smart quotes and similar → ASCII apostrophe so PDF extract matches needles.
_APOSTROPHE_LIKE = (
    "\u2019",
    "\u2018",
    "\u2032",
    "\u02bc",
    "\u00b4",
    "`",
)


def _normalize_match_text(text: str) -> str:
    if not text:
        return ""
    t = text.lower()
    for ch in _APOSTROPHE_LIKE:
        t = t.replace(ch, "'")
    return re.sub(r"\s+", " ", t)


def _haystack(case_text: str, agencies_blob: str) -> str:
    parts = [case_text or "", agencies_blob or ""]
    return _normalize_match_text("\n".join(parts))


def _matches(needle: str | re.Pattern, hay: str) -> bool:
    hay_n = _normalize_match_text(hay)
    if isinstance(needle, re.Pattern):
        return needle.search(hay_n) is not None
    return _normalize_match_text(needle) in hay_n


def _tf_text_hit(label: str, needles: Sequence[str | re.Pattern], hay: str, source: str) -> bool:
    """Narrative needle match, or case ingested on that row's mapped pipeline (mangled PDF text)."""
    if any(_matches(n, hay) for n in needles):
        return True
    aligned = TF_TO_ALIGNED_SOURCES.get(label, set())
    return bool(aligned and source in aligned)


# Federal / national feeds (name-drops common; not “state pipeline” for TF rows).
AGGREGATOR_SOURCES = frozenset({"NCMEC", "DOJ CEOS", "DOJ ARCHIVES", "DOJ SAFE CHILDHOOD"})

# Any CaseLinker source we treat as a state / regional ICAC-style ingest (excludes NCMEC + DOJ).
ICAC_LIKE_SOURCES = frozenset(
    {
        "ALEA",
        "ARKANSAS DPS",
        "AZICAC",
        "GBI",
        "HI AG",
        "CCSAO",
        "CSPD",
        "DE AG",
        "FL AG",
        "FRESNO SO",
        "OSCEOLA SO",
        "ILLINOIS AG",
        "IA DCI",
        "Idaho ICAC",
        "KY SP",
        "NE SP",
        "LA AG",
        "LAPD",
        "LVMPD",
        "SJPD",
        "Michigan ICAC",
        "MS AG",
        "MT DOJ",
        "NC SBI",
        "NEWYORK SP",
        "NJ AG",
        "NM AG",
        "OHIO AG",
        "OREGON DOJ",
        "PA AG",
        "RI AG",
        "SCAG ICAC",
        "SD AG",
        "ANCHORAGE PD",
        "ARMY CID",
        "SEDGWICK SO",
        "SOUTH FLORIDA ICAC",
        "SPD",
        "SDPD",
        "SVICAC",
        "TBI ICAC",
        "Texas AG",
        "UT AG",
        "VT AG",
        "WA AG",
        "WCSO",
        "WY DCI",
        "MA ICAC",  # legacy rows in older DBs
    }
)

# ICAC contact-row label → CaseLinker ``source`` values that count as explicit pipeline
# for that row (exact strings as stored in SQLite). Empty set = no dedicated ingest
# for that lead in this repo.
TF_TO_ALIGNED_SOURCES: Dict[str, Set[str]] = {
    "AL — Alabama Law Enforcement Agency": {"ALEA"},
    "AK — Anchorage Police Department": {"ANCHORAGE PD"},
    "AZ — Phoenix Police Department": {"AZICAC"},
    "AR — Arkansas State Police": {"ARKANSAS DPS"},
    "CA — Fresno County Sheriff's Office": {"FRESNO SO"},
    "CA — Los Angeles Police Department": {"LAPD"},
    "CA — Sacramento County Sheriff's Office": set(),
    "CA — San Diego Police Department": {"SDPD"},
    "CA — San Jose Police Department": {"SJPD"},
    "CO — Colorado Springs Police Department": {"CSPD"},
    "CT — Connecticut State Police": set(),
    "DE — Delaware Department of Justice": {"DE AG"},
    "FL — Central (Osceola County Sheriff's Office)": {"OSCEOLA SO"},
    "FL — Northern (Gainesville Police Department)": set(),
    "FL — Southern (Broward County Sheriff's Office)": {"SOUTH FLORIDA ICAC"},
    "GA — Georgia Bureau of Investigation": {"GBI"},
    "HI — Hawaii Department of the Attorney General": {"HI AG"},
    "ID — Idaho Office of Attorney General": {"Idaho ICAC"},
    "IL — Illinois Office of the Attorney General": {"ILLINOIS AG"},
    "IL — Cook County State's Attorney's Office": {"CCSAO"},
    "IN — Indiana State Police": set(),
    "IA — Iowa Division of Criminal Investigation": {"IA DCI"},
    "KS — Sedgwick County Sheriff's Office": {"SEDGWICK SO"},
    "KY — Kentucky State Police": {"KY SP"},
    "LA — Louisiana Department of Justice": {"LA AG"},
    "ME — Maine State Police": set(),
    "MD — Maryland State Police": set(),
    "MA — Massachusetts State Police": set(),
    "MI — Michigan State Police": {"Michigan ICAC"},
    "MN — Minnesota Bureau of Criminal Apprehension": set(),
    "MS — Mississippi Office of the Attorney General": {"MS AG"},
    "MO — St. Charles County Police Department": set(),
    "MT — Montana Division of Criminal Investigation": {"MT DOJ"},
    "NE — Nebraska State Patrol": {"NE SP"},
    "NV — Las Vegas Metropolitan Police Department": {"LVMPD"},
    "NH — Portsmouth Police Department": set(),
    "NJ — New Jersey State Police": {"NJ AG"},
    "NM — New Mexico Attorney General's Office": {"NM AG"},
    "NY — New York State Police": {"NEWYORK SP"},
    "NY — New York City Police Department": set(),
    "NC — North Carolina State Bureau of Investigation": {"NC SBI"},
    "ND — North Dakota Bureau of Criminal Investigation": set(),
    "OH — Cuyahoga County Prosecuting Attorney's Office": {"OHIO AG"},
    "OK — Oklahoma State Bureau of Investigation": set(),
    "OR — Oregon Department of Justice": {"OREGON DOJ"},
    "PA — Delaware County District Attorney's Office": {"PA AG"},
    "RI — Rhode Island State Police": {"RI AG"},
    "SC — South Carolina Attorney General's Office": {"SCAG ICAC"},
    "SD — South Dakota Division of Criminal Investigation": {"SD AG"},
    # Card lists Knoxville PD; CaseLinker Tennessee ICAC channel is TBI newsroom.
    "TN — Knoxville Police Department": {"TBI ICAC"},
    "TX — Office of the Attorney General of Texas": {"Texas AG"},
    "TX — Dallas Police Department": set(),
    "TX — Houston Police Department": set(),
    "UT — Utah Office of the Attorney General": {"UT AG"},
    "VT — Vermont Office of the Attorney General": {"VT AG"},
    "VA — Virginia State Police": set(),
    "VA — Bedford County Sheriff's Office": set(),
    "WA — Seattle Police Department": {"SPD"},
    "WV — West Virginia State Police": set(),
    "WI — Wisconsin Department of Justice": set(),
    "WY — Wyoming Division of Criminal Investigation": {"WY DCI"},
    "U.S. — Armed Forces / military investigative agencies": {"ARMY CID", "DOJ CEOS", "DOJ ARCHIVES", "DOJ SAFE CHILDHOOD"},
}


def analyze_icac_task_forces(
    conn: sqlite3.Connection,
    *,
    include_agencies: bool = True,
) -> Dict[str, Any]:
    """
    Analyze 61 geographic ICAC TF leads vs case narrative and ingest ``source``.

    Returns summary counts, per-TF rows, cross-source rows, and an ingest-backlog list
    for task forces without aligned pipeline coverage.
    """
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM cases")
    (n_rows,) = cur.fetchone()

    text_hits: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    aligned_hits: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    cross_rows: List[Tuple[str, str, str, str]] = []
    icac_like_hit: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    non_agg_hit: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)

    q = "SELECT id, source, raw_data, extracted_features FROM cases"
    for cid, src, raw_json, ex_json in cur.execute(q):
        src_s = (src or "").strip()
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except (TypeError, json.JSONDecodeError):
            raw = {}
        ct = raw.get("case_text") if isinstance(raw.get("case_text"), str) else ""
        agencies_txt = ""
        if include_agencies and ex_json:
            try:
                ex = json.loads(ex_json) if isinstance(ex_json, str) else ex_json
            except (TypeError, json.JSONDecodeError):
                ex = None
            if isinstance(ex, dict):
                ag = ex.get("agencies_involved")
                if isinstance(ag, list):
                    agencies_txt = " ".join(str(x) for x in ag if x)
                elif isinstance(ag, str):
                    agencies_txt = ag
        hay = _haystack(ct, agencies_txt)

        for label, needles in TF_ROWS:
            if not _tf_text_hit(label, needles, hay, src_s):
                continue
            text_hits[label].add((str(cid), src_s))
            if src_s in ICAC_LIKE_SOURCES:
                icac_like_hit[label].add((str(cid), src_s))
            if src_s not in AGGREGATOR_SOURCES:
                non_agg_hit[label].add((str(cid), src_s))
            aligned = TF_TO_ALIGNED_SOURCES.get(label, set())
            if aligned and src_s in aligned:
                aligned_hits[label].add((str(cid), src_s))
            else:
                if not aligned:
                    reason = "no_aligned_source_in_repo"
                elif src_s in AGGREGATOR_SOURCES:
                    reason = "aggregator_or_federal_feed"
                else:
                    reason = "other_state_or_misaligned_feed"
                cross_rows.append((label, str(cid), src_s, reason))

    reason_ct = Counter(r[3] for r in cross_rows)
    cross_reason_by_tf: Dict[str, Counter[str]] = defaultdict(Counter)
    for lab, _cid, _src, reason in cross_rows:
        cross_reason_by_tf[lab][reason] += 1

    n_agg_cross = reason_ct.get("aggregator_or_federal_feed", 0)
    n_other_cross = reason_ct.get("other_state_or_misaligned_feed", 0)
    n_no_map = reason_ct.get("no_aligned_source_in_repo", 0)

    n_geo_text = sum(1 for lab in GEOGRAPHIC_TF_LABELS if len(text_hits[lab]) > 0)
    n_geo_aligned = sum(1 for lab in GEOGRAPHIC_TF_LABELS if len(aligned_hits[lab]) > 0)
    n_geo_icac_like = sum(1 for lab in GEOGRAPHIC_TF_LABELS if len(icac_like_hit[lab]) > 0)
    n_geo_non_agg = sum(1 for lab in GEOGRAPHIC_TF_LABELS if len(non_agg_hit[lab]) > 0)

    per_tf: List[Dict[str, Any]] = []
    ingest_backlog: List[Dict[str, Any]] = []
    for lab in GEOGRAPHIC_TF_LABELS:
        mapped = sorted(TF_TO_ALIGNED_SOURCES.get(lab, set()))
        t_n = len(text_hits[lab])
        a_n = len(aligned_hits[lab])
        row = {
            "label": lab,
            "text_hit_pairs": t_n,
            "aligned_hit_pairs": a_n,
            "icac_like_source_pairs": len(icac_like_hit[lab]),
            "mapped_sources": mapped,
            "has_mapped_ingest": bool(mapped),
        }
        per_tf.append(row)
        if a_n > 0:
            continue
        if t_n == 0:
            priority = "no_narrative_hit"
        elif not mapped:
            priority = "add_ingest_feed"
        else:
            priority = "map_exists_no_aligned_cases"
        ingest_backlog.append({**row, "priority": priority})

    priority_order = {"no_narrative_hit": 0, "add_ingest_feed": 1, "map_exists_no_aligned_cases": 2}
    ingest_backlog.sort(
        key=lambda r: (priority_order.get(r["priority"], 9), -r["text_hit_pairs"], r["label"])
    )

    source_rows = [
        (str(src).strip(), int(n))
        for src, n in cur.execute(
            "SELECT source, COUNT(*) FROM cases GROUP BY source ORDER BY COUNT(*) DESC"
        )
        if src and str(src).strip()
    ]

    return {
        "total_cases": n_rows,
        "geographic_tf_roster": ICAC_TF_ROSTER_GEOGRAPHIC,
        "narrative_hit_tf_count": n_geo_text,
        "aligned_pipeline_tf_count": n_geo_aligned,
        "icac_like_source_tf_count": n_geo_icac_like,
        "non_aggregator_tf_count": n_geo_non_agg,
        "no_narrative_hit_labels": [lab for lab in GEOGRAPHIC_TF_LABELS if len(text_hits[lab]) == 0],
        "cross_source_row_count": len(cross_rows),
        "cross_aggregator_count": n_agg_cross,
        "cross_other_state_count": n_other_cross,
        "cross_no_mapped_ingest_count": n_no_map,
        "icac_like_sources_in_repo": sorted(ICAC_LIKE_SOURCES),
        "icac_like_source_count": len(ICAC_LIKE_SOURCES),
        "per_tf": per_tf,
        "ingest_backlog": ingest_backlog,
        "ingest_backlog_count": len(ingest_backlog),
        "cross_rows": cross_rows,
        "text_hits": {k: list(v) for k, v in text_hits.items()},
        "aligned_hits": {k: list(v) for k, v in aligned_hits.items()},
        "distinct_ingest_source_count": len(source_rows),
        "ingest_sources": [{"source": s, "cases": n} for s, n in source_rows],
    }


def run(db_path: Path, include_agencies: bool, cross_csv: Path | None, aggregator_only_csv: Path | None) -> int:
    if not db_path.is_file():
        print(f"No database at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    analysis = analyze_icac_task_forces(conn, include_agencies=include_agencies)
    conn.close()

    n_rows = analysis["total_cases"]
    GEOGRAPHIC = GEOGRAPHIC_TF_LABELS
    text_hits = {k: set(tuple(p) for p in v) for k, v in analysis["text_hits"].items()}
    aligned_hits = {k: set(tuple(p) for p in v) for k, v in analysis["aligned_hits"].items()}
    cross_rows = list(analysis["cross_rows"])
    cross_reason_by_tf: Dict[str, Counter[str]] = defaultdict(Counter)
    for lab, _cid, _src, reason in cross_rows:
        cross_reason_by_tf[lab][reason] += 1

    n_agg_cross = analysis["cross_aggregator_count"]
    n_other_cross = analysis["cross_other_state_count"]
    n_no_map = analysis["cross_no_mapped_ingest_count"]
    n_geo_text = analysis["narrative_hit_tf_count"]
    n_geo_aligned = analysis["aligned_pipeline_tf_count"]
    n_geo_icac_like = analysis["icac_like_source_tf_count"]
    n_geo_non_agg = analysis["non_aggregator_tf_count"]

    # Rebuild hit sets for per-TF print loop from serialized data
    icac_like_hit = defaultdict(set)
    non_agg_hit = defaultdict(set)
    for lab, pairs in analysis["text_hits"].items():
        for cid, src in pairs:
            if src in ICAC_LIKE_SOURCES:
                icac_like_hit[lab].add((cid, src))
            if src not in AGGREGATOR_SOURCES:
                non_agg_hit[lab].add((cid, src))

    print("=== ICAC TF text hit vs explicit CaseLinker source (aligned pipeline) ===")
    print(f"Database: {db_path}  |  cases: {n_rows}")
    print()
    print("Rules:")
    print("  • Text hit: agency needles on normalized case_text [+ agencies] (smart ’ → ').")
    print("  • Also: CCSAO / HICAC / Keiki Shield needles; mapped ingest source ⇒ text hit.")
    print("  • Aligned hit: text hit AND cases.source is in that TF row’s mapped ingest set.")
    print("  • Cross-source: text hit but NOT aligned (listed in CSV if --cross-csv).")
    print()
    print(f"Geographic TF rows (61) with ≥1 text hit:              {n_geo_text}")
    print(f"Geographic TF rows (61) with ≥1 aligned hit:          {n_geo_aligned}")
    print(
        f"Geographic TF rows (61) with ≥1 hit on ICAC-like state source: {n_geo_icac_like} "
        f"(any of {len(ICAC_LIKE_SOURCES)} state/regional feeds; still not same-TF guarantee)"
    )
    print(
        f"Geographic TF rows (61) with ≥1 hit & source ∉ {{NCMEC,DOJ}}: {n_geo_non_agg}"
    )
    print(f"At least 52 geographic rows with ≥1 aligned hit? {'YES' if n_geo_aligned >= 52 else 'NO'}")
    print(f"At least 52 … ICAC-like-source hit?              {'YES' if n_geo_icac_like >= 52 else 'NO'}")
    print(f"At least 52 … non-federal-aggregator hit?        {'YES' if n_geo_non_agg >= 52 else 'NO'}")
    print()
    print("--- Interpretation (proxy; not human coding of ‘real’ ops) ---")
    print(f"  Cross-source (TF text hit but not aligned) row count: {len(cross_rows)}")
    print(f"    • aggregator_or_federal_feed (NCMEC / DOJ): {n_agg_cross}  ← strongest ‘name-drop’ proxy")
    print(f"    • other_state_or_misaligned_feed:          {n_other_cross}")
    print(f"    • no_aligned_source_in_repo:               {n_no_map}")
    print(
        f"  Geographic TF rows with ≥1 aligned case (ingest mapped to that lead): {n_geo_aligned}"
    )
    print()
    print("Per-TF (geographic only): text | aligned | icac_like_src | non_fed_agg")
    for lab in GEOGRAPHIC:
        t, a = len(text_hits[lab]), len(aligned_hits[lab])
        il, na = len(icac_like_hit[lab]), len(non_agg_hit[lab])
        if t == 0 and a == 0:
            continue
        flag = "OK" if a else "no-aligned"
        print(f"  {t:5d} | {a:5d} | {il:5d} | {na:5d}   [{flag}]  {lab}")

    def _tf_row_line(lab: str) -> str:
        t = len(text_hits[lab])
        a = len(aligned_hits[lab])
        il = len(icac_like_hit[lab])
        na = len(non_agg_hit[lab])
        cr = cross_reason_by_tf[lab]
        x_tot = sum(cr.values())
        x_agg = cr.get("aggregator_or_federal_feed", 0)
        x_oth = cr.get("other_state_or_misaligned_feed", 0)
        x_nom = cr.get("no_aligned_source_in_repo", 0)
        aligned_srcs = TF_TO_ALIGNED_SOURCES.get(lab, set())
        src_note = ", ".join(sorted(aligned_srcs)) if aligned_srcs else "(no mapped ingest in repo)"
        return (
            f"{t}\t{a}\t{il}\t{na}\t{x_tot}\t{x_agg}\t{x_oth}\t{x_nom}\t{lab}\t{src_note}"
        )

    print()
    print("--- Ranked lists (geographic only; counts = distinct (case_id, source) pairs) ---")
    confirmed = [lab for lab in GEOGRAPHIC if len(aligned_hits[lab]) > 0]
    confirmed.sort(key=lambda lab: (-len(aligned_hits[lab]), -len(text_hits[lab]), lab))
    print()
    print(
        f"A) CONFIRMED (pipeline): text hit + source in mapped ingest for this row — "
        f"{len(confirmed)} rows"
    )
    print("rank\ttext\taligned\ticac_like\tnon_NCMEC_DOJ\tcross_all\tcross_NCMEC_DOJ\tcross_other_state\tcross_no_map\tlabel\tmapped_sources")
    for i, lab in enumerate(confirmed, 1):
        print(f"{i}\t{_tf_row_line(lab)}")

    second_hand = [lab for lab in GEOGRAPHIC if len(text_hits[lab]) > 0 and len(aligned_hits[lab]) == 0]
    second_hand.sort(key=lambda lab: (-len(text_hits[lab]), lab))
    print()
    print(
        f"B) SECOND-HAND (pipeline): text/agency needle hit but zero aligned pairs — "
        f"{len(second_hand)} rows (collab / name-drop / wrong card vs ingest; not “fake” by itself)"
    )
    print("rank\ttext\taligned\ticac_like\tnon_NCMEC_DOJ\tcross_all\tcross_NCMEC_DOJ\tcross_other_state\tcross_no_map\tlabel\tmapped_sources")
    for i, lab in enumerate(second_hand, 1):
        print(f"{i}\t{_tf_row_line(lab)}")

    no_text = [lab for lab in GEOGRAPHIC if len(text_hits[lab]) == 0]
    no_text.sort(key=lambda lab: lab)
    print()
    print(f"C) NO_TEXT_HIT (needles never matched in case_text[+agencies]): {len(no_text)} rows")
    for lab in no_text:
        aligned_srcs = TF_TO_ALIGNED_SOURCES.get(lab, set())
        src_note = ", ".join(sorted(aligned_srcs)) if aligned_srcs else "(no mapped ingest in repo)"
        print(f"  • {lab}  |  mapped: {src_note}")

    print()
    print("D) ALL geographic rows by text-hit frequency (most → least)")
    print("rank\ttext\taligned\ticac_like\tnon_NCMEC_DOJ\tcross_all\tcross_NCMEC_DOJ\tcross_other_state\tcross_no_map\tlabel\tmapped_sources")
    by_text = sorted(GEOGRAPHIC, key=lambda lab: (-len(text_hits[lab]), lab))
    for i, lab in enumerate(by_text, 1):
        print(f"{i}\t{_tf_row_line(lab)}")

    if cross_csv:
        cross_csv.parent.mkdir(parents=True, exist_ok=True)
        with cross_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["task_force_label", "case_id", "source", "reason"])
            for row in sorted(cross_rows, key=lambda x: (x[0], x[2], x[1])):
                w.writerow(row)
        print()
        print(f"Wrote {len(cross_rows)} cross-source rows to {cross_csv}")

    if aggregator_only_csv:
        agg_rows = [r for r in cross_rows if r[3] == "aggregator_or_federal_feed"]
        aggregator_only_csv.parent.mkdir(parents=True, exist_ok=True)
        with aggregator_only_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["task_force_label", "case_id", "source", "reason"])
            for row in sorted(agg_rows, key=lambda x: (x[0], x[2], x[1])):
                w.writerow(row)
        print(f"Wrote {len(agg_rows)} aggregator/federal cross rows to {aggregator_only_csv}")

    print()
    print("Note: “Aligned” is pipeline match, not a human read of whether the agency")
    print("      led the operation. NV row maps to WCSO (Washoe ingest) vs LV Metro card.")
    print("      TN row maps to TBI ICAC vs Knoxville PD card.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path(os.environ.get("CASELINKER_DB", REPO_ROOT / "caselinker.db")))
    ap.add_argument("--no-agencies", action="store_true")
    ap.add_argument("--cross-csv", type=Path, default=None)
    ap.add_argument(
        "--aggregator-only-csv",
        type=Path,
        default=None,
        help="Subset of cross rows where source is NCMEC or DOJ (name-drop in federal/national feeds)",
    )
    args = ap.parse_args()
    raise SystemExit(
        run(
            args.db,
            include_agencies=not args.no_agencies,
            cross_csv=args.cross_csv,
            aggregator_only_csv=args.aggregator_only_csv,
        )
    )


if __name__ == "__main__":
    main()
