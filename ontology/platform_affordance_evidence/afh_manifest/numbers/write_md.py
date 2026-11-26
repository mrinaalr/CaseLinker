"""Render numbers.md from numbers.json (every number in the .md comes from the .json)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
d = json.loads((OUT / "numbers.json").read_text())
c, r2, r3, r4, r5, r6, r7, r8, r9 = (d[k] for k in ("1_cover", "2_recurrence", "3_contact_discovery_g1", "4_affordance_harm",
                                                    "5_q1", "6_families", "7_pacer", "8_limitations", "9_duplicate_pair"))
H = ["h1_contact_sexual_abuse", "h2_depicted_in_abuse_imagery", "h3_imagery_circulated", "h4_coerced_by_exposure_threat",
     "h5_commercial_sexual_exploitation"]
L = []
w = L.append
n = lambda x: f"{x:,}" if isinstance(x, int) else str(x)  # noqa: E731
pct = lambda a, b: f"{100 * a / b:.1f}%"  # noqa: E731

I = d["inputs"]
PR = I["pacer_release"]
if I["afh_2_0_snapshot"]:
    w("# AfH 2.0 numbers")
    w("")
    w(f"AfH 2.0 snapshot: corpus **{n(I['corpus_cases'])} cases** · `{I['codebook']}` · registry `{I['registry']}` · "
      f"PACER `{PR}` (hashes in SNAPSHOT.md). Values in numbers.json; run order in run_all.sh. Read-only on the DB and the PACER release.")
else:
    w("# AfH numbers (not the AfH 2.0 snapshot)")
    w("")
    w(f"> ⚠ **These inputs are not the frozen AfH 2.0 snapshot.** Corpus DB matches AfH 2.0: **{I['db_matches_afh_2_0']}** "
      f"(`{I['db_sha256'][:12]}…`, {n(I['db_cases'])} cases; AfH 2.0 has {n(I['afh_2_0_reference']['db_cases']) if 'afh_2_0_reference' in I else 'see SNAPSHOT.md'}) · "
      f"PACER `{PR}` matches AfH 2.0: **{I['pacer_matches_afh_2_0']}** (`{I['pacer_sha256'][:12]}…`). "
      "Every number below is computed in full by the same code and definitions; it is not an AfH 2.0 published value.")
    w("")
    w(f"Corpus **{n(I['corpus_cases'])} cases** · `{I['codebook']}` · registry `{I['registry']}` · PACER `{PR}`. Values in numbers.json.")
w("")
w("Data caveats are marked ⚑ and collected in [Flags](#flags).")
w("")

w("## 1. Cover and abstract")
w("")
w("| Placeholder | Value | Definition | Source |")
w("|---|---:|---|---|")
w(f"| NCases | {n(c['NCases'])} | rows in `cases` | `CaseStorage.get_all_cases` |")
w(f"| NFeatures | {n(c['NFeatures'])} | `/api/stats` `unique_features`: every value read from the case text and stored; each list value counts; labels count, and the quoted spans behind them are listed, not counted; place names count (their role is not stated); placeholders, program boilerplate (incl. the CyberTipline flag), provenance and copies excluded | `run/feature_count.py` |")
w(f"| NSources | {n(c['NSources'])} | publishing families: distinct `source` labels after `_source_count_key` folding | `run/feature_count.py` `source_count_key` (as in `get_stats`) |")
w(f"| NSourceLabels | {n(c['NSourceLabels'])} | distinct raw `source` labels | same |")
w(f"| NAgencies | {n(c['NAgencies_corpus_normalized'])} | distinct agencies named in the corpus after `distinct_named_agencies` | `agency_label_normalize.distinct_named_agencies` (as in `get_stats`) |")
w(f"| NAgencyVariants | {n(c['NAgencyVariants_raw_labels'])} | distinct raw `agencies_involved` strings before normalization | `extracted_features.agencies_involved` |")
w(f"| NTaskForces | {c['NTaskForces_corpus_mentioned']} of {c['NTaskForces_list']} | geographic ICAC task forces whose lead agency is named in case text (agency needles on normalized text and agencies); {c['NTaskForces_corpus_aligned']} have a case from that task force's own ingest source, {c['NTaskForces_corpus_non_federal_feed']} a mention outside NCMEC/DOJ feeds | `scripts/verify/icac_tf_verify.py`, output in `task_forces/` |")
w(f"| NPacerCases | {c['NPacerCases']} | cases in {PR} | `<PACER release>/manifest.json` |")
w(f"| NPacerDocs | {c['NPacerDocs']} | source documents in {PR} (dockets included) | manifest `source_documents` |")
w(f"| NPacerIndictments | {c['NPacerIndictments_docs']} docs / {c['NPacerIndictments_cases']} cases | documents typed `indictment` or `superseding_indictment` ⚑ | bundle `doc_type` |")
w(f"| NPacerSoO | {c['NPacerSoO_docs_strict']} docs (strict) · {c['NPacerSoO_docs_factual_family']} docs / {c['NPacerSoO_cases_factual_family']} cases (factual family) | strict: `statement_of_offense`; family adds statement of facts, factual proffer, stipulation of facts, factual basis ⚑ | bundle `doc_type` |")
w(f"| NNamedPlatforms | {c['NNamedPlatforms_q1']} | distinct specific (non-generic, non-alias, non-technology) platform labels in the Q1 pool | `build/inventory.json` `labels.specific` |")
w(f"| (platforms analysed) | {c['NManifestPlatforms']} | manifest platforms: ≥3 use-documented cases | `build/manifest.json` |")
w(f"| YearStart | {c['YearStart_publication_year']} | earliest publication year after the load-time year corrections "
  f"({len(c['publication_year_corrections'])} records, §13); `/api/stats` reads the stored dates without them ({c['YearStart_api_stats']}). "
  f"{c['cases_before_2002_publication_year']} case(s) before 2002 | `raw_data.year`, `afhq1/labels.year_corrections` |")
w(f"| YearEnd | {c['YearEnd_publication_year']} | latest publication year | `raw_data.year` |")
w("")
w("PACER document types: " + ", ".join(f"{k} {v}" for k, v in c["NPacerDocs_by_type"].items()) + ".")
w("")

w("## 2. Recurrence and persistence")
w("")
w("Rule (`afhq1/harm_release.py` `build`, `_on_at`, `_recurs`): a row is a stated-tier (line-wrap) record of a platform where the class is `default_on` and its registry window covers the publication year (`since`…`ended`). A bin qualifies at **n_min = 30** distinct coded cases; a class is present at **k = 3**; recurs/persists = present in ≥2 qualifying bins and every qualifying bin after its first.")
w("")
for title, blk, verdict_word in (("Recurrence by launch cohort", r2["launch_cohort"], "recurs"),
                                 ("Persistence by publication era", r2["publication_era"], "persists")):
    bins = blk["bins"]
    w(f"**{title}.** Qualifying: {', '.join(blk['qualifying'])}.")
    w("")
    w("| | " + " | ".join(bins) + " | verdict |")
    w("|---|" + "---:|" * len(bins) + "---|")
    w("| cases in bin | " + " | ".join(n(blk["cases_per_bin"][b]) + ("" if b in blk["qualifying"] else " ✗") for b in bins) + " | |")
    for cls, v in blk["classes"].items():
        cells = [f"**{n(v['cases'][b])}**" if b in v["present"] else n(v["cases"][b]) for b in bins]
        w(f"| {cls} | " + " | ".join(cells) + f" | {v['verdict']} |")
    gs = blk["generative_synthesis_descriptive"]
    w("| GenerativeSynthesis (descriptive) | " + " | ".join(n(gs[b]) for b in bins) + " | not tested |")
    w("")
lcb = r2["launch_cohort"]
w("Bold = present; ✗ = bin does not qualify. Non-qualifying launch cohorts: "
  + ", ".join(f"{b} ({n(lcb['cases_per_bin'][b])} coded cases)" for b in lcb["bins"] if b not in lcb["qualifying"])
  + ". Verdicts: " + "; ".join(f"{k}: {v['verdict']} (cohort), {r2['publication_era']['classes'][k]['verdict']} (era)" for k, v in lcb["classes"].items())
  + ". Top platform per era cell is in numbers.json (`top_platform_share`).")
w("")

w("## 3. ContactDiscovery in the ≤2003 cohort without P2P")
w("")
w(f"P2P rows = rows whose platform has registry `family: p2p` ({', '.join(r3['p2p_platforms'])}). Recomputed with the same row rule as §2 (`compute_numbers.py` §3; the with-P2P count matches the committed table: {r3['check_matches_committed_count']}).")
w("")
w("| | ≤2003 coded cases | qualifies | ContactDiscovery cases | present (k=3) |")
w("|---|---:|---|---:|---|")
for k in ("with_p2p", "without_p2p"):
    v = r3[k]
    w(f"| {k.replace('_', ' ')} | {v['g1_coded_cases']} | {v['g1_qualifies']} | {v['contact_discovery_cases']} | {v['present']} |")
w("")
wo, wi = r3["without_p2p"], r3["with_p2p"]
w(f"Without P2P: ContactDiscovery {wo['contact_discovery_cases']} cases (present: {wo['present']}); cohort {wo['g1_coded_cases']} coded cases (qualifies: {wo['g1_qualifies']}). "
  f"{r3['cases_only_via_p2p']} of the {wi['contact_discovery_cases']} with-P2P cases reach ContactDiscovery only through a P2P row.")
w("")

w("## 4. Affordance × harm (rows closed at registry end dates)")
w("")
w("A row counts a class only while the platform's registry window for it is open (`since`…`ended`, `harm_release._on_at`). `harm_open/` keeps the unclosed tables for comparison.")
w("")
for t in ("strict", "broad"):
    tb = r4[f"{t}_closed"]
    rule = ("harm cue in a sentence naming the platform, and the harm in the case set" if t == "strict"
            else "the case-level harm set")
    w(f"**{t.title()}** ({rule}). Distinct cases per cell; base: {n(tb['stated_cases_with_default_on'])} stated-tier cases with a default-on class ({n(tb['stated_mentions_with_default_on'])} mentions).")
    w("")
    w("| class | h1 | h2 | h3 | h4 | h5 |")
    w("|---|---:|---:|---:|---:|---:|")
    for cls, row in tb["counts"].items():
        w(f"| {cls} | " + " | ".join(n(row[h]) for h in H) + " |")
    w("")
mv = r4["moved_by_closing_rows_open_to_closed"]
w("Moved by closing rows (open → closed): " + "; ".join(f"{t} {k.replace('|', ' × ')} {a}→{b}" for t in mv for k, (a, b) in mv[t].items()) + ". "
  f"Stated cases with a default-on class: {r4['stated_cases_with_default_on_open_vs_closed'][0]} → {r4['stated_cases_with_default_on_open_vs_closed'][1]}.")
w("")
f = r4["h1_form"]
w(f"**h1_form** (cases with h1): in_person {n(f['in_person'])} · online {n(f['online'])} · both {n(f['both'])}; no h1 {n(f['none'])}. Rule: `pipeline.h1_form` on line-repaired text (`harm_release.classify_release`).")
w("")
eg, ov = r4["excluded_groups"], r4["excluded_overlap"]
w(f"**Excluded groups** (`harm_release.build`, `excluded_groups`): ai_no_identifiable_child {n(eg['ai_no_identifiable_child'])} · attempted_contact {n(eg['attempted_contact'])} · sting_no_minor {n(eg['sting_no_minor'])} · **union {n(r4['excluded_union'])}**. "
  "Overlaps: " + ", ".join(f"{k} {v}" for k, v in ov.items()) + f". Stings kept in the base: {r4['stings_keeping_h2_or_h3']} keep h2/h3, {r4['stings_with_another_harm']} keep another harm.")
w("")
u = r4["uncovered_share"]
w(f"**Uncovered share** = {n(u['numerator'])} / {n(u['denominator'])} = **{u['share']:.4f}** ({100 * u['share']:.2f}%). Rule: {u['rule']}")
w("")

w("## 5. Q1 evidence base")
w("")
w("Q1 pool: cases whose platform labels include anything other than `online`/`internet`; generic categories (`social media`, `chat`) stay in the pool but are never named platforms. Source: `build/records.csv`, `build/inventory.json`.")
w("")
tl, t1 = r5["record_tiers_linewrap_primary"], r5["record_tiers_tiers1_baseline"]
R = r5["platform_case_records"]
w("| Value | Number |")
w("|---|---:|")
w(f"| NQOneCases (Q1 candidate cases) | {n(r5['q1_candidate_cases'])} ({100 * r5['q1_share_of_corpus']:.1f}% of corpus) |")
w(f"| PctNoPlatform (no label beyond online/internet) | {100 * r5['no_platform_beyond_online_internet_share']:.1f}% |")
w(f"| NPlatformCaseRecords | {n(R)} |")
w(f"| stated / inferred / named-only, line-wrap (primary) | {n(tl['stated'])} ({pct(tl['stated'], R)}) / {n(tl['inferred'])} ({pct(tl['inferred'], R)}) / {n(tl['named_only'])} ({pct(tl['named_only'], R)}) |")
w(f"| stated / inferred / named-only, tiers-1 (baseline) | {n(t1['stated'])} / {n(t1['inferred'])} / {n(t1['named_only'])} |")
w(f"| cases with a named platform | {n(r5['cases_with_named_platform'])} |")
nl = r5["named_record_tiers_linewrap_primary"]
w(f"| named-platform records (line-wrap stated / inferred / named-only) | {n(r5['named_platform_records'])} ({n(nl['stated'])} / {n(nl['inferred'])} / {n(nl['named_only'])}) |")
w(f"| named platforms | {r5['named_platforms']} |")
w("")
w("Per platform (manifest table: platforms with ≥3 use-documented cases). Stated = cases whose best line-wrap tier for that platform is stated; total = all cases naming it (`afhq1/build.py` `manifest`).")
w("")
w("| platform | stated | total |")
w("|---|---:|---:|")
for p, v in r5["per_platform"].items():
    w(f"| {p} | {n(v['stated_cases'])} | {n(v['total_cases'])} |")
w("")

w("## 6. Affordance families")
w("")
w(f"Base: the {n(r6['base_n'])} Q1 candidate cases, assigned by offense topic (or the matching codebook-9 harm); a case can sit in several families; {n(r6['in_no_family'])} sit in none.")
w("")
w("| family | cases | rule |")
w("|---|---:|---|")
for k, v in r6["counts"].items():
    w(f"| {k.replace('_', ' ')} | {n(v)} | {r6['rules'][k]} |")
cp = r6["coordination_parts"]
w("")
w(f"Coordination parts: multi_defendant_operation {cp['multi_defendant_operation']}, §2252A(g) enterprise charge in the text {cp['enterprise_charge_text']} "
  f"({len(cp['enterprise_only'])} by the charge alone). The charge has no stored field; it is matched in the case text.")
w("")

w(f"## 7. PACER ({PR})")
w("")
ro = r7["reliability_overall"]
w(f"Cases **{r7['cases']}** (press-linked {r7['press_linked']}/{r7['cases']}) · documents **{r7['documents']}** · agreed acts **{r7['agreed_acts']}** · chains **{r7['chains']}** · observations **{r7['observations']}** · derived steps with capability candidates **{r7['derived_steps_with_capability_candidates']} of {r7['derived_steps']}**. Source: `<PACER release>/manifest.json`, `derived/`.")
w("")
w(f"**Two-coder reliability** (pipeline report, `state_machines/coding/report.py` `build`, `reliability_real_cases`; model-coded acts only, docket-parser acts excluded): coder A {n(ro['events_coder_A'])} acts, coder B {n(ro['events_coder_B'])}, matched {n(ro['matched'])}, mean event F1 {ro['mean_event_f1']}. "
  f"Action code on matched pairs: raw agreement {ro['pooled_action_agreement']['exact']}/{ro['pooled_action_agreement']['of']} = {ro['pooled_action_agreement']['exact'] / ro['pooled_action_agreement']['of']:.3f}; mean per-case Cohen's κ {ro['mean_action_kappa']}. "
  "This is agreement conditional on both coders coding the act; it has no negatives.")
w("")
w("| case | acts | chains | obs | docs | A | B | matched | F1 | action exact | κ |")
w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for cid, v in r7["per_case"].items():
    ex = f"{v['action_exact']}/{v['action_of']}" if v["action_of"] is not None else ""
    w(f"| {cid} | {v['agreed_acts']} | {v['chains']} | {v['observations']} | {v['documents']} | {v['coder_a_events'] or ''} | {v['coder_b_events'] or ''} | {v['matched'] if v['matched'] is not None else ''} | {v['event_f1'] if v['event_f1'] is not None else ''} | {ex} | {v['action_kappa'] if v['action_kappa'] is not None else ''} |")
w("")

w("## 8. Limitations")
w("")
w(f"CSAM-related (rule: {r8['rule']}): **NCSAM {n(r8['NCSAM'])}** (PctCSAM {r8['PctCSAM']}%). "
  f"Of those, **{n(r8['NCSAM_with_named_platform'])}** ({r8['PctCSAM_with_named_platform']}%) have a named platform, and "
  f"NCSAMQOne **{n(r8['NCSAMQOne'])}** ({r8['PctCSAMQOne']}%) are Q1 candidates (generic categories included). NQOneCases {n(r8['NQOneCases'])} (PctQOneCases {r8['PctQOneCases']}%).")
w("")

w("## 9. doj_safe_childhood_2023_103 vs 2024_461")
w("")
if r9.get("available") is False:
    w(f"Not available for this corpus: {r9['reason']}.")
    w("")
else:
    a, b = r9["doj_safe_childhood_2023_103"], r9["doj_safe_childhood_2024_461"]
    w("**Two releases about one prosecution, not one release ingested twice.**")
    w("")
    w("| | 2023_103 | 2024_461 |")
    w("|---|---|---|")
    w(f"| source URL | {a['source_url']} | {b['source_url']} |")
    w(f"| release date in text | {a['dates_in_text'][0]} | {b['dates_in_text'][0]} |")
    w(f"| shared conduct date in text | {a['dates_in_text'][1]} | {b['dates_in_text'][1]} |")
    w(f"| text length | {n(a['chars'])} | {n(b['chars'])} |")
    w(f"| fingerprint (fp-1) | {r9['fingerprints']['doj_safe_childhood_2023_103'][0][:16]}… | {r9['fingerprints']['doj_safe_childhood_2024_461'][0][:16]}… |")
    w("")
    w(f"Different URLs (plea, then sentencing), different release dates, different fingerprints; text similarity {r9['text_similarity_ratio']} with {r9['sentences_shared']} sentences shared and {r9['sentences_only_first']}/{r9['sentences_only_second']} unique (the plea and the sentence). "
      "The corpus counts one prosecution twice.")
    w("")

# ---------------------------------------------------------------- 10-12
b, pv, fu = d["10_cooccurrence_bicm"], d["11_prevalence"], d["12_data_checks"]
w("## 10. Platform co-occurrence (BiCM)")
w("")
w("Q1 cases × named platforms; an edge is dropped when the case was published after the platform's registry `until`. Bipartite Configuration Model (Saracco et al. 2015) fitted with `bicm` 3.5.0 in an isolated venv; for each platform pair, observed co-occurrence, BiCM expectation, and the exact Poisson-binomial upper-tail p-value; Benjamini–Hochberg at q = 0.05 over every pair. "
  f"Fit: max degree error {max(max(b[k]['fit_degree_error'].values()) for k in ('stated', 'all')):.1e}; exact vs package `poibin` p-values differ by at most "
  f"{max((b[k]['package_crosscheck'] or {}).get('max_abs_diff', 0) for k in ('stated', 'all')):.1e}. Code: [cooc/](cooc/).")
w("")
w("| run | cases | platforms | edges | pairs tested | pairs co-occurring | significant | of those flagged (<5 cases or one source) |")
w("|---|---:|---:|---:|---:|---:|---:|---:|")
for k in ("stated", "all", "stated_clean", "all_clean"):
    x = b[k]
    w(f"| {k}: {x['what']} | {n(x['cases'])} | {x['platforms']} | {n(x['edges'])} | {n(x['pairs_tested'])} | {x['pairs_with_cooccurrence']} | {x['significant_n']} | {x['significant_flagged_n']} |")
w("")
fbp = next((y for y in b["stated"]["watch"] if sorted(y["pair"]) == ["Facebook", "Facebook Messenger"]), None)
w("Platform labels carry the Facebook-in-Messenger correction (§12). Boilerplate: an edge is dropped when every sentence naming the platform matches an app-list pattern (`config/cooc_boilerplate_sentences.yaml`).")
w("")
w(f"**Summary.** Stated tier: {n(b['stated']['pairs_tested'])} pairs tested, {b['stated']['significant_n']} significant"
  + (f"; Facebook + Facebook Messenger {fbp['observed']} cases against {fbp['expected']} expected" if fbp else "") + ". "
  f"All tiers: {b['all']['significant_n']} significant, {b['all']['significant_flagged_n']} flagged (<5 cases or one source); without boilerplate edges, "
  f"stated **{b['stated_clean']['significant_n']}**, all tiers **{b['all_clean']['significant_n']}**. Significant on both boilerplate-free runs: "
  + (", ".join(" + ".join(p) for p in b["robust_after_fixes"]) or "none") + ". Most Q1 cases name one platform (§11), so the test has little power.")
w("")
w("Affordance classes on each significant pair are in numbers.json (`significant[].classes`). Same-platform class pairs (registry bundling) are listed per platform under `mechanical_same_platform_class_pairs` and not tested.")
w("")
w("## 11. Prevalence by class, tier and level")
w("")
w(f"Over the {n(pv['records'])} Q1 platform–case records (line-wrap tiers: stated {n(pv['records_by_tier']['stated'])}, inferred {n(pv['records_by_tier']['inferred'])}, named-only {n(pv['records_by_tier']['named_only'])}). "
  "Levels: A the class is registry default_on on the platform with its window open at publication; A_any the platform offered it at all; B capability-relevant conduct; I inferred facilitation; C instrumental, stated in the platform sentence. Cells: records (share of all Q1 records); then stated / inferred / named-only. Source: `build/records.csv` (`<Class>.<level>` columns).")
w("")
w("| class | A | B | I | C |")
w("|---|---|---|---|---|")
for cls_, row in pv["classes"].items():
    cells = []
    for lv in ("A", "B", "I", "C"):
        x = row[lv]; t = x["by_tier"]
        cells.append(f"{n(x['records'])} ({100 * x['share_of_q1_records']:.1f}%): {n(t['stated']['records'])} / {n(t['inferred']['records'])} / {n(t['named_only']['records'])}")
    w(f"| {cls_} | " + " | ".join(cells) + " |")
w("")
pc = pv["named_platforms_per_case"]
w(f"Named platforms per case: stated tier {n(pc['stated']['exactly_1'])} cases name exactly 1, {n(pc['stated']['two_plus'])} name 2+ (of {n(pc['stated']['cases'])}); "
  f"all tiers {n(pc['all']['exactly_1'])} vs {n(pc['all']['two_plus'])} (of {n(pc['all']['cases'])}). B, I and C are zero on named-only records by construction. "
  "C, I and B nest within A_any (C ⊆ I ⊆ B ⊆ A_any); A counts only capabilities on by default, so a C on an opt-in feature is not in A. "
  "I is B on a default_on platform with its window open, or C. A_any (every capability the platform had shipped): " + ", ".join(f"{k} {n(v['A_any']['records'])}" for k, v in pv["classes"].items()) + " (`A_any` in numbers.json).")
w("")
w("## 12. Data checks")
w("")
bp = fu["boilerplate_app_lists"]
w(f"**Boilerplate app lists.** Rule: {bp['rule']}. Flagged: {n(bp['records_boilerplate_only'])} records ({bp['records_by_tier_linewrap'].get('named_only', 0)} named-only, {bp['records_by_tier_linewrap'].get('inferred', 0)} inferred, {bp['records_by_tier_linewrap'].get('stated', 0)} stated); "
  f"{bp['q1_cases_all_tags_boilerplate']} Q1 cases carry only flagged tags, {bp['q1_cases_all_named_platform_tags_boilerplate']} carry only flagged named-platform tags. "
  + "Named-only totals may be inflated by up to the flagged named-only records. This is an upper bound.")
w("")
fb = fu["facebook_double_tag"]
w(f"**Facebook double tag.** {fb['cause']}. Corpus: {fb['corpus_cases_tagged_facebook_raw']} cases tagged Facebook in the DB, {fb['corpus_double_tags']} only from 'Facebook Messenger' ({fb['q1_double_tags']} in Q1) → **{fb['corpus_cases_tagged_facebook_corrected']}**. "
  f"Applied {fb['applied']}. Manifest Facebook after the correction: {fb['manifest_facebook_total_cases']} total, {fb['manifest_facebook_stated_cases']} stated.")
w("")
y = fu["yahoo_chat"]
w(f"**Yahoo Chat end year.** {y['resolution']} Fix: {y['fix']}")
w("")
fc = fu["feature_count"]
w(f"**Feature count.** `/api/stats` gives {n(fc['unique_features_fresh'])} on the frozen corpus under the rule in §1. "
  f"Span-checked field assertions: {n(fc['field_assertions_rows'])} rows over {n(fc['field_assertions_cases'])} cases, {n(fc['field_assertions_span_ok'])} span-ok, {len(fc['field_assertions_by_field'])} fields. "
  "Excluded by rule (`run/feature_count.py` EXCLUDED; stored items): " + ", ".join(f"{k} {n(v['stored_items'])}" for k, v in c["NFeatures_breakdown"]["excluded"].items() if v["stored_items"]) + ". "
  "Counted case attributes: " + ", ".join(f"{k} {n(v)}" for k, v in c["NFeatures_breakdown"]["counted_case_attributes"].items() if v) + "; "
  "span-checked assertions: " + ", ".join(f"{k} {n(v)}" for k, v in c["NFeatures_breakdown"]["counted_span_checked_assertions"].items()) + ". The two sum to NFeatures.")
w("")

y13 = d["13_publication_year"]
w("## 13. Publication year")
w("")
w(f"Rule: {y13['rule']}. **{y13['corrected_n']} stored years corrected** at load (table below); the DB is unchanged. "
  f"**{y13['flagged_n']} records flagged** because their stored year conflicts with their own fields "
  f"({y13['flagged_still_uncorrected_n']} of them not corrected; list in `year_evidence.json`).")
w("")
w("| case | stored | corrected | agreeing evidence |")
w("|---|---:|---:|---|")
for cid, (a_, b_, ag) in y13["corrections"].items():
    w(f"| {cid} | {a_} | {b_} | {', '.join(ag)} |")
w("")
w(f"**Sensitivity.** Every year-dependent result (launch cohorts, publication eras, affordance × harm tables, prevalence, Q1) "
  f"recomputed without the {y13['sensitivity_flagged_left_out']} flagged records ({y13['sensitivity_flagged_in_q1']} of them in Q1): "
  + (f"**{len(y13['sensitivity_verdict_changes'])} verdict(s) change**: " + "; ".join(f"{v['result']} {v['with_flagged']} → {v['without_flagged']}" for v in y13['sensitivity_verdict_changes'])
     if y13['sensitivity_verdict_changes'] else "**no verdict changes**")
  + ". Values side by side in `year_sensitivity.json`.")
w("")
w("## Flags")
w("")
tl_, t1_ = r5["record_tiers_linewrap_primary"], r5["record_tiers_tiers1_baseline"]
low = min((v for v in r7["per_case"].items() if v[1]["event_f1"] is not None), key=lambda kv: kv[1]["event_f1"])
flags = [
    f"**NAgencies** is {n(c['NAgencies_corpus_normalized'])} after normalization; {n(c['NAgencyVariants_raw_labels'])} raw labels remain distinct before it.",
    f"**NTaskForces**: {c['NTaskForces_corpus_mentioned']} of {c['NTaskForces_list']} task forces are mentioned in corpus text, {c['NTaskForces_corpus_aligned']} have a case from their own feed; stored agency labels cannot count them (ingest collapses every ICAC task force to `ICAC`).",
    f"**Publication year**: {d['13_publication_year']['corrected_n']} stored years corrected at load and {d['13_publication_year']['flagged_n']} records flagged (§13); the DB is unchanged.",
    "**Launch cohorts** that do not qualify: " + ", ".join(f"{b_} ({n(lcb['cases_per_bin'][b_])} coded cases)" for b_ in lcb["bins"] if b_ not in lcb["qualifying"]) + ".",
    f"**PACER doc types**: {c['NPacerIndictments_docs']} indictment documents in {c['NPacerIndictments_cases']} cases; {c['NPacerSoO_docs_strict']} typed `statement_of_offense`; {c['NPacerSoO_cases_factual_family']} cases have a factual-statement document of some type.",
    f"**Record tiers**: two rules (line-wrap, primary; tiers-1, baseline). Line-wrap moves {tl_['stated'] - t1_['stated']} records into stated.",
    f"**PACER reliability** is conditional (matched pairs only): mean κ {ro['mean_action_kappa']}, mean event F1 {ro['mean_event_f1']}; lowest F1 `{low[0]}` ({low[1]['event_f1']}: {low[1]['agreed_acts']} agreed acts from {low[1]['coder_a_events']} vs {low[1]['coder_b_events']} coded).",
    f"**Facebook double tag**: {fb['corpus_double_tags']} DB Facebook tags exist only inside 'Facebook Messenger'; corrected at analysis time, the DB still holds them.",
    "**Duplicate prosecution**: 2023_103 and 2024_461 are one prosecution counted twice; other such pairs are not measured here.",
]
for x in flags:
    w(f"- ⚑ {x}")
(OUT / "numbers.md").write_text("\n".join(L) + "\n")
print(len(L), "lines")
