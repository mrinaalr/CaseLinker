"""Emit CASE/UCO/CAC graphs from a coded bundle and its derived trajectories.

Built with the pinned CASE-UCO SDK (``case_uco.CASEGraph``). Canonical terms do the
structural work; the experimental ``clt:`` extension carries evidence status, codes and
the two classes no canonical term covers (ontology/extensions/caselinker-trajectory/0.3.0/).

Evidence graph (canonical, one per case):
  investigation   case-investigation:Investigation, uco-core:object -> documents
  document        uco-observable:ObservableObject + FileFacet + ContentDataFacet/Hash (SHA-256)
  participant     uco-identity:Person (person), uco-identity:Identity (undercover persona),
                  uco-identity:Organization, or clt:Collective; pseudonymous (P1, P2, ...)
  legal status    participant --Has_Legal_Status--> investigation, clt:legalStatus, cited
  membership      member --Member_Of--> collective, with status, cited
  event           uco-action:Action, performer/participant/object, clt:actionCode/outcome/status
  event role      participant --Has_Event_Role--> action, clt:eventRole (+ participation mode)
  time            action --clt:timeAssertion--> clt:TimeAssertion (each dated assertion, cited)
  relation        uco-core:Relationship between actions (Occurs_Before, ..., Possibly_Same_Act)
  affordance      cac-platforms:<Class> individual --Supports_Action--> action (level C)
  platform        action --Carried_Out_Through / Moved_From / Moved_To / Acted_On--> platform
  harm            action --Documents_Harm--> victim participant, clt:victimKind
  track           uco-core:Grouping of actions
  evidence        oa:Annotation(body = assertion, target = SpecificResource(source = document,
                  FragmentSelector page=N refinedBy TextPositionSelector)), quote hash only

Trajectory graph (derived view): uco-action:ActionLifecycle + uco-action:ArrayOfAction, and
one uco-core:Relationship "Trajectory_Step" per step with clt:stepIndex and clt:stepAffordance.

No person names, quote text, phases, terminal states or probabilities are written.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List

from case_uco import CASEGraph
from case_uco.graph import canonical_hex_binary

from state_machines.evidence import vocab as V

BASE = "https://w3id.org/caselinker/resource/pacer/"
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
    "RESUMES_AFTER": "Resumes_After", "SAME_MATERIAL": "Same_Material", "SAME_ACT": "Possibly_Same_Act",
}
INTERACTION_KIND = {"through": "Carried_Out_Through", "from": "Moved_From", "to": "Moved_To", "acted_on": "Acted_On"}
PARTICIPANT_TYPE = {
    "person": "uco-identity:Person", "persona": "uco-identity:Identity",
    "organization": "uco-identity:Organization", "collective": "clt:Collective",
}
_STR = lambda v: {"@type": "xsd:string", "@value": v}  # noqa: E731  (UCO string properties)
_CL = lambda v: v  # noqa: E731  plain literals for clt: codes, matching the sh:in lists of the extension shapes
_INT = lambda v: {"@type": "xsd:nonNegativeInteger", "@value": str(v)}  # noqa: E731
_BOOL = lambda v: {"@type": "xsd:boolean", "@value": "true" if v else "false"}  # noqa: E731


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "unnamed"


def _h(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def _graph(case_id: str) -> CASEGraph:
    return CASEGraph(kb_prefix=f"{BASE}{case_id}/", extra_context=CONTEXT)


def _ref(node_id: str) -> Dict[str, str]:
    return {"@id": node_id}


def _datetime(day: str, end: bool) -> Dict[str, str]:
    return {"@type": "xsd:dateTime", "@value": f"{day}T{'23:59:59' if end else '00:00:00'}Z"}


class _Emitter:
    def __init__(self, bundle: dict):
        self.b = bundle
        self.g = _graph(bundle["case_id"])
        self.passages = {p["passage_id"]: p for p in bundle["passages"]}
        self.pages = {(d["doc_id"], pg["pdf_page"]): pg for d in bundle["documents"] for pg in d["pages"]}

    # -- identifiers ---------------------------------------------------------------
    @staticmethod
    def doc(doc_id: str) -> str:
        return f"kb:document-{doc_id}"

    @staticmethod
    def participant(ref: str) -> str:
        return f"kb:participant-{ref}"

    @staticmethod
    def event(event_id: str) -> str:
        return f"kb:action-{event_id}"

    def platform(self, key: str, surface: str) -> str:
        """Named platforms share one IRI across cases; unnamed ones stay inside the case."""
        if key.startswith("unnamed:"):
            node = f"kb:platform-{_slug(key)}"
        else:
            node = PLATFORM_BASE + _slug(key)
        self.g.upsert_node(node, types=[V.UCO_OBSERVABLE + "ObservableObject"], properties={"uco-core:name": _STR(surface)})
        return node

    # -- evidence ------------------------------------------------------------------
    def annotate(self, body: str, supports: List[dict]) -> None:
        for s in sorted(supports, key=lambda s: (s["passage_id"], s["facet"], s["status"])):
            p = self.passages[s["passage_id"]]
            key = _h(body, s["passage_id"], s["facet"])
            page_sel, pos_sel, target = f"kb:selector-page-{key}", f"kb:selector-text-{key}", f"kb:target-{key}"
            self.g.upsert_node(pos_sel, types=["oa:TextPositionSelector"], properties={
                "oa:start": _INT(p["char_start"]), "oa:end": _INT(p["char_end"])})
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

    @staticmethod
    def _passage_supports(pids: List[str], facet: str, status: str) -> List[dict]:
        return [{"passage_id": pid, "facet": facet, "status": status} for pid in pids]

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
                "uco-observable:fileName": _STR(f"{self.b['case_id']} {d['doc_type']}.pdf"),
                "uco-observable:extension": _STR("pdf")})
            self.g.upsert_node(node, types=["uco-observable:ObservableObject"], properties={
                "uco-core:hasFacet": [_ref(file_id), _ref(content_id)],
                "uco-core:description": _STR(f"{d['doc_type']} ({V.DOC_TYPES[d['doc_type']][0].lower()} by default)")})
        self.g.upsert_node("kb:investigation", types=["case-investigation:Investigation"], properties={
            "uco-core:name": _STR(f"PACER case {self.b['case_id']}"),
            "uco-core:object": [_ref(self.doc(d["doc_id"])) for d in sorted(self.b["documents"], key=lambda d: d["doc_id"])]})

    def participants(self) -> None:
        for a in sorted(self.b["participants"], key=lambda a: int(a["participant_ref"][1:])):
            ref, node = a["participant_ref"], self.participant(a["participant_ref"])
            props: Dict[str, Any] = {"clt:participantKind": _CL(a["kind"]),
                                     "uco-core:description": _STR(f"pseudonymous {a['kind']} {ref}")}
            count = a.get("count")
            if count:
                props["clt:countStated"] = _CL(count["stated"])
                if count.get("min") is not None:
                    props["clt:countMin"] = _INT(count["min"])
                if count.get("max") is not None:
                    props["clt:countMax"] = _INT(count["max"])
            self.g.upsert_node(node, types=[PARTICIPANT_TYPE[a["kind"]]], properties=props)
            if count and count.get("support"):
                self.annotate(node, count["support"])
            for i, ls in enumerate(sorted(a.get("legal_status", []), key=lambda x: x["status"])):
                rel = self.g.create_relationship(node, "kb:investigation", "Has_Legal_Status",
                                                 relationship_id=f"kb:legal-{ref}-{i}",
                                                 properties={"clt:legalStatus": _CL(ls["status"])})
                self.annotate(rel["@id"], ls["support"])
            for m in sorted(a.get("members", []), key=lambda m: m["participant_ref"]):
                rel = self.g.create_relationship(self.participant(m["participant_ref"]), node, "Member_Of",
                                                 relationship_id=f"kb:member-{m['participant_ref']}-{ref}",
                                                 properties={"clt:assertionStatus": _CL(m["status"])})
                self.annotate(rel["@id"], m["support"])

    def _role(self, ref: str, action: str, eid: str, role: str, mode: str = "") -> None:
        props = {"clt:eventRole": _CL(role)}
        if mode:
            props["clt:participationMode"] = _CL(mode)
        self.g.create_relationship(self.participant(ref), action, "Has_Event_Role",
                                   relationship_id=f"kb:role-{eid}-{ref}-{role}", properties=props)

    def events(self) -> None:
        for e in sorted(self.b["events"], key=lambda e: e["event_id"]):
            node, eid = self.event(e["event_id"]), e["event_id"]
            assertions = e["time"]["assertions"]
            props: Dict[str, Any] = {
                "uco-action:performer": _ref(self.participant(e["actor"]["participant_ref"])),
                "uco-core:description": _STR(e["description"]),
                "clt:actionCode": _CL(e["action"]), "clt:outcome": _CL(e["outcome"]),
                "clt:assertionStatus": _CL(e["status"]), "clt:reviewStatus": _CL(e["review"]["status"]),
                "clt:timeConflict": _BOOL(bool(e["time"].get("conflict_flagged"))),
            }
            if e.get("targets"):
                props["uco-action:object"] = [_ref(self.participant(t["participant_ref"]))
                                              for t in sorted(e["targets"], key=lambda t: t["participant_ref"])]
            if e.get("co_actors"):
                props["uco-action:participant"] = [_ref(self.participant(c["participant_ref"]))
                                                   for c in sorted(e["co_actors"], key=lambda c: c["participant_ref"])]
            direct_days = [a for a in assertions if a["status"] == "DIRECT" and a["precision"] == "day"]
            if len(assertions) == 1 and direct_days and not e["time"].get("conflict_flagged"):
                props["uco-action:startTime"] = _datetime(direct_days[0]["earliest"], False)
                props["uco-action:endTime"] = _datetime(direct_days[0]["latest"], True)
            if e.get("channels"):
                props["clt:channel"] = [_CL(c["channel"]) for c in sorted(e["channels"], key=lambda c: c["channel"])]
            rep = e.get("repetition") or {}
            if rep.get("count"):
                props["uco-action:actionCount"] = _INT(rep["count"])
            time_nodes = []
            for i, a in enumerate(assertions):
                tnode = f"kb:time-{eid}-{i}"
                tprops = {"clt:timeEarliest": _CL(a["earliest"]), "clt:timeLatest": _CL(a["latest"]),
                          "clt:timePrecision": _CL(a["precision"]), "clt:timeBasis": _CL(a["basis"]),
                          "clt:assertionStatus": _CL(a["status"])}
                if a.get("expression"):
                    tprops["clt:timeExpression"] = _CL(a["expression"])
                self.g.upsert_node(tnode, types=["clt:TimeAssertion"], properties=tprops)
                self.annotate(tnode, self._passage_supports(a["passage_ids"], "time", a["status"]))
                time_nodes.append(_ref(tnode))
            if time_nodes:
                props["clt:timeAssertion"] = time_nodes
            self.g.upsert_node(node, types=["uco-action:Action"], properties=props)
            self.annotate(node, e["support"] + [s for c in e.get("channels", []) for s in c["support"]])
            self._role(e["actor"]["participant_ref"], node, eid, e["actor"]["role"], "performer")
            for c in e.get("co_actors", []):
                self._role(c["participant_ref"], node, eid, c["role"], c["mode"])
            for t in e.get("targets", []):
                self._role(t["participant_ref"], node, eid, t["role"])
            for a in sorted(e.get("affordances", []), key=lambda a: a["affordance"]):
                ind = f"kb:affordance-{eid}-{a['affordance']}"
                self.g.upsert_node(ind, types=[V.AFFORDANCE_CLASSES[a["affordance"]]], properties={
                    "uco-core:description": _STR(f"{a['affordance']} as used in {eid}")})
                rel = self.g.create_relationship(ind, node, "Supports_Action",
                                                 relationship_id=f"kb:supports-{eid}-{a['affordance']}",
                                                 properties={"clt:affordanceBasis": _CL(a["basis"]),
                                                             "clt:assertionStatus": _CL(a["status"]),
                                                             **({"clt:featureTerm": _CL(a["feature_term"])} if a.get("feature_term") else {})})
                self.annotate(rel["@id"], a["support"])
            for inter in sorted(e.get("platform_interactions", []), key=lambda i: (i["platform_key"], i["mode"])):
                pnode = self.platform(inter["platform_key"], inter["platform_surface"])
                if inter["mode"] in ("through", "to"):
                    self.g.add_property(node, "uco-action:instrument", _ref(pnode))
                iprops = {"clt:assertionStatus": _CL(inter["status"]), "clt:interactionMode": _CL(inter["mode"]),
                          "clt:audience": _CL(inter["audience"])}
                if inter.get("feature_term"):
                    iprops["clt:featureTerm"] = _CL(inter["feature_term"])
                if inter.get("configuration"):
                    iprops["clt:featureSetting"] = [_CL(f"{c['feature_term']}={c['setting']}") for c in inter["configuration"]]
                rel = self.g.create_relationship(node, pnode, INTERACTION_KIND[inter["mode"]],
                                                 relationship_id=f"kb:{inter['mode']}-{eid}-{_slug(inter['platform_key'])}",
                                                 properties=iprops)
                self.annotate(rel["@id"], inter["support"] + [s for c in inter.get("configuration", []) for s in c["support"]])
            for m in sorted(e.get("platform_mentions", []), key=lambda m: m["platform_surface"]):
                pnode = self.platform(m["platform_surface"], m["platform_surface"])
                rel = self.g.create_relationship(node, pnode, "Platform_Named_With",
                                                 relationship_id=f"kb:named-{eid}-{_slug(m['platform_surface'])}")
                self.annotate(rel["@id"], self._passage_supports(m["passage_ids"], "platform", "DIRECT"))
            for i, h in enumerate(sorted(e.get("harms", []), key=lambda h: (h["harm"], h["victim_ref"]))):
                props_h = {"clt:harmCode": _CL(h["harm"]), "clt:assertionStatus": _CL(h["status"]),
                           "clt:victimKind": _CL(h["victim_kind"])}
                if V.HARM_H0[h["harm"]]:
                    props_h["clt:h0Category"] = _CL(V.HARM_H0[h["harm"]])
                rel = self.g.create_relationship(node, self.participant(h["victim_ref"]), "Documents_Harm",
                                                 relationship_id=f"kb:harm-{eid}-{i}", properties=props_h)
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
            props: Dict[str, Any] = {"uco-core:context": [_CL(f"{t['kind']} track")], "clt:trackKind": _CL(t["kind"]),
                                     "uco-core:object": [_ref(self.event(e)) for e in sorted(t["event_ids"])]}
            self.g.upsert_node(f"kb:track-{t['track_id']}", types=["uco-core:Grouping"], properties=props)


def evidence_graph(bundle: dict) -> CASEGraph:
    em = _Emitter(bundle)
    em.documents()
    em.participants()
    em.events()
    em.relations()
    em.tracks()
    return em.g


def trajectory_graph(bundle: dict, derived: dict) -> CASEGraph:
    """Derived view. Each step carries O_i (clt:stepAffordance, level C) and, kept apart,
    level B (clt:stepRelevantAffordance) and level A (clt:stepAvailableAffordance) with the
    registry entries they rest on (clt:capabilityEntry: platform|class|availability)."""
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
                "uco-action:phase": _ref(arr), "uco-core:name": _STR(f"derived trajectory {tid}"),
                "clt:affordanceThreshold": _CL(derived["derivation"]["threshold"]),
                "clt:derivationRule": _CL(derived["derivation"]["rule_version"]),
                "clt:trackKind": _CL(track["kind"])})
            for step in L["steps"]:
                g.create_relationship(life, _Emitter.event(step["event_id"]), "Trajectory_Step",
                                      relationship_id=f"kb:step-{tid}-{step['index']}",
                                      properties={
                                          "clt:stepIndex": _INT(step["index"]),
                                          "clt:immediateAfterPrevious": _BOOL(step["immediate_after_previous"]),
                                          **({"clt:stepAffordance": [_ref(V.AFFORDANCE_CLASSES[o]) for o in step["affordances"]]}
                                             if step["affordances"] else {}),
                                          **({"clt:stepRelevantAffordance": [_ref(V.AFFORDANCE_CLASSES[o]) for o in step.get("action_relevant_affordances", [])]}
                                             if step.get("action_relevant_affordances") else {}),
                                          **({"clt:stepAvailableAffordance": [_ref(V.AFFORDANCE_CLASSES[o]) for o in step.get("available_affordances", [])]}
                                             if step.get("available_affordances") else {}),
                                          **({"clt:capabilityEntry": [_CL("|".join(c)) for c in step.get("capability_evidence", [])]}
                                             if step.get("capability_evidence") else {})})
    return g


def capability_graph(registry_data: dict) -> CASEGraph:
    """Level A: what platforms provided, when, according to which public sources."""
    from state_machines.trajectories.affordances import _period_bound

    g = CASEGraph(kb_prefix=PLATFORM_BASE, extra_context=CONTEXT)
    for _key, plat in sorted(registry_data["platforms"].items()):
        pnode = PLATFORM_BASE + _slug(plat["name"])
        g.upsert_node(pnode, types=[V.UCO_OBSERVABLE + "ObservableObject"], properties={"uco-core:name": _STR(plat["name"])})
        for cls, cap in sorted(plat["capabilities"].items()):
            urls = sorted({ev["url"] for ev in (cap.get("evidence") or []) if ev.get("url")})
            if str(cap.get("native", "")).lower() in ("no", "false") or not urls:
                continue
            ind = f"{pnode}/affordance/{cls}"
            g.upsert_node(ind, types=[V.AFFORDANCE_CLASSES[cls]], properties={"uco-core:description": _STR(f"{cls} on {plat['name']}")})
            props: Dict[str, Any] = {"clt:capabilityConfidence": _CL(str(cap.get("confidence", "uncertain"))),
                                     "dcterms:source": [_ref(u) for u in urls]}
            lo, hi = _period_bound(cap.get("first_available"), False), _period_bound(cap.get("ended"), True)
            if lo:
                props["uco-core:startTime"] = _datetime(lo.isoformat(), False)
            if hi:
                props["uco-core:endTime"] = _datetime(hi.isoformat(), True)
            g.create_relationship(pnode, ind, "Provides_Affordance", relationship_id=f"{pnode}/provides/{cls}", properties=props)
    return g


def serialize(graph: CASEGraph) -> str:
    """Deterministic JSON-LD: nodes sorted by @id, keys sorted."""
    doc = json.loads(graph.serialize())
    doc["@graph"] = sorted(doc["@graph"], key=lambda n: n["@id"])
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
