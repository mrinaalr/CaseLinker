"""BiCM validated projection of Q1 cases x named platforms onto platforms (section 10).

  <venv with requirements-afh.txt>/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/cooc/bicm_run.py

Model: Bipartite Configuration Model (Saracco et al. 2015), maximum-entropy null that preserves the
expected degree of every case and every platform; fitted with `bicm` (solve_tool).
For platforms a, b: observed V_ab = #cases naming both; under BiCM V_ab is Poisson-binomial with
success probabilities p_ca * p_cb over cases c; expected = sum_c p_ca p_cb; p = P(V_ab >= observed),
computed exactly (dynamic programming). Benjamini-Hochberg over every platform pair, q = 0.05.
Cross-check: the package's own poibin p-values (compute_projection(rows=False, approx_method='poibin')).
"""
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from bicm import BipartiteGraph

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir() / "cooc"
OUT.mkdir(parents=True, exist_ok=True)
ALPHA = 0.05


def poibin_sf(probs: np.ndarray, k: int) -> float:
    """P(sum of independent Bernoulli(probs) >= k), exact."""
    if k <= 0:
        return 1.0
    dist = np.zeros(k + 1)
    dist[0] = 1.0
    for p in probs:
        if p <= 0:
            continue
        nxt = dist * (1 - p)
        nxt[1:] += dist[:-1] * p
        nxt[k] += dist[k] * p          # mass at >= k stays at >= k
        dist = nxt
    return float(min(1.0, max(0.0, dist[k])))


def bh(pvals: list, alpha: float) -> list:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh_rank = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= alpha * rank / m:
            thresh_rank = rank
    keep = set(order[:thresh_rank])
    return [i in keep for i in range(m)]


def run(edge_set: str) -> dict:
    m = json.loads((OUT / f"matrix_{edge_set}.json").read_text())
    rows, cols = m["rows"], m["cols"]
    ri, ci = {r: i for i, r in enumerate(rows)}, {c: j for j, c in enumerate(cols)}
    A = np.zeros((len(rows), len(cols)), dtype=int)
    for r, c in m["edges"]:
        A[ri[r], ci[c]] = 1
    g = BipartiteGraph(biadjacency=A)
    g.solve_tool(print_error=False)
    P = g.get_bicm_matrix()
    deg_err = {"rows_max_abs": float(np.max(np.abs(P.sum(1) - A.sum(1)))),
               "cols_max_abs": float(np.max(np.abs(P.sum(0) - A.sum(0))))}
    pk = None
    try:
        g.compute_projection(rows=False, alpha=ALPHA, approx_method="poibin", threads_num=1, progress_bar=False)
        pk = g.get_projected_pvals_mat()
    except Exception as exc:  # the cross-check is optional; the exact p-values below are the result
        pk = f"package projection failed: {exc!r}"
    V = A.T @ A
    pairs = []
    for a, b in itertools.combinations(range(len(cols)), 2):
        probs = P[:, a] * P[:, b]
        obs = int(V[a, b])
        cases = [rows[i] for i in np.nonzero(A[:, a] & A[:, b])[0]]
        src = Counter(m["case_source"][c] for c in cases)
        pairs.append({
            "pair": [cols[a], cols[b]], "observed": obs, "expected": round(float(probs.sum()), 3),
            "p": poibin_sf(probs, obs),
            "p_package": (None if not isinstance(pk, np.ndarray) else float(pk[a, b])),
            "sources": dict(src.most_common()),
            "flags": [f for f, cond in (("fewer_than_5_cases", obs < 5),
                                        ("one_source", obs > 0 and len(src) == 1)) if cond],
        })
    sig = bh([x["p"] for x in pairs], ALPHA)
    for x, s in zip(pairs, sig):
        x["significant_bh05"] = bool(s)
    cls = m["platform_default_on_classes"]
    for x in pairs:
        a, b = x["pair"]
        x["classes"] = {a: cls[a], b: cls[b]}
        x["class_pairs_across"] = sorted({tuple(sorted((ca, cb))) for ca in cls[a] for cb in cls[b]})
    mech = {p: sorted(itertools.combinations(cls[p], 2)) for p in cols}
    agree = None
    if isinstance(pk, np.ndarray):
        diffs = [abs(x["p"] - x["p_package"]) for x in pairs]
        agree = {"max_abs_diff": max(diffs), "pairs": len(diffs)}
    return {
        "edge_set": edge_set, "cases": len(rows), "platforms": len(cols), "edges": int(A.sum()),
        "pairs_tested": len(pairs), "pairs_with_cooccurrence": sum(1 for x in pairs if x["observed"] > 0),
        "fit_degree_error": deg_err, "package_crosscheck": agree if agree else (pk if isinstance(pk, str) else None),
        "significant": sorted([x for x in pairs if x["significant_bh05"]], key=lambda x: x["p"]),
        "all_pairs": pairs,
        "same_platform_class_pairs_mechanical_untested": {p: [list(t) for t in v] for p, v in mech.items() if v},
    }


res = {s: run(s) for s in ("stated", "all")}
st = {tuple(x["pair"]) for x in res["stated"]["significant"]}
al = {tuple(x["pair"]) for x in res["all"]["significant"]}
res["robust_both"] = sorted(list(p) for p in st & al)
res["stated_only"] = sorted(list(p) for p in st - al)
res["all_only"] = sorted(list(p) for p in al - st)
res["afh_inputs"] = AI.inputs_label(OUT.parent)
(OUT / "bicm_results.json").write_text(json.dumps(res, indent=1) + "\n")
for s in ("stated", "all"):
    r = res[s]
    print(s, {k: r[k] for k in ("cases", "platforms", "edges", "pairs_tested", "pairs_with_cooccurrence", "fit_degree_error", "package_crosscheck")},
          "significant:", len(r["significant"]))
print("robust (both):", len(res["robust_both"]), "| stated only:", len(res["stated_only"]), "| all only:", len(res["all_only"]))
