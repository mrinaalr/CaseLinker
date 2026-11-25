"""Extracted-feature count for GET /api/stats (`unique_features`).

An extracted feature is a value read from a case record's text and stored for that case. A
list-valued attribute counts each value. Placeholders ("unknown"), program boilerplate, provenance
and copies of other attributes are not features.

Two sources, never both for the same attribute:
- ASSERTED: fields extracted with a span-checked assertion (`field_assertions`). Each distinct
  (case, field, value) in the case's current run counts once, except the roles in EXCLUDED_ROLES.
- COUNTED: the other attributes in `extracted_features` / case columns, per case.

Every attribute stored in `extracted_features` is in ASSERTED_COPIES, COUNTED or EXCLUDED;
tests/api/test_feature_count.py fails when a stored attribute is in none, so a new field cannot
go uncounted by accident. (Until 2026-11-24 the count was a hand-kept list from March 2026 that
missed later fields and counted "unknown" placeholders: 5,161 investigation types, 10,006
relationships.)
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable

_UNSTATED = frozenset({"", "unknown", "null", "none", "n/a", "na", "unspecified"})

# Publishing families for /api/stats `source_count` (NSources): these source labels fold into one family.
SOURCE_COUNT_FAMILY = {
    "DOJ AI CSAM": "DOJ SAFE CHILDHOOD",
    "DOJ ARCHIVES": "DOJ CEOS",
}


def source_count_key(source: str) -> str:
    return SOURCE_COUNT_FAMILY.get(source, source)

ASSERTED_FIELDS = ("age", "date", "sentence", "investigation_type", "legal_context", "prior_history",
                   "cybertip_reporter")
EXCLUDED_ROLES = {
    "program_boilerplate": "dates about the program (e.g. when ICAC was founded), not the case",
    "boilerplate": "investigation types lifted from program or PSA text, not the case",
    "not_age": "a number the age reader rejected as not an age",
    "not_prior": "a prior-history cue the reader rejected",
    "statutory_threshold": "the law's age line (e.g. under 18), not a fact about the case",
}
# extracted_features attributes whose values the assertions above already count
ASSERTED_COPIES = {
    "perpetrator_age": "age assertions",
    "investigation_type": "investigation_type assertions",
    "investigation_types": "investigation_type assertions",
    "legal_context": "legal_context assertions",
    "prior_history": "prior_history assertions",
    "previous_conviction": "prior_history assertions",
    "perpetrator_registered_sex_offender": "prior_history assertions (registered_offender)",
    "cybertip_reporter": "cybertip_reporter assertions",
}


def _json_list(value: Any) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def _stated(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in _UNSTATED


def _items(value: Any) -> int:
    return len([x for x in _json_list(value) if x and not (isinstance(x, str) and not _stated(x))])


def _filled(value: Any) -> bool:
    if isinstance(value, str):
        return _stated(value)
    return value not in (None, "", [], {}) and value is not False


def _prosecution(v: Any) -> int:
    if not isinstance(v, dict):
        return 0
    status = int(_stated(v.get("status") or v.get("booking_status")))
    return status + _items(v.get("charges"))        # sentences are counted from sentence assertions


def _evidence(v: Any) -> int:
    return sum(int(_filled(v.get(k))) for k in ("images", "videos", "storage_size")) if isinstance(v, dict) else 0


def _demographics(v: Any) -> int:
    # victim ages are counted from age assertions
    return sum(int(_filled(v.get(k))) for k in ("age_range", "victim_gender")) if isinstance(v, dict) else 0


COUNTED: Dict[str, Any] = {
    "platforms_used": _items,
    "case_topics": _items,
    "severity_indicators": _items,
    "agencies_involved": _items,
    "perpetrator_admission_themes": _items,
    # Tor, BitTorrent, LimeWire ... are often also platform labels: a value already in platforms_used is a copy.
    "anonymization_network": _items,
    "p2p_clients": _items,
    "relationship_to_victim": lambda v: int(_stated(v)),
    "perpetrator_gender": lambda v: int(_stated(v)),
    "multi_defendant_operation": lambda v: int(v is True),
    "victim_count": lambda v: int(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0),
    "prosecution_outcome": _prosecution,
    "evidence_volume": _evidence,
    "case_demographics": _demographics,
}

EXCLUDED: Dict[str, str] = {
    "agency_grounds": "provenance: where each agency was found",
    "location_grounds": "provenance: where each location was found",
    "person_spans": "provenance: name spans used for masking",
    "comparison_values": "derived comparison keys, not read from the text",
    "ml_features": "model input vector, not an extracted value",
    "date_range": "publication dates, counted from date assertions",
    "document_version_id": "ingest bookkeeping",
    "extraction_run_id": "ingest bookkeeping",
    "press_digest_pollution": "quality flag on the source text",
    "organizations": "superset of agencies_involved (counted there)",
    "pathway_agencies_federal": "derived from agencies_involved",
    "pathway_agencies_state_local": "derived from agencies_involved",
    # Labels count; the quoted spans behind them are listed, not counted (one rule for every span field).
    "severity_phrases": "quoted spans behind severity_indicators (the labels are counted)",
    "perpetrator_admissions": "quoted spans behind perpetrator_admission_themes (the labels are counted)",
    "investigation_technology": ("one flag value ('CyberTipline'); in 745 of 1,810 frozen-corpus cases its only mention is a "
                                 "report-to-the-CyberTipline line (program boilerplate), and the stored value cannot tell the two apart"),
    "locations": ("place names; location_grounds records what a place is (state, city), never its role, so offense "
                  "locations cannot be told from an agency's or court's; left out by the maintainer 2026-11-24"),
}


def _nested(case: Dict[str, Any]) -> Dict[str, Any]:
    nested = case.get("extracted_features") or {}
    if isinstance(nested, str):
        try:
            nested = json.loads(nested)
        except ValueError:
            nested = {}
    return nested if isinstance(nested, dict) else {}


# Fields whose values copy a platform label: count only values not already in platforms_used.
PLATFORM_COPY_FIELDS = ("anonymization_network", "p2p_clients")


def _platform_labels(case: Dict[str, Any], nested: Dict[str, Any]) -> set:
    plats = case["platforms_used"] if "platforms_used" in case else nested.get("platforms_used")
    return {p.strip().lower() for p in _json_list(plats) if isinstance(p, str)}


def count_case_attributes(case: Dict[str, Any]) -> int:
    """Features of one case from the attributes that have no span-checked assertion."""
    nested = _nested(case)
    total = 0
    for key, rule in COUNTED.items():
        value = case[key] if key in case else nested.get(key)
        if key in PLATFORM_COPY_FIELDS:
            plats = _platform_labels(case, nested)
            value = [x for x in _json_list(value) if not (isinstance(x, str) and x.strip().lower() in plats)]
        if key == "case_demographics" and not value:
            value = case.get("victim_demographics") or nested.get("victim_demographics")
        total += rule(value)
    return total


def count_extracted_features(cases: Iterable[Dict[str, Any]], asserted: Dict[str, int]) -> int:
    """Corpus total: per-case attributes plus the asserted values (count_assertion_feature_values)."""
    return sum(count_case_attributes(c) for c in cases) + sum(asserted.get(f, 0) for f in ASSERTED_FIELDS)
