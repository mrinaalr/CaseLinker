"""JSON Schema for a coded case bundle, generated from ``state_machines.evidence.vocab``.

A bundle is one case as coded by one coder (or the adjudicated merge). It holds
documents, verified passages (locator + hash; quote text lives in the local quote
store, never in the bundle), role-neutral participants, events with event-specific
roles, relations and tracks. Trajectories are derived from it, never stored in it.

``python -m state_machines.evidence.schema`` writes ``state_machines/evidence/schema/case_bundle.schema.json``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from state_machines.evidence import vocab as V

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "case_bundle.schema.json"

_ID = {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_.\-]*$", "maxLength": 120}
_SHA = {"type": "string", "pattern": r"^[0-9a-f]{64}$"}
_DAY = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
_DATE = {"type": ["string", "null"], "pattern": r"^\d{4}(-\d{2}(-\d{2})?)?$"}
_TEXT = lambda n: {"type": "string", "maxLength": n}  # noqa: E731
_ENUM = lambda values: {"enum": list(values)}  # noqa: E731
_REF = {"type": "string", "pattern": V.PARTICIPANT_REF_PATTERN}


def _obj(required, props, **extra) -> Dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": list(required),
            "properties": props, **extra}


def _list(item, min_items: int = 0) -> Dict[str, Any]:
    return {"type": "array", "items": item, "minItems": min_items}


def build_schema() -> Dict[str, Any]:
    support = _obj(
        ("passage_id", "facet", "status"),
        {"passage_id": _ID, "facet": _ENUM(V.SUPPORT_FACETS), "status": _ENUM(V.ASSERTION_STATUS),
         "note": _TEXT(300)},
    )
    supports = _list({"$ref": "#/$defs/support"}, 1)
    review = _obj(
        ("status",),
        {"status": _ENUM(V.REVIEW_STATUS), "coders": _list({"type": "string", "pattern": r"^coder_[A-Za-z0-9]+$"}),
         "adjudicator": {"type": ["string", "null"]}, "note": _TEXT(300)},
        description="Coder adjudication: agreement between coders. Never the court's adjudication.",
    )
    page = _obj(
        ("pdf_page", "text_method", "page_text_sha256"),
        {"pdf_page": {"type": "integer", "minimum": 1}, "court_page_label": {"type": ["string", "null"]},
         "text_method": _ENUM(V.TEXT_METHOD), "page_text_sha256": _SHA,
         "ocr_engine": {"type": ["string", "null"]}, "ocr_mean_confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
         "image_checked": {"type": "boolean"}, "limitations": _list(_ENUM(V.PAGE_LIMITATIONS))},
    )
    document = _obj(
        ("doc_id", "doc_type", "source_path", "sha256", "page_count", "pages"),
        {"doc_id": _ID, "doc_type": _ENUM(V.DOC_TYPES), "source_path": _TEXT(300), "sha256": _SHA,
         "ecf_document_number": {"type": ["string", "null"]}, "filed_date": _DATE,
         "page_count": {"type": "integer", "minimum": 1}, "pages": _list(page)},
    )
    passage = _obj(
        ("passage_id", "doc_id", "pdf_page", "char_start", "char_end", "quote_sha256", "source_status", "verification"),
        {"passage_id": _ID, "doc_id": _ID, "pdf_page": {"type": "integer", "minimum": 1},
         "court_locator": {"type": ["string", "null"], "maxLength": 60},
         "char_start": {"type": "integer", "minimum": 0}, "char_end": {"type": "integer", "minimum": 1},
         "quote_sha256": _SHA, "quote_word_count": {"type": "integer", "minimum": 1},
         "source_status": _ENUM(V.SOURCE_STATUS), "source_status_reason": _TEXT(300),
         "verification": _obj(("status", "method"),
                              {"status": _ENUM(V.VERIFICATION_STATUS), "method": _ENUM(V.VERIFICATION_METHOD),
                               "checked_by": {"type": ["string", "null"]}, "note": _TEXT(300)})},
    )
    participant = _obj(
        ("participant_ref", "kind"),
        {"participant_ref": _REF, "kind": _ENUM(V.PARTICIPANT_KINDS),
         "age_band": {"enum": [*V.AGE_BAND, None]}, "description": _TEXT(120),
         "legal_status": _list(_obj(("status", "support"), {"status": _ENUM(V.LEGAL_STATUS), "support": supports})),
         # collectives only: who is a member (uncertain membership allowed) and how many
         "members": _list(_obj(("participant_ref", "status", "support"),
                               {"participant_ref": _REF, "status": _ENUM(V.ASSERTION_STATUS), "support": supports})),
         "count": _obj(("stated",), {"min": {"type": ["integer", "null"], "minimum": 0},
                                     "max": {"type": ["integer", "null"], "minimum": 0},
                                     "stated": _ENUM(V.COUNT_STATED), "support": _list({"$ref": "#/$defs/support"})})},
        description="Role-neutral participant: a person, an undercover persona, a collective or an organization.",
    )
    time_assertion = _obj(
        ("precision", "earliest", "latest", "basis", "status", "passage_ids"),
        {"expression": _TEXT(120), "precision": _ENUM(V.TIME_PRECISION), "earliest": _DAY, "latest": _DAY,
         "basis": _ENUM(V.TIME_BASIS), "status": _ENUM(V.ASSERTION_STATUS), "passage_ids": _list(_ID, 1)},
        description="One dated assertion about when the act happened, with its source expression and normalized bounds.",
    )
    time = _obj(
        ("assertions",),
        {"assertions": _list({"$ref": "#/$defs/time_assertion"}), "conflict_flagged": {"type": "boolean"},
         "note": _TEXT(300)},
        description="Every dated assertion is kept. Disjoint assertions must be flagged as a conflict, never resolved.",
    )
    affordance = _obj(
        ("affordance", "basis", "status", "support"),
        {"affordance": _ENUM(V.AFFORDANCES), "basis": _ENUM(V.AFFORDANCE_BASIS), "feature_term": _TEXT(80),
         "platform_surface": _TEXT(60), "status": _ENUM(V.ASSERTION_STATUS), "support": supports,
         "counterparty_is_undercover": {"type": "boolean"}, "note": _TEXT(300)},
    )
    candidate = _obj(
        ("candidate", "basis", "status", "support"),
        {"candidate": _ENUM(V.CANDIDATE_AFFORDANCES), "basis": _ENUM(V.AFFORDANCE_BASIS), "feature_term": _TEXT(80),
         "platform_surface": _TEXT(60), "status": _ENUM(V.ASSERTION_STATUS), "support": supports,
         "would_otherwise_map_to": {"enum": [*V.AFFORDANCES, None]}},
    )
    interaction = _obj(
        ("platform_surface", "platform_key", "mode", "audience", "status", "support"),
        {"platform_surface": _TEXT(60),
         "platform_key": {"type": "string", "pattern": r"^(unnamed:[a-z0-9 _\-]{1,50}|[A-Za-z0-9][A-Za-z0-9 ._+\-]{0,59})$"},
         "mode": _ENUM(V.INTERACTION_MODES), "audience": _ENUM(V.AUDIENCES), "feature_term": _TEXT(80),
         "configuration": _list(_obj(("feature_term", "setting", "support"),
                                     {"feature_term": _TEXT(80), "setting": _ENUM(V.FEATURE_SETTINGS), "support": supports})),
         "status": _ENUM(V.ASSERTION_STATUS), "support": supports, "note": _TEXT(300)},
        description="Documented platform interaction: the act went through, from or to the platform, or was done to it.",
    )
    access = _obj(
        ("form", "target_ref", "status", "support"),
        {"form": _ENUM(V.ACCESS_FORMS), "target_ref": _REF, "status": _ENUM(V.ASSERTION_STATUS), "support": supports},
    )
    harm = _obj(
        ("harm", "victim_ref", "victim_kind", "status", "support"),
        {"harm": _ENUM(V.HARM_CODES), "victim_ref": _REF, "victim_kind": _ENUM(V.VICTIM_KIND),
         "status": _ENUM(V.ASSERTION_STATUS), "support": supports,
         "other_label": _TEXT(80)},
    )
    event = _obj(
        ("event_id", "actor", "action", "outcome", "description", "support", "status", "time",
         "affordances", "access", "harms", "review"),
        {"event_id": _ID,
         "actor": _obj(("participant_ref", "role"), {"participant_ref": _REF, "role": _ENUM(V.ACTOR_ROLES)}),
         "co_actors": _list(_obj(("participant_ref", "role", "mode"),
                                 {"participant_ref": _REF, "role": _ENUM(V.ACTOR_ROLES), "mode": _ENUM(V.PARTICIPATION_MODES)})),
         "targets": _list(_obj(("participant_ref", "role"), {"participant_ref": _REF, "role": _ENUM(V.TARGET_ROLES)})),
         "action": _ENUM(V.ACTION_CODES), "other_action_label": _TEXT(80), "outcome": _ENUM(V.OUTCOMES),
         "description": {"type": "string", "minLength": 5, "maxLength": 200}, "support": supports,
         "status": _ENUM(V.ASSERTION_STATUS), "time": {"$ref": "#/$defs/time"},
         "repetition": _obj(("kind",), {"kind": _ENUM(V.REPETITION_KIND), "count": {"type": ["integer", "null"], "minimum": 2},
                                        "passage_ids": _list(_ID)}),
         # platform named in connection with the event; no claim that the act went through it
         "platform_mentions": _list(_obj(("platform_surface", "passage_ids"),
                                         {"platform_surface": _TEXT(60), "passage_ids": _list(_ID, 1)})),
         # the act was carried out through this platform (or feature): uco-action:instrument
         "platform_interactions": _list({"$ref": "#/$defs/interaction"}),
         # telephony, email, mail or in person: a channel, never a platform (I3)
         "channels": _list(_obj(("channel", "status", "support"),
                                {"channel": _ENUM(V.CHANNELS), "status": _ENUM(V.ASSERTION_STATUS), "support": supports})),
         "affordances": _list({"$ref": "#/$defs/affordance"}),
         "candidate_affordances": _list({"$ref": "#/$defs/candidate"}),
         "access": _list({"$ref": "#/$defs/access"}), "harms": _list({"$ref": "#/$defs/harm"}),
         "review": {"$ref": "#/$defs/review"}, "prior_artifact_refs": _list(_TEXT(200)), "notes": _TEXT(600)},
    )
    relation = _obj(
        ("relation_id", "type", "from_event", "to_event", "basis", "status", "support"),
        {"relation_id": _ID, "type": _ENUM(V.RELATION_TYPES), "from_event": _ID, "to_event": _ID,
         "basis": _ENUM(V.RELATION_BASIS), "status": _ENUM(V.ASSERTION_STATUS), "support": _list({"$ref": "#/$defs/support"}),
         "review": {"$ref": "#/$defs/review"}, "note": _TEXT(300)},
    )
    track = _obj(
        ("track_id", "kind", "event_ids"),
        {"track_id": _ID, "kind": _ENUM(V.TRACK_KINDS), "anchor_ref": _REF, "event_ids": _list(_ID, 1), "note": _TEXT(300)},
    )
    coding = _obj(
        ("coder_id", "method", "coded_on"),
        {"coder_id": {"type": "string", "pattern": r"^coder_[A-Za-z0-9]+$"}, "method": _ENUM(V.CODER_METHOD),
         "model": {"type": ["string", "null"]}, "coded_on": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
         "blind_to": _list(_TEXT(60)), "note": _TEXT(600)},
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://w3id.org/caselinker/trajectory/schema/case_bundle/" + V.SCHEMA_VERSION,
        "title": "CaseLinker coded case bundle (evidence layer)",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "codebook_version", "case_id", "coding", "documents", "passages",
                     "participants", "events", "relations", "tracks"],
        "properties": {
            "schema_version": {"enum": list(V.SUPPORTED_SCHEMA_VERSIONS)},
            "codebook_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "case_id": {"type": "string", "pattern": r"^[a-z0-9_]+$"},
            "coding": {"$ref": "#/$defs/coding"},
            "documents": _list({"$ref": "#/$defs/document"}, 1),
            "passages": _list({"$ref": "#/$defs/passage"}),
            "participants": _list({"$ref": "#/$defs/participant"}, 1),
            "events": _list({"$ref": "#/$defs/event"}),
            "relations": _list({"$ref": "#/$defs/relation"}),
            "tracks": _list({"$ref": "#/$defs/track"}),
            "notes": _TEXT(2000),
        },
        "$defs": {"support": support, "review": review, "interaction": interaction, "document": document, "passage": passage, "participant": participant,
                  "time_assertion": time_assertion, "time": time, "affordance": affordance, "candidate": candidate, "access": access, "harm": harm,
                  "event": event, "relation": relation, "track": track, "coding": coding},
    }


def schema_json() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":  # pragma: no cover
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(schema_json(), encoding="utf-8")
    print(SCHEMA_PATH)
