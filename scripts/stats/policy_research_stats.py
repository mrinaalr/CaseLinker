#!/usr/bin/env python3
"""
Policy-oriented corpus statistics for CaseLinker (SQLite ``cases`` + joins).

Run from repo root:
  python3 scripts/stats/policy_research_stats.py
  CASELINKER_DB=/path/to/caselinker.db python3 scripts/stats/policy_research_stats.py

All percentages and cohorts are documented inline. This DB does **not** store
final convictions or sentence text in ``prosecution_outcomes.sentences`` (often
empty); prosecution analyses use **booking/charge stage** proxies only.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "caselinker.db"

US_STATE_NAMES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
}
# Map common press abbreviations / noise tokens -> canonical state name
ABBREV_TO_STATE = {
    "ala.": "alabama",
    "alaska": "alaska",
    "ariz.": "arizona",
    "ark.": "arkansas",
    "calif.": "california",
    "california": "california",
    "colo.": "colorado",
    "conn.": "connecticut",
    "del.": "delaware",
    "fla.": "florida",
    "ga.": "georgia",
    "ill.": "illinois",
    "ind.": "indiana",
    "kan.": "kansas",
    "kans.": "kansas",
    "ky.": "kentucky",
    "la.": "louisiana",
    "md.": "maryland",
    "mass.": "massachusetts",
    "mich.": "michigan",
    "minn.": "minnesota",
    "miss.": "mississippi",
    "mo.": "missouri",
    "mont.": "montana",
    "neb.": "nebraska",
    "nebr.": "nebraska",
    "nev.": "nevada",
    "n.h.": "new hampshire",
    "n.j.": "new jersey",
    "n.m.": "new mexico",
    "n.y.": "new york",
    "n.c.": "north carolina",
    "n.d.": "north dakota",
    "okla.": "oklahoma",
    "ore.": "oregon",
    "pa.": "pennsylvania",
    "r.i.": "rhode island",
    "s.c.": "south carolina",
    "s.d.": "south dakota",
    "tenn.": "tennessee",
    "tex.": "texas",
    "texas": "texas",
    "utah": "utah",
    "vt.": "vermont",
    "va.": "virginia",
    "wash.": "washington",
    "w.va.": "west virginia",
    "wis.": "wisconsin",
    "wyo.": "wyoming",
    "d.c.": "district of columbia",
}


def db_path() -> Path:
    p = os.environ.get("CASELINKER_DB", "").strip()
    return Path(p) if p else DEFAULT_DB


def j(x: Any) -> Any:
    if x is None or (isinstance(x, str) and not str(x).strip()):
        return None
    if isinstance(x, (dict, list)):
        return x
    try:
        return json.loads(x)
    except Exception:
        return None


def topic_set(case_topics_blob: Any) -> Set[str]:
    t = j(case_topics_blob)
    if isinstance(t, list):
        return {str(x).lower() for x in t if x is not None}
    return set()


def platforms_list(blob: Any) -> List[str]:
    p = j(blob)
    if not isinstance(p, list):
        return []
    return [str(x).strip() for x in p if x is not None and str(x).strip()]


def load_cases(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT id, date_start, date_end, case_topics, platforms_used, "
        "severity_indicators, relationship_to_victim, raw_data, extracted_features "
        "FROM cases"
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def prosecution_rows(conn: sqlite3.Connection, case_id: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT status, charges, sentences FROM prosecution_outcomes WHERE case_id = ?",
        (case_id,),
    )
    return [dict(zip(("status", "charges", "sentences"), r)) for r in cur.fetchall()]


def parse_charges(charges_json: Any) -> List[Dict[str, Any]]:
    c = j(charges_json)
    return [x for x in c if isinstance(x, dict)] if isinstance(c, list) else []


def charge_texts(rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for r in rows:
        for item in parse_charges(r.get("charges")):
            ch = item.get("charge")
            if isinstance(ch, str) and ch.strip():
                out.append(ch.lower())
    return out


def case_text_lower(raw_blob: Any) -> str:
    rd = j(raw_blob)
    if isinstance(rd, dict):
        t = rd.get("case_text")
        if isinstance(t, str):
            return t.lower()
    return ""


# --- 1) CSAM possession + contact -------------------------------------------

# Same pattern as ``extract_severity`` -> ``sexual_abuse`` in
# ``src/Processing Layer/Pattern Processing Layer/pattern_processing.py`` (word-boundary).
_SEXUAL_ABUSE_CONTACT_RE = re.compile(
    r"\b(rape|raped|raping|sexual\s+assault|sexually\s+assaulted|sexual\s+abuse|sexually\s+abused|molest|molested|molesting)\b",
    re.IGNORECASE,
)

# Strip CSAM *category* phrasing where ``sexual abuse`` names material, not contact allegations,
# before applying ``_SEXUAL_ABUSE_CONTACT_RE`` (avoids "child sexual abuse material" inflation).
_CSAM_DEF_LABEL_SCRUB_RE = re.compile(
    r"""(?ix)
    child[\s-]+sexual[\s-]+abuse[\s-]+(?:material|materials|images?|videos?|content|depictions?|files?|csam)\b
    | minor[\s-]+sexual[\s-]+abuse[\s-]+(?:material|materials|images?|videos?|content)\b
    | (?:images?|videos?|materials?|content|depictions?|files?)\s+of\s+child\s+sexual\s+abuse\b
    """
)

# Substring recall for statutory / contact wording (applied to original text, not scrubbed).
_CONTACT_TOKENS = (
    "rape",
    "sodom",
    "molest",
    "sexual contact",
    "physical contact",
    "hands-on",
    "hands on",
    "assault",
    "indecency with",
    "exploitation of a child",
    "sexual conduct with a minor",
    "lewd and lascivious",
    "lewd or lascivious",
    "lascivious exhibition",
    "criminal sexual conduct",
    "carnal knowledge",
    "fondling",
    "fondled",
    "fondles",
    "unlawful sexual contact",
    "unlawful sexual intercourse",
    "unlawful sexual activity with a minor",
    "unlawful sexual conduct with",
    "sexual activity with a minor",
    "penetrative",
    "penetration",
)


def scrub_csam_definitional_labels(text: str) -> str:
    """Remove CSAM product/category labels so regex hits reflect contact allegations, not CSAM naming."""
    return _CSAM_DEF_LABEL_SCRUB_RE.sub(" ", text)


def cohort_csam_possession(T: Set[str]) -> bool:
    """Topics flag both possession and csam (strict ICAM-style bucket)."""
    return "possession" in T and "csam" in T


def contact_signal(T: Set[str], charges_lower: List[str], narrative: str) -> bool:
    """
    Clear contact / hands-on signal for CSAM cohort stats.

    True if ``hands_on`` in ``case_topics``; else if ``_SEXUAL_ABUSE_CONTACT_RE`` matches
    charge + narrative text **after** scrubbing CSAM definitional labels (so ``sexual abuse``
    inside ``child sexual abuse material`` alone does not count); else if any
    ``_CONTACT_TOKENS`` substring hits the **original** charge + narrative text.
    """
    if "hands_on" in T:
        return True
    blob = "\n".join([*charges_lower, narrative])
    scrubbed = scrub_csam_definitional_labels(blob)
    if _SEXUAL_ABUSE_CONTACT_RE.search(scrubbed):
        return True
    for tok in _CONTACT_TOKENS:
        for ch in charges_lower:
            if tok in ch:
                return True
        if tok in narrative:
            return True
    return False


def analyze_possession_contact(cases: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 78)
    print("1) CSAM POSSESSION COHORT vs CONTACT / HANDS-ON SIGNAL")
    print("=" * 78)
    print(
        "Cohort: case_topics contains BOTH 'possession' AND 'csam' (strict).\n"
        "Contact signal: hands_on topic OR extract_severity sexual_abuse regex on text **after**\n"
        "  scrubbing CSAM definitional labels (child sexual abuse material, images of child sexual abuse, ...)\n"
        "  OR broad statutory / contact substring tokens on original text - see contact_signal().\n"
        "Limitation: topics are extracted labels; not all jurisdictions phrase\n"
        "  possession the same way; charges JSON is often empty in PR corpora."
    )
    n_cohort = 0
    n_contact = 0
    n_hands_only = 0
    for c in cases:
        T = topic_set(c.get("case_topics"))
        if not cohort_csam_possession(T):
            continue
        n_cohort += 1
        rows = prosecution_rows(conn, c["id"])
        chg = charge_texts(rows)
        nar = case_text_lower(c.get("raw_data"))
        if "hands_on" in T:
            n_hands_only += 1
        if contact_signal(T, chg, nar):
            n_contact += 1
    if n_cohort == 0:
        print("No cases in cohort.")
        return
    print(f"Cases in cohort (possession + csam topics):     {n_cohort}")
    print(f"... also hands_on topic only:                    {n_hands_only} ({100 * n_hands_only / n_cohort:.1f}%)")
    print(f"... contact / hands_on (broad signal):           {n_contact} ({100 * n_contact / n_cohort:.1f}%)")


# --- 2) Platform concentration ----------------------------------------------


def analyze_platforms(cases: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 78)
    print("2) PLATFORM CONCENTRATION (cases listing each platform)")
    print("=" * 78)
    # Count cases that mention each platform string (normalized display form)
    per_platform: Counter[str] = Counter()
    for c in cases:
        seen: Set[str] = set()
        for p in platforms_list(c.get("platforms_used")):
            key = p.strip()
            if key and key not in seen:
                seen.add(key)
                per_platform[key] += 1
    top3 = [p for p, _ in per_platform.most_common(3)]
    top3_set = {x.lower() for x in top3}
    print("Top 3 platforms by #cases listing them:", top3)
    n = len(cases)
    with_top3 = 0
    only_top3_subset = 0
    nonempty = 0
    for c in cases:
        plats = [x.lower() for x in platforms_list(c.get("platforms_used"))]
        if not plats:
            continue
        nonempty += 1
        if any(p in top3_set for p in plats):
            with_top3 += 1
        if plats and all(p in top3_set for p in plats):
            only_top3_subset += 1
    print(f"Cases with >=1 platform listed:              {nonempty} / {n} ({100 * nonempty / n:.1f}%)")
    print(
        f"Cases listing >=1 of top-3 platforms:        {with_top3} / {n} "
        f"({100 * with_top3 / n:.1f}% of all cases)"
    )
    print(
        f"Cases where ALL listed platforms are subset of top3: {only_top3_subset} / {n} "
        f"({100 * only_top3_subset / n:.1f}% of all cases)"
    )
    print(
        "Note: 'online' / 'social media' dominate - interpret as modality,\n"
        "  not a single commercial platform."
    )


def distinct_platform_count(blob: Any) -> int:
    """Count distinct platforms_used strings (case-folded, min length 2)."""
    pl = platforms_list(blob)
    return len({x.casefold() for x in pl if len(x) >= 2})


def analyze_hands_on_platforms(cases: List[Dict[str, Any]]) -> None:
    """
    Hands-on (case_topics 'hands_on') vs platform breadth in the same extracted row.
    Positive association: contact-tagged cases list more distinct platforms on average.
    """
    print("\n" + "=" * 78)
    print("2b) HANDS-ON TOPIC vs PLATFORMS_USED (co-tag association)")
    print("=" * 78)
    print(
        "Per case: topic_set(case_topics) for 'hands_on'; distinct count from platforms_used.\n"
        "Cohort: case_topics contains BOTH 'possession' AND 'csam' (same strict bucket as section 1).\n"
        "Interpretation: association in press-derived tags, not causal."
    )
    hands_pl: List[int] = []
    other_pl: List[int] = []
    coh_h: List[int] = []
    coh_n: List[int] = []
    bins: Dict[str, Dict[str, int]] = {
        "0": {"h": 0, "t": 0},
        "1": {"h": 0, "t": 0},
        "2+": {"h": 0, "t": 0},
    }
    for c in cases:
        T = topic_set(c.get("case_topics"))
        ho = "hands_on" in T
        n = distinct_platform_count(c.get("platforms_used"))
        if ho:
            hands_pl.append(n)
        else:
            other_pl.append(n)
        if cohort_csam_possession(T):
            (coh_h if ho else coh_n).append(n)
        key = "0" if n == 0 else ("1" if n == 1 else "2+")
        bins[key]["t"] += 1
        if ho:
            bins[key]["h"] += 1

    def mean(xs: List[int]) -> float:
        return statistics.mean(xs) if xs else 0.0

    nh, no = len(hands_pl), len(other_pl)
    mh, mo = mean(hands_pl), mean(other_pl)
    ratio = (mh / mo) if mo > 0 else 0.0
    print(f"hands_on cases:              n={nh:4d}  mean distinct platforms={mh:.2f}")
    print(f"all other cases:             n={no:4d}  mean distinct platforms={mo:.2f}")
    print(f"ratio (hands_on / other):     {ratio:.2f}x")
    for key, lab in [("0", "0 platforms"), ("1", "1 platform"), ("2+", "2+ platforms")]:
        b = bins[key]
        pct = 100.0 * b["h"] / b["t"] if b["t"] else 0.0
        print(f"P(hands_on | {lab:14s})  {pct:5.1f}%  ({b['h']}/{b['t']})")
    if coh_h or coh_n:
        print(
            f"\nPossession+CSAM cohort only:  hands_on n={len(coh_h):4d}  mean plat={mean(coh_h):.2f}"
        )
        print(f"                              no hands_on n={len(coh_n):4d}  mean plat={mean(coh_n):.2f}")
    mid = ""
    if coh_h or coh_n:
        mid = (
            f"Tighten to possession+CSAM-only charging frames and the gap persists "
            f"({mean(coh_h):.2f} vs {mean(coh_n):.2f} platforms on average): "
            "multi-surface grooming language and contact allegations tend to co-occur in the same releases. "
            "Association in extracted tags only; not a causal claim. "
        )
    else:
        mid = "Read as co-tagged association in press-derived features, not causation. "
    print(
        "\n--- Suggested slide / finding copy (HTML fragment) ---\n"
        '<div class="finding-item"><strong>Hands-on allegations ride denser platform stacks.</strong> '
        f"In this corpus, <code>hands_on</code> rows average <strong>{mh:.2f}</strong> distinct "
        f"<code>platforms_used</code> tags versus <strong>{mo:.2f}</strong> elsewhere (~<strong>{ratio:.2f}x</strong>). "
        + mid
        + "</div>"
    )




# --- 3) Investigation origin vs prosecution proxy -----------------------------


def extract_inv(conn: sqlite3.Connection, case_id: str) -> Tuple[Optional[str], List[str]]:
    cur = conn.execute("SELECT extracted_features FROM cases WHERE id = ?", (case_id,))
    row = cur.fetchone()
    if not row:
        return None, []
    ex = j(row[0])
    if not isinstance(ex, dict):
        return None, []
    inv = ex.get("investigation_type")
    inv_s = str(inv).strip().lower() if inv is not None and str(inv).strip() else None
    tech = ex.get("investigation_technology")
    tech_list: List[str] = []
    if isinstance(tech, list):
        tech_list = [str(t).lower() for t in tech if t]
    return inv_s, tech_list


def prosecution_proxy(rows: List[Dict[str, Any]], ex_blob: Any) -> str:
    """
    'advanced' = charged or booked in table OR extracted booking_status;
    'arrest_only' = arrested / unknown early stage.
    """
    statuses = [r.get("status") for r in rows if r.get("status")]
    ex = j(ex_blob)
    bs = None
    if isinstance(ex, dict):
        po = ex.get("prosecution_outcome")
        if isinstance(po, dict):
            bs = po.get("booking_status")
    if bs:
        statuses.append(str(bs).lower())
    st = " ".join(str(s).lower() for s in statuses if s)
    if "charged" in st or "booked" in st:
        return "advanced"
    if "arrested" in st:
        return "arrest_only"
    return "other_or_unknown"


def analyze_investigation_outcome(cases: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 78)
    print("3) INVESTIGATION ORIGIN vs PROSECUTION PROXY")
    print("=" * 78)
    print(
        "CyberTip-origin: investigation_technology contains 'cybertip' substring\n"
        "  OR narrative mentions cybertipline / cybertip.\n"
        "Undercover-origin: investigation_type == 'undercover'.\n"
        "Prosecution proxy: status/booking includes 'charged' or 'booked' (not only 'arrested').\n"
        "Note: No conviction / sentence fields populated in this DB snapshot."
    )

    def bucket(case: Dict[str, Any]) -> str:
        inv, tech = extract_inv(conn, case["id"])
        nar = case_text_lower(case.get("raw_data"))
        cybertip = any("cybertip" in t for t in tech) or "cybertipline" in nar or "cybertip" in nar
        if cybertip and inv == "undercover":
            return "both_cybertip_and_undercover"
        if cybertip:
            return "cybertip"
        if inv == "undercover":
            return "undercover"
        return "other"

    buckets = ("cybertip", "undercover", "both_cybertip_and_undercover", "other")
    stats: Dict[str, Counter[str]] = {b: Counter() for b in buckets}
    counts = Counter()
    for c in cases:
        b = bucket(c)
        counts[b] += 1
        rows = prosecution_rows(conn, c["id"])
        proxy = prosecution_proxy(rows, c.get("extracted_features"))
        stats[b][proxy] += 1

    for b in buckets:
        tot = counts[b]
        if tot == 0:
            continue
        adv = stats[b]["advanced"]
        print(f"\n{b}: n={tot}")
        print(f"  ... prosecution proxy 'advanced' (charged/booked): {adv} ({100 * adv / tot:.1f}%)")
        print(f"  ... 'arrest_only' / other breakdown: {dict(stats[b])}")


# --- 4) Geographic gaps -------------------------------------------------------


def states_from_case(ex_blob: Any) -> Set[str]:
    ex = j(ex_blob)
    if not isinstance(ex, dict):
        return set()
    locs = ex.get("locations")
    if not isinstance(locs, list):
        return set()
    found: Set[str] = set()
    for item in locs:
        if not isinstance(item, str):
            continue
        s = item.strip().lower()
        if not s:
            continue
        if s in US_STATE_NAMES:
            found.add(s)
            continue
        if s in ABBREV_TO_STATE:
            found.add(ABBREV_TO_STATE[s])
            continue
        # substring match full state name inside longer location string
        for st in US_STATE_NAMES:
            if re.search(rf"\b{re.escape(st)}\b", s):
                found.add(st)
    return found


def analyze_geo_gaps(cases: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 78)
    print("4) GEOGRAPHIC COVERAGE (US states from extracted `locations`)")
    print("=" * 78)
    print(
        "A case can increment multiple states if NER listed several.\n"
        "States with **zero** rows in `locations` are counted as 0 cases.\n"
        "This measures **reporting / extraction footprint**, not crime rates."
    )
    state_case_counts: Counter[str] = Counter()
    for c in cases:
        for st in states_from_case(c.get("extracted_features")):
            state_case_counts[st] += 1
    n_states = len(US_STATE_NAMES)
    with_any = sum(1 for st in US_STATE_NAMES if state_case_counts[st] > 0)
    under10 = sum(1 for st in US_STATE_NAMES if 0 < state_case_counts[st] < 10)
    zero = sum(1 for st in US_STATE_NAMES if state_case_counts[st] == 0)
    total_cases = len(cases)
    print(f"US jurisdictions in model (incl. DC):     {n_states}")
    print(f"States with >=1 case hit in `locations`:   {with_any}")
    print(f"States with 0 cases:                        {zero} ({100 * zero / n_states:.1f}%)")
    print(f"States with 1-9 cases:                      {under10} ({100 * under10 / n_states:.1f}%)")
    low_list = sorted(
        (st, state_case_counts[st]) for st in US_STATE_NAMES if 0 < state_case_counts[st] < 10
    )
    if low_list:
        print(f"  (those states): {', '.join(f'{s} ({n})' for s, n in low_list)}")
    print(f"Total case rows:                            {total_cases}")
    # mention year span
    ys = []
    for c in cases:
        ds = c.get("date_start")
        if ds:
            try:
                ys.append(int(str(ds)[:4]))
            except Exception:
                pass
    if ys:
        print(f"date_start year span:                      {min(ys)}-{max(ys)}")


# --- 5) Complexity by era -----------------------------------------------------


def year_from_case(c: Dict[str, Any]) -> Optional[int]:
    ds = c.get("date_start")
    if not ds:
        return None
    try:
        return int(str(ds)[:4])
    except Exception:
        return None


def era_label(y: Optional[int]) -> str:
    if y is None:
        return "unknown_year"
    if y <= 2013:
        return "2008-2013"
    if y <= 2018:
        return "2014-2018"
    if y <= 2021:
        return "2019-2021"
    if y <= 2023:
        return "2022-2023"
    return "2024-2026"


def agency_count(ex_blob: Any) -> int:
    ex = j(ex_blob)
    if not isinstance(ex, dict):
        return 0
    ag = ex.get("agencies_involved")
    return len(ag) if isinstance(ag, list) else 0


def charge_count(conn: sqlite3.Connection, case_id: str) -> int:
    n = 0
    for r in prosecution_rows(conn, case_id):
        for item in parse_charges(r.get("charges")):
            if isinstance(item.get("count"), int):
                n += item["count"]
            else:
                n += 1
    return n


def analyze_complexity_eras(cases: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 78)
    print("5) CASE COMPLEXITY BY ERA (agency list length + charge counts)")
    print("=" * 78)
    by_era: Dict[str, List[int]] = defaultdict(list)
    by_era_ch: Dict[str, List[int]] = defaultdict(list)
    for c in cases:
        y = year_from_case(c)
        lab = era_label(y)
        by_era[lab].append(agency_count(c.get("extracted_features")))
        by_era_ch[lab].append(charge_count(conn, c["id"]))
    order = ["2008-2013", "2014-2018", "2019-2021", "2022-2023", "2024-2026", "unknown_year"]
    for lab in order:
        ac = by_era.get(lab)
        if not ac:
            continue
        cc = by_era_ch[lab]
        print(
            f"{lab:12s}  n={len(ac):4d}  "
            f"mean agencies={statistics.mean(ac):.2f}  "
            f"mean charge-count={statistics.mean(cc):.2f}  "
            f"(charge JSON often empty - interpret cautiously)"
        )


# --- 6) Victim age by era -----------------------------------------------------


def victim_min_age(conn: sqlite3.Connection, case_id: str) -> Optional[int]:
    """Minimum victim `min` age from victim_demographics.age_range JSON."""
    ages: List[int] = []
    cur = conn.execute(
        "SELECT age_range FROM victim_demographics WHERE case_id = ?",
        (case_id,),
    )
    for (blob,) in cur.fetchall():
        d = j(blob)
        if isinstance(d, dict):
            m = d.get("min")
            if isinstance(m, int):
                ages.append(m)
            elif isinstance(m, list) and m:
                try:
                    ages.append(min(int(x) for x in m))
                except Exception:
                    pass
    if not ages:
        return None
    return min(ages)


def analyze_victim_age_eras(cases: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 78)
    print("6) VICTIM AGE (minimum parsed age) BY ERA")
    print("=" * 78)
    print(
        "Uses victim_demographics.age_range JSON `min` (smallest across rows).\n"
        "Cases with no parseable age are skipped per-era mean.\n"
        "Era buckets follow section 5."
    )
    by_era: Dict[str, List[int]] = defaultdict(list)
    for c in cases:
        y = year_from_case(c)
        lab = era_label(y)
        m = victim_min_age(conn, c["id"])
        if m is not None:
            by_era[lab].append(m)
    order = ["2008-2013", "2014-2018", "2019-2021", "2022-2023", "2024-2026"]
    for lab in order:
        xs = by_era.get(lab)
        if not xs:
            print(f"{lab:12s}  (no ages)")
            continue
        print(
            f"{lab:12s}  n={len(xs):4d}  "
            f"mean min-age={statistics.mean(xs):.2f}  "
            f"median={statistics.median(xs):.1f}  "
            f"p(under 12)={100 * sum(1 for a in xs if a < 12) / len(xs):.1f}%"
        )


def _intify_age_val(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def perpetrator_ages_flat(conn: sqlite3.Connection, case_id: str, ex_blob: Any) -> List[int]:
    """All parsed perpetrator ages for a case (extracted_features + demographics rows)."""
    ages: List[int] = []
    ex = j(ex_blob)
    if isinstance(ex, dict):
        pa = ex.get("perpetrator_age")
        if isinstance(pa, list):
            for x in pa:
                n = _intify_age_val(x)
                if n is not None and 10 <= n <= 100:
                    ages.append(n)
        elif isinstance(pa, int) and 10 <= pa <= 100:
            ages.append(pa)

    cur = conn.execute(
        "SELECT age_range FROM perpetrator_demographics WHERE case_id = ?",
        (case_id,),
    )
    for (blob,) in cur.fetchall():
        d = j(blob)
        if not isinstance(d, dict):
            continue
        for key in ("min", "max"):
            v = d.get(key)
            if isinstance(v, int) and 10 <= v <= 100:
                ages.append(v)
            elif isinstance(v, list):
                for x in v:
                    n = _intify_age_val(x)
                    if n is not None and 10 <= n <= 100:
                        ages.append(n)
    return ages


def analyze_perpetrator_age_eras(cases: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 78)
    print("7) PERPETRATOR (OFFENDER) AGE BY ERA")
    print("=" * 78)
    print(
        "Per-case: collect ages from extracted_features.perpetrator_age and\n"
        "perpetrator_demographics.age_range (min/max lists). Drop garbage outside 10-100.\n"
        "Then per case: youngest offender = min(ages); mean offender age = mean(ages).\n"
        "Cases with no parseable perpetrator age are omitted from that row's n."
    )
    by_min: Dict[str, List[int]] = defaultdict(list)
    by_mean: Dict[str, List[float]] = defaultdict(list)
    for c in cases:
        y = year_from_case(c)
        lab = era_label(y)
        if lab == "unknown_year":
            continue
        ages = perpetrator_ages_flat(conn, c["id"], c.get("extracted_features"))
        if not ages:
            continue
        by_min[lab].append(min(ages))
        by_mean[lab].append(statistics.mean(ages))
    order = ["2008-2013", "2014-2018", "2019-2021", "2022-2023", "2024-2026"]
    for lab in order:
        mins = by_min.get(lab)
        means = by_mean.get(lab)
        if not mins or not means:
            print(f"{lab:12s}  (no perpetrator ages)")
            continue
        print(
            f"{lab:12s}  n={len(mins):4d}  "
            f"youngest-offender mean={statistics.mean(mins):.2f}  median={statistics.median(mins):.1f}  "
            f"p(<25)={100 * sum(1 for a in mins if a < 25) / len(mins):.1f}%"
        )
        print(
            f"{'':12s}      "
            f"within-case mean-age mean={statistics.mean(means):.2f}  median={statistics.median(means):.1f}"
        )


def print_what_db_supports() -> None:
    print("\n" + "=" * 78)
    print("WHAT THIS DATABASE SUPPORTS TODAY")
    print("=" * 78)
    print(
        """
* Topics / severity / platforms / relationship / investigation_type (sparse) /
  agencies_involved, NER locations, ML comparison_values, press narrative text.
* prosecution_outcomes.status + charges JSON (charges often []).
* prosecution_outcomes.sentences is effectively unused in this snapshot.
* investigation_technology lists (CyberTipline appears there when extracted).
* victim_demographics.age_range JSON for aggregate ages.
* perpetrator_age in extracted_features and perpetrator_demographics.age_range.

Unsupported or weak without external data:
* Actual convictions, sentence months, acquittals.
* Primary charging jurisdiction as a single ground-truth state.
* Complete CyberTip vs undercover mutual exclusivity (many stories mention both).
"""
    )


def main() -> int:
    path = db_path()
    if not path.is_file():
        print(f"Database not found: {path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(path))
    cases = load_cases(conn)
    print(f"Database: {path}")
    print(f"Cases:    {len(cases)}")

    analyze_possession_contact(cases, conn)
    analyze_platforms(cases)
    analyze_hands_on_platforms(cases)
    analyze_investigation_outcome(cases, conn)
    analyze_geo_gaps(cases)
    analyze_complexity_eras(cases, conn)
    analyze_victim_age_eras(cases, conn)
    analyze_perpetrator_age_eras(cases, conn)
    print_what_db_supports()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
