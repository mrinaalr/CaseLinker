"""Emit CASE/UCO/CAC graphs from a coded bundle and its derived trajectories.

Built with the pinned CASE-UCO SDK (``case_uco.CASEGraph``). Canonical terms do the
structural work; the experimental ``clt:`` extension only carries evidence status
and codes (ontology/extensions/caselinker-trajectory/0.2.0/).

Evidence graph (one per case):
  investigation   case-investigation:Investigation, uco-core:object -> documents
  document        uco-observable:ObservableObject + FileFacet + ContentDataFacet/Hash (SHA-256)
  actor           uco-identity:Identity, pseudonymous (D1, V1, UC1 ...), clt:actorRole
  event           uco-action:Action, performer/object/participant, clt:actionCode/outcome/assertionStatus
  relation        uco-core:Relationship between actions (Occurs_Before, Overlaps, Interrupts ...)
  affordance      cac-platforms:<Class> individual --Supports_Action--> action (uco-core:Relationship)
  harm            action --Documents_Harm--> victim identity (uco-core:Relationship)
  track           uco-core:Grouping of actions
  evidence        oa:Annotation(body = assertion, target = SpecificResource(source = document,
                  FragmentSelector page=N refinedBy TextPositionSelector)), quote hash only

Trajectory graph (derived): uco-action:ActionLifecycle + uco-action:ArrayOfAction, and one
uco-core:Relationship "Trajectory_Step" per step with clt:stepIndex and clt:stepAffordance (O_i).

No person names, quote text, phases, terminal states or probabilities are written.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from typing import Any, Dict, List

from case_uco import CASEGraph
from case_uco.graph import canonical_hex_binary

from state_machines.evidence import vocab as V

BASE = "https://w3id.org/caselinker/resource/pacer/v4/"
PLATFORM_BASE = "https://w3id.org/caselinker/resource/platform/"
CONTEXT = {
    "clt": "https://w3id.org/caselinker/trajectory#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "oa": "http://www.w3.org/ns/oa#",
    "dcterms": "http://purl.org/dc/terms/",
    "cac-platforms": "https://cacontology.projectvic.org/platforms#",
}
RELATION_KIND = {
    "BEFORE": "Occurs_Before", "MEETS": "Immediately_Before", "OVERLAPS": "Overlaps", "DURING": "Occurs_During",
    "SAME_TIME": "Same_Time", "UNORDERED": "Order_Unknown", "PART_OF": "Part_Of", "REPEATS": "Repeats",
    "RESPONDS_TO": "Responds_To", "BACKED_BY_THREAT": "Backed_By_Threat", "INTERRUPTS": "Interrupts",
    "RESUMES_AFTER": "Resumes_After", "SAME_MATERIAL": "Same_Material",
}
_STR = lambda v: {"@type": "xsd:string", "@value": v}  # noqa: E731  (UCO string properties)
_CL = lambda v: v  # noqa: E731  plain literals for clt: codes, matching the sh:in lists of the extension shapes


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "unnamed"


def _bound(d: str, end: bool) -> str:
    parts = d.split("-")
    if len(parts) == 1:
        return d + ("-12-31" if end else "-01-01")
    if len(parts) == 2:
        return d + (f"-{calendar.monthrange(int(parts[0]), int(parts[1]))[1]:02d}" if end else "-01")
    return d


def _h(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def _graph(case_id: str) -> CASEGraph:
    return CASEGraph(kb_prefix=f"{BASE}{case_id}/", extra_context=CONTEXT)


def _ref(node_id: str) -> Dict[str, str]:
    return {"@id": node_id}


def _datetime(day: str, end: bool) -> Dict[str, str]:
    return {"@type": "xsd:dateTime", "@value": f"{day}T{'23:59:59' if end else '00:00:00'}Z"}


class _Emitter:
    def __init__(self, bundle: dict, registry=None):
        from state_machines.trajectories.affordances import Registry, load

        self.registry = registry if registry is not None else Registry(load())
        self.b = bundle
        self.g = _graph(bundle["case_id"])
        self.passages = {p["passage_id"]: p for p in bundle["passages"]}
        self.docs = {d["doc_id"]: d for d in bundle["documents"]}
        self.pages = {(d["doc_id"], pg["pdf_page"]): pg for d in bundle["documents"] for pg in d["pages"]}

    # -- identifiers ---------------------------------------------------------------
    @staticmethod
    def doc(doc_id: str) -> str:
        return f"kb:document-{doc_id}"

    @staticmethod
    def actor(ref: str) -> str:
        return f"kb:actor-{ref}"

    @staticmethod
    def event(event_id: str) -> str:
        return f"kb:action-{event_id}"

    def platform(self, surface: str) -> str:
        """Registry platforms get a shared IRI (joins across cases); others a per-case node."""
        pid = self.registry.platform_id(surface)
        if pid:
            node = PLATFORM_BASE + pid
            self.g.upsert_node(node, types=[V.PLATFORM_KIND_CLASS[self.registry.kind[pid]]],
                               properties={"uco-core:name": _STR(pid)})
        else:
            node = f"kb:platform-{_slug(surface)}"
            self.g.upsert_node(node, types=[V.UCO_OBSERVABLE + "ObservableObject"],
                               properties={"uco-core:name": _STR(surface)})
        return node

    # -- evidence ------------------------------------------------------------------
    def annotate(self, body: str, supports: List[dict]) -> None:
        for s in sorted(supports, key=lambda s: (s["passage_id"], s["facet"])):
            p = self.passages[s["passage_id"]]
            key = _h(body, s["passage_id"], s["facet"])
            page_sel, pos_sel, target = f"kb:selector-page-{key}", f"kb:selector-text-{key}", f"kb:target-{key}"
            self.g.upsert_node(pos_sel, types=["oa:TextPositionSelector"], properties={
                "oa:start": {"@type": "xsd:nonNegativeInteger", "@value": str(p["char_start"])},
                "oa:end": {"@type": "xsd:nonNegativeInteger", "@value": str(p["char_end"])}})
            self.g.upsert_node(page_sel, types=["oa:FragmentSelector"], properties={
                "rdf:value": _STR(f"page={p['pdf_page']}"),
                "dcterms:conformsTo": _ref("http://tools.ietf.org/rfc/rfc3778"),
                "oa:refinedBy": _ref(pos_sel)})
            self.g.upsert_node(target, types=["oa:SpecificResource"], properties={
                "oa:hasSource": _ref(self.doc(p["doc_id"])), "oa:hasSelector": _ref(page_sel)})
            page = self.pages[(p["doc_id"], p["pdf_page"])]
            self.g.upsert_node(f"kb:evidence-{key}", types=["oa:Annotation"], properties={
                "oa:hasBody": _ref(body), "oa:hasTarget": _ref(target),
                "clt:supportFacet": _CL(s["facet"]), "clt:assertionStatus": _CL(s["status"]),
                "clt:sourceStatus": _CL(p["source_status"]), "clt:verificationStatus": _CL(p["verification"]["status"]),
                "clt:quoteSha256": _CL(p["quote_sha256"]), "clt:pageTextSha256": _CL(page["page_text_sha256"])})

    # -- nodes ---------------------------------------------------------------------
    def documents(self) -> None:
        for d in sorted(self.b["documents"], key=lambda d: d["doc_id"]):
            node = self.doc(d["doc_id"])
            hash_id, content_id, file_id = f"{node}-hash", f"{node}-content", f"{node}-file"
            self.g.upsert_node(hash_id, types=["uco-types:Hash"], properties={
                "uco-types:hashMethod": _STR("SHA256"),
                "uco-types:hashValue": {"@type": "xsd:hexBinary", "@value": canonical_hex_binary(d["sha256"])}})
            self.g.upsert_node(content_id, types=["uco-observable:ContentDataFacet"],
                               properties={"uco-observable:hash": _ref(hash_id)})
            self.g.upsert_node(file_id, types=["uco-observable:FileFacet"], properties={
                "uco-observable:fileName": _STR(d["source_path"].rsplit("/", 1)[-1]),
                "uco-observable:extension": _STR("pdf")})
            self.g.upsert_node(node, types=["uco-observable:ObservableObject"], properties={
                "uco-core:hasFacet": [_ref(file_id), _ref(content_id)],
                "uco-core:description": _STR(f"{d['doc_type']} ({V.DOC_TYPES[d['doc_type']][0].lower()} by default)")})
        self.g.upsert_node("kb:investigation", types=["case-investigation:Investigation"], properties={
            "uco-core:name": _STR(f"PACER case {self.b['case_id']}"),
            "uco-core:object": [_ref(self.doc(d["doc_id"])) for d in sorted(self.b["documents"], key=lambda d: d["doc_id"])]})

    def actors(self) -> None:
        for a in sorted(self.b["actors"], key=lambda a: a["actor_ref"]):
            props: Dict[str, Any] = {"clt:actorRole": _CL(a["role"]),
                                     "uco-core:description": _STR(f"pseudonymous {a['role']} {a['actor_ref']}")}
            self.g.upsert_node(self.actor(a["actor_ref"]), types=["uco-identity:Identity"], properties=props)

    def events(self) -> None:
        for e in sorted(self.b["events"], key=lambda e: e["event_id"]):
            node = self.event(e["event_id"])
            t = e["time"]
            props: Dict[str, Any] = {
                "uco-action:performer": _ref(self.actor(e["actor_ref"])),
                "uco-core:description": _STR(e["description"]),
                "clt:actionCode": _CL(e["action"]), "clt:outcome": _CL(e["outcome"]),
                "clt:assertionStatus": _CL(e["status"]), "clt:reviewStatus": _CL(e["review"]["status"]),
                "clt:timePrecision": _CL(t["precision"]),
            }
            if e.get("target_refs"):
                props["uco-action:object"] = [_ref(self.actor(r)) for r in sorted(e["target_refs"])]
            if e.get("co_actor_refs"):
                props["uco-action:participant"] = [_ref(self.actor(r)) for r in sorted(e["co_actor_refs"])]
            for key, prop in (("earliest", "clt:timeEarliest"), ("latest", "clt:timeLatest")):
                if t.get(key):
                    props[prop] = _CL(t[key])
            if t["precision"] == "day" and t.get("earliest") and t.get("latest"):
                props["uco-action:startTime"] = _datetime(t["earliest"], False)
                props["uco-action:endTime"] = _datetime(t["latest"], True)
            rep = e.get("repetition") or {}
            if rep.get("count"):
                props["uco-action:actionCount"] = {"@type": "xsd:nonNegativeInteger", "@value": str(rep["count"])}
            self.g.upsert_node(node, types=["uco-action:Action"], properties=props)
            time_support = [{"passage_id": pid, "facet": "time", "status": "DIRECT"} for pid in t.get("passage_ids", [])
                            if not any(s["passage_id"] == pid and s["facet"] == "time" for s in e["support"])]
            self.annotate(node, e["support"] + time_support)
            for a in sorted(e.get("affordances", []), key=lambda a: a["affordance"]):
                ind = f"kb:affordance-{e['event_id']}-{a['affordance']}"
                self.g.upsert_node(ind, types=[V.AFFORDANCE_CLASSES[a["affordance"]]], properties={
                    "uco-core:description": _STR(f"{a['affordance']} as used in {e['event_id']}")})
                rel = self.g.create_relationship(ind, node, "Supports_Action",
                                                 relationship_id=f"kb:supports-{e['event_id']}-{a['affordance']}",
                                                 properties={"clt:affordanceBasis": _CL(a["basis"]),
                                                             "clt:assertionStatus": _CL(a["status"]),
                                                             **({"clt:featureTerm": _CL(a["feature_term"])} if a.get("feature_term") else {})})
                self.annotate(rel["@id"], a["support"])
            # documented platform interaction: canonical uco-action:instrument, plus a cited relationship
            for inter in sorted(e.get("platform_interactions", []), key=lambda i: i["platform_surface"]):
                pnode = self.platform(inter["platform_surface"])
                self.g.add_property(node, "uco-action:instrument", _ref(pnode))
                rel = self.g.create_relationship(node, pnode, "Carried_Out_Through",
                                                 relationship_id=f"kb:through-{e['event_id']}-{_slug(inter['platform_surface'])}",
                                                 properties={"clt:assertionStatus": _CL(inter["status"]),
                                                             **({"clt:featureTerm": _CL(inter["feature_term"])} if inter.get("feature_term") else {})})
                self.annotate(rel["@id"], inter["support"])
            # platform named with the event, no claim that the act went through it
            for m in sorted(e.get("platform_mentions", []), key=lambda m: m["platform_surface"]):
                pnode = self.platform(m["platform_surface"])
                rel = self.g.create_relationship(node, pnode, "Platform_Named_With",
                                                 relationship_id=f"kb:named-{e['event_id']}-{_slug(m['platform_surface'])}")
                self.annotate(rel["@id"], [{"passage_id": pid, "facet": "platform", "status": "DIRECT"} for pid in m["passage_ids"]])
            for i, h in enumerate(sorted(e.get("harms", []), key=lambda h: (h["harm"], h["victim_ref"]))):
                props_h = {"clt:harmCode": _CL(h["harm"]), "clt:assertionStatus": _CL(h["status"])}
                if V.HARM_H0[h["harm"]]:
                    props_h["clt:h0Category"] = _CL(V.HARM_H0[h["harm"]])
                rel = self.g.create_relationship(node, self.actor(h["victim_ref"]), "Documents_Harm",
                                                 relationship_id=f"kb:harm-{e['event_id']}-{i}", properties=props_h)
                self.annotate(rel["@id"], h["support"])

    def relations(self) -> None:
        for r in sorted(self.b["relations"], key=lambda r: r["relation_id"]):
            rel = self.g.create_relationship(self.event(r["from_event"]), self.event(r["to_event"]), RELATION_KIND[r["type"]],
                                             relationship_id=f"kb:relation-{r['relation_id']}",
                                             properties={"clt:assertionStatus": _CL(r["status"])})
            if r["support"]:
                self.annotate(rel["@id"], r["support"])

    def tracks(self) -> None:
        for t in sorted(self.b["tracks"], key=lambda t: t["track_id"]):
            self.g.upsert_node(f"kb:track-{t['track_id']}", types=["uco-core:Grouping"], properties={
                "uco-core:context": [_CL(f"{t['kind']} track")], "clt:trackKind": _CL(t["kind"]),
                "uco-core:object": [_ref(self.event(e)) for e in sorted(t["event_ids"])]})


def evidence_graph(bundle: dict, registry=None) -> CASEGraph:
    em = _Emitter(bundle, registry)
    em.documents()
    em.actors()
    em.events()
    em.relations()
    em.tracks()
    return em.g


def trajectory_graph(bundle: dict, derived: dict) -> CASEGraph:
    """Derived trajectories. Each step carries O_i (clt:stepAffordance, level C) and, kept
    apart, level B (clt:stepRelevantAffordance) and level A (clt:stepAvailableAffordance)
    with the registry entries they rest on (clt:capabilityEntry)."""
    g = _graph(bundle["case_id"])
    for track in derived["tracks"]:
        for L in track["trajectories"]:
            tid = L["trajectory_id"]
            arr, life = f"kb:actions-{tid}", f"kb:trajectory-{tid}"
            for step in L["steps"]:  # referenced actions, typed so the graph stands alone
                g.upsert_node(_Emitter.event(step["event_id"]), types=["uco-action:Action"])
            g.upsert_node(arr, types=["uco-action:ArrayOfAction"], properties={
                "uco-action:action": [_ref(_Emitter.event(s["event_id"])) for s in L["steps"]]})
            g.upsert_node(life, types=["uco-action:ActionLifecycle"], properties={
                "uco-action:phase": _ref(arr), "uco-core:name": _STR(f"trajectory {tid}"),
                "clt:affordanceThreshold": _CL(derived["derivation"]["threshold"]),
                "clt:derivationRule": _CL(derived["derivation"]["rule_version"]),
                "clt:trackKind": _CL(track["kind"])})
            for step in L["steps"]:
                g.create_relationship(life, _Emitter.event(step["event_id"]), "Trajectory_Step",
                                      relationship_id=f"kb:step-{tid}-{step['index']}",
                                      properties={
                                          "clt:stepIndex": {"@type": "xsd:nonNegativeInteger", "@value": str(step["index"])},
                                          "clt:immediateAfterPrevious": {"@type": "xsd:boolean",
                                                                          "@value": "true" if step["immediate_after_previous"] else "false"},
                                          **({"clt:stepAffordance": [_ref(V.AFFORDANCE_CLASSES[o]) for o in step["affordances"]]}
                                             if step["affordances"] else {}),
                                          **({"clt:stepRelevantAffordance": [_ref(V.AFFORDANCE_CLASSES[o]) for o in step.get("action_relevant_affordances", [])]}
                                             if step.get("action_relevant_affordances") else {}),
                                          **({"clt:stepAvailableAffordance": [_ref(V.AFFORDANCE_CLASSES[o]) for o in step.get("available_affordances", [])]}
                                             if step.get("available_affordances") else {}),
                                          **({"clt:capabilityEntry": [_CL(c[0]) for c in step.get("capability_evidence", [])]}
                                             if step.get("capability_evidence") else {})})
    return g


def capability_graph(reg: dict) -> CASEGraph:
    """Affordance level A: what platforms provided, when, according to which public sources."""
    g = CASEGraph(kb_prefix=PLATFORM_BASE, extra_context=CONTEXT)
    kinds = {p["platform_id"]: p["kind"] for p in reg["platforms"]}
    for p in sorted(reg["platforms"], key=lambda p: p["platform_id"]):
        g.upsert_node(PLATFORM_BASE + p["platform_id"], types=[V.PLATFORM_KIND_CLASS[p["kind"]]],
                      properties={"uco-core:name": _STR(p["platform_id"])})
    for c in sorted(reg["capabilities"], key=lambda c: c["capability_id"]):
        if c["platform_id"] not in kinds:
            continue
        ind = f"{PLATFORM_BASE}{c['platform_id']}/affordance/{c['capability_id']}"
        g.upsert_node(ind, types=[V.AFFORDANCE_CLASSES[c["affordance"]]],
                      properties={"uco-core:description": _STR(c["feature"])})
        props: Dict[str, Any] = {"clt:featureTerm": _CL(c["feature"]), "clt:capabilityReview": _CL(c["review_status"]),
                                 "dcterms:source": [_ref(src["url"]) for src in sorted(c["sources"], key=lambda x: x["url"])]}
        if c["valid_from"]:
            props["uco-core:startTime"] = _datetime(_bound(c["valid_from"], False), False)
        if c["valid_to"]:
            props["uco-core:endTime"] = _datetime(_bound(c["valid_to"], True), True)
        g.create_relationship(PLATFORM_BASE + c["platform_id"], ind, "Provides_Affordance",
                              relationship_id=f"{PLATFORM_BASE}{c['platform_id']}/provides/{c['capability_id']}", properties=props)
    return g


def serialize(graph: CASEGraph) -> str:
    """Deterministic JSON-LD: nodes sorted by @id, keys sorted."""
    doc = json.loads(graph.serialize())
    doc["@graph"] = sorted(doc["@graph"], key=lambda n: n["@id"])
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
