"""Build pilot outputs from coder drafts.

    python -m state_machines.coding.release_report <release> <case_id> [...]

For each case:
  coded/<coder>/<case>.json        compiled bundle per coder (no quote text)
  coded/agreed/<case>.json         agreed core: events both coders coded with the same
                                   action on overlapping passages; affordances and harms
                                   only where both coders annotated them; weaker status kept
  derived/<bundle>/<case>.<threshold>.json
  graphs/<case>.evidence.jsonld, graphs/<case>.trajectories.jsonld   (agreed core, INFERRED)
  agreement/<case>.json
and one REPORT.md with validation, SHACL, privacy, agreement and the audit comparison.

The agreed core is a mechanical intersection, not an adjudication: anything only one
coder found is listed as unresolved and left out of the agreed trajectories.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.evidence import evidence as E, vocab as V
from state_machines.trajectories import afh
from state_machines.trajectories.derive import derive, derived_json
from state_machines.graphs.emit import evidence_graph, serialize, trajectory_graph
from state_machines.coding.workflow import agreement, compile_draft, deny_list, write_bundle
from state_machines.graphs.shacl import validation_report
from state_machines.evidence.validate import identifier_hits, validate

DATA = E.REPO_ROOT / "state_machines" / "data"
CODERS = ("coder_A", "coder_B")
_RANK = {"DIRECT": 0, "INFERRED": 1, "UNSUPPORTED": 2, "CONTRADICTED": 3}


def _weaker(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def agreed_core(a: dict, b: dict, pairs) -> dict:
    """Coder A's bundle restricted to events B matched with the same action code."""
    eb = {e["event_id"]: e for e in b["events"]}
    keep = {}
    for ia, ib in pairs:
        x = next(e for e in a["events"] if e["event_id"] == ia)
        y = eb[ib]
        if x["action"] != y["action"]:
            continue
        e = copy.deepcopy(x)
        e["status"] = _weaker(x["status"], y["status"])
        yb = {o["affordance"]: o for o in y["affordances"]}
        e["affordances"] = []
        for o in x["affordances"]:
            if o["affordance"] in yb:
                o = copy.deepcopy(o)
                o["status"] = _weaker(o["status"], yb[o["affordance"]]["status"])
                if o["status"] == "DIRECT" and not any(s["status"] == "DIRECT" and s["facet"] == "feature" for s in o["support"]):
                    o["status"] = "INFERRED"
                e["affordances"].append(o)
        yc = {c["candidate"] for c in y.get("candidate_affordances", [])}
        e["candidate_affordances"] = [c for c in x.get("candidate_affordances", []) if c["candidate"] in yc]
        yh = {(h["harm"]) for h in y["harms"]}
        e["harms"] = [h for h in x["harms"] if h["harm"] in yh]
        ya = {(c["form"]) for c in y.get("access", [])}
        e["access"] = [c for c in x.get("access", []) if c["form"] in ya]
        e["review"] = {"status": "agreed", "coders": list(CODERS), "adjudicator": None,
                       "note": f"matched {ib} in coder_B; status is the weaker of the two"}
        keep[ia] = e
    core = copy.deepcopy(a)
    core["events"] = [keep[k] for k in sorted(keep)]
    a_to_b = dict(pairs)
    b_rel = {(r["type"], r["from_event"], r["to_event"]): r for r in b["relations"]}
    core["relations"] = []
    for r in a["relations"]:
        if r["from_event"] in keep and r["to_event"] in keep:
            other = b_rel.get((r["type"], a_to_b[r["from_event"]], a_to_b[r["to_event"]]))
            if other:  # both coders asserted this relation
                core["relations"].append(dict(r, status=_weaker(r["status"], other["status"])))
    core["tracks"] = [dict(t, event_ids=[x for x in t["event_ids"] if x in keep]) for t in a["tracks"]]
    core["tracks"] = [t for t in core["tracks"] if t["event_ids"]]
    used = {s["passage_id"] for e in core["events"] for group in (e["support"], *[x["support"] for k in ("affordances", "candidate_affordances", "access", "harms") for x in e.get(k, [])]) for s in group}
    used |= {pid for e in core["events"] for a in e["time"]["assertions"] for pid in a["passage_ids"]}
    used |= {pid for e in core["events"] for m in e.get("platform_mentions", []) for pid in m["passage_ids"]}
    used |= {pid for e in core["events"] for pid in (e.get("repetition") or {}).get("passage_ids", [])}
    used |= {s["passage_id"] for r in core["relations"] for s in r["support"]}
    core["passages"] = [p for p in a["passages"] if p["passage_id"] in used]
    core["coding"] = dict(a["coding"], coder_id="coder_agreed", method="agent",
                          note="mechanical intersection of coder_A and coder_B; not adjudicated")
    return core


def _scan_outputs(paths: List[Path], deny: List[str]) -> List[str]:
    hits = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        for word in deny:
            if re.search(r"\b" + re.escape(word) + r"\b", text):
                hits.append(f"{p.name}: deny-list word")
    return hits


def build_case(release: str, case_id: str, text_root: Optional[Path] = None) -> dict:
    out = DATA / release
    deny = deny_list(case_id, text_root)
    res: Dict[str, object] = {"case_id": case_id, "coders": {}}
    bundles = {}
    for coder in CODERS:
        draft_path = E.text_root(text_root) / case_id / "drafts" / coder / "draft.json"
        draft = json.loads(draft_path.read_text())
        bundle, quotes, problems = compile_draft(draft, text_root)
        findings = validate(bundle, text_root=text_root, deny_list=deny)
        write_bundle(bundle, quotes, out / "coded" / coder / f"{case_id}.json", text_root)
        bundles[coder] = bundle
        res["coders"][coder] = {
            "events": len(bundle["events"]), "passages": len(bundle["passages"]), "relations": len(bundle["relations"]),
            "tracks": len(bundle["tracks"]), "unplaced_quotes": len(problems),
            "errors": sorted({f.code for f in findings if f.severity == "error"}),
            "warnings": sum(f.severity == "warning" for f in findings),
            "unverified_passages": sum(p["verification"]["status"] != "VERIFIED" for p in bundle["passages"]),
        }
        for thr in ("DIRECT", "INFERRED"):
            p = out / "derived" / coder / f"{case_id}.{thr.lower()}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(derived_json(bundle, thr), encoding="utf-8")
    agree = agreement(bundles["coder_A"], bundles["coder_B"])
    (out / "agreement").mkdir(parents=True, exist_ok=True)
    (out / "agreement" / f"{case_id}.json").write_text(json.dumps(agree, indent=1, sort_keys=True) + "\n")
    core = agreed_core(bundles["coder_A"], bundles["coder_B"], agree["pairs"])
    core_findings = validate(core, text_root=text_root, deny_list=deny)
    core_path = out / "coded" / "agreed" / f"{case_id}.json"
    core_path.parent.mkdir(parents=True, exist_ok=True)
    core_path.write_text(json.dumps(core, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    derived = {}
    for thr in ("DIRECT", "INFERRED"):
        derived[thr] = derive(core, thr)
        p = out / "derived" / "agreed" / f"{case_id}.{thr.lower()}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(derived_json(core, thr), encoding="utf-8")
    ev = serialize(evidence_graph(core))
    tr = serialize(trajectory_graph(core, derived["INFERRED"]))
    (out / "graphs").mkdir(parents=True, exist_ok=True)
    gp = [out / "graphs" / f"{case_id}.evidence.jsonld", out / "graphs" / f"{case_id}.trajectories.jsonld"]
    gp[0].write_text(ev, encoding="utf-8")
    gp[1].write_text(tr, encoding="utf-8")
    shacl = validation_report(ev, tr)
    committed = [core_path, *gp, *(out / "coded" / c / f"{case_id}.json" for c in CODERS),
                 *(out / "derived").glob(f"*/{case_id}.*.json"), out / "agreement" / f"{case_id}.json"]
    res.update({
        "agreement": {k: v for k, v in agree.items() if k != "pairs"},
        "agreed": {"events": len(core["events"]), "relations": len(core["relations"]), "tracks": len(core["tracks"]),
                   "errors": sorted({f.code for f in core_findings if f.severity == "error"}),
                   "trajectories": {thr: [[s["action"] + ("{" + ",".join(s["affordances"]) + "}") for s in L["steps"]]
                                          for t in d["tracks"] for L in t["trajectories"]] for thr, d in derived.items()},
                   "unordered_pairs": sum(len(t["unordered_pairs"]) for t in derived["INFERRED"]["tracks"]),
                   "affordances": sorted(afh.case_affordances(derived["INFERRED"])),
                   "harms_h0": sorted(afh.case_harms(core, "INFERRED")),
                   "only_coder_A": sorted({e["event_id"] for e in bundles["coder_A"]["events"]} - {i for i, _ in agree["pairs"]}),
                   "only_coder_B": sorted({e["event_id"] for e in bundles["coder_B"]["events"]} - {j for _, j in agree["pairs"]})},
        "shacl": {k: shacl[k] for k in ("conformance", "violations", "upstream_defect_shapes", "applicable_skipped",
                                        "unwaived_applicable_skipped", "release_ok")}
                 | {"upstream_defect_violations": len(shacl["upstream_defect_violations"])},
        "privacy_hits": _scan_outputs(committed, deny),
        "audit_checks": audit_checks(case_id, bundles, core),
    })
    return res


def _events(bundle, action, statuses=("DIRECT", "INFERRED")):
    return [e for e in bundle["events"] if e["action"] == action and e["status"] in statuses]


def audit_checks(case_id: str, bundles: Dict[str, dict], core: dict) -> List[dict]:
    """Findings of the 2026-11-16 audit that were verified against the PDFs, as checks on fresh coding.

    Each check is evaluated on both coders' bundles; the agreed core is reported alongside.
    """
    checks = []

    def add(claim, fn):
        checks.append({"audit_finding": claim, **{k: fn(b) for k, b in {**bundles, "agreed": core}.items()}})

    if case_id == "enticement":
        add("no DIRECT retention/storage event (June t4 'Material Retained' unsupported)",
            lambda b: not _events(b, "STORE_MATERIAL", ("DIRECT",)))
        add("two separate in-person meetings coded (June merged them)",
            lambda b: len(_events(b, "IN_PERSON_SEXUAL_ABUSE")) + len(_events(b, "TRAVEL_TO_MEET")) >= 2)
        add("post-charge contact coded as obstruction or recontact",
            lambda b: bool(_events(b, "OBSTRUCT_OR_TAMPER") or _events(b, "RECONTACT")))
    if case_id == "texas_ag_2019_013":
        def threat_not_after_production(b):
            prod = [e for e in b["events"] if e["action"] in ("SOLICIT_IMAGERY", "RECEIVE_SELF_GENERATED", "DIRECT_CONDUCT")]
            thr = _events(b, "THREATEN_EXPOSURE")
            bad = [r for r in b["relations"] if r["type"] in V.ORDER_RELATIONS and r["status"] == "DIRECT"
                   and r["from_event"] in {e["event_id"] for e in prod} and r["to_event"] in {e["event_id"] for e in thr}]
            return bool(thr) and not bad
        add("threat coded, and not DIRECTLY ordered after production (count windows overlap)", threat_not_after_production)
    if case_id == "svicac_2022_009":
        add("no DIRECT channel migration (source describes a rename)", lambda b: not _events(b, "MOVE_CHANNEL", ("DIRECT",)))
        add("no in-person abuse invented for a distribution case", lambda b: not _events(b, "IN_PERSON_SEXUAL_ABUSE"))
    if case_id == "ncis_2023_001":
        add("no harm coded against the undercover persona",
            lambda b: all(h["victim_kind"] != "undercover_persona"
                          for e in b["events"] for h in e["harms"]))
        add("no hands-on abuse coded (attempt-only sting)", lambda b: not _events(b, "IN_PERSON_SEXUAL_ABUSE"))
        add("interdiction or arrest coded as law enforcement, not offender conduct",
            lambda b: bool(_events(b, "LE_INTERDICT") or _events(b, "LE_ARREST")))
    if case_id == "anchorage_pd_2022_006":
        add("victims kept on separate tracks (June merged them)",
            lambda b: sum(t["kind"] == "victim" for t in b["tracks"]) >= 2)
    return checks


def report(release: str, results: List[dict]) -> str:
    L = [f"# Pilot report: {release}", "",
         "SHACL is run against the shape set in `trajectories/shacl.py`: UCO/CASE 1.5.0, legalproc, gUFO, oa, all 97 files of CAC 3.1.0 "
         "as published, and the caselinker-trajectory extension. `full` means every applicable constraint ran and passed; `partial` means "
         "applicable upstream constraints could not run as published (listed; they block the release check unless waived in "
         "`trajectories/shacl_waivers.json`); `fails` means a constraint that ran was violated. Violations from upstream shapes known to reject "
         "valid UCO data (`trajectories/shacl_upstream_defects.json`) are counted apart from violations of our own output; they still mean `fails`.", "",
         "Coders: two agent coders per case (claude-opus-5-5), blind to the June machines, `_facts.txt`, the audit and each other. "
         "They are **not** independent human reviewers. The agreed core is a mechanical intersection of the two codings, not an adjudication.", ""]
    L += ["## Summary", "", "| case | coder A events | coder B events | matched | action κ | agreed events | agreed trajectories (INFERRED) | SHACL conformance | privacy hits | errors |",
          "|---|---:|---:|---:|---:|---:|---:|---|---:|---|"]
    for r in results:
        a, ag = r["agreement"], r["agreed"]
        errs = sorted(set(r["coders"]["coder_A"]["errors"]) | set(r["coders"]["coder_B"]["errors"]) | set(ag["errors"]))
        L.append(f"| `{r['case_id']}` | {a['events']['coder_a']} | {a['events']['coder_b']} | {a['events']['matched']} | "
                 f"{a['action_code']['kappa']} | {ag['events']} | {len(ag['trajectories']['INFERRED'])} | "
                 f"{r['shacl']['conformance']} | {len(r['privacy_hits'])} | {', '.join(errs) or 'none'} |")
    for r in results:
        a, ag = r["agreement"], r["agreed"]
        L += ["", f"## `{r['case_id']}`", ""]
        for coder, c in r["coders"].items():
            L.append(f"- {coder}: {c['events']} events, {c['relations']} relations, {c['tracks']} tracks, {c['passages']} passages "
                     f"({c['unverified_passages']} unverified), unplaced quotes {c['unplaced_quotes']}, errors {c['errors'] or 'none'}")
        L.append(f"- event F1 {a['events']['f1']}; action exact {a['action_code']['exact']}/{a['action_code']['of']} (κ {a['action_code']['kappa']}); "
                 f"harm exact {a['harm_set']['exact']}/{a['harm_set']['of']}; affordance-set Jaccard {a['affordance_set_jaccard_mean']}; "
                 f"order on matched pairs: A {a['order_on_matched_pairs']['a_ordered']}, B {a['order_on_matched_pairs']['b_ordered']}, both {a['order_on_matched_pairs']['both']}")
        pc = ", ".join(f"{o} {v['both_yes']}/{max(v['a_yes'], v['b_yes'])}" for o, v in a["affordance_per_class"].items() if v["a_yes"] or v["b_yes"])
        L.append(f"- affordance agreement (both/either-max): {pc or 'none annotated'}")
        L.append(f"- agreed core: {ag['events']} events, Aff = {ag['affordances'] or '∅'}, H0 harms = {ag['harms_h0'] or '∅'}, "
                 f"unordered pairs {ag['unordered_pairs']}; unresolved: {len(ag['only_coder_A'])} events only A, {len(ag['only_coder_B'])} only B")
        L.append("- agreed trajectories (INFERRED threshold; action{O_i}):")
        for i, t in enumerate(ag["trajectories"]["INFERRED"], 1):
            L.append(f"  {i}. " + " → ".join(t))
        L.append(f"- SHACL: {r['shacl']['conformance']}; applicable upstream constraints not evaluated: "
                 f"{len(r['shacl']['applicable_skipped'])}; release check {'passes' if r['shacl']['release_ok'] else 'FAILS'}")
        if r["shacl"]["violations"]:
            L.append("- SHACL violations of our output: " + "; ".join(r["shacl"]["violations"][:5]))
        else:
            L.append("- SHACL violations of our output: none")
        if r["shacl"]["upstream_defect_violations"]:
            L.append(f"- SHACL violations from known upstream defects: {r['shacl']['upstream_defect_violations']} "
                     f"({', '.join(s.rsplit('#', 1)[-1] for s in r['shacl']['upstream_defect_shapes'])})")
        if r["audit_checks"]:
            L.append("- audit comparison (verified audit findings, checked on fresh coding):")
            for c in r["audit_checks"]:
                L.append(f"  - {c['audit_finding']}: coder_A {'yes' if c['coder_A'] else 'NO'}, coder_B {'yes' if c['coder_B'] else 'NO'}, agreed {'yes' if c['agreed'] else 'NO'}")
    return "\n".join(L) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    release, cases = argv[0], argv[1:]
    results = [build_case(release, c) for c in cases]
    (DATA / release / "pilot_summary.json").write_text(json.dumps(results, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    (DATA / release / "REPORT.md").write_text(report(release, results), encoding="utf-8")
    print(DATA / release / "REPORT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
