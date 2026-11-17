"""Evidence-tier variants for Decision 1 (2026-11-17).

A original   published tier rules on the stored text
B unwrap     same rules on text with mid-sentence line breaks joined
C verbs      same rules on the stored text with the extra conduct verbs
D combined   B and C together (the earlier "sensitivity tier")

Every variant reuses the published builder's functions; only the input text
and the offense-keyword tuple change. Nothing here alters the published tier.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from . import pipeline as pl

VARIANTS = ("A_original", "B_unwrap", "C_verbs", "D_combined", "Bplus_unwrap_additive", "Bplus_guarded")
_RANK = {"dropped": -1, "named_only": 0, "inferred": 1, "stated": 2}
RULES = {
    "A_original": "published rules (platform_affordance_evidence.py classify_sentence) on stored case text",
    "B_unwrap": "published rules on text where a single line break not preceded by . ! ? : is replaced by a space (paragraph breaks kept)",
    "C_verbs": "published rules on stored text; OFFENSE_KEYWORDS + " + ", ".join(pl.SENSITIVITY_EXTRA_VERBS),
    "D_combined": "B and C together",
    "Bplus_unwrap_additive": "max(A, B) per record: the repair can add evidence a hard wrap hid, never remove a tier the stored text earns",
    "Bplus_guarded": "Bplus, but a promotion earned only by agency social-media boilerplate is refused (builder linewrap_tiers, tiers-1+linewrap-2); the primary rule",
}


def tiers_for(case: dict, platforms: List[str], variant: str) -> Dict[str, str]:
    pe = pl.evidence_module()
    text = pl.unwrap(case["text"]) if variant in ("B_unwrap", "D_combined") else case["text"]
    original = pe.OFFENSE_KEYWORDS
    if variant in ("C_verbs", "D_combined"):
        pe.OFFENSE_KEYWORDS = original + pl.SENSITIVITY_EXTRA_VERBS
    try:
        recs = pe.process_case(case["id"], platforms, text)["records"]
    finally:
        pe.OFFENSE_KEYWORDS = original
    return {r["platform"]: r["stated_vs_inferred"] for r in recs}


def all_variants(cases: List[dict], registry) -> Dict[Tuple[str, str], Dict[str, str]]:
    """(case_id, platform) -> {variant: tier} for specific-platform records."""
    out: Dict[Tuple[str, str], Dict[str, str]] = defaultdict(dict)
    for case in cases:
        kept, _ = pl.candidate_pairs(case)
        kept = [p for p in kept if pl.platform_info(p, registry).status == "specific"]
        if not kept:
            continue
        for v in VARIANTS[:4]:
            for p, t in tiers_for(case, kept, v).items():
                out[(case["id"], p)][v] = t
        pe = pl.evidence_module()
        published = pe.process_case(case["id"], kept, case["text"])["records"]
        guarded = pe.linewrap_tiers(case["id"], kept, case["text"], published)
        for p in kept:
            row = out[(case["id"], p)]
            a, b = row.get("A_original", "dropped"), row.get("B_unwrap", "dropped")
            row["Bplus_unwrap_additive"] = a if _RANK[a] >= _RANK[b] else b
            row["Bplus_guarded"] = guarded.get(p, a)
    return out


def summarize(rows: Dict[Tuple[str, str], Dict[str, str]]) -> dict:
    rank = {"named_only": 0, "inferred": 1, "stated": 2, "dropped": -1}
    by_case: Dict[str, Dict[str, str]] = defaultdict(dict)
    for (cid, _p), tiers in rows.items():
        for v in VARIANTS:
            t = tiers.get(v, "dropped")
            if rank[t] > rank.get(by_case[cid].get(v, "dropped"), -1):
                by_case[cid][v] = t
    out = {}
    for v in VARIANTS:
        case_t = Counter(by_case[c].get(v, "dropped") for c in by_case)
        rec_t = Counter(t.get(v, "dropped") for t in rows.values())
        moves = Counter((t.get("A_original", "dropped"), t.get(v, "dropped")) for t in rows.values())
        case_moves = Counter((by_case[c].get("A_original", "dropped"), by_case[c].get(v, "dropped")) for c in by_case)
        out[v] = {
            "rule": RULES[v],
            "strict_cases": len(by_case),
            "use_documented_cases": case_t["stated"] + case_t["inferred"],
            "cases_by_tier": dict(sorted(case_t.items())),
            "records_by_tier": dict(sorted(rec_t.items())),
            "record_moves_from_A": {f"{a}->{b}": n for (a, b), n in sorted(moves.items()) if a != b},
            "case_moves_from_A": {f"{a}->{b}": n for (a, b), n in sorted(case_moves.items()) if a != b},
        }
    return out


USE_TYPES = ("offender_use_stated", "offender_use_via_report", "victim_or_third_party_use", "law_enforcement_use",
             "reporting_only", "evidence_receipt", "generic_discussion", "not_in_passage")
OFFENDER_USE = {"offender_use_stated", "offender_use_via_report"}


def strata(rows: Dict[Tuple[str, str], Dict[str, str]]) -> Dict[str, List[Tuple[str, str]]]:
    used = {"stated", "inferred"}
    up = lambda t, v: t.get("A_original") == "named_only" and t.get(v) in used  # noqa: E731
    down = lambda t, v: t.get("A_original") in used and t.get(v) not in used  # noqa: E731
    out = {
        "B_promoted": [k for k, t in rows.items() if up(t, "B_unwrap")],
        "C_only_promoted": [k for k, t in rows.items() if up(t, "C_verbs") and not up(t, "B_unwrap")],
        "D_only_promoted": [k for k, t in rows.items() if up(t, "D_combined") and not up(t, "B_unwrap") and not up(t, "C_verbs")],
        "B_demoted": [k for k, t in rows.items() if down(t, "B_unwrap")],
        "D_demoted": [k for k, t in rows.items() if down(t, "D_combined")],
        "A_named_only": [k for k, t in rows.items() if t.get("A_original") == "named_only"],
        "A_stated": [k for k, t in rows.items() if t.get("A_original") == "stated"],
        "A_inferred": [k for k, t in rows.items() if t.get("A_original") == "inferred"],
    }
    return {k: sorted(v) for k, v in out.items()}


def review_analysis(sample: List[dict], codes: Dict[int, dict], rows, wilson) -> dict:
    """Combine blind use-type codes with the variant tiers of each sampled record."""
    import math
    used = {"stated", "inferred"}
    by_stratum: Dict[str, Counter] = defaultdict(Counter)
    coded = []
    for i, x in enumerate(sample):
        c = codes[i]
        assert c["case_id"] == x["case_id"], (i, c["case_id"], x["case_id"])
        by_stratum[x["stratum"]][c["code"]] += 1
        coded.append({**x, "code": c["code"], "offender_use": c["code"] in OFFENDER_USE})
    out: Dict[str, dict] = {"codes_by_stratum": {k: dict(sorted(v.items())) for k, v in sorted(by_stratum.items())}}
    # Precision of what each variant ADDS (promotions), from the targeted strata.
    prec = {}
    for name, strata_names in {"B_promotions": ["B_promoted"], "C_only_promotions": ["C_only_promoted"],
                               "D_only_promotions": ["D_only_promoted"]}.items():
        rs = [r for r in coded if r["stratum"] in strata_names]
        k = sum(r["offender_use"] for r in rs)
        prec[name] = {"n": len(rs), "offender_use": k, "precision": round(k / len(rs), 3) if rs else None, "wilson95": wilson(k, len(rs))}
    dem = [r for r in coded if r["stratum"] == "B_demoted"]
    prec["B_demotions_that_are_offender_use"] = {"n": len(dem), "offender_use": sum(r["offender_use"] for r in dem),
                                                 "wilson95": wilson(sum(r["offender_use"] for r in dem), len(dem))}
    out["promotion_precision"] = prec
    # Recall / false-positive rate inside the published named_only tier: random sample R_named_only.
    rand = [r for r in coded if r["stratum"] == "R_named_only"]
    pos = [r for r in rand if r["offender_use"]]
    neg = [r for r in rand if not r["offender_use"]]
    rec = {}
    for v in VARIANTS[1:]:
        tp = sum(r[v] in used for r in pos)
        fp = sum(r[v] in used for r in neg)
        rec[v] = {"recovered_offender_use": f"{tp}/{len(pos)}", "recall_within_named_only": round(tp / len(pos), 3) if pos else None,
                  "recall_wilson95": wilson(tp, len(pos)), "false_promotions": f"{fp}/{len(neg)}",
                  "false_promotion_rate": round(fp / len(neg), 3) if neg else None, "fpr_wilson95": wilson(fp, len(neg))}
    out["named_only_random_sample"] = {"n": len(rand), "offender_use": len(pos), "by_variant": rec}
    # Precision of the published tiers themselves (random stated / inferred samples).
    pub = {}
    for t in ("R_stated", "R_inferred"):
        rs = [r for r in coded if r["stratum"] == t]
        k = sum(r["offender_use"] for r in rs)
        pub[t] = {"n": len(rs), "offender_use": k, "precision": round(k / len(rs), 3) if rs else None, "wilson95": wilson(k, len(rs))}
    out["published_tier_precision"] = pub
    # Expected offender-use records per variant (record level): stratified estimator with normal-approx 95% CI.
    pop = Counter(t.get("A_original", "dropped") for t in rows.values())
    p = {"stated": pub["R_stated"], "inferred": pub["R_inferred"]}
    est = {}
    nr = len(rand)
    pn = len(pos) / nr if nr else 0
    for tier, n_pop in pop.items():
        if tier == "named_only":
            est[tier] = (n_pop * pn, n_pop ** 2 * pn * (1 - pn) / nr)
        elif tier in p and p[tier]["n"]:
            q = p[tier]["offender_use"] / p[tier]["n"]
            est[tier] = (n_pop * q, n_pop ** 2 * q * (1 - q) / p[tier]["n"])
    mean = sum(m for m, _ in est.values())
    sd = math.sqrt(sum(v for _, v in est.values()))
    out["expected_offender_use_records"] = {
        "population_records_by_published_tier": dict(pop), "estimate": round(mean), "ci95_normal": [round(mean - 1.96 * sd), round(mean + 1.96 * sd)],
        "note": "Record-level (platform-case observations); random samples only; a case-level figure needs case-level sampling.",
    }
    out["examples"] = {
        "false_positive_promotions": [{k: r[k] for k in ("stratum", "case_id", "platform", "code")} for r in coded
                                      if r["stratum"].endswith("promoted") and not r["offender_use"]],
        "false_negatives_left_by_D": [{k: r[k] for k in ("stratum", "case_id", "platform", "code")} for r in rand
                                      if r["offender_use"] and r["D_combined"] not in used],
        "B_demotions": [{k: r[k] for k in ("case_id", "platform", "code")} for r in dem],
    }
    return out
