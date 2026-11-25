"""Collect the co-occurrence (BiCM) runs into cooccurrence.json. Run with the requirements-afh.txt venv after
build_variants.py and bicm_run.py."""
import json
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir() / "cooc"
OUT.mkdir(parents=True, exist_ok=True)
src = (HERE / "bicm_run.py").read_text().split("res = {s: run(s)")[0]
ns = {"__file__": str(HERE / "bicm_run.py")}
exec(src, ns)
WATCH = [["Facebook", "Facebook Messenger"], ["Instagram", "TikTok"], ["Discord", "TikTok"], ["Discord", "Twitter / X"],
         ["TikTok", "Twitter / X"], ["Discord", "Fortnite"]]
out = {}
M = {k: json.loads((OUT / f"matrix_{k}.json").read_text()) for k in ("stated_clean", "all_clean")}
for s, what in (("stated", "stated tier, rows closed at `until`"), ("all", "all tiers"),
                ("stated_clean", f"stated tier without the {M['stated_clean']['removed_edges']} boilerplate-only edges ({M['stated_clean']['boilerplate_rule']})"),
                ("all_clean", f"all tiers without the {M['all_clean']['removed_edges']} boilerplate-only edges ({M['all_clean']['boilerplate_rule']})")):
    r = ns["run"](s)
    out[s] = {"what": what, "cases": r["cases"], "platforms": r["platforms"], "edges": r["edges"],
              "pairs_tested": r["pairs_tested"], "pairs_with_cooccurrence": r["pairs_with_cooccurrence"],
              "fit_degree_error": r["fit_degree_error"], "package_crosscheck": r["package_crosscheck"],
              "significant_n": len(r["significant"]),
              "significant_flagged_n": sum(1 for x in r["significant"] if x["flags"]),
              "significant": [{k: x[k] for k in ("pair", "observed", "expected", "p", "flags", "sources", "classes")} for x in r["significant"]],
              "watch": [{k: x[k] for k in ("pair", "observed", "expected", "p", "significant_bh05")}
                        for x in r["all_pairs"] if sorted(x["pair"]) in [sorted(w) for w in WATCH]],
              "mechanical_same_platform_class_pairs": r["same_platform_class_pairs_mechanical_untested"]}
sig = lambda k: {tuple(sorted(x["pair"])) for x in out[k]["significant"]}  # noqa: E731
out["robust_stated_and_all"] = sorted(list(p) for p in sig("stated") & sig("all"))
out["robust_after_fixes"] = sorted(list(p) for p in sig("stated_clean") & sig("all_clean"))
out["afh_inputs"] = AI.inputs_label(OUT.parent)
(OUT / "cooccurrence.json").write_text(json.dumps(out, indent=1) + "\n")
print({k: (v["significant_n"] if isinstance(v, dict) and "significant_n" in v else "…") for k, v in out.items()})
