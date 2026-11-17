"""Integrity rules for coded case bundles.

Every rule has a code, and every code has a failing fixture in tests/pacer.
``validate(bundle)`` returns findings; a bundle is valid when no finding has
severity "error". Warnings are reported, never silently fixed.

  T01 schema                        T08 actor role vs action family
  T02 duplicate ids                 T09 affordance basis / candidate separation
  T03 dangling references           T10 harm victim and labels
  T04 passage verification          T11 order cycle
  T05 OCR page needs image check    T12 order contradicted by dates
  T06 source status vs document     T13 time sanity
  T07 event status vs its support   T14 direct identifiers in coded text
                                    T15 documented platform interaction
                                    T16 coded order vs cited dates (transitive)
                                    T17 participants, roles, collectives (R04/R10)
                                    T18 possible identity, SAME_ACT (R05)
                                    T19 channels are not platforms (I3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import jsonschema

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.trajectories.derive import order_cycle
from state_machines.evidence.schema import build_schema


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # error | warning
    where: str
    message: str


_VALIDATOR = jsonschema.Draft202012Validator(build_schema())

# T14: patterns for direct identifiers in coder-written text. Names are caught by the
# per-case deny list (built from the PDFs' captions, kept in the local store) because
# no regex can tell a surname from an ordinary word.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?<!\d)(?:\(\d{3}\)\s*|\d{3}[-. ])\d{3}[-. ]\d{4}(?!\d)")
_AT_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_.]{3,}")
_HANDLE = re.compile(r"\b(?=[A-Za-z0-9_]*[A-Za-z])(?=[A-Za-z0-9_]*\d)[A-Za-z0-9]+_[A-Za-z0-9_]+\b|\b[a-z]+\d{3,}[a-z0-9]*\b")
_INITIALS = re.compile(r"\b(?!U\.S\.)(?![NSEWMC]\.D\.)(?!D\.C\.)[A-Z]\.[A-Z]\.(?![A-Z])")
_FREE_TEXT_KEYS = ("description", "notes", "note", "feature_term", "other_action_label", "other_label",
                   "expression", "platform_surface")


def _free_text(bundle: dict) -> Iterable[tuple]:
    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and k in _FREE_TEXT_KEYS:
                    yield path + "." + k, v
                else:
                    yield from walk(v, path + "." + k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from walk(v, f"{path}[{i}]")
    yield from walk(bundle, "$")


def identifier_hits(text: str, deny: Sequence[str] = ()) -> List[str]:
    hits = [p.pattern[:12] for p in (_EMAIL, _PHONE, _AT_HANDLE, _HANDLE, _INITIALS) if p.search(text)]
    for word in deny:
        if word and re.search(r"\b" + re.escape(word) + r"\b", text, re.I):
            hits.append("deny-list")
    return hits


def validate(bundle: dict, *, text_root: Optional[Path] = None, deny_list: Sequence[str] = (),
             require_verified: bool = False) -> List[Finding]:
    out: List[Finding] = []
    err = lambda code, where, msg: out.append(Finding(code, "error", where, msg))  # noqa: E731
    warn = lambda code, where, msg: out.append(Finding(code, "warning", where, msg))  # noqa: E731

    schema_errors = sorted(_VALIDATOR.iter_errors(bundle), key=lambda e: list(e.absolute_path))
    for e in schema_errors:
        err("T01", "/".join(map(str, e.absolute_path)) or "$", e.message[:200])
    if schema_errors:
        return out  # later rules assume the shape is right

    case_id = bundle["case_id"]
    docs = {d["doc_id"]: d for d in bundle["documents"]}
    passages = {p["passage_id"]: p for p in bundle["passages"]}
    people = {a["participant_ref"]: a for a in bundle["participants"]}
    events = {e["event_id"]: e for e in bundle["events"]}

    # T02 duplicate ids
    for label, items, key in (("document", bundle["documents"], "doc_id"), ("passage", bundle["passages"], "passage_id"),
                              ("participant", bundle["participants"], "participant_ref"), ("event", bundle["events"], "event_id"),
                              ("relation", bundle["relations"], "relation_id"), ("track", bundle["tracks"], "track_id")):
        seen = set()
        for item in items:
            if item[key] in seen:
                err("T02", f"{label}:{item[key]}", f"duplicate {label} id")
            seen.add(item[key])

    # T03 dangling references
    def need_passage(pid, where):
        if pid not in passages:
            err("T03", where, f"unknown passage {pid}")

    def need_actor(ref, where):
        if ref not in people:
            err("T03", where, f"unknown participant {ref}")

    for p in bundle["passages"]:
        if p["doc_id"] not in docs:
            err("T03", f"passage:{p['passage_id']}", f"unknown document {p['doc_id']}")
    for e in bundle["events"]:
        w = f"event:{e['event_id']}"
        need_actor(e["actor"]["participant_ref"], w)
        for x in e.get("targets", []) + e.get("co_actors", []) + e.get("unresolved_participants", []):
            need_actor(x["participant_ref"], w)
        for x in e.get("unresolved_participants", []):
            for pid in x["passage_ids"]:
                need_passage(pid, w + ".unresolved_participants")
        for s in e["support"]:
            need_passage(s["passage_id"], w)
        for a in e["time"]["assertions"]:
            for pid in a["passage_ids"]:
                need_passage(pid, w + ".time")
        for c in e.get("channels", []):
            for s in c["support"]:
                need_passage(s["passage_id"], w + ".channels")
        for i in e.get("platform_interactions", []):
            for c in i.get("configuration", []):
                for s in c["support"]:
                    need_passage(s["passage_id"], w + ".configuration")
        for m in e.get("platform_mentions", []):
            for pid in m["passage_ids"]:
                need_passage(pid, w + ".platform_mentions")
        for pid in (e.get("repetition") or {}).get("passage_ids", []):
            need_passage(pid, w + ".repetition")
        for group in ("affordances", "candidate_affordances", "access", "harms", "platform_interactions"):
            for ann in e.get(group, []):
                for s in ann["support"]:
                    need_passage(s["passage_id"], f"{w}.{group}")
        for ann in e.get("access", []):
            need_actor(ann["target_ref"], w + ".access")
        for h in e.get("harms", []):
            need_actor(h["victim_ref"], w + ".harms")
    for a in bundle["participants"]:
        w = f"participant:{a['participant_ref']}"
        for ls in a.get("legal_status", []):
            for s in ls["support"]:
                need_passage(s["passage_id"], w)
        for m in a.get("members", []):
            need_actor(m["participant_ref"], w + ".members")
            for s in m["support"]:
                need_passage(s["passage_id"], w + ".members")
        for s in (a.get("count") or {}).get("support", []):
            need_passage(s["passage_id"], w + ".count")
    for r in bundle["relations"]:
        w = f"relation:{r['relation_id']}"
        for end in (r["from_event"], r["to_event"]):
            if end not in events:
                err("T03", w, f"unknown event {end}")
        for s in r["support"]:
            need_passage(s["passage_id"], w)
        if r["status"] in ("DIRECT", "INFERRED") and not r["support"] and r["basis"] != "dated_events":
            err("T03", w, "a DIRECT or INFERRED relation needs a supporting passage unless it rests on dated events")
    for t in bundle["tracks"]:
        for eid in t["event_ids"]:
            if eid not in events:
                err("T03", f"track:{t['track_id']}", f"unknown event {eid}")
        if t.get("anchor_ref"):
            need_actor(t["anchor_ref"], f"track:{t['track_id']}")
    if any(f.code == "T03" for f in out):
        return out

    # T04/T05 passage verification against the local page text, and OCR image checks
    pages = {(d["doc_id"], pg["pdf_page"]): pg for d in bundle["documents"] for pg in d["pages"]}
    for p in bundle["passages"]:
        w = f"passage:{p['passage_id']}"
        page = pages.get((p["doc_id"], p["pdf_page"]))
        if page is None:
            err("T04", w, "page is not listed on its document")
            continue
        if p["pdf_page"] > docs[p["doc_id"]]["page_count"]:
            err("T04", w, "page beyond the document's page count")
        check = E.verify_passage(p, E.read_page(case_id, p["doc_id"], p["pdf_page"], text_root), page["page_text_sha256"])
        if check.status == "FAILED":
            err("T04", w, check.reason)
        elif check.status == "NOT_CHECKABLE":
            (err if require_verified else warn)("T04", w, check.reason)
        if p["verification"]["status"] == "VERIFIED" and check.status == "FAILED":
            err("T04", w, "marked VERIFIED but the text does not verify")
        if page["text_method"] == "ocr" and p["verification"]["status"] == "VERIFIED" and not page.get("image_checked"):
            err("T05", w, "OCR page: a VERIFIED passage needs the page image checked")
        if p["verification"]["status"] == "VERIFIED" and page["text_method"] == "ocr" \
                and p["verification"]["method"] == "text_layer_exact":
            err("T05", w, "OCR page cannot be verified by text_layer_exact")

    # T06 source status must be one the document type can carry; changes need a reason
    for p in bundle["passages"]:
        default, allowed = V.DOC_TYPES[docs[p["doc_id"]]["doc_type"]]
        w = f"passage:{p['passage_id']}"
        if p["source_status"] not in allowed:
            err("T06", w, f"{docs[p['doc_id']]['doc_type']} cannot establish {p['source_status']}")
        elif p["source_status"] != default and not p.get("source_status_reason"):
            err("T06", w, "source status differs from the document default without a reason")

    # T07 event status must be backed by its action support
    for e in bundle["events"]:
        w = f"event:{e['event_id']}"
        action_support = [s["status"] for s in e["support"] if s["facet"] == "action"]
        if not action_support:
            err("T07", w, "no passage supports the action itself")
        elif e["status"] == "DIRECT" and "DIRECT" not in action_support:
            err("T07", w, "DIRECT event without a DIRECT action passage")
        elif e["status"] == "INFERRED" and not set(action_support) & {"DIRECT", "INFERRED"}:
            err("T07", w, "INFERRED event without a DIRECT or INFERRED action passage")
        if e["action"] == "OTHER_OFFENDER_ACTION" and not e.get("other_action_label"):
            err("T07", w, "OTHER_OFFENDER_ACTION needs other_action_label")

    # T08 who may perform what: the role the actor holds in this event decides the family
    for e in bundle["events"]:
        family = V.FAMILY_OF[e["action"]]
        for x in [e["actor"]] + [c for c in e.get("co_actors", []) if c["mode"] != "directing"]:
            if x["role"] not in V.FAMILY_ROLES[family]:
                err("T08", f"event:{e['event_id']}", f"{x['role']} cannot perform {family} action {e['action']}")

    # T09 affordances: a platform name never supports DIRECT/INFERRED; O and candidates stay apart
    for e in bundle["events"]:
        w = f"event:{e['event_id']}"
        seen_aff = set()
        for a in e.get("affordances", []):
            if a["status"] == "DIRECT" and not any(s["status"] == "DIRECT" and s["facet"] == "feature" for s in a["support"]):
                err("T09", w, f"{a['affordance']}: DIRECT needs a DIRECT passage on the feature facet")
            if a["affordance"] in seen_aff:
                err("T09", w, f"{a['affordance']} annotated twice on one event")
            seen_aff.add(a["affordance"])
            if V.FAMILY_OF[e["action"]] not in V.TRAJECTORY_FAMILIES:
                warn("T09", w, "affordance on a non-offender event is recorded but never enters O_i")
        for c in e.get("candidate_affordances", []):
            if c["status"] == "DIRECT" and not any(s["status"] == "DIRECT" and s["facet"] == "feature" for s in c["support"]):
                err("T09", w, f"candidate {c['candidate']}: DIRECT needs a DIRECT passage on the feature facet")
        # T15 documented platform interaction: the passage must say the act went through the platform
        for i in e.get("platform_interactions", []):
            if i["status"] == "DIRECT" and not any(s["status"] == "DIRECT" and s["facet"] in ("platform", "feature")
                                                   for s in i["support"]):
                err("T15", w, f"{i['platform_surface']}: DIRECT interaction needs a DIRECT passage on the platform facet")
            if i["status"] in ("DIRECT", "INFERRED") and V.FAMILY_OF[e["action"]] not in V.TRAJECTORY_FAMILIES:
                warn("T15", w, "platform interaction on a non-offender event never reaches a trajectory step")

    # T10 harms
    for e in bundle["events"]:
        w = f"event:{e['event_id']}"
        victims = {x["participant_ref"] for x in e.get("targets", []) if x["role"] == "victim"}
        for h in e.get("harms", []):
            if h["victim_kind"] == "undercover_persona" or people[h["victim_ref"]]["kind"] == "persona":
                err("T10", w, "harm recorded against an undercover persona")
            elif h["victim_ref"] not in victims:
                err("T10", w, f"harm recorded against {h['victim_ref']}, who is not a victim target of this event")
            if h["harm"] == "HARM_OTHER" and not h.get("other_label"):
                err("T10", w, "HARM_OTHER needs other_label")

    # T11 order cycle
    for threshold in ("INFERRED",):
        cyc = order_cycle(bundle, threshold)
        if cyc:
            err("T11", "relations", "order cycle: " + " -> ".join(cyc))

    # T16 coded order and cited dates contradict each other, possibly through other events
    if not any(f.code == "T11" for f in out):
        cyc = order_cycle(bundle, "INFERRED", with_dates=True)
        if cyc:
            err("T16", "relations", "coded order and cited dates conflict: " + " -> ".join(cyc))

    # T13 time: real calendar dates, ordered bounds, windows are inferred, conflicts flagged (T1-T3)
    for e in bundle["events"]:
        w, t = f"event:{e['event_id']}", e["time"]
        spans = []
        for a in t["assertions"]:
            try:
                lo, hi = date.fromisoformat(a["earliest"]), date.fromisoformat(a["latest"])
            except ValueError:
                err("T13", w, f"not a calendar date: {a['earliest']} / {a['latest']}")
                continue
            if lo > hi:
                err("T13", w, "earliest is after latest")
            if a["basis"] == "enclosing_window" and a["status"] == "DIRECT":
                err("T13", w, "a date taken from an enclosing window is an inferred constraint, not a DIRECT date")
            if a["status"] in ("DIRECT", "INFERRED"):
                spans.append((lo, hi))
        disjoint = any(a_hi < b_lo or b_hi < a_lo for i, (a_lo, a_hi) in enumerate(spans) for b_lo, b_hi in spans[i + 1:])
        if disjoint and not t.get("conflict_flagged"):
            err("T13", w, "dated assertions contradict each other; set conflict_flagged and keep both")
        if t.get("conflict_flagged") and not disjoint:
            warn("T13", w, "conflict_flagged but the dated assertions overlap")

    # T12 a coded BEFORE that every dated assertion contradicts
    from state_machines.trajectories.derive import event_spans
    for r in bundle["relations"]:
        if r["type"] not in V.ORDER_RELATIONS or r["status"] not in ("DIRECT", "INFERRED"):
            continue
        a, b = event_spans(events[r["from_event"]], ("DIRECT", "INFERRED")), event_spans(events[r["to_event"]], ("DIRECT", "INFERRED"))
        if a and b and all(lo_a > hi_b for lo_a, _ in a for _, hi_b in b):
            err("T12", f"relation:{r['relation_id']}", "says before, but the first event starts after the second ends")

    # T17 participants: kinds, collectives, roles (R04/R10)
    for a in bundle["participants"]:
        w = f"participant:{a['participant_ref']}"
        if a["kind"] != "collective" and (a.get("members") or a.get("count")):
            err("T17", w, "only a collective has members or a count")
        c = a.get("count") or {}
        if c.get("min") is not None and c.get("max") is not None and c["min"] > c["max"]:
            err("T17", w, "count min is above count max")
        if c and c["stated"] != "unknown" and not c.get("support"):
            err("T17", w, "a stated count needs a supporting passage")
        if a["kind"] == "collective" and a.get("age_band"):
            err("T17", w, "a collective has no age band")
    for e in bundle["events"]:
        refs = [e["actor"]["participant_ref"]] + [x["participant_ref"] for x in e.get("co_actors", [])]
        if len(refs) != len(set(refs)):
            err("T17", f"event:{e['event_id']}", "a participant appears twice among the actors of one event")
        if people[e["actor"]["participant_ref"]]["kind"] == "persona" and e["actor"]["role"] != "undercover":
            err("T17", f"event:{e['event_id']}", "an undercover persona can only act in the undercover role")
        for x in e.get("unresolved_participants", []):
            warn("T17", f"event:{e['event_id']}", f"{x['participant_ref']}: role not yet decided ({x['note'][:80]})")

    # T18 possible identity (R05)
    seen_pairs = set()
    reach = _reach(bundle)
    for r in bundle["relations"]:
        if r["type"] not in V.IDENTITY_RELATIONS:
            continue
        w = f"relation:{r['relation_id']}"
        a, b = r["from_event"], r["to_event"]
        if a == b:
            err("T18", w, "an event cannot be possibly the same act as itself")
        if r["status"] == "DIRECT":
            err("T18", w, "confirmed identity is one event citing both passages, not a DIRECT SAME_ACT")
        pair = tuple(sorted((a, b)))
        if pair in seen_pairs:
            warn("T18", w, "the same pair is linked twice")
        seen_pairs.add(pair)
        if r["status"] == "INFERRED" and (b in reach.get(a, ()) or a in reach.get(b, ())):
            warn("T18", w, "possibly the same act, but the two events are ordered; check the dates (R06)")

    # T19 channels are not platforms (I3)
    for e in bundle["events"]:
        for i in e.get("platform_interactions", []):
            if _CHANNEL_WORDS.search(i["platform_surface"]) or _CHANNEL_WORDS.search(i["platform_key"]):
                err("T19", f"event:{e['event_id']}", f"{i['platform_surface']} is a channel; record it under channels")

    # T14 direct identifiers in coder-written text
    for where, text in _free_text(bundle):
        hits = identifier_hits(text, deny_list)
        if hits:
            err("T14", where, "possible direct identifier (" + ", ".join(sorted(set(hits))) + ")")
    return out


_CHANNEL_WORDS = re.compile(r"(?i)\b(sms|text messag\w*|phone( call)?s?|telephone|voice call|e-?mail|mail)\b")


def _reach(bundle: dict) -> dict:
    """Order reachability at the INFERRED threshold, coded relations and cited dates together."""
    from state_machines.trajectories.derive import _closure, _order_edges
    edges = _order_edges(bundle, V.ADMISSIBLE["INFERRED"])
    return _closure(edges, [e["event_id"] for e in bundle["events"]])


def errors(findings: Iterable[Finding]) -> List[Finding]:
    return [f for f in findings if f.severity == "error"]


def release_errors(bundle: dict, *, text_root: Optional[Path] = None, deny_list: Sequence[str] = (),
                   allow_unreviewed: bool = False) -> List[str]:
    """Why a bundle cannot be released (empty list = releasable).

    Every validation error blocks. With page text available, passages must verify. Every
    event and relation must be adjudicated, unless ``allow_unreviewed`` builds a preview,
    which the release manifest then labels as not adjudicated."""
    out = [f"{f.code} {f.where}: {f.message}" for f in errors(
        validate(bundle, text_root=text_root, deny_list=deny_list, require_verified=text_root is not None))]
    if not allow_unreviewed:
        pending = [e["event_id"] for e in bundle["events"] if e["review"]["status"] != "adjudicated"]
        pending += [r["relation_id"] for r in bundle["relations"] if (r.get("review") or {}).get("status", "adjudicated") != "adjudicated"]
        if pending:
            out.append(f"{len(pending)} events/relations not adjudicated (first: {', '.join(pending[:5])})")
    unresolved = [e["event_id"] for e in bundle["events"] if e.get("unresolved_participants")]
    if unresolved and not allow_unreviewed:
        out.append(f"{len(unresolved)} events have participants whose role is not decided: {', '.join(unresolved[:5])}")
    return out
