"""
Persistence helpers: separate raw ingestion material from structured extracted features.

- raw_data column: JSON from ingestion (includes case_text, source_file, etc.).
- extracted_features column: structured fields only — no duplicate narrative, no duplicate
  columns already stored on the cases row (see _SLIM_EXCLUDED_KEYS).

At read time, hydrate_case_text_from_raw_data() can copy case_text from raw_data when
the raw column is present (include_raw_data=True or get_case).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

# Omitted from extracted_features blob: narrative, raw duplicate, and fields already
# persisted as columns on `cases` (avoids triplicating the same strings in SQLite/Postgres).
_SLIM_EXCLUDED_KEYS = frozenset(
    {
        "case_text",
        "raw_data",
        "extracted_features",
        "id",
        "notes",
        "tags",
        "source",
        "date_start",
        "date_end",
        "victim_count",
        "perpetrator_count",
        "relationship_to_victim",
        "platforms_used",
        "severity_indicators",
        "case_topics",
        "created_at",
        "updated_at",
    }
)


def dumps_json_safe(value: Any) -> str:
    """
    JSON-serialize analysis/cache payloads that may contain datetime (or other)
    non-JSON types. Prefer orjson when available; fall back to stdlib + default=str.
    """
    try:
        import orjson

        return orjson.dumps(value, default=str).decode("utf-8")
    except ImportError:
        return json.dumps(value, default=str)


def investigation_types_for_case(case: Dict[str, Any]) -> List[str]:
    """
    All investigation type tags for a case (list field + legacy single investigation_type).
    """
    types = case.get("investigation_types")
    if isinstance(types, list):
        out = [str(t).strip().lower() for t in types if t is not None and str(t).strip()]
        if out:
            return out
    t = case.get("investigation_type")
    if t is not None and str(t).strip():
        return [str(t).strip().lower()]
    return []


def slim_extracted_features_for_storage(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the JSON object stored in cases.extracted_features.

    Excludes raw narrative and table-duplicated fields so the blob holds only derived /
    non-column structure (e.g. comparison_values, date_range, evidence_volume, demographics,
    investigation_technology, anonymization_network, p2p_clients) used by merge and analysis.
    """
    return {k: v for k, v in case.items() if k not in _SLIM_EXCLUDED_KEYS}


def hydrate_case_text_from_raw_data(case_dict: Dict[str, Any]) -> None:
    """
    If case_text is missing, copy from raw_data.case_text (in-place).

    Call when raw_data was loaded from DB (e.g. get_case or get_all_cases with
    include_raw_data=True). Do not call when raw_data was stripped for slim API responses.
    """
    if case_dict.get("case_text"):
        return
    rd = case_dict.get("raw_data")
    if isinstance(rd, str):
        try:
            rd = json.loads(rd)
        except (json.JSONDecodeError, TypeError):
            rd = None
    if isinstance(rd, dict):
        ct = rd.get("case_text") or ""
        if ct:
            case_dict["case_text"] = ct
