"""Merge sections 10-12 (co-occurrence, prevalence, data checks) into numbers.json. Run after compute_numbers.py,
cooc/summarize.py, prevalence.py and data_checks.py:  python3 ontology/platform_affordance_evidence/afh_manifest/numbers/merge_sections.py"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
J = lambda p: json.loads((OUT / p).read_text())  # noqa: E731
d = J("numbers.json")
cooc = J("cooc/cooccurrence.json")
d["10_cooccurrence_bicm"] = cooc
ye, ys = J("year_evidence.json"), J("year_sensitivity.json")
d["13_publication_year"] = {
    "rule": ye["rule"], "corrected_n": ye["corrected_n"], "flagged_n": ye["flagged_n"],
    "flagged_still_uncorrected_n": ye["flagged_still_uncorrected_n"],
    "corrections": {cid: [f["stored"], f["corrected"], f["agreeing"]] for cid, f in sorted(ye["corrections"].items())},
    "sensitivity_flagged_left_out": ys["flagged_left_out"], "sensitivity_flagged_in_q1": ys["flagged_in_q1"],
    "sensitivity_verdict_changes": ys["verdict_changes"],
    "sensitivity_values": "year_sensitivity.json (every year-dependent value with and without the flagged records)",
}
d["11_prevalence"] = J("prevalence.json")
fu = J("data_checks.json")
db = sqlite3.connect(f"file:{AI.COLLECTED}?mode=ro", uri=True)     # the feature counter describes the collected corpus
fa = db.execute("select count(*), count(distinct case_id), sum(span_ok) from field_assertions").fetchone()
fa_fields = dict(db.execute("select field, count(*) from field_assertions group by 1").fetchall())
d["12_data_checks"] = {
    "boilerplate_app_lists": {
        **fu["1_boilerplate"],
        "named_only_records_flagged_unread": fu["1_boilerplate"]["records_by_tier_linewrap"].get("named_only"),
        "status": "upper bound: every flagged record is counted as boilerplate",
    },
    "facebook_double_tag": {**{k: v for k, v in fu["2_facebook"].items() if k != "double_tag_case_ids"},
                            "double_tag_case_ids": fu["2_facebook"]["double_tag_case_ids"],
                            "cause": "the platform matcher tags 'Facebook' inside the phrase 'Facebook Messenger'"},
    "bicm_power": fu["3_bicm_power"],
    "yahoo_chat": {
        "conflict": "platform until 2012 vs unmonitored_communication ended 2018",
        "resolution": "both capability years are right for their product (public chat rooms closed Dec 14, 2012; Yahoo! Messenger private messages until Jul 17, 2018). "
                      "The platform-level end was wrong: the label also matches 'Yahoo! Messenger' (pattern_processing.py, the 'Yahoo Chat' platform pattern).",
        "fix": "capability_sources/messaging.yaml Yahoo Chat ended 2012 -> 2018; platforms.yaml regenerated (until 2012 -> 2018).",
    },
    "feature_count": {
        "unique_features_fresh": d["1_cover"]["NFeatures"],
        "field_assertions_rows": fa[0], "field_assertions_cases": fa[1], "field_assertions_span_ok": fa[2],
        "field_assertions_by_field": fa_fields,
        "breakdown": "see 1_cover.NFeatures_breakdown (generated from run/feature_count.py)",
    },
}
(OUT / "numbers.json").write_text(json.dumps(d, indent=1, default=str) + "\n")
print("merged", [k for k in d if k[:2] in ("10", "11", "12")])
