"""Derived views of a documented event graph: the partial order ≺_θ, its unordered pairs,
and trajectories L = ((a1, O1), ..., (an, On)) as maximal chains.

The canonical artifact is the coded bundle (the event graph). Everything here is a view
of it at a threshold θ (DIRECT or INFERRED), with derivation metadata.

Rules (codebook F):

* Order comes from BEFORE/MEETS relations whose status is admissible (direct relative
  chronology counts as direct evidence, T5), and from dated assertions: a precedes b when
  every admissible dated assertion of a ends before every admissible dated assertion of
  b starts. Dates taken from an enclosing window are INFERRED, so they order events only
  at the INFERRED threshold (T2). An event whose dated assertions contradict each other
  contributes no date order at all (T3). Order is transitive through any event.
* SAME_ACT (possible identity, R05) never merges events and never creates order; each
  track reports its possible-identity pairs.
* A trajectory is a maximal chain of offender events in one track under that partial
  order. A chain is an analytic view, not an observed history: it omits events that are
  unordered with it, and one event can sit in many chains. Consecutive steps mean "known to come later", not "came next": a step is
  marked ``immediate`` only when an admissible MEETS relation joins the pair.
* Events the evidence leaves unordered are never forced into a sequence; each such
  pair is reported in ``unordered_pairs`` and they fall into different chains.
* O_i holds the step's instrumental (level C) affordance annotations with an admissible
  status. O_i may be empty. Beside it, each step reports level B (action-relevant:
  capabilities of the platform the act went through, relevant to that action) and level
  A (available on that platform at the time), both from the reviewed capability registry,
  with the registry entries they rest on. Candidate concepts are reported beside O_i.
* Victim, undercover, law-enforcement and procedural events never become steps. An
  INTERRUPTS relation attaches them to the step they interrupt.
* No phases, terminal states, probabilities or utilities are produced.

Output is deterministic: the same bundle gives byte-identical JSON.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from state_machines.evidence import vocab as V

RULE_VERSION = "derive-2.0.0"
MAX_CHAINS_PER_TRACK = 256


class DerivationError(ValueError):
    pass


def bundle_sha256(bundle: dict) -> str:
    return hashlib.sha256(json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def event_spans(event: dict, admissible: Tuple[str, ...]) -> List[Tuple[date, date]]:
    """Admissible dated assertions of an event as (earliest, latest) calendar dates.

    Empty when the event is undated or when its admissible assertions contradict each other
    (disjoint spans): a contradicted event gives no date order (T3)."""
    spans = []
    for a in event["time"]["assertions"]:
        if a["status"] not in admissible:
            continue
        try:
            spans.append((date.fromisoformat(a["earliest"]), date.fromisoformat(a["latest"])))
        except ValueError:      # not a calendar date: validator rule T13 reports it; no order from it
            return []
    if any(a_hi < b_lo or b_hi < a_lo for i, (a_lo, a_hi) in enumerate(spans) for b_lo, b_hi in spans[i + 1:]):
        return []
    return spans


def time_conflict(event: dict) -> bool:
    spans = [(a["earliest"], a["latest"]) for a in event["time"]["assertions"] if a["status"] in ("DIRECT", "INFERRED")]
    return any(a_hi < b_lo or b_hi < a_lo for i, (a_lo, a_hi) in enumerate(spans) for b_lo, b_hi in spans[i + 1:])


def date_order(bundle: dict, admissible: Tuple[str, ...]) -> Set[Tuple[str, str]]:
    """Order implied by dated assertions: every span of a ends before every span of b starts."""
    spans = {e["event_id"]: event_spans(e, admissible) for e in bundle["events"]}
    spans = {k: v for k, v in spans.items() if v}
    return {(a, b) for a, sa in spans.items() for b, sb in spans.items()
            if a != b and max(hi for _, hi in sa) < min(lo for lo, _ in sb)}


def _order_edges(bundle: dict, admissible: Tuple[str, ...], use_dates: bool = True) -> Dict[str, Set[str]]:
    edges: Dict[str, Set[str]] = defaultdict(set)
    for rel in bundle["relations"]:
        if rel["type"] in V.ORDER_RELATIONS and rel["status"] in admissible:
            edges[rel["from_event"]].add(rel["to_event"])
    if use_dates:
        for a, b in date_order(bundle, admissible):
            edges[a].add(b)
    return edges


def order_cycle(bundle: dict, threshold: str = "INFERRED", with_dates: bool = False) -> Optional[List[str]]:
    """A cycle in the admissible order relation, if any (as an event-id path).

    ``with_dates`` adds the order implied by cited dates, so a coded relation that the
    dates contradict (directly or through other events) shows up as a cycle.
    """
    edges = _order_edges(bundle, V.ADMISSIBLE[threshold], use_dates=with_dates)
    color: Dict[str, int] = {}
    stack: List[str] = []

    def visit(node: str) -> Optional[List[str]]:
        color[node] = 1
        stack.append(node)
        for nxt in sorted(edges.get(node, ())):
            if color.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if nxt not in color:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = 2
        return None

    for start in sorted(edges):
        if start not in color:
            found = visit(start)
            if found:
                return found
    return None


def _closure(edges: Dict[str, Set[str]], nodes: Iterable[str]) -> Dict[str, Set[str]]:
    reach: Dict[str, Set[str]] = {}
    for n in nodes:
        seen: Set[str] = set()
        todo = list(edges.get(n, ()))
        while todo:
            m = todo.pop()
            if m not in seen:
                seen.add(m)
                todo.extend(edges.get(m, ()))
        reach[n] = seen
    return reach


def step_affordances(event: dict, admissible: Tuple[str, ...]) -> List[str]:
    """O_i: instrumental (level C) affordances with an admissible status."""
    return sorted({a["affordance"] for a in event.get("affordances", []) if a["status"] in admissible})


def _step_candidates(event: dict, admissible: Tuple[str, ...]) -> List[str]:
    return sorted({c["candidate"] for c in event.get("candidate_affordances", []) if c["status"] in admissible})


def _levels(event: dict, registry, admissible, event_levels) -> Dict[str, Any]:
    lv = event_levels(event, registry, admissible)
    return {
        "platforms": sorted({i["platform_key"] for i in event.get("platform_interactions", []) if i["status"] in admissible}),
        "action_relevant_affordances": sorted({c["affordance"] for c in lv["action_relevant"]}),   # level B
        "available_affordances": sorted({c["affordance"] for c in lv["available"]}),               # level A
        "capability_evidence": sorted({(c["platform"], c["affordance"], c["availability"]) for c in lv["available"]}),
        "unmatched_platforms": lv["unmatched_platforms"],
        "level_unit": "event",
    }


def derive(bundle: dict, threshold: str = "DIRECT", registry=None) -> Dict[str, Any]:
    """Trajectories for every track of one bundle. ``threshold`` is DIRECT or INFERRED.

    ``registry`` (a ``capabilities.Registry``) adds affordance levels A and B to each step,
    beside O_i. O_i itself is level C only and does not depend on the registry.
    """
    from state_machines.trajectories.affordances import Registry, event_levels, load

    registry = registry if registry is not None else Registry(load())
    if threshold not in V.ADMISSIBLE:
        raise ValueError(f"threshold must be one of {sorted(V.ADMISSIBLE)}")
    admissible = V.ADMISSIBLE[threshold]
    cycle = order_cycle(bundle, "INFERRED")  # contradictory order is an evidence error at any threshold
    if cycle:
        raise DerivationError("order relations form a cycle: " + " -> ".join(cycle))
    cycle = order_cycle(bundle, threshold, with_dates=True)
    if cycle:  # never drop events silently: a contradiction between relations and dates is an error
        raise DerivationError("order relations and cited dates conflict: " + " -> ".join(cycle))

    events = {e["event_id"]: e for e in bundle["events"]}
    edges = _order_edges(bundle, admissible)
    dated = date_order(bundle, admissible)
    reach = _closure(edges, events)
    meets = {(r["from_event"], r["to_event"]) for r in bundle["relations"]
             if r["type"] == "MEETS" and r["status"] in admissible}
    interrupts: Dict[str, List[str]] = defaultdict(list)
    for r in bundle["relations"]:
        if r["type"] == "INTERRUPTS" and r["status"] in admissible:
            interrupts[r["to_event"]].append(r["from_event"])

    tracks_out = []
    for track in sorted(bundle["tracks"], key=lambda t: t["track_id"]):
        steps: List[str] = []
        excluded = []
        for eid in sorted(set(track["event_ids"])):
            ev = events[eid]
            if V.FAMILY_OF[ev["action"]] not in V.TRAJECTORY_FAMILIES:
                excluded.append({"event_id": eid, "reason": "not offender conduct (" + V.FAMILY_OF[ev["action"]] + ")"})
            elif ev["status"] not in admissible:
                excluded.append({"event_id": eid, "reason": f"event status {ev['status']} below threshold {threshold}"})
            else:
                steps.append(eid)
        less = {a: {b for b in steps if b in reach[a]} for a in steps}
        covers = {a: sorted(b for b in less[a] if not any(b in less[c] for c in less[a] if c != b)) for a in steps}
        minimal = [a for a in steps if not any(a in less[b] for b in steps)]
        chains: List[List[str]] = []
        truncated = False

        def walk(path: List[str]) -> None:
            nonlocal truncated
            if len(chains) >= MAX_CHAINS_PER_TRACK:
                truncated = True
                return
            nxt = covers[path[-1]]
            if not nxt:
                chains.append(list(path))
                return
            for b in nxt:
                walk(path + [b])

        for start in sorted(minimal):
            walk([start])
        chains.sort()
        trajectories = []
        for n, chain in enumerate(chains, 1):
            trajectories.append({
                "trajectory_id": f"{track['track_id']}.L{n}",
                "steps": [{
                    "index": i,
                    "event_id": eid,
                    "action": events[eid]["action"],
                    "affordances": step_affordances(events[eid], admissible),   # O_i: level C only
                    **_levels(events[eid], registry, admissible, event_levels),
                    "candidate_affordances": _step_candidates(events[eid], admissible),
                    "outcome": events[eid]["outcome"],
                    "immediate_after_previous": bool(i and (chain[i - 1], eid) in meets),
                    "interrupted_by": sorted(interrupts.get(eid, [])),
                    "repetition": (events[eid].get("repetition") or {}).get("kind", "single"),
                } for i, eid in enumerate(chain)],
            })
        unordered = sorted((a, b) for a in steps for b in steps
                           if a < b and b not in reach[a] and a not in reach[b])
        in_track = set(track["event_ids"])
        possible_same = sorted({tuple(sorted((r["from_event"], r["to_event"]))) for r in bundle["relations"]
                                if r["type"] in V.IDENTITY_RELATIONS and r["status"] == "INFERRED"
                                and r["from_event"] in in_track and r["to_event"] in in_track})
        tracks_out.append({
            "track_id": track["track_id"], "kind": track["kind"], "anchor_ref": track.get("anchor_ref"),
            "trajectories": trajectories, "unordered_pairs": [list(p) for p in unordered],
            "possible_same_act": [list(p) for p in possible_same],
            "time_conflicts": sorted(e for e in in_track if time_conflict(events[e])),
            "excluded_events": excluded, "chains_truncated": truncated,
        })
    return {
        "case_id": bundle["case_id"],
        "derivation": {"rule_version": RULE_VERSION, "threshold": threshold, "date_order_pairs": len(dated),
                       "capability_registry_sha256": hashlib.sha256(json.dumps(registry.data, sort_keys=True, default=str).encode()).hexdigest(),
                       "codebook_version": bundle["codebook_version"], "input_sha256": bundle_sha256(bundle)},
        "tracks": tracks_out,
    }


def derived_json(bundle: dict, threshold: str = "DIRECT", registry=None) -> str:
    return json.dumps(derive(bundle, threshold, registry), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
