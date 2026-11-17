"""The /lifecycle payload: documented event graphs and their derived views, for display.

Built from one PACER release folder (manifest, coded bundles, derived views). It carries
codes, roles, statuses, dates and document/page provenance. It carries no quotes, no
coder-written descriptions, and no names: participants appear as P1, P2, ...

Which release is shown: ``CASELINKER_PACER_RELEASE`` (a release id under
state_machines/data/ or a path to a release folder); otherwise the newest adjudicated
release under state_machines/data/; otherwise an empty payload.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.evidence import vocab as V

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "state_machines" / "data"
STANDING_RANK = {s: i for i, s in enumerate((
    "PROCEDURAL", "ADVOCACY", "ALLEGATION", "SWORN_AFFIDAVIT", "COURT_RECORD", "ADMITTED",
    "ADMITTED_UNDER_OATH", "JUDICIAL_FINDING", "VERDICT_ELEMENT"))}


def release_dir() -> Optional[Path]:
    env = os.environ.get("CASELINKER_PACER_RELEASE", "").strip()
    if env:
        p = Path(env)
        p = p if p.is_absolute() else (DATA / env if (DATA / env).is_dir() else REPO / env)
        return p if (p / "manifest.json").is_file() else None
    candidates = []
    for m in sorted(DATA.glob("*/manifest.json")):
        doc = json.loads(m.read_text(encoding="utf-8"))
        if doc.get("adjudicated"):
            candidates.append(m.parent)
    return candidates[-1] if candidates else None


def _label(code: str) -> str:
    return code.replace("RESP_", "").replace("LE_", "").replace("PROC_", "").replace("_", " ").lower()


def _event(e: dict, passages: Dict[str, dict], docs: Dict[str, dict]) -> dict:
    action_passages = [passages[s["passage_id"]] for s in e["support"] if s["facet"] == "action"]
    standing = max((p["source_status"] for p in action_passages), key=lambda s: STANDING_RANK.get(s, -1), default=None)
    prov = sorted({(docs[p["doc_id"]]["doc_type"], p["pdf_page"], p["source_status"], p["verification"]["status"])
                   for s in e["support"] for p in [passages[s["passage_id"]]]})
    return {
        "id": e["event_id"], "action": e["action"], "label": _label(e["action"]),
        "family": V.FAMILY_OF[e["action"]], "status": e["status"], "outcome": e["outcome"],
        "standing": standing, "review": e["review"]["status"],
        "actor": e["actor"], "co_actors": e.get("co_actors", []), "targets": e.get("targets", []),
        "unresolved": [x["participant_ref"] for x in e.get("unresolved_participants", [])],
        "time": [{k: a[k] for k in ("earliest", "latest", "precision", "basis", "status")} for a in e["time"]["assertions"]],
        "time_conflict": bool(e["time"].get("conflict_flagged")),
        "affordances": [{"class": a["affordance"], "status": a["status"], "basis": a["basis"]} for a in e.get("affordances", [])],
        "harms": [{"code": h["harm"], "h0": V.HARM_H0[h["harm"]], "victim_kind": h["victim_kind"], "status": h["status"]}
                  for h in e.get("harms", [])],
        "platforms": [{"key": i["platform_key"], "mode": i["mode"], "audience": i["audience"], "status": i["status"]}
                      for i in e.get("platform_interactions", [])],
        "mentions": sorted({m["platform_surface"] for m in e.get("platform_mentions", [])}),
        "channels": [c["channel"] for c in e.get("channels", [])],
        "provenance": [{"doc_type": d, "page": pg, "standing": st, "verification": v} for d, pg, st, v in prov],
    }


def case_payload(bundle: dict, derived: Dict[str, dict]) -> dict:
    passages = {p["passage_id"]: p for p in bundle["passages"]}
    docs = {d["doc_id"]: d for d in bundle["documents"]}
    events = {e["event_id"]: _event(e, passages, docs) for e in bundle["events"]}
    relations = [{"from": r["from_event"], "to": r["to_event"], "type": r["type"], "status": r["status"], "basis": r["basis"]}
                 for r in bundle["relations"]]
    tracks = []
    for t in bundle["tracks"]:
        views = {}
        for thr, d in derived.items():
            dt = next((x for x in d["tracks"] if x["track_id"] == t["track_id"]), None)
            if dt:
                views[thr] = {"chains": [[s["event_id"] for s in L["steps"]] for L in dt["trajectories"]],
                              "aff": sorted({o for L in dt["trajectories"] for s in L["steps"] for o in s["affordances"]}),
                              "unordered_pairs": len(dt["unordered_pairs"]), "truncated": dt["chains_truncated"],
                              "date_order": [list(p) for p in _date_pairs(bundle, thr, set(t["event_ids"]))]}
        tracks.append({"id": t["track_id"], "kind": t["kind"], "anchor": t.get("anchor_ref"),
                       "events": sorted(t["event_ids"]), "views": views})
    return {
        "case_id": bundle["case_id"],
        "documents": sorted(({"doc_type": d["doc_type"], "pages": d["page_count"],
                              "default_standing": V.DOC_TYPES[d["doc_type"]][0]} for d in bundle["documents"]),
                            key=lambda d: d["doc_type"]),
        "participants": [{"ref": p["participant_ref"], "kind": p["kind"],
                          "legal_status": sorted({ls["status"] for ls in p.get("legal_status", [])}),
                          **({"count": {k: p["count"].get(k) for k in ("min", "max", "stated")}} if p.get("count") else {})}
                         for p in bundle["participants"]],
        "events": events, "relations": relations, "tracks": tracks,
        "summary": {"events": len(events), "offender_events": sum(e["family"] == "offender" for e in events.values()),
                    "relations": len(relations),
                    "possible_same_act": sum(r["type"] == "SAME_ACT" and r["status"] == "INFERRED" for r in relations),
                    "time_conflicts": sum(e["time_conflict"] for e in events.values()),
                    "unresolved_roles": sum(bool(e["unresolved"]) for e in events.values())},
    }


def _date_pairs(bundle: dict, threshold: str, ids: set) -> List[tuple]:
    from state_machines.trajectories.derive import date_order
    return sorted((a, b) for a, b in date_order(bundle, V.ADMISSIBLE[threshold]) if a in ids and b in ids)


def build_payload(root: Optional[Path] = None) -> dict:
    root = root or release_dir()
    if root is None:
        return {"release": None, "cases": []}
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    cases = []
    for c in manifest["cases"]:
        bundle = json.loads((root / "cases" / f"{c['case_id']}.json").read_text(encoding="utf-8"))
        derived = {thr: json.loads((root / "derived" / f"{c['case_id']}.{thr.lower()}.json").read_text(encoding="utf-8"))
                   for thr in ("DIRECT", "INFERRED")}
        cp = case_payload(bundle, derived)
        cp["shacl"] = c["shacl"]["conformance"]
        cases.append(cp)
    return {"release": {"id": manifest["release_id"], "adjudicated": manifest["adjudicated"],
                        "schema_version": manifest["schema_version"], "codebook_version": manifest["codebook_version"],
                        "derivation_rule": manifest["derivation_rule"], "cases": len(cases)},
            "cases": cases}
