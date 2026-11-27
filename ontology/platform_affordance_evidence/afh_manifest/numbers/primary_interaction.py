"""Primary-interaction sensitivity of the AfH 2.0 verdicts (numbers.md section 2), level-A prevalence and Table 1.

  DATABASE_URL='' REDIS_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/primary_interaction.py

The registry-validity audit of 2026-11-26 (author review, not applied to the registry) judged which default_on rows
depart from the primary-interaction rule (README, Operational definitions). This script is that audit's rerun,
moved here unchanged so it runs from the repo: the overrides below are the audit's judgments, verbatim; only the
input and output paths changed (inputs: numbers/build/records.csv, config/platforms.yaml through afhq1, and
primary_interaction/platforms_top12.txt; outputs: primary_interaction/*.csv). Run by run_all.sh after run_afh.py.

  SOURCED  1 override with a dated source (Facebook contact_discovery, default Public until May 2014)
  ALL      SOURCED plus 13 unverified rule breaks (14 overrides). Availability windows are unchanged.
"""
import csv, json, sys, os
from collections import defaultdict, Counter
A = "ontology/platform_affordance_evidence/afh_manifest"; sys.path[:0] = [A, "ontology/platform_affordance_evidence"]
from afhq1 import pipeline as pl, harm_release as hr
import launch_years as LY
reg = pl.platform_registry(); cb = pl.Codebook.load(); key = {c: s["capability"] for c, s in cb.classes.items()}
launch = {r["platform_id"]: r["launch_year"] for r in LY.load()}
# overrides: (platform, capability) -> function(year) -> default_on (None = use registry). Availability window unchanged.
FB_CD = lambda y: y <= 2014                      # sourced: new users' first-post default Public -> Friends, May 2014
SOURCED = {("Facebook", "contact_discovery"): FB_CD}
ALL = dict(SOURCED)
for p in ["Dropbox", "Google Drive", "Instagram", "Twitter / X", "TikTok", "Tumblr", "YouTube", "MeWe", "Grindr"]:
    ALL[(p, "anonymity")] = lambda y: True
for p in ["Reddit", "Tumblr", "Whisper"]:
    ALL[(p, "contact_discovery")] = lambda y: True
ALL[("Snapchat", "contact_discovery")] = lambda y: False
def on_at(info, k, y, ov):
    if not hr._on_at(info, k, y) and (info.label, k) not in ov: return False
    s = info.capabilities.get(k); e = (info.cap_meta.get(k) or {}).get("ended")
    if s is None or y is None or y < s or (e is not None and y > e): return False
    f = ov.get((info.label, k)); return f(y) if f else bool(info.default_on.get(k))
recs_all = list(csv.DictReader(open(f"{A}/numbers/build/records.csv"))); recs = [r for r in recs_all if r["tier_linewrap"] == "stated"]
def run(ov):
    cell = defaultdict(lambda: defaultdict(set)); coded = defaultdict(set)
    for r in recs:
        p = r["platform"]; info = pl.platform_info(p, reg); y = int(r["pub_year"]) if r["pub_year"] else None
        on = [c for c in hr.TEST_CLASSES if on_at(info, key[c], y, ov)]
        g = LY.generation(launch[p]) if launch.get(p) is not None else None; e = hr._publication_era(y)
        if g and on: coded[("cohort", g)].add(r["case_id"])
        if e and on: coded[("era", e)].add(r["case_id"])
        for c in on:
            if g: cell[(c, "cohort")][g].add(r["case_id"])
            if e: cell[(c, "era")][e].add(r["case_id"])
    V = {}
    for kind, bins in (("cohort", hr.GENERATIONS), ("era", hr.PUBLICATION_ERAS)):
        q = [b for b in bins if len(coded[(kind, b)]) >= hr.N_MIN]
        for c in hr.TEST_CLASSES:
            n = {b: len(cell[(c, kind)][b]) for b in bins}; pres = [b for b in q if n[b] >= hr.K_PRESENT]
            v = ("untestable" if len(q) < 2 else "first in last qualifying bin; untestable" if pres and pres[0] == q[-1] else "no" if len(pres) < 2
                 else ("recurs" if kind == "cohort" else "persists") if all(b in pres for b in q if bins.index(b) > bins.index(pres[0])) else "no")
            V[(c, kind)] = (v, n, q)
    prevA = Counter()
    for r in recs_all:
        info = pl.platform_info(r["platform"], reg); y = int(r["pub_year"]) if r["pub_year"] else None
        for c in hr.TEST_CLASSES: prevA[c] += on_at(info, key[c], y, ov)
    return V, prevA
V0, P0 = run({}); VS, PS = run(SOURCED); VA, PA = run(ALL)
rows = []
for k in sorted(V0):
    rows.append({"class": k[0], "test": k[1], "current": V0[k][0], "sourced_only": VS[k][0], "all_rule_breaks_unverified": VA[k][0],
                 "cells_current": json.dumps(V0[k][1]), "cells_sourced_only": json.dumps(VS[k][1]), "cells_all": json.dumps(VA[k][1])})
O = "ontology/platform_affordance_evidence/afh_manifest/numbers/primary_interaction"
with open(f"{O}/primary_interaction_rerun_verdicts.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
with open(f"{O}/primary_interaction_rerun_prevalence_A.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["class", "level_A_current", "level_A_sourced_only", "level_A_all_rule_breaks"]); [w.writerow([c, P0[c], PS[c], PA[c]]) for c in hr.TEST_CLASSES]
for r in rows: print(r["class"], r["test"], "|", r["current"], "|", r["sourced_only"], "|", r["all_rule_breaks_unverified"], "| cells", r["cells_current"], "->S", r["cells_sourced_only"], "->A", r["cells_all"])
print({c: (P0[c], PS[c], PA[c]) for c in hr.TEST_CLASSES})
# Table 1: majority status over stated cases, top 12
top = [l.strip() for l in open(f"{O}/platforms_top12.txt") if l.strip() and not l.startswith("#")]
yrs = defaultdict(list)
for r in recs:
    if r["pub_year"]: yrs[r["platform"]].append(int(r["pub_year"]))
CL = ["anonymity", "ephemerality", "contact_discovery", "unmonitored_communication", "distribution_infrastructure", "generative_synthesis"]
def sym(p, k, y, ov):
    info = pl.platform_info(p, reg); s = info.capabilities.get(k); e = (info.cap_meta.get(k) or {}).get("ended")
    if s is None or y < s or (e is not None and y > e): return "blank"
    return "●" if on_at(info, k, y, ov) else "○"
t = []
for p in top:
    for k in CL:
        a, b, c = (Counter(sym(p, k, y, ov) for y in yrs[p]).most_common(1)[0][0] for ov in ({}, SOURCED, ALL))
        if a != b or a != c: t.append({"platform": p, "class": k, "current": a, "sourced_only": b, "all_rule_breaks": c})
with open(f"{O}/primary_interaction_table1_changes.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["platform", "class", "current", "sourced_only", "all_rule_breaks"]); w.writeheader(); w.writerows(t)
print("Table 1 cell changes:", t)
