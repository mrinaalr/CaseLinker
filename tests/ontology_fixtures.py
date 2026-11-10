"""Made-up cases that reach every branch of the CAC mapper.

Every name, place mention and quote here is invented. The case dicts have the
shape ``CaseStorage.get_case`` returns (``ml_features`` under
``extracted_features``, as stored).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

_GROUNDED_PLACE = {
    "mention": "Campton Hills", "slug": "campton-hills-village", "status": "grounded",
    "reason": "place_match", "fips": "1710906", "geoid": "1710906",
    "entity_name": "Campton Hills village", "entity_kind": "place", "state_hint": "IL",
    "hint_source": "dateline", "gazetteer_version": "2024.1",
}
_UNGROUNDED_PLACE = {
    "mention": "Springfield", "slug": "springfield", "status": "ambiguous",
    "reason": "multiple_states", "fips": None, "geoid": None, "entity_name": None,
    "entity_kind": None, "state_hint": None, "hint_source": "none", "gazetteer_version": "2024.1",
}
_NCMEC = {
    "mention": "NCMEC", "status": "grounded", "reason": "federal_table", "ori": None,
    "code": "NCMEC", "agency_name": "National Center for Missing & Exploited Children",
    "agency_kind": "nonprofit", "state_hint": None, "hint_source": "federal", "slug": "ncmec",
    "registry_version": "cde-2026-10-20",
}
_FBI = dict(_NCMEC, mention="FBI", code="FBI", agency_name="Federal Bureau of Investigation",
            agency_kind="federal", slug="fbi")

_TIP_TEXT = (
    "SPRINGFIELD – Wren Halloway, 37, of Campton Hills, was sentenced to 190 months in prison. "
    "Halloway was caught after the social media app Kik submitted a CyberTip to the National "
    "Center for Missing and Exploited Children about someone who uploaded videos. "
    "\"I have a problem,\" Halloway told agents."
)

FULL_CASE: Dict[str, Any] = {
    "id": "fixture_full_001",
    "source": "TEST SOURCE",
    "source_url": "https://www.justice.gov/usao-ndil/pr/fixture-full-001",
    "date_start": "2024-10-16",
    "date_end": "2024-10-16",
    "date_range": {"start": "2024-10-16", "end": "2024-10-16"},
    "victim_count": 2,
    "perpetrator_count": None,
    "perpetrator_age": [37],
    "perpetrator_registered_sex_offender": True,
    "relationship_to_victim": "family",
    "platforms_used": ["Kik", "Cash App", "social media"],
    "p2p_clients": ["BitTorrent"],
    "anonymization_network": ["Tor"],
    "investigation_type": "unknown",
    "investigation_types": ["cybertip", "unknown"],
    "investigation_technology": ["CyberTipline", "PhotoDNA"],
    "agencies_involved": ["NCMEC", "FBI", "Halloway County Sheriff"],
    "agency_grounds": [_NCMEC, _FBI],
    "organizations": [],
    "locations": ["Campton Hills", "Springfield"],
    "location_grounds": [_GROUNDED_PLACE, _UNGROUNDED_PLACE],
    "prosecution_outcome": {
        "booking_status": "sentenced",
        "charges": [
            {"count": 3, "charge": "sexual exploitation of a minor"},
            {"count": 1, "charge": "sextortion"},
            {"count": 1, "charge": "possession of child pornography"},
        ],
        "jail": None,
        "sentences": ["190 Months"],
    },
    "prosecution_outcomes": [],
    "severity_indicators": ["sexual_abuse", "multiple_perpetrators"],
    "case_topics": ["csam", "sextortion", "grooming", "production", "multi_state"],
    "perpetrator_admissions": [
        {
            "quote": "I have a problem", "quote_type": "direct", "frame": "told_agents",
            "themes": ["recidivism_escalation"], "confidence": "high",
            "context": "Defendant-1 told agents \"I have a problem\"",
        }
    ],
    "perpetrator_admission_themes": ["recidivism_escalation"],
    "press_digest_pollution": False,
    "cybertip_reporter": {"kind": "esp", "esps": ["Kik"], "category": None},
    "tags": ["fixture"],
    "notes": None,
    "case_text": _TIP_TEXT,
    "raw_data": {"case_text": _TIP_TEXT},
    "extracted_features": {
        "ml_features": {
            "semantic_severity": {
                "scores": {
                    "grooming": 0.61, "sextortion": 0.52, "production_csam": 0.30,
                    "possession_csam": 0.70, "dissemination": 0.47,
                    "exploitive_positions": 0.10, "registered_sex_offender": 0.66,
                    "evidence_seizure": 0.55,
                },
            }
        }
    },
    "created_at": "2026-10-18T02:38:15.185052",
    "updated_at": "2026-10-18 05:52:13.049383",
}

ARREST_CASE: Dict[str, Any] = {
    "id": "fixture_arrest_002",
    "source": "TEST SOURCE",
    "source_url": None,
    "date_start": "2017-03-01",
    "date_range": {"start": "2017-03-01", "end": "2017-03-01"},
    "victim_count": None,
    "perpetrator_count": None,
    "perpetrator_age": [],
    "platforms_used": ["Snapchat"],
    "investigation_type": "undercover",
    "investigation_types": ["undercover"],
    "agencies_involved": ["NCMEC"],
    "agency_grounds": [_NCMEC],
    "locations": [],
    "prosecution_outcome": {"booking_status": "arrested", "charges": [{"count": 1, "charge": "luring"}]},
    "severity_indicators": [],
    "case_topics": ["online_only"],
    "case_text": "Police arrested a man. NCMEC is a partner of the task force.",
}

EMPTY_CASE: Dict[str, Any] = {
    "id": "fixture_empty_003",
    "source": "TEST SOURCE",
    "date_start": None,
    "victim_count": None,
    "perpetrator_age": [],
    "case_topics": [],
    "case_text": "A roundup of prevention tips for parents.",
}

CASES: List[Dict[str, Any]] = [FULL_CASE, ARREST_CASE, EMPTY_CASE]

# Stored assertions for FULL_CASE (offsets into _TIP_TEXT).
_KIK = _TIP_TEXT.index("Kik")
_TIP = _TIP_TEXT.index("CyberTip")
FULL_CASE_ASSERTIONS: List[Dict[str, Any]] = [
    {
        "field": "investigation_type", "method": "regex", "method_version": "regex_3.0.1",
        "family": "surface_pattern", "value": "cybertip", "role": "case_action",
        "span_start": _TIP, "span_end": _TIP + 8, "span_text": "CyberTip", "confidence": 0.85,
    },
    {
        "field": "age", "method": "regex", "method_version": "regex_3.0.1",
        "family": "surface_pattern", "value": 37, "role": "perpetrator",
        "span_start": _TIP_TEXT.index("37"), "span_end": _TIP_TEXT.index("37") + 2,
        "span_text": "37", "confidence": 0.9,
    },
]
FULL_CASE_ASSERTIONS.append({
    "field": "cybertip_reporter", "method": "regex", "method_version": "regex_3.0.1",
    "family": "surface_pattern", "value": "Kik", "role": "named_esp",
    "span_start": _KIK, "span_end": _KIK + 3, "span_text": "Kik", "confidence": 0.9,
})
FULL_CASE_RESOLUTIONS: Dict[str, Dict[str, Any]] = {
    "investigation_type": {"status": "resolved", "rule_set_version": "resolve_v3.0",
                           "final_value": ["cybertip"]},
    "age": {"status": "resolved", "rule_set_version": "resolve_v3.0",
            "final_value": {"perpetrators": [37], "victims": []}},
    "cybertip_reporter": {"status": "resolved", "rule_set_version": "resolve_v3.0",
                          "final_value": {"kind": "esp", "esps": ["Kik"], "category": None}},
}


def case(name: str) -> Dict[str, Any]:
    """A fresh copy, so a mapper that mutates its input cannot leak between tests."""
    return copy.deepcopy({c["id"]: c for c in CASES}[name])
