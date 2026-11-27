"""Every AfH 2.0 number, from the frozen corpus, codebook-9, platforms-3 and pacer-v2 (SNAPSHOT.md).

Run run_afh.py first (it writes build/, harm_open/, harm_closed/ here). Then:
  DATABASE_URL='' REDIS_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/compute_numbers.py
Reads caselinker.db read-only; writes numbers.json here. No names are read out or written.
"""
import collections
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
REPO = AI.REPO
AFH = REPO / "ontology" / "platform_affordance_evidence" / "afh_manifest"
sys.path.insert(0, str(AFH))
sys.path.insert(0, str(REPO / "run"))
sys.path.insert(0, str(REPO))
for sub in ("src/Storage Layer", "src/Processing Layer", "src/Processing Layer/Pattern Processing Layer", "src"):
    sys.path.insert(0, str(REPO / sub))

DB = AI.DB
PACER = AI.PACER
db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
J = lambda p: json.loads((OUT / p).read_text())  # noqa: E731
out = {"inputs": {}}

# ---------------------------------------------------------------- inputs
from afhq1 import pipeline as pl  # noqa: E402
out["inputs"] = {
    "corpus_cases": db.execute("select count(*) from cases").fetchone()[0],          # analysis DB (exclusions applied)
    "collected_corpus_cases": sqlite3.connect(f"file:{AI.COLLECTED}?mode=ro", uri=True).execute("select count(*) from cases").fetchone()[0],
    "codebook": pl.Codebook.load().version,
    "registry": pl.load_yaml("platforms.yaml")["version"],
    "pacer_release": json.loads((PACER / "manifest.json").read_text())["release_id"],
    "snapshot_identity": J("build/RUN_IDENTITY.json").get("dataset_identity"),
    **AI.run_inputs(OUT),
}

# ---------------------------------------------------------------- 1. cover
# Same rules as GET /api/stats (run/main.py get_stats), on the same storage rows, without importing the API:
# run/main.py builds a writable CaseStorage at import. Every read here is SQLite mode=ro.
# The cover describes the collected corpus (AFH_DB_COLLECTED): records, features, sources, agencies and task
# forces count every collected record. Every later section reads the analysis DB (`db`, exclusions applied).
from storage import CaseStorage  # noqa: E402
from agency_label_normalize import distinct_named_agencies  # noqa: E402
from feature_count import source_count_key  # noqa: E402
store = CaseStorage.read_only(str(AI.COLLECTED))
cases = store.get_all_cases(include_raw_data=False)


def parse_field(field):
    if isinstance(field, str):
        try:
            return json.loads(field)
        except Exception:
            return []
    return field if field else []


sources, total_features, agency_labels, pub_starts = set(), 0, [], []
for case in cases:
    s = case.get("source") or (case.get("raw_data") or {}).get("source")
    if s:
        sources.add(s)
    for key in ("platforms_used", "case_topics", "severity_indicators", "agencies_involved"):
        v = case.get(key, [])
        if isinstance(v, list) and v:
            total_features += len([x for x in v if x])
for case in cases:
    for org in parse_field(case.get("agencies_involved", [])) or []:
        if org and isinstance(org, str) and org.strip():
            agency_labels.append(org.strip())
    if case.get("investigation_type"):
        total_features += 1
    if case.get("relationship_to_victim"):
        total_features += 1
    if case.get("perpetrator_registered_sex_offender") is True:
        total_features += 1
    if case.get("perpetrator_age") is not None:
        total_features += 1
    vc = case.get("victim_count")
    if vc and isinstance(vc, (int, float)) and vc > 0:
        total_features += 1
    ev = case.get("evidence_volume")
    if ev and isinstance(ev, dict) and (ev.get("images") or ev.get("videos") or ev.get("storage_size")):
        total_features += 1
    pr = case.get("prosecution_outcome")
    if pr and isinstance(pr, dict) and (pr.get("booking_status") or pr.get("charges") or pr.get("jail")):
        total_features += 1
    vd = case.get("case_demographics") or case.get("victim_demographics")
    if vd and isinstance(vd, dict) and (vd.get("ages") or vd.get("age_range") or vd.get("victim_gender")):
        total_features += 1
    if case.get("perpetrator_gender"):
        total_features += 1
    dr = case.get("date_range") if isinstance(case.get("date_range"), dict) else {}
    st = case.get("date_start") or (dr.get("start") if dr else None)
    if st:
        pub_starts.append(str(st))

agencies = distinct_named_agencies(agency_labels)
ICAC = re.compile(r"\b(?:ICAC|Internet\s+Crimes\s+Against\s+Child(?:ren)?)\b", re.I)
task_forces = sorted(a for a in agencies if ICAC.search(a))
from afhq1.labels import year_corrections as _year_corrections  # noqa: E402
_fixes = _year_corrections(db)
pub_year_of = {cid: (_fixes[cid]["corrected"] if cid in _fixes else y)
               for cid, y in db.execute("select id, cast(json_extract(raw_data,'$.year') as int) from cases")}
pub_years = [y for y in pub_year_of.values() if y]
year_corrections = {cid: [f["stored"], f["corrected"]] for cid, f in sorted(_fixes.items())}
denoms = J("build/inventory.json")["denominators"]

pacer = json.loads((PACER / "manifest.json").read_text())
bundles = [json.loads(p.read_text()) for p in sorted((PACER / "cases").glob("*.json"))]
doc_types = collections.Counter(d["doc_type"] for b in bundles for d in b["documents"])
# Text-free per-case document-type inventory: ships, so public document counts reproduce without the bundles.
(OUT / "pacer_doc_types.json").write_text(json.dumps({
    "release": json.loads((PACER / "manifest.json").read_text())["release_id"],
    "afh_inputs": AI.inputs_label(OUT),
    "cases": {b["case_id"]: dict(sorted(collections.Counter(d["doc_type"] for d in b["documents"]).items())) for b in bundles},
}, indent=1, sort_keys=True) + "\n")
cases_with = lambda kinds: sorted({b["case_id"] for b in bundles for d in b["documents"] if d["doc_type"] in kinds})  # noqa: E731
FACTUAL = {"statement_of_offense", "statement_of_facts", "factual_proffer", "stipulation_of_facts", "factual_basis"}
labels = J("build/inventory.json")["labels"]
manifest_rows = J("build/manifest.json")["platforms"]

import feature_count as fcount  # run/feature_count.py, the /api/stats definition
asserted_counts = store.count_assertion_feature_values(fcount.EXCLUDED_ROLES)
total_features = fcount.count_extracted_features(cases, asserted_counts)
# The breakdown comes from the counter's own categories (run/feature_count.py), so docs cannot drift from code.
_attr = {k: 0 for k in fcount.COUNTED}
for case in cases:
    nested = fcount._nested(case)
    for key, rule in fcount.COUNTED.items():
        value = case[key] if key in case else nested.get(key)
        if key == "case_demographics" and not value:
            value = case.get("victim_demographics") or nested.get("victim_demographics")
        if key in fcount.PLATFORM_COPY_FIELDS:
            plats = fcount._platform_labels(case, nested)
            value = [x for x in fcount._json_list(value) if not (isinstance(x, str) and x.strip().lower() in plats)]
        _attr[key] += rule(value)
_asserted = {f: asserted_counts.get(f, 0) for f in fcount.ASSERTED_FIELDS}
_excluded_items = dict.fromkeys(fcount.EXCLUDED, 0)
for case in cases:
    nested = fcount._nested(case)
    for key in fcount.EXCLUDED:
        v = nested.get(key)
        if v:
            _excluded_items[key] += len([x for x in v if x]) if isinstance(v, list) else 1
assert sum(_attr.values()) + sum(_asserted.values()) == total_features, "feature breakdown must sum to NFeatures"
feature_breakdown = {
    "rule": ("a value read from the case text and stored for the case; a list counts each value; labels count, and the quoted "
             "spans behind them are listed, not counted; placeholders, program boilerplate, provenance and copies of other attributes are excluded"),
    "counted_case_attributes": _attr,
    "counted_span_checked_assertions": _asserted,
    "asserted_copies_not_counted_again": fcount.ASSERTED_COPIES,
    "excluded": {k: {"reason": fcount.EXCLUDED[k], "stored_items": _excluded_items[k]} for k in fcount.EXCLUDED},
}
out["1_cover"] = {
    "NCases": len(cases),
    "NFeatures": total_features,
    "NFeatures_breakdown": feature_breakdown,
    "NSources": len({source_count_key(s) for s in sources}),
    "NSourceLabels": len(sources),
    "NAgencies_corpus_normalized": len(agencies),
    "NAgencyVariants_raw_labels": len(set(agency_labels)),
    "NTaskForces_corpus_named": len(task_forces),
    "NPacerCases": len(pacer["cases"]),
    "NPacerDocs": sum(len(c.get("source_documents", [])) for c in pacer["cases"]),
    "NPacerDocs_by_type": dict(doc_types.most_common()),
    "NPacerIndictments_docs": doc_types["indictment"] + doc_types["superseding_indictment"],
    "NPacerIndictments_cases": len(cases_with({"indictment", "superseding_indictment"})),
    "NPacerSoO_docs_strict": doc_types["statement_of_offense"],
    "NPacerSoO_docs_factual_family": sum(doc_types[k] for k in FACTUAL),
    "NPacerSoO_cases_factual_family": len(cases_with(FACTUAL)),
    "NNamedPlatforms_q1": len(labels["specific"]),
    "NManifestPlatforms": len(manifest_rows),
    "YearStart_api_stats": min(pub_starts)[:4] if pub_starts else None,
    "YearStart_publication_year": min(pub_years),
    "YearEnd_publication_year": max(pub_years),
    "cases_before_2002_publication_year": sum(1 for y in pub_years if y < 2002),
    "cases_before_2002_ids": sorted(cid for cid, y in pub_year_of.items() if y and y < 2002),
    "publication_year_corrections": year_corrections,   # stored -> corrected (biography date used as year)
}

# ---------------------------------------------------------------- 2. recurrence / persistence
rec = J("harm_open/recurrence_by_generation.json")
assert rec == J("harm_closed/recurrence_by_generation.json"), "recurrence must not depend on the harm-table patch"
lc, pe_ = rec["recurrence by launch cohort"], rec["persistence by publication era"]
out["2_recurrence"] = {
    "launch_cohort": {
        "bins": lc["rule"]["bins"],
        "cases_per_bin": {g: v["coded_cases"] for g, v in lc["generations"].items()},
        "qualifying": [g for g, v in lc["generations"].items() if v["qualifies"]],
        "classes": {c: {"verdict": "recurs" if v["recurs"] else "does not recur",
                        "cases": {g: x["stated_tier_default_on_cases"] for g, x in v["generations"].items()},
                        "present": [g for g, x in v["generations"].items() if x["present"]]}
                    for c, v in lc["classes"].items()},
        "generative_synthesis_descriptive": lc["generative_synthesis"]["generations"],
    },
    "publication_era": {
        "bins": pe_["bins"],
        "cases_per_bin": {g: v["coded_cases"] for g, v in pe_["eras"].items()},
        "qualifying": [g for g, v in pe_["eras"].items() if v["qualifies"]],
        "cases_after_2026": pe_["cases_after_2026"],
        "classes": {c: {"verdict": "persists" if v["persists"] else "does not persist",
                        "cases": {g: x["cases"] for g, x in v["eras"].items()},
                        "present": [g for g, x in v["eras"].items() if x["present"]],
                        "top_platform_share": {g: [x["top_platform"], x["top_platform_share"]] for g, x in v["eras"].items()}}
                    for c, v in pe_["classes"].items()},
        "generative_synthesis_descriptive": {g: x["cases"] for g, x in pe_["generative_synthesis"]["eras"].items()},
    },
}
for block, unit, test in ((out["2_recurrence"]["launch_cohort"], "cohort", "recurrence"),
                          (out["2_recurrence"]["publication_era"], "era", "persistence")):
    for c, v in block["classes"].items():
        if len(block["qualifying"]) < 2:
            v["verdict"] = "untestable (fewer than two qualifying bins)"
        elif v["present"] and v["present"][0] == block["qualifying"][-1]:
            # present only from the last qualifying bin on: no later bin can show it again
            v["verdict"] = f"first appears in the last qualifying {unit}; {test} untestable"

# ---------------------------------------------------------------- 3. ContactDiscovery, G1, with / without P2P rows
from afhq1 import harm_release as hr  # noqa: E402
from afhq1.labels import correct_platform_labels  # noqa: E402
registry = pl.platform_registry()
pe = pl.evidence_module()
launch = {r["platform_id"]: r["launch_year"] for r in hr._launch_years.load()}
codebook = pl.Codebook.load()
key = {n: s["capability"] for n, s in codebook.classes.items()}
P2P = sorted(p for p, v in pl.load_yaml("platforms.yaml")["platforms"].items() if v.get("family") == "p2p")
g1 = hr.GENERATIONS[0]
coded = {"with_p2p": set(), "without_p2p": set()}
cd = {"with_p2p": set(), "without_p2p": set()}
cd_p2p_only = set()
for cid, raw, plats in db.execute("select id, raw_data, platforms_used from cases order by id"):
    raw = json.loads(raw or "{}")
    labels_ = [p for p in correct_platform_labels(json.loads(plats or "[]"), raw.get("case_text") or "")
               if pl.platform_info(p, registry).status != "excluded"]
    if not labels_:
        continue
    year = pub_year_of[cid]
    text = raw.get("case_text") or ""
    published = pe.process_case(cid, labels_, text)
    tiers = pe.linewrap_tiers(cid, labels_, text, published["records"])
    for r in published["records"]:
        p = r["platform"]
        if tiers.get(p) != "stated" or p not in launch or hr._launch_years.generation(launch[p]) != g1:
            continue
        info = pl.platform_info(p, registry)
        ons = [c for c in hr.TEST_CLASSES if hr._on_at(info, key[c], year)]
        for variant in ("with_p2p", "without_p2p"):
            if variant == "without_p2p" and p in P2P:
                continue
            if ons:
                coded[variant].add(cid)
            if "ContactDiscovery" in ons:
                cd[variant].add(cid)
cd_p2p_only = cd["with_p2p"] - cd["without_p2p"]
out["3_contact_discovery_g1"] = {
    "generation": g1, "p2p_platforms": P2P,
    "with_p2p": {"g1_coded_cases": len(coded["with_p2p"]), "g1_qualifies": len(coded["with_p2p"]) >= hr.N_MIN,
                 "contact_discovery_cases": len(cd["with_p2p"]), "present": len(cd["with_p2p"]) >= hr.K_PRESENT and len(coded["with_p2p"]) >= hr.N_MIN},
    "without_p2p": {"g1_coded_cases": len(coded["without_p2p"]), "g1_qualifies": len(coded["without_p2p"]) >= hr.N_MIN,
                    "contact_discovery_cases": len(cd["without_p2p"]), "present": len(cd["without_p2p"]) >= hr.K_PRESENT and len(coded["without_p2p"]) >= hr.N_MIN},
    "cases_only_via_p2p": len(cd_p2p_only),
    "check_matches_committed_count": len(cd["with_p2p"]) == lc["classes"]["ContactDiscovery"]["generations"][g1]["stated_tier_default_on_cases"],
}

# ---------------------------------------------------------------- 4. affordance x harm
ch = J("harm_closed/case_harms.json")
assert ch == J("harm_open/case_harms.json")
tables = {}
for v in ("open", "closed"):
    for t in ("strict", "broad"):
        d = J(f"harm_{v}/affordance_harm_{t}.json")
        tables[f"{t}_{v}"] = {"counts": d["counts"], "stated_cases_with_default_on": d["stated_cases_with_default_on"],
                              "stated_mentions_with_default_on": d["stated_mentions_with_default_on"]}
moved = {}
for t in ("strict", "broad"):
    a, b = tables[f"{t}_open"]["counts"], tables[f"{t}_closed"]["counts"]
    moved[t] = {f"{c}|{h}": [a[c][h], b[c][h]] for c in a for h in a[c] if a[c][h] != b[c][h]}
out["4_affordance_harm"] = {
    "strict_closed": tables["strict_closed"], "broad_closed": tables["broad_closed"],
    "moved_by_closing_rows_open_to_closed": moved,
    "stated_cases_with_default_on_open_vs_closed": [tables["strict_open"]["stated_cases_with_default_on"], tables["strict_closed"]["stated_cases_with_default_on"]],
    "h1_form": ch["h1_form_counts"],
    "excluded_groups": ch["excluded_groups"]["sizes"],
    "excluded_overlap": {k: v["count"] for k, v in ch["excluded_groups"]["overlap"].items()},
    "excluded_union": ch["excluded_groups"]["union"],
    "uncovered_share": ch["uncovered_share"],
    "stings_keeping_h2_or_h3": ch["stings_keeping_h2_or_h3"]["count"],
    "stings_with_another_harm": ch["stings_with_another_harm"]["count"],
}

# ---------------------------------------------------------------- 5. Q1 evidence base
recs = list(csv.DictReader(open(OUT / "build/records.csv")))
named = [r for r in recs if r["status"] == "specific"]
tierc = lambda rows, col: dict(collections.Counter(r[col] for r in rows))  # noqa: E731
out["5_q1"] = {
    "q1_candidate_cases": len({r["case_id"] for r in recs}),
    "q1_share_of_corpus": round(len({r["case_id"] for r in recs}) / out["inputs"]["corpus_cases"], 4),
    "platform_case_records": len(recs),
    "record_tiers_linewrap_primary": tierc(recs, "tier_linewrap"),
    "record_tiers_tiers1_baseline": tierc(recs, "tier"),
    "cases_with_named_platform": len({r["case_id"] for r in named}),
    "named_platform_records": len(named),
    "named_record_tiers_linewrap_primary": tierc(named, "tier_linewrap"),
    "named_record_tiers_tiers1_baseline": tierc(named, "tier"),
    "named_platforms": len(labels["specific"]),
    "no_platform_beyond_online_internet_share": round((denoms["cases_with_no_platform_label"] + denoms["cases_with_only_online_or_internet"]) / out["inputs"]["corpus_cases"], 4),
    "per_platform": {p: {"stated_cases": v["cases_by_tier"].get("stated", 0), "total_cases": v["cases"],
                         "use_documented_cases": v["use_documented_cases"]} for p, v in sorted(manifest_rows.items())},
}

# ---------------------------------------------------------------- 6. families (by offense topic, Q1 base)
q1_ids = {r["case_id"] for r in recs}
harm_of = {c["id"]: set(c["harms"]) for c in ch["cases"]}
topics_of, multi_of = {}, {}
for cid, t, f in db.execute("select id, case_topics, extracted_features from cases"):
    topics_of[cid] = set(json.loads(t or "[]"))
    multi_of[cid] = bool((json.loads(f or "{}") or {}).get("multi_defendant_operation"))
from afhq1.labels import names_enterprise_charge  # noqa: E402
enterprise_of = {cid: names_enterprise_charge(t) for cid, t in db.execute("select id, json_extract(raw_data,'$.case_text') from cases")}
fam = {
    "contact_and_approach": {c for c in q1_ids if topics_of[c] & {"hands_on", "sextortion"} or harm_of[c] & {"h1_contact_sexual_abuse", "h4_coerced_by_exposure_threat"}},
    "production": {c for c in q1_ids if "production" in topics_of[c] or "h2_depicted_in_abuse_imagery" in harm_of[c]},
    "possession_and_trade": {c for c in q1_ids if topics_of[c] & {"possession", "distribution"} or "h3_imagery_circulated" in harm_of[c]},
    "coordination": {c for c in q1_ids if multi_of[c] or enterprise_of[c]},
}
out["6_families"] = {
    "base": "Q1 candidate cases", "base_n": len(q1_ids),
    "counts": {k: len(v) for k, v in fam.items()},
    "coordination_parts": {"multi_defendant_operation": sum(1 for c in q1_ids if multi_of[c]),
                           "enterprise_charge_text": sum(1 for c in q1_ids if enterprise_of[c]),
                           "enterprise_only": sorted(c for c in q1_ids if enterprise_of[c] and not multi_of[c])},
    "in_no_family": len(q1_ids - set().union(*fam.values())),
    "rules": {
        "contact_and_approach": "topic hands_on or sextortion, or h1 or h4 in the codebook-9 case harm set",
        "production": "topic production, or h2 in the case harm set",
        "possession_and_trade": "topic possession or distribution, or h3 in the case harm set",
        "coordination": "extracted multi_defendant_operation, or a §2252A(g) child exploitation enterprise charge named in the case text; naming Discord or a game platform alone does not count",
        "overlap": "a case can be in several families",
    },
}

# ---------------------------------------------------------------- 7. PACER
rep = json.loads((PACER / "report.json").read_text())


def walk(o, acc):
    if isinstance(o, dict):
        if "candidate_capabilities" in o:
            acc[0] += 1
            acc[1] += bool(o["candidate_capabilities"])
        for v in o.values():
            walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            walk(v, acc)


# One derivation (DIRECT). The *.inferred.json files hold the same steps under the INFERRED threshold;
# reading both counted every step twice. A step is one act in one chain, so an act in several chains
# is several steps: unique acts are counted beside them.
acc = [0, 0]
unique_acts, unique_with = set(), set()
for p in sorted((PACER / "derived").glob("*.direct.json")):
    derived = json.loads(p.read_text())
    walk(derived, acc)
    for track in derived["tracks"]:
        for chain in track["trajectories"]:
            for step in chain["steps"]:
                unique_acts.add((derived["case_id"], step["event_id"]))
                if step["claims"]["candidate_capabilities"]:
                    unique_with.add((derived["case_id"], step["event_id"]))
per_case = {}
for c in pacer["cases"]:
    a = (rep["cases"].get(c["case_id"], {}).get("agreement_model_coded") or {})
    per_case[c["case_id"]] = {
        "agreed_acts": (c.get("review") or {}).get("agreed", 0),
        "chains": c["graphs"]["trajectories"].get("chains", 0),
        "observations": c["graphs"].get("observations", {}).get("observations", 0),
        "documents": len(c.get("source_documents", [])),
        "coder_a_events": a.get("events", {}).get("coder_a"), "coder_b_events": a.get("events", {}).get("coder_b"),
        "matched": a.get("events", {}).get("matched"), "event_f1": a.get("events", {}).get("f1"),
        "action_exact": a.get("action_code", {}).get("exact"), "action_of": a.get("action_code", {}).get("of"),
        "action_kappa": a.get("action_code", {}).get("kappa"),
    }
out["7_pacer"] = {
    "cases": len(pacer["cases"]),
    "press_linked": sum(1 for c in pacer["cases"] if db.execute("select 1 from cases where id=?", (c["case_id"],)).fetchone()),
    "documents": out["1_cover"]["NPacerDocs"],
    "agreed_acts": sum(v["agreed_acts"] for v in per_case.values()),
    "chains": sum(v["chains"] for v in per_case.values()),
    "observations": sum(v["observations"] for v in per_case.values()),
    "derived_steps": acc[0], "derived_steps_with_capability_candidates": acc[1],
    "derived_step_acts": len(unique_acts), "derived_step_acts_with_capability_candidates": len(unique_with),
    "derived_steps_derivation": "DIRECT (derived/*.direct.json); the INFERRED derivation is not added",
    "reliability_overall": rep["reliability_real_cases"],
    "per_case": per_case,
}

# ---------------------------------------------------------------- 8. limitations
CSAM = {"csam", "ai_csam", "possession", "distribution", "production"}
csam_ids = {c for c, t in topics_of.items() if t & CSAM}
named_ids = {r["case_id"] for r in named}
out["8_limitations"] = {
    "rule": "topic csam, ai_csam, possession, distribution or production",
    "NCSAM": len(csam_ids), "PctCSAM": round(100 * len(csam_ids) / len(topics_of), 1),
    "NCSAM_with_named_platform": len(csam_ids & named_ids),
    "PctCSAM_with_named_platform": round(100 * len(csam_ids & named_ids) / len(csam_ids), 1),
    "NCSAMQOne": len(csam_ids & q1_ids), "PctCSAMQOne": round(100 * len(csam_ids & q1_ids) / len(csam_ids), 1),
    "NQOneCases": len(q1_ids), "PctQOneCases": round(100 * len(q1_ids) / len(topics_of), 1),
}

# ---------------------------------------------------------------- 9. duplicate pair (no names)
pair = ("doj_safe_childhood_2023_103", "doj_safe_childhood_2024_461")
if not all(db.execute("select 1 from cases where id=?", (cid,)).fetchone() for cid in pair):
    # AfH 2.0-specific evidence: another corpus may not hold this pair
    out["9_duplicate_pair"] = {"available": False, "reason": "this corpus does not hold both AfH 2.0 example cases"}
else:
    rows = {cid: db.execute("select source_url, json_extract(raw_data,'$.case_text'), json_extract(raw_data,'$.year'), "
                            "date_start, json_extract(raw_data,'$.source_file'), json_extract(raw_data,'$.page') from cases where id=?", (cid,)).fetchone()
            for cid in pair}
    import difflib  # noqa: E402
    ta, tb = rows[pair[0]][1] or "", rows[pair[1]][1] or ""
    norm = lambda t: re.sub(r"\s+", " ", t).strip()  # noqa: E731
    sa, sb = set(re.split(r"(?<=[.!?])\s+", norm(ta))), set(re.split(r"(?<=[.!?])\s+", norm(tb)))
    date_line = lambda t: re.findall(r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}", t)[:2]  # noqa: E731
    title = lambda t: norm(t.split("\n")[0])[:0]  # noqa: E731
    out["9_duplicate_pair"] = {
        pair[0]: {"source_url": rows[pair[0]][0], "year": rows[pair[0]][2], "date_start": rows[pair[0]][3], "chars": len(ta), "dates_in_text": date_line(ta), "source_file": rows[pair[0]][4]},
        pair[1]: {"source_url": rows[pair[1]][0], "year": rows[pair[1]][2], "date_start": rows[pair[1]][3], "chars": len(tb), "dates_in_text": date_line(tb), "source_file": rows[pair[1]][4]},
        "same_url": rows[pair[0]][0] == rows[pair[1]][0],
        "text_similarity_ratio": round(difflib.SequenceMatcher(None, norm(ta), norm(tb)).ratio(), 3),
        "sentences_shared": len(sa & sb), "sentences_only_first": len(sa - sb), "sentences_only_second": len(sb - sa),
        "fingerprints": {cid: (db.execute("select * from case_fingerprints where case_id=?", (cid,)).fetchone() or [None])[1:3] for cid in pair},
    }

(OUT / "numbers.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
print(json.dumps({k: (v if k in ("inputs", "1_cover", "8_limitations") else "…") for k, v in out.items()}, indent=1, default=str))

# ---------------------------------------------------------------- 1b. task forces (scripts/verify/icac_tf_verify.py)
# Run first: .venv/bin/python scripts/verify/icac_tf_verify.py --db caselinker.db --cross-csv <here>/task_forces/tf_cross.csv
tf = (OUT / "task_forces/icac_tf_verify.out").read_text()
grab = lambda label: int(re.search(re.escape(label) + r"\s*(\d+)", tf).group(1))  # noqa: E731
out["1_cover"]["NTaskForces_list"] = int(re.search(r"Geographic TF rows \((\d+)\)", tf).group(1))
out["1_cover"]["NTaskForces_corpus_mentioned"] = grab("Geographic TF rows (61) with ≥1 text hit:")
out["1_cover"]["NTaskForces_corpus_aligned"] = grab("Geographic TF rows (61) with ≥1 aligned hit:")
out["1_cover"]["NTaskForces_corpus_non_federal_feed"] = grab("Geographic TF rows (61) with ≥1 hit & source ∉ {NCMEC,DOJ}:")
out["1_cover"].pop("NTaskForces_corpus_named", None)
(OUT / "numbers.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
print("task forces", {k: v for k, v in out["1_cover"].items() if k.startswith("NTaskForces")})
