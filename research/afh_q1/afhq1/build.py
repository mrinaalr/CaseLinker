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
# Evidence levels, each a subset of the one before (A > B > I > C).
LEVELS = (
    ("A_available_capability", "available"),
    ("B_capability_relevant_conduct", "action_relevant"),
    ("I_inferred_facilitation", "inferred"),
    ("C_explicit_instrumental_use", "instrumental"),
)
LEVEL_TEXT = {
    "A_available_capability": "the platform offered the capability natively in the case's publication year",
    "B_capability_relevant_conduct": "documented use of the platform for conduct of the kind the capability bears on",
    "I_inferred_facilitation": "B on a platform where the capability is on for every use by design (registry default_on), or C",
    "C_explicit_instrumental_use": "the release states the capability-specific behaviour in a sentence naming the platform",
}


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
    lw = [pl.Record(r.case_id, r.fingerprint, r.source, r.pub_year, r.platform, r.status, r.family,
                    r.tier_linewrap or r.tier, r.text_found) for r in records]
    strict_lw = pl.tier_counts(lw, lambda r: r.status == "specific")
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
        "tiers_linewrap_alternative": {"strict": strict_lw, "rules": "tiers-1+linewrap-1 (additive line-wrap repair); "
                                       "not the published denominator until the authors adopt it"},
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
        for level, attr in LEVELS:
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
        if c == "GenerativeSynthesis":
            row["ai_material_documented_cases"] = len({r.case_id for r in pool if r.ai_material})
            row["ai_material_without_creation_cases"] = len({r.case_id for r in pool if r.ai_material and not r.instrumental[c]})
        row["A_only_cases"] = len({r.case_id for r in pool if r.available[c]} - {r.case_id for r in pool if r.action_relevant[c]})
        row["review_candidates"] = dict(sorted(Counter(r.review[c] for r in pool if r.review.get(c)).items()))
        out[c] = row
    return {"classes": out, "platform_statuses_assessed": list(ANALYSED_STATUSES), "levels": LEVEL_TEXT,
            "reading": ("Each level is a subset of the one before. C counts what press releases spell out; "
                        "releases rarely describe mechanisms, so a low C is a property of the record, not "
                        "evidence that a capability played no role.")}


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
            for lvl, attr in (("A", "available"), ("B", "action_relevant"), ("I", "inferred"), ("C", "instrumental")):
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


def _spread(rs: List[pl.Record]) -> dict:
    cases = {r.case_id for r in rs}
    fam = Counter(r.family for r in rs)
    plats = Counter(r.platform for r in rs)
    first = {}
    for r in rs:
        first.setdefault(r.case_id, r)
    srcs = Counter(first[c].source for c in cases)
    era_cases = Counter(era_of(first[c].pub_year) for c in cases)
    fam_cases = Counter()
    for f in fam:
        fam_cases[f] = len({r.case_id for r in rs if r.family == f})
    top_p, top_s = plats.most_common(1), srcs.most_common(1)
    return {
        "cases": len(cases), "platforms": len(plats), "families": dict(sorted(fam_cases.items())),
        "eras_with_cases": dict(sorted(era_cases.items())),
        "top_platform": top_p[0][0] if top_p else None,
        "top_platform_share_of_observations": round(top_p[0][1] / len(rs), 3) if rs else None,
        "top_source": top_s[0][0] if top_s else None,
        "top_source_share_of_cases": round(top_s[0][1] / len(cases), 3) if cases else None,
        "families_with_2plus_cases": sum(1 for v in fam_cases.values() if v >= 2),
        "eras_with_2plus_cases": sum(1 for v in era_cases.values() if v >= 2),
    }


def _recurs(x: dict) -> bool:
    return x["cases"] >= 20 and x["families_with_2plus_cases"] >= 3 and x["eras_with_2plus_cases"] >= 2


def recurrence(records: List[pl.Record]) -> dict:
    out = {}
    pool = [r for r in records if r.status in ANALYSED_STATUSES]
    for c in pl.CLASSES:
        row = {lvl: _spread([r for r in pool if getattr(r, attr)[c]]) for lvl, attr in LEVELS}
        row["recurs_across_families_and_eras"] = {lvl: _recurs(row[lvl]) for lvl, _ in LEVELS}
        out[c] = row
    return {"classes": out,
            "rule": "recurs = at least 20 cases, 3+ platform families with 2+ cases each, 2+ publication eras with 2+ cases each",
            "reading": "Report the strongest level at which a class recurs; absence at C reflects what releases spell out."}


def harm_tables(records: List[pl.Record], codebook: pl.Codebook) -> dict:
    """Potential harm = AfH psi(a) pathway open in a case (class at B or I). Documented harm = harm cue
    in the release (direct: in a platform sentence; case-level: anywhere or case topic)."""
    harms = sorted(codebook.harms)
    pool = [r for r in records if r.status in ANALYSED_STATUSES]
    by_level = {}
    for c in pl.CLASSES:
        by_level[c] = {}
        for lvl, attr in LEVELS[1:]:
            rs = [r for r in pool if getattr(r, attr)[c]]
            n = len({r.case_id for r in rs})
            by_level[c][lvl] = {"of_cases": n, **{h: {
                "documented_direct": len({r.case_id for r in rs if r.harm_direct[h]}),
                "documented_case_level": len({r.case_id for r in rs if r.harm_case[h]}),
                "potential_per_afh_psi": h in AFH1_PSI[c]} for h in harms}}
    conceptual = {}
    for c, hs in AFH1_PSI.items():
        conceptual[c] = {}
        for h in hs:
            b = by_level[c]["B_capability_relevant_conduct"][h]
            i = by_level[c]["I_inferred_facilitation"][h]
            cc = by_level[c]["C_explicit_instrumental_use"][h]
            conceptual[c][h] = {
                "potential_pathway_cases_B": by_level[c]["B_capability_relevant_conduct"]["of_cases"],
                "documented_case_level_given_B": b["documented_case_level"],
                "documented_direct_given_B": b["documented_direct"],
                "documented_direct_given_I": i["documented_direct"],
                "documented_direct_given_C": cc["documented_direct"],
                "label": ("documented example available" if cc["documented_direct"] or i["documented_direct"] >= 3 else
                          "documented in cases where the pathway is open" if b["documented_case_level"] else
                          "conceptual; label as such"),
            }
    by_platform = {}
    used = [r for r in pool if r.tier in USED]
    for p in sorted({r.platform for r in used}):
        rs = [r for r in used if r.platform == p]
        by_platform[p] = {h: len({r.case_id for r in rs if r.harm_direct[h]}) for h in harms}
        by_platform[p]["use_documented_cases"] = len({r.case_id for r in rs})
    return {"by_class_and_level": by_level, "afh1_psi_pathways": conceptual,
            "platform_by_harm_direct": by_platform,
            "support_levels": "direct = harm cue in a platform sentence of a stated/inferred record; case_level = case_topics or cue anywhere in release",
            "shared_trigger_warning": ("DistributionInfrastructure C and h3, GenerativeSynthesis C and h6 share trigger verbs; "
                                       "treat those pairs as one observation, not as independent confirmation."),
            "caution": "Co-occurrence in enforcement releases. Not causal, not prevalence. A potential harm is a conceptual pathway, not an observed outcome."}


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
                                 for lvl, attr in (("A", "available"), ("B", "action_relevant"), ("I", "inferred"), ("C", "instrumental"))}
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
    dump("exemplar_inventory.json", exemplar_inventory(man))
    dump("registry_checks.json", registry_checks())
    cit.dump(cites, OUT / "citations.json")
    dump("legacy_afh1_exemplars.json", legacy_manifest_check(records, texts))
    dump("validation.json", validation(records, fingerprints))
    dump("validation_round2.json", validation_round2(records))
    dump("tier_variants.json", tier_variant_report(cases))
    dump("validation_sample.json", rv.sample_rows(records))
    write_records_csv(records)
    from . import latex, report
    report.write(OUT)
    latex.write(OUT)
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


# ------------------------------------------------------- 2026-11-17 validation

def _csv(name: str) -> List[dict]:
    path = RESEARCH / "config" / name
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def kappa(pairs: List[Tuple[bool, bool]]) -> Optional[float]:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def _r1_holds(item: str, tier: str, verdict: str) -> bool:
    kind = item.split(":")[0]
    if kind == "tier":
        return verdict == "correct" if tier == "stated" else verdict == "use_documented"
    if kind == "C":
        return verdict == "correct"
    if kind == "review":
        return verdict in ("missed_instrumental", "missed_generic_label")
    return verdict == "alias_correct"


def _r2_holds(item: str, answer: str) -> bool:
    kind = item.split(":")[0]
    if kind == "tier":
        return answer in ("explicit_use", "implied_use")
    if kind in ("C", "review"):
        return answer == "explicit"
    return answer.split("|")[0] == "yes"


def validation_round2(records: List[pl.Record]) -> dict:
    r1 = {(r["item"], r["case_id"], r["platform"]): r for r in _csv("validation_reviews.csv")}
    r2 = _csv("review_round2_classification.csv")
    adj = {(r["item"], r["case_id"], r["platform"]): r for r in _csv("validation_adjudication.csv")}
    out: Dict[str, Any] = {}
    # 1. classification sample: two independent reviewers + adjudication
    by_kind: Dict[str, List[Tuple[bool, bool]]] = defaultdict(list)
    final: Dict[str, Counter] = defaultdict(Counter)
    inferable: Counter = Counter()
    for row in r2:
        key = (row["item"], row["case_id"], row["platform"])
        a = _r1_holds(row["item"], r1[key]["tier"], r1[key]["verdict"])
        b = _r2_holds(row["item"], row["r2_answer"])
        by_kind[row["item"].split(":")[0]].append((a, b))
        if row["r2_answer"] == "analytically_inferable":
            inferable[row["item"]] += 1
        verdict = a if a == b else adj.get(key, {}).get("adjudicated", "") in ("correct", "explicit", "explicit_generic_label")
        final[row["item"]]["holds" if verdict else "fails"] += 1
    out["classification_sample"] = {
        "rows": len(r2),
        "agreement": {k: {"n": len(v), "agree": sum(a == b for a, b in v), "kappa": kappa(v)} for k, v in sorted(by_kind.items())},
        "adjudicated": {k: {"n": sum(c.values()), "holds": c["holds"], "wilson95": wilson(c["holds"], sum(c.values()))}
                        for k, c in sorted(final.items())},
        "reviewer2_analytically_inferable": dict(sorted(inferable.items())),
        "adjudication_rows": len(adj),
    }
    # 2. harm sample
    harm_rows = _csv("review_round2_harm.csv")
    harm: Dict[str, Counter] = defaultdict(Counter)
    basis: Counter = Counter()
    for row in harm_rows:
        group = row["item"].split(":")[-1] if row["item"].startswith("harm:") else "shared_trigger"
        harm[f"{row['harm']}|{group}"][row["r2_answer"]] += 1
        basis[row["r2_basis"]] += 1
    summary = {}
    for k, c in sorted(harm.items()):
        n = sum(c.values())
        tied = c.get("documented_with_platform", 0)
        summary[k] = {"n": n, **dict(c), "share_documented_with_platform": round(tied / n, 3), "wilson95": wilson(tied, n)}
    out["harm_sample"] = {"rows": len(harm_rows), "by_harm_and_group": summary, "basis": dict(basis),
                          "groups": "direct = cue in platform sentence; case_level_only = cue elsewhere/topic only; negative = no cue; shared_trigger = class C and harm fired by the same verbs"}
    # 3. tier sample
    tier_rows = _csv("review_round2_tiers.csv")
    current = {(r.case_id, r.platform): r for r in records}
    by_tier: Dict[str, Counter] = defaultdict(Counter)
    by_gate: Dict[str, Counter] = defaultdict(Counter)
    sens: Counter = Counter()
    for row in tier_rows:
        use = row["r2_answer"] in ("explicit_use", "implied_use")
        by_tier[row["tier"]][row["r2_answer"]] += 1
        if row["tier"] == "named_only":
            by_gate[row["gate"]]["use" if use else "no_use"] += 1
            rec = current.get((row["case_id"], row["platform"]))
            up = bool(rec and rec.tier_sensitivity in USED)
            sens[("reviewer_use" if use else "reviewer_no_use", "sensitivity_use" if up else "sensitivity_named_only")] += 1
    rates = {}
    for t, c in by_tier.items():
        n = sum(c.values())
        k = c.get("explicit_use", 0) + c.get("implied_use", 0)
        rates[t] = (k, n)
    out["tier_sample"] = {
        "rows": len(tier_rows),
        "by_published_tier": {t: {"n": n, "use": k, "share_use": round(k / n, 3), "wilson95": wilson(k, n), **dict(by_tier[t])}
                              for t, (k, n) in sorted(rates.items())},
        "named_only_by_gate": {g: dict(c) for g, c in sorted(by_gate.items())},
        "sensitivity_tier_vs_reviewer_named_only": {f"{a}|{b}": v for (a, b), v in sorted(sens.items())},
    }
    # 3b. inferred-facilitation sample (I but not C)
    inf_rows = _csv("review_round2_inferred.csv")
    inf: Dict[str, Counter] = defaultdict(Counter)
    for row in inf_rows:
        inf[row["item"]][row["r2_answer"]] += 1
    out["inferred_sample"] = {
        "rows": len(inf_rows),
        "by_class": {k: {"n": sum(c.values()), **dict(c),
                         "share_reasonable": round(c.get("reasonable_inference", 0) / sum(c.values()), 3),
                         "wilson95": wilson(c.get("reasonable_inference", 0), sum(c.values()))}
                     for k, c in sorted(inf.items())},
        "question": "given the platform's by-design feature and the documented conduct, is the facilitation inference reasonable",
    }
    # 4. estimated strict use-documented cases (record-level rates applied to case tiers)
    strict = pl.case_tiers(records, lambda r: r.status == "specific")
    counts = Counter(strict.values())
    est = lo = hi = 0.0
    for t in pl.TIERS:
        k, n = rates.get(t, (0, 0))
        if not n:
            continue
        w = wilson(k, n)
        est += counts[t] * k / n
        lo += counts[t] * w[0]
        hi += counts[t] * w[1]
    sens_cases = pl.case_tiers([pl.Record(r.case_id, r.fingerprint, r.source, r.pub_year, r.platform, r.status, r.family,
                                          r.tier_sensitivity if r.tier_sensitivity in pl.TIERS else "named_only", r.text_found)
                                for r in records if r.status == "specific"])
    out["use_documented_strict_cases"] = {
        "published_rules_stated_or_inferred": counts["stated"] + counts["inferred"],
        "sensitivity_rules_stated_or_inferred": sum(1 for t in sens_cases.values() if t in USED),
        "sample_weighted_estimate": round(est), "estimate_bounds_wilson": [round(lo), round(hi)],
        "strict_cases": len(strict),
        "note": "Estimate applies record-level review rates to case-level tiers; treat as approximate.",
    }
    return out


def tier_variant_report(cases: List[dict]) -> dict:
    """Decision 1: four tier variants plus the additive repair, with the round-3 blind review."""
    from . import tier_variants as tv
    rows = tv.all_variants(cases, pl.platform_registry())
    out = {"variants": tv.summarize(rows)}
    sample = _csv("review_round3_tier_variants.csv")
    if sample:
        codes = {i: {"case_id": r["case_id"], "code": r["r3_code"]} for i, r in enumerate(sample)}
        for x in sample:
            x.update(rows.get((x["case_id"], x["platform"]), {}))
        out["review"] = tv.review_analysis(sample, codes, rows, wilson)
    return out


def exemplar_inventory(man: dict) -> dict:
    """Every manifest exemplar with its blind review verdict (config/review_exemplars.csv)."""
    reviews = {(r["item"], r["case_id"]): r for r in _csv("review_exemplars.csv")}
    rows, tally = [], Counter()
    for p, e in sorted(man["platforms"].items()):
        for x in e["exemplars"]:
            _, plat, kind, what = x["purpose"].split(":", 3)
            r = reviews.get((x["purpose"], x["case_id"]))
            verdict = r["verdict"] if r and r.get("fingerprint") == x["fingerprint"] else "unreviewed"
            tally[(kind, verdict)] += 1
            rows.append({"platform": plat, "kind": kind, "cited_for": what, "case_id": x["case_id"],
                         "fingerprint": x["fingerprint"], "span": x["span"], "verdict": verdict})
    by_kind: Dict[str, Dict[str, int]] = defaultdict(dict)
    for (k, v), n in tally.items():
        by_kind[k][v] = n
    return {"exemplars": len(rows), "by_kind_and_verdict": {k: dict(sorted(v.items())) for k, v in sorted(by_kind.items())},
            "rows": rows, "span_basis": pl.SPAN_BASIS,
            "use": "cite only verdict == supported; partly_supported needs wording checked against the reviewer note in config/review_exemplars.csv"}


def registry_checks() -> dict:
    """Summary of source verification for the platform registry (no source text)."""
    src = RESEARCH / "config" / "capability_sources"
    claims = _csv("capability_sources/manuscript_claims_verified.csv")
    urls = json.loads((src / "url_check.json").read_text()) if (src / "url_check.json").is_file() else {"status": {}}
    codes = Counter(v[0] for v in urls["status"].values())
    cfg = pl.load_yaml("platforms.yaml")["platforms"]
    conf = Counter(c["confidence"] for r in cfg.values() for c in (r.get("capabilities") or {}).values())
    return {
        "capability_rows": sum(conf.values()), "capability_confidence": dict(sorted(conf.items())),
        "cited_urls": len(urls["status"]), "url_status_classes": {f"{k}xx": n for k, n in sorted(codes.items())},
        "manuscript_claims_checked": len(claims),
        "manuscript_claims_verdicts": dict(sorted(Counter(r["verdict"] for r in claims).items())),
        "manuscript_claims_fetched": sum(r["fetched_ok"] == "yes" for r in claims),
        "corrections": [{"claim_id": r["claim_id"], "date_found": r["date_found"]} for r in claims if r["verdict"] != "confirmed"],
    }
