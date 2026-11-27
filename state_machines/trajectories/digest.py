"""The analysis frame for one release: trajectories, stated platforms, registry capabilities, researcher use.

Reads the committed release and a capability registry. Writes a digest beside which a person
can judge use. Does not modify the release, and does not copy a registry capability into O_i.

    python -m state_machines.trajectories.digest pacer-v1 --registry <capability_sources> --out <dir>
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.graphs.release import DATA
from state_machines.trajectories.affordances import Registry, event_levels, load
from state_machines.trajectories.claims import claims
from state_machines.trajectories.derive import event_spans
from state_machines.trajectories.use_notes import by_step, load as load_notes, validate

ADMISSIBLE = ("DIRECT", "INFERRED")
_CLAIM = {
    "stated_platform_means": "a platform the act's coding records it as going through (platform_interactions, taken from coder A's coding of an act both coders agreed on; coder B's platform is not compared). It is not the observation layer's stated-means tie",
    "candidate_capabilities": "the registry says the platform offered a capability relevant to this kind of act; this is availability, not use",
    "available_on_platform": "the platform offered this capability, and the codebook does not treat it as relevant to this kind of act",
    "documented_feature_use": "the act's own sentence states the feature as the means; this is O_i",
    "how_used": "a person's judgment, stored separately, and never copied into O_i",
}


def _date(event: dict) -> Optional[dict]:
    spans = event_spans(event, ADMISSIBLE)
    if not spans:
        return None
    return {"earliest": min(s for s, _ in spans).isoformat(), "latest": max(e for _, e in spans).isoformat()}


def _for_levels(step: dict, life: Optional[dict]) -> dict:
    """The derived step plus the lifecycle's mode and date, which the derived file does not keep."""
    plats = (life or {}).get("platforms") or []
    if plats:
        interactions = [{"platform_key": p["key"], "mode": p["mode"], "status": p["status"],
                         "configuration": p.get("configuration") or []} for p in plats]
    else:
        interactions = [{"platform_key": name, "mode": "through", "status": "DIRECT", "configuration": []}
                        for name in step.get("platforms") or []]
    time = (life or {}).get("time") or []
    return {"action": step["action"], "platform_interactions": interactions,
            "time": {"assertions": time if isinstance(time, list) else []}}


def _entries(rows: List[dict]) -> List[dict]:
    return [{"platform": r["platform"], "affordance": r["affordance"], "availability": r["availability"]} for r in rows]


def step_view(step: dict, life: Optional[dict], registry: Registry, notes: List[dict]) -> dict:
    """One trajectory step, with the three machine claims and any researcher notes beside them."""
    event = _for_levels(step, life)
    levels = event_levels(event, registry, ADMISSIBLE)
    relevant = _entries(levels["action_relevant"])
    relevant_names = {r["affordance"] for r in relevant}
    offered = [e for e in _entries(levels["available"]) if e["affordance"] not in relevant_names]
    documented = list(step.get("affordances") or [])
    view = {
        "event_id": step["event_id"],
        "action": step["action"],
        "label": (life or {}).get("label") or step["action"].replace("_", " ").lower(),
        "date": _date(event),
        "stated_platform_means": list(step.get("platforms") or []),
        "candidate_capabilities": relevant,
        "available_on_platform": offered,
        "documented_feature_use": documented,
        "unmatched_platforms": levels["unmatched_platforms"],
        "how_used": list(notes),
    }
    split = claims({
        "platforms": view["stated_platform_means"],
        "action_relevant_affordances": sorted(relevant_names),
        "available_affordances": sorted({e["affordance"] for e in offered} | relevant_names),
        "affordances": documented,
    })
    if split["documented_feature_use"] != documented or split["how_used"] is not None:
        raise RuntimeError("the digest tried to treat a capability as documented use")
    return view


def _phrases(observations: dict) -> List[dict]:
    out = []
    for o in observations.get("observations") or []:
        if o.get("kind") != "feature":
            continue
        out.append({"observation_id": o["observation_id"], "feature_class": o["feature_class"],
                    "feature_term": o["feature_term"], "doc_id": o.get("doc_id"), "pdf_page": o.get("pdf_page")})
    return out


def case_digest(case: dict, derived: dict, observations: dict, registry: Registry, notes: Dict) -> dict:
    events = case["events"]
    phrases = _phrases(observations)
    tracks = []
    for track in derived["tracks"]:
        chains = []
        for traj in track["trajectories"]:
            steps = []
            for step in traj["steps"]:
                life = events.get(step["event_id"])
                steps.append(step_view(step, life, registry, notes.get((case["case_id"], step["event_id"]), [])))
            chains.append({"trajectory_id": traj["trajectory_id"], "steps": steps})
        tracks.append({"track_id": track["track_id"], "kind": track["kind"], "chains": chains,
                       "unordered_pairs": track.get("unordered_pairs") or []})
    return {"case_id": case["case_id"], "tracks": tracks, "stated_feature_phrases": phrases}


def _offered(cases: List[dict]) -> Dict:
    """Classes a note is allowed to name: on the step, or a phrase stated in the case."""
    offered = {}
    for case in cases:
        phrases = {p["feature_class"] for p in case["stated_feature_phrases"]}
        for track in case["tracks"]:
            for chain in track["chains"]:
                for step in chain["steps"]:
                    classes = {e["affordance"] for e in step["candidate_capabilities"]}
                    classes |= {e["affordance"] for e in step["available_on_platform"]}
                    classes |= set(step["documented_feature_use"])
                    classes |= phrases
                    offered[(case["case_id"], step["event_id"])] = classes
    return offered


def release_digest(root: Path, registry: Registry, notes_path: Optional[Path] = None) -> dict:
    """Build the digest. Notes are checked and attached. The release files are only read."""
    life = json.loads((root / "lifecycle.json").read_text(encoding="utf-8"))
    cases = []
    for case in life["cases"]:
        derived = json.loads((root / "derived" / f"{case['case_id']}.inferred.json").read_text(encoding="utf-8"))
        obs_path = root / "observations" / f"{case['case_id']}.json"
        observations = json.loads(obs_path.read_text(encoding="utf-8")) if obs_path.is_file() else {"observations": []}
        cases.append(case_digest(case, derived, observations, registry, {}))
    raw = load_notes(notes_path) if notes_path else []
    clean = validate(raw, _offered(cases))
    grouped = by_step(clean)
    if grouped:
        cases = []
        for case in life["cases"]:
            derived = json.loads((root / "derived" / f"{case['case_id']}.inferred.json").read_text(encoding="utf-8"))
            obs_path = root / "observations" / f"{case['case_id']}.json"
            observations = json.loads(obs_path.read_text(encoding="utf-8")) if obs_path.is_file() else {"observations": []}
            cases.append(case_digest(case, derived, observations, registry, grouped))
    return {"release": root.name, "claims": _CLAIM, "use_notes": len(clean), "cases": cases}


def render(digest: dict) -> str:
    """One readable page of the 30 cases. Feature phrases are terms, not quotations."""
    lines = [
        f"# {digest['release']}: trajectories, capabilities, and use",
        "",
        "Chains are the documented partial order. An undated step is not given a place by guesswork.",
        "A candidate capability is what the platform offered for this kind of act. It is not use.",
        "Documented use is empty unless the sentence states the feature as the means.",
        "A line under `how used` is a person's note. None are filled until that file exists.",
        "",
    ]
    steps = [s for c in digest["cases"] for t in c["tracks"] for L in t["chains"] for s in L["steps"]]
    lines.append(f"{len(digest['cases'])} cases, {len(steps)} steps, "
                 f"{sum(1 for s in steps if s['stated_platform_means'])} with a coded platform interaction, "
                 f"{sum(1 for s in steps if s['documented_feature_use'])} with documented feature use, "
                 f"{digest['use_notes']} use notes.")
    lines.append("")
    for case in digest["cases"]:
        lines.append(f"## {case['case_id']}")
        for track in case["tracks"]:
            lines.append(f"### {track['kind']} {track['track_id']}")
            for chain in track["chains"]:
                lines.append(f"**{chain['trajectory_id']}**")
                for i, s in enumerate(chain["steps"], 1):
                    when = s["date"]["earliest"] if s["date"] else "undated"
                    plat = ", ".join(s["stated_platform_means"]) or "no platform"
                    lines.append(f"{i}. {s['event_id']} {s['action']} — {when} — {plat}")
                    if s["candidate_capabilities"]:
                        bits = [f"{e['affordance']} ({e['availability']})" for e in s["candidate_capabilities"]]
                        lines.append("   candidates: " + ", ".join(bits))
                    if s["documented_feature_use"]:
                        lines.append("   documented use: " + ", ".join(s["documented_feature_use"]))
                    if s["unmatched_platforms"]:
                        lines.append("   platform not in the registry: " + ", ".join(s["unmatched_platforms"]))
                    for note in s["how_used"]:
                        lines.append(f"   how used ({note['author']}, {note['judgment']}): {note['affordance']} — {note['note']}")
                lines.append("")
            if track["unordered_pairs"]:
                pairs = ", ".join(f"{a}|{b}" for a, b in track["unordered_pairs"])
                lines.append(f"unordered: {pairs}")
                lines.append("")
        if case["stated_feature_phrases"]:
            lines.append("Feature phrases stated in the record, not use:")
            for p in case["stated_feature_phrases"]:
                lines.append(f"- {p['feature_class']}: {p['feature_term']} ({p['observation_id']}, {p['doc_id']} p{p['pdf_page']})")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(digest: dict) -> str:
    """A local coding bench. The page contains the digest and no source text."""
    payload = json.dumps(digest, ensure_ascii=False).replace("<", "\\u003c")
    template = (Path(__file__).resolve().parent / "coding_bench.html").read_text(encoding="utf-8")
    if "__DIGEST__" not in template:
        raise RuntimeError("coding bench template has no digest slot")
    return template.replace("__DIGEST__", payload)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("release_id")
    ap.add_argument("--registry", type=Path, required=True, help="directory of capability-source yaml files")
    ap.add_argument("--notes", type=Path, default=None, help="researcher use notes; omit for an empty slot")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    registry = Registry(load(sorted(a.registry.glob("*.yaml"))))
    digest = release_digest(DATA / a.release_id, registry, a.notes)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "digest.json").write_text(json.dumps(digest, indent=1) + "\n", encoding="utf-8")
    (a.out / "digest.md").write_text(render(digest), encoding="utf-8")
    (a.out / "index.html").write_text(render_html(digest), encoding="utf-8")
    print(f"wrote {a.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
