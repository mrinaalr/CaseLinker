"""Build every AfH 2.0 Q1 output from the pinned snapshot. No timestamps: same inputs, same bytes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import citations as cit
from . import identity as idn
from . import pipeline as pl
from . import review as rv
from . import temporal as tmp
from .snapshot import REPO, RESEARCH, connect, iter_cases, snapshot_meta

OUT = RESEARCH / "outputs"
ERAS = (("2002-2014", 2002, 2014), ("2015-2019", 2015, 2019), ("2020-2022", 2020, 2022), ("2023-2026", 2023, 2026))
USED = ("stated", "inferred")
MIN_MANIFEST_CASES = 3
EXEMPLARS_PER_CELL = 3
# AfH 1.0 Sec. 7 conceptual mapping psi(a) (affordance class -> harms). Conceptual, not observed.
AFH1_PSI = {
    "Anonymity": ["h1_groomed_toward_in_person", "h2_coerced_self_generated", "h4_sextorted"],
    "Ephemerality": ["h2_coerced_self_generated", "h4_sextorted"],
    "ContactDiscovery": ["h1_groomed_toward_in_person"],
    "UnmonitoredCommunication": ["h1_groomed_toward_in_person", "h2_coerced_self_generated", "h4_sextorted"],
    "DistributionInfrastructure": ["h3_material_distributed"],
    "GenerativeSynthesis": ["h6_likeness_synthesized"],
}
ANALYSED_STATUSES = ("specific", "technology", "ambiguous_alias")  # platforms the six classes are assessed on


def era_of(year: Optional[int]) -> str:
    for name, lo, hi in ERAS:
        if year is not None and lo <= year <= hi:
            return name
    return "outside_2002_2026"


def wilson(k: int, n: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - r) / d, 3), round((c + r) / d, 3))


def dump(name: str, obj: Any) -> Path:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> Dict[str, Any]:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "research/afh_q1/afhq1",
                            "research/afh_q1/config", "ontology/platform_affordance_evidence/platform_affordance_evidence.py",
                            "ontology/platform_affordance_evidence/build_candidates.py",
                            "src/Processing Layer/Pattern Processing Layer/temporal_tags.py"],
                           capture_output=True, text=True).stdout.strip()
    return {"commit": head, "code_dirty": bool(dirty)}


# ------------------------------------------------------------------ sections

def inventory(cases: List[dict], records: List[pl.Record], excluded: List[dict], dates: Dict[str, dict]) -> dict:
    sources = Counter(c["source"] for c in cases)
    years = [c["pub_year"] for c in cases if c["pub_year"] is not None]
    by_case_status: Dict[str, set] = defaultdict(set)
    for r in records:
        by_case_status[r.case_id].add(r.status)
    raw_label_cases = {c["id"] for c in cases if c["platforms"]}
    any_eligible = set(by_case_status)
    strict = {cid for cid, s in by_case_status.items() if "specific" in s}
    generic_only = {cid for cid, s in by_case_status.items() if s <= {"generic"}}
    tech_only = {cid for cid, s in by_case_status.items() if "specific" not in s and "technology" in s}
    ambiguous_only = {cid for cid, s in by_case_status.items() if s <= {"ambiguous_alias", "generic"} and "ambiguous_alias" in s}
    broad = pl.tier_counts(records, lambda r: r.status != "excluded")
    strict_t = pl.tier_counts(records, lambda r: r.status == "specific")
    analysed = pl.tier_counts(records, lambda r: r.status in ANALYSED_STATUSES)
    checks = {}
    for name, t in (("broad", broad), ("strict", strict_t), ("analysed", analysed)):
        checks[name] = {
            "case_tiers_sum_to_cases": sum(t[f"cases_{x}"] for x in pl.TIERS) == t["cases"],
            "record_tiers_sum_to_records": sum(t[f"records_{x}"] for x in pl.TIERS) == t["records"],
        }
    excl_pairs = Counter(e["reason"] for e in excluded)
    excl_cases = {reason: len({e["case_id"] for e in excluded if e["reason"] == reason}) for reason in excl_pairs}
    lost_all = {e["case_id"] for e in excluded if e["reason"] in ("psa_only", "gen_ai_scrape_noise", "gen_ai_embed_only")} - any_eligible
    no_platform = len(cases) - len(raw_label_cases)
    only_excluded_labels = len(raw_label_cases - any_eligible - lost_all)
    return {
        "denominators": {
            "corpus_cases": len(cases), "sources": len(sources),
            "publication_year_range": [min(years), max(years)], "cases_missing_publication_year": len(cases) - len(years),
            "cases_outside_2002_2026": sum(1 for y in years if not 2002 <= y <= 2026),
            "cases_with_any_platform_label": len(raw_label_cases),
            "cases_with_no_platform_label": no_platform,
            "cases_with_only_online_or_internet": only_excluded_labels,
            "cases_lost_to_psa_or_gen_ai_filters": len(lost_all),
            "broad_eligible_cases": len(any_eligible),
            "strict_eligible_cases": len(strict),
            "generic_category_only_cases": len(generic_only),
            "technology_only_cases_no_specific_platform": len(tech_only),
            "ambiguous_alias_only_cases": len(ambiguous_only),
        },
        "reconciliation": {
            "corpus = no_label + only_online_internet + lost_to_filters + broad_eligible":
                no_platform + only_excluded_labels + len(lost_all) + len(any_eligible) == len(cases),
            "broad = strict + generic_only + technology_only_or_alias_only":
                len(strict) + len(generic_only) + len(tech_only | ambiguous_only) == len(any_eligible),
            **{f"{k}.{c}": v for k, d in checks.items() for c, v in d.items()},
        },
        "tiers": {"broad": broad, "strict": strict_t, "analysed_for_affordances": analysed},
        "tier_definition": "case tier = best record tier (stated > inferred > named_only); tiers are mutually exclusive per case",
        "exclusions": {"platform_case_pairs": dict(sorted(excl_pairs.items())), "distinct_cases": dict(sorted(excl_cases.items()))},
        "labels": {s: sorted({r.platform for r in records if r.status == s}) for s in ("specific", "technology", "ambiguous_alias", "generic")},
        "dates": date_summary(cases, dates),
    }


def date_summary(cases: List[dict], dates: Dict[str, dict]) -> dict:
    with_role: Counter = Counter()
    for c in cases:
        for role in dates[c["id"]]["roles"]:
            with_role[role] += 1
    return {
        "temporal_tags_version": next(iter(dates.values()))["version"],
        "primary_timeline": "publication year (raw_data.year); an upper bound on conduct time, not an offense date",
        "cases_with_role": dict(sorted(with_role.items())),
        "cases_with_dated_offense": with_role.get("event:offense", 0),
        "cases_with_program_boilerplate_date": with_role.get("program_boilerplate", 0),
    }


def june_reconciliation() -> dict:
    ev = idn.git_json(idn.JUNE_COMMIT, idn.JUNE_EVIDENCE)
    cand = idn.git_json(idn.JUNE_COMMIT, idn.JUNE_CANDIDATES)
    best: Dict[str, set] = defaultdict(set)
    for r in ev["records"]:
        best[r["case_id"]].add(r["stated_vs_inferred"])
    reg = pl.platform_registry()
    pool = {cid for e in cand["flat"] for cid in e["case_ids"]}
    specific_pool = {cid for e in cand["flat"] if pl.platform_info(e["platform"], reg).status == "specific" for cid in e["case_ids"]}
    nongeneric_pool = {cid for e in cand["flat"] if pl.platform_info(e["platform"], reg).status != "generic" for cid in e["case_ids"]}
    n = len(best)
    stated = sum("stated" in t for t in best.values())
    inf = sum("inferred" in t and "stated" not in t for t in best.values())
    named = sum(t == {"named_only"} for t in best.values())
    return {
        "source": f"git {idn.JUNE_COMMIT}: {idn.JUNE_CANDIDATES}, {idn.JUNE_EVIDENCE} (generated {ev['_meta']['generated']})",
        "candidate_cases": cand["summary"]["total_candidate_cases"],
        "platform_case_pairs": cand["summary"]["total_platform_case_pairs"],
        "labels": cand["summary"]["platforms_with_named_label"],
        "cases_with_records": n,
        "cases_lost_to_psa": cand["summary"]["total_candidate_cases"] - n,
        "stated": stated, "inferred_only": inf, "named_only": named,
        "percent_denominator_used_in_paper": n,
        "percents": {"stated": round(100 * stated / n, 1), "inferred_only": round(100 * inf / n, 1), "named_only": round(100 * named / n, 1)},
        "candidate_cases_non_generic": len(nongeneric_pool),
        "candidate_cases_specific_only": len(specific_pool),
        "note": ("The June paper text says 856 / 134 / 881 with percentages over 1,871 cases with records, "
                 "while calling the evidence base 1,875 cases. 858 / 136 appear in no committed output or paper "
                 "text in this repository; they cannot be reproduced. The 1,875 includes cases whose only labels "
                 "are 'social media', 'chat' or 'Webcam platform'."),
    }


def affordance_coverage(records: List[pl.Record]) -> dict:
    out = {}
    pool = [r for r in records if r.status in ANALYSED_STATUSES]
    for c in pl.CLASSES:
        row = {}
        for level, attr in (("A_available", "available"), ("B_action_relevant", "action_relevant"), ("C_instrumental", "instrumental")):
            rs = [r for r in pool if getattr(r, attr)[c]]
            tiers = pl.case_tiers(rs)
            row[level] = {
                "distinct_cases": len({r.case_id for r in rs}),
                "platform_case_observations": len(rs),
                "distinct_platform_labels": len({r.platform for r in rs}),
                "platform_families": len({r.family for r in rs}),
                "case_tier_breakdown": dict(sorted(Counter(tiers.values()).items())),
                "top_platforms": Counter(r.platform for r in rs).most_common(5),
                "period_uncertain_observations": sum(r.period_uncertain[c] for r in rs),
            }
        cap_only = {r.case_id for r in pool if r.available[c]} - {r.case_id for r in pool if r.instrumental[c]}
        row["capability_only_cases"] = len(cap_only)
        row["review_candidates"] = dict(sorted(Counter(r.review[c] for r in pool if r.review.get(c)).items()))
        out[c] = row
    return {"classes": out, "platform_statuses_assessed": list(ANALYSED_STATUSES),
            "levels": "A available (platform had it natively in publication year) > B action-relevant (documented conduct of the matching kind on that platform, stated/inferred) > C instrumental (platform sentence states the capability-specific behaviour)"}


def temporal_tables(cases: List[dict], records: List[pl.Record]) -> dict:
    by_case: Dict[str, List[pl.Record]] = defaultdict(list)
    for r in records:
        by_case[r.case_id].append(r)
    def summarize(group: Iterable[dict]) -> dict:
        group = list(group)
        n = len(group)
        src = Counter(c["source"] for c in group)
        strict = [c for c in group if any(r.status == "specific" for r in by_case.get(c["id"], []))]
        used = [c for c in strict if any(r.status == "specific" and r.tier in USED for r in by_case[c["id"]])]
        row = {
            "cases": n, "sources": len(src), "ncmec_cases": src.get("NCMEC", 0),
            "top_source_share": round(src.most_common(1)[0][1] / n, 3) if n else None,
            "strict_named_platform_cases": len(strict),
            "strict_use_documented_cases": len(used),
            "pct_strict_named": round(100 * len(strict) / n, 1) if n else None,
            "pct_use_documented_of_named": round(100 * len(used) / len(strict), 1) if strict else None,
            "distinct_platforms_use_documented": len({r.platform for c in used for r in by_case[c["id"]] if r.status == "specific" and r.tier in USED}),
        }
        for cl in pl.CLASSES:
            rs = [r for c in group for r in by_case.get(c["id"], []) if r.status in ANALYSED_STATUSES]
            for lvl, attr in (("A", "available"), ("B", "action_relevant"), ("C", "instrumental")):
                row[f"{cl}.{lvl}"] = len({r.case_id for r in rs if getattr(r, attr)[cl]})
        return row
    annual = {str(y): summarize(c for c in cases if c["pub_year"] == y) for y in sorted({c["pub_year"] for c in cases if c["pub_year"]})}
    eras = {name: summarize(c for c in cases if era_of(c["pub_year"]) == name) for name, _, _ in ERAS}
    within = {}
    for src in ("DOJ SAFE CHILDHOOD", "NCMEC", "DOJ CEOS", "NJ AG"):
        within[src] = {str(y): summarize(c for c in cases if c["source"] == src and c["pub_year"] == y)
                       for y in sorted({c["pub_year"] for c in cases if c["source"] == src and c["pub_year"]})}
    no_ncmec = {name: summarize(c for c in cases if era_of(c["pub_year"]) == name and c["source"] != "NCMEC") for name, _, _ in ERAS}
    return {"timeline": "publication year", "annual": annual, "eras": eras,
            "eras_excluding_ncmec": no_ncmec, "within_source_annual": within,
            "caution": "Counts are enforcement-report coverage, not offense prevalence. Source mix changes by year."}


def recurrence(records: List[pl.Record]) -> dict:
    out = {}
    for c in pl.CLASSES:
        row = {}
        for lvl, attr in (("A_available", "available"), ("C_instrumental", "instrumental")):
            rs = [r for r in records if r.status in ANALYSED_STATUSES and getattr(r, attr)[c]]
            cases = {r.case_id for r in rs}
            fam = Counter(r.family for r in rs)
            plats = Counter(r.platform for r in rs)
            srcs = Counter()
            for cid in cases:
                srcs[next(r.source for r in rs if r.case_id == cid)] += 1
            era_cases = Counter(era_of(next(r.pub_year for r in rs if r.case_id == cid)) for cid in cases)
            top_p = plats.most_common(1)
            top_s = srcs.most_common(1)
            row[lvl] = {
                "cases": len(cases), "platforms": len(plats), "families": sorted(fam),
                "eras_with_cases": dict(sorted(era_cases.items())),
                "top_platform": top_p[0][0] if top_p else None,
                "top_platform_share_of_observations": round(top_p[0][1] / len(rs), 3) if rs else None,
                "top_source": top_s[0][0] if top_s else None,
                "top_source_share_of_cases": round(top_s[0][1] / len(cases), 3) if cases else None,
                "families_with_2plus_cases": sum(1 for f in fam if len({r.case_id for r in rs if r.family == f}) >= 2),
                "eras_with_2plus_cases": sum(1 for v in era_cases.values() if v >= 2),
            }
        ci = row["C_instrumental"]
        if ci["cases"] >= 20 and ci["families_with_2plus_cases"] >= 3 and ci["eras_with_2plus_cases"] >= 2:
            verdict = "documented misuse recurs across platform families and periods"
        elif ci["cases"] >= 5 and ci["families_with_2plus_cases"] >= 2:
            verdict = "documented misuse recurs across families; too sparse to compare periods"
        elif ci["cases"] > 0:
            verdict = "documented misuse is sparse or concentrated in one platform"
        else:
            verdict = "no documented misuse; capability recurrence only"
        row["verdict"] = verdict
        out[c] = row
    return out


def harm_tables(records: List[pl.Record], codebook: pl.Codebook) -> dict:
    harms = sorted(codebook.harms)
    empirical = {}
    for c in pl.CLASSES:
        rs = [r for r in records if r.status in ANALYSED_STATUSES and r.instrumental[c]]
        empirical[c] = {h: {"direct_cases": len({r.case_id for r in rs if r.harm_direct[h]}),
                            "case_level_cases": len({r.case_id for r in rs if r.harm_case[h]}),
                            "of_cases": len({r.case_id for r in rs})} for h in harms}
    conceptual = {}
    for c, hs in AFH1_PSI.items():
        conceptual[c] = {h: {"afh1_claims": True,
                             "observed_direct_cases_given_C": empirical[c][h]["direct_cases"],
                             "support": ("direct" if empirical[c][h]["direct_cases"] >= 5 else
                                         "thin" if empirical[c][h]["direct_cases"] > 0 else
                                         "case_level_only" if empirical[c][h]["case_level_cases"] > 0 else "none")}
                         for h in hs}
    by_platform = {}
    used = [r for r in records if r.status in ANALYSED_STATUSES and r.tier in USED]
    for p in sorted({r.platform for r in used}):
        rs = [r for r in used if r.platform == p]
        by_platform[p] = {h: len({r.case_id for r in rs if r.harm_direct[h]}) for h in harms}
        by_platform[p]["use_documented_cases"] = len({r.case_id for r in rs})
    return {"empirical_given_instrumental_class": empirical, "afh1_conceptual_psi_checked": conceptual,
            "platform_by_harm_direct": by_platform,
            "support_levels": "direct = harm cue in a platform sentence of a stated/inferred record; case_level = case_topics or cue anywhere in release",
            "caution": "Co-occurrence in enforcement releases. Not causal, not prevalence."}


def pick(rs: List[pl.Record], key: str, n: int = EXEMPLARS_PER_CELL) -> List[pl.Record]:
    return sorted(rs, key=lambda r: hashlib.sha256(f"{key}|{r.case_id}|{r.platform}".encode()).hexdigest())[:n]


def manifest(records: List[pl.Record], codebook: pl.Codebook) -> Tuple[dict, List[cit.Citation]]:
    cfg = pl.load_yaml("platforms.yaml")["platforms"]
    entries, cites = {}, []
    for p in sorted({r.platform for r in records if r.status in ANALYSED_STATUSES}):
        rs = [r for r in records if r.platform == p]
        used = [r for r in rs if r.tier in USED]
        if len({r.case_id for r in used}) < MIN_MANIFEST_CASES:
            continue
        tiers = pl.case_tiers(rs)
        conduct = Counter(c for r in used for c in r.conduct)
        row = {
            "status": rs[0].status, "family": rs[0].family,
            "capability_profile": cfg[p].get("capabilities", {}), "until": cfg[p].get("until"),
            "profile_note": cfg[p].get("note", ""), "profile_basis": "needs_author_check",
            "cases": len(tiers), "cases_by_tier": dict(sorted(Counter(tiers.values()).items())),
            "use_documented_cases": len({r.case_id for r in used}),
            "pub_year_range_use_documented": [min(r.pub_year for r in used), max(r.pub_year for r in used)],
            "conduct_mix_records": dict(conduct.most_common()),
            "classes": {}, "harms_direct_cases": {}, "exemplars": [],
        }
        for c in pl.CLASSES:
            row["classes"][c] = {lvl: len({r.case_id for r in rs if getattr(r, attr)[c]})
                                 for lvl, attr in (("A", "available"), ("B", "action_relevant"), ("C", "instrumental"))}
            for r in pick([r for r in rs if r.instrumental[c]], f"{p}|{c}"):
                purpose = f"manifest:{p}:instrumental:{c}"
                cites.append(cit.Citation(r.case_id, r.fingerprint, purpose, p))
                row["exemplars"].append({"purpose": purpose, "case_id": r.case_id, "fingerprint": r.fingerprint,
                                         "span": list(r.instrumental_span.get(c, (-1, -1)))})
        for h in sorted(codebook.harms):
            hs = [r for r in used if r.harm_direct[h]]
            row["harms_direct_cases"][h] = len({r.case_id for r in hs})
            for r in pick(hs, f"{p}|{h}", 2):
                purpose = f"manifest:{p}:harm:{h}"
                cites.append(cit.Citation(r.case_id, r.fingerprint, purpose, p))
                row["exemplars"].append({"purpose": purpose, "case_id": r.case_id, "fingerprint": r.fingerprint,
                                         "span": list(r.sentence_spans[0]) if r.sentence_spans else [-1, -1]})
        entries[p] = row
    return {"min_use_documented_cases": MIN_MANIFEST_CASES, "platforms": entries}, cites


def legacy_manifest_check(records: List[pl.Record], texts: Dict[str, str]) -> dict:
    """AfH 1.0 harm-vector exemplars, resolved by content rather than by id."""
    import re as _re
    h = json.loads((pl.EVIDENCE_DIR / "platform_affordance_evidence_harm_analysis.json").read_text(encoding="utf-8"))
    ev = idn.git_json(idn.JUNE_COMMIT, idn.JUNE_EVIDENCE)
    cited = []
    for p, v in sorted(h.items()):
        if p == "_note":
            continue
        for i, hv in enumerate(v.get("harm_vector") or []):
            for cid in _re.findall(r"[a-z_]+_\d{4}_\d+", hv):
                cited.append((p, i, cid, v.get("analysis_author")))
    old_ids = sorted({c for _, _, c, _ in cited})
    xw = {m.old_id: m for m in idn.build_crosswalk(ev["records"], old_ids, texts)}
    tier = {(r.case_id, r.platform): r.tier for r in records}
    rows, tally = [], Counter()
    for p, i, cid, author in cited:
        cur, how = idn.resolve(cid, xw)
        t = tier.get((cur, p)) if cur else None
        if cur is None:
            verdict = f"unresolved_{how}"
        elif t in USED:
            verdict = "verified_use_documented"
        elif t == "named_only":
            verdict = "platform_named_only"
        else:
            verdict = "platform_not_tagged_in_current_case"
        tally[verdict] += 1
        rows.append({"platform": p, "harm_vector_index": i, "author": author, "cited_id": cid, "crosswalk": how,
                     "current_id": cur, "reassigned": bool(cur and cur != cid), "current_tier": t, "verdict": verdict})
    return {"citations": len(rows), "tally": dict(sorted(tally.items())), "rows": rows,
            "note": "AfH 1.0 exemplars cited by bare case id. Resolved through the June evidence quotes, never by id."}


def validation(records: List[pl.Record], fingerprints: Dict[str, str]) -> dict:
    reviews = rv.load_reviews()
    by_item: Dict[str, Counter] = defaultdict(Counter)
    stale = 0
    current = {(r.case_id, r.platform): r for r in records}
    still_c: Counter = Counter()
    for (item, cid, plat), row in reviews.items():
        by_item[item][row["verdict"]] += 1
        if fingerprints.get(cid) != row["fingerprint"]:
            stale += 1
        if item.startswith("C:"):
            r = current.get((cid, plat))
            still_c[(item, row["verdict"], bool(r and r.instrumental[item[2:]]))] += 1
    summary = {}
    good = {"correct", "alias_correct"}
    for item, cnt in sorted(by_item.items()):
        n = sum(cnt.values())
        if item.startswith("C:") or item == "tier:stated" or item.startswith("alias:"):
            k = sum(v for verdict, v in cnt.items() if verdict in good)
            summary[item] = {"n": n, "verdicts": dict(cnt), "precision": round(k / n, 3), "wilson95": wilson(k, n)}
        elif item in ("tier:inferred", "tier:named_only"):
            k = cnt.get("use_documented", 0)
            summary[item] = {"n": n, "verdicts": dict(cnt), "share_actually_documenting_use": round(k / n, 3), "wilson95": wilson(k, n)}
        else:
            summary[item] = {"n": n, "verdicts": dict(cnt)}
    c_after = {}
    for (item, verdict, kept), v in sorted(still_c.items()):
        c_after.setdefault(item, Counter())[f"{verdict}->{'still_C' if kept else 'dropped'}"] += v
    return {"reviewed_rows": len(reviews), "rows_with_changed_fingerprint": stale, "by_item": summary,
            "C_rows_under_current_codebook": {k: dict(v) for k, v in c_after.items()},
            "reviewer": "one reviewer (agent); author adjudication pending",
            "sample": "deterministic: sha256(case_id|platform|item) order, see review.SAMPLE_PLAN"}


# --------------------------------------------------------------------- main

def write_records_csv(records: List[pl.Record]) -> Path:
    path = OUT / "records.csv"
    rows = [r.row() for r in sorted(records, key=lambda r: (r.case_id, r.platform))]
    fields = sorted({k for row in rows for k in row}, key=lambda k: (k not in ("case_id", "platform"), k))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return path


def build(log=print) -> dict:
    con = connect()
    meta = snapshot_meta(con)
    fingerprints = dict(con.execute("SELECT case_id, fingerprint FROM fingerprints"))
    cases = list(iter_cases(con))
    texts = {c["id"]: c["text"] for c in cases}
    reg = pl.platform_registry()
    cb = pl.Codebook.load()
    records, excluded = [], []
    for c in cases:
        r, e = pl.classify_case(c, fingerprints.get(c["id"], ""), reg, cb)
        records += r
        excluded += e
    unregistered = sorted({r.platform for r in records if r.status == "unregistered"})
    if unregistered:
        raise SystemExit(f"platform labels missing from config/platforms.yaml: {unregistered}")
    log(f"records={len(records)}")
    dates = {c["id"]: tmp.case_dates(c["text"], c["pub_year"]) for c in cases}
    OUT.mkdir(parents=True, exist_ok=True)
    dump("inventory.json", inventory(cases, records, excluded, dates))
    dump("june_2026_reconciliation.json", june_reconciliation())
    dump("affordance_coverage.json", affordance_coverage(records))
    dump("temporal.json", temporal_tables(cases, records))
    dump("recurrence.json", recurrence(records))
    dump("harm.json", harm_tables(records, cb))
    man, cites = manifest(records, cb)
    verdicts = cit.verify(cites, fingerprints)
    man["citation_check"] = dict(Counter(v.status for v in verdicts))
    dump("manifest.json", man)
    cit.dump(cites, OUT / "citations.json")
    dump("legacy_afh1_exemplars.json", legacy_manifest_check(records, texts))
    dump("validation.json", validation(records, fingerprints))
    dump("validation_sample.json", rv.sample_rows(records))
    write_records_csv(records)
    from . import report
    report.write(OUT)
    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "RUN_IDENTITY.json")
    code = sorted((RESEARCH / "afhq1").glob("*.py"))
    identity = {
        "dataset_identity": meta["dataset_identity"], "case_count": int(meta["case_count"]),
        "git": git_head(),
        "configs": {n: {"version": pl.load_yaml(n)["version"], "sha256": pl.config_sha(n)}
                    for n in ("platforms.yaml", "codebook.yaml")},
        "code_sha256": {str(p.relative_to(REPO)): sha_file(p) for p in code + [
            pl.EVIDENCE_DIR / "platform_affordance_evidence.py", pl.EVIDENCE_DIR / "build_candidates.py",
            REPO / "src" / "Processing Layer" / "Pattern Processing Layer" / "temporal_tags.py"]},
        "outputs_sha256": {str(p.relative_to(OUT)): sha_file(p) for p in files},
    }
    dump("RUN_IDENTITY.json", identity)
    return identity
