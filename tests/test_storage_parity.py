"""The same store/load/assertion/resolution checks on SQLite and local Postgres.

Postgres is a throwaway database on 127.0.0.1. This file never reads DATABASE_URL
from the environment, so it cannot reach Railway.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import processing  # noqa: E402
from case_storage_utils import EXTRACTED_FEATURE_FIELDS  # noqa: E402

LOCAL_URL = "postgresql://127.0.0.1:5432/caselinker_parity"
MARKERS = ("railway", "rlwy.net", "proxy.rlwy")


def _forbid_remote(url: str) -> None:
    lowered = url.lower()
    for marker in MARKERS:
        if marker in lowered:
            raise RuntimeError(f"refusing a non-local database url containing {marker}")
    if "127.0.0.1" not in url and "localhost" not in url:
        raise RuntimeError(f"refusing a database url that is not local: {url}")


def _pipeline_case() -> dict:
    text = (
        "LEXINGTON, Ky. – A Lexington man, Avery Rowan Ravensworth, 30, was sentenced to 50 years in prison. "
        "A 12-year-old victim met Ravensworth on Snapchat."
    )
    raw = {
        "case_text": text,
        "case_id": "parity_case",
        "source": "TEST",
        "source_file": "parity.pdf",
        "source_url": "https://example.test/parity",
        "year": "2025",
    }
    features = processing.extract_features(raw)
    case = processing.assign_comparison_values(processing.MergeProcessing().merge_features(features, None))
    case["id"] = "parity_case"
    case["perpetrator_gender"] = "male"
    case["press_digest_pollution"] = False
    return case


def _norm(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
        if isinstance(parsed, (dict, list)):
            return _norm(parsed)
        return value
    return value


def _logical_assertions(payload: dict) -> list[dict]:
    keep = ("field", "method", "family", "value", "role", "span_start", "span_end", "span_ok", "confidence")
    rows = []
    for assertion in payload.get("assertions") or []:
        row = {key: assertion.get(key) for key in keep}
        row["span_ok"] = int(bool(row["span_ok"]))
        row["extras_entity"] = (assertion.get("extras") or {}).get("defendant_entity")
        rows.append(row)
    return sorted(rows, key=lambda row: (row["field"] or "", row["span_start"] or 0, row["method"] or "", str(row["value"])))


def _logical_resolutions(payload: dict) -> dict:
    out = {}
    for field, res in (payload.get("resolutions") or {}).items():
        out[field] = {
            "status": res.get("status"),
            "rule_id": res.get("rule_id"),
            "rule_set_version": res.get("rule_set_version"),
            "final_value": _norm(res.get("final_value")),
            "disagreement": _norm(res.get("disagreement")),
        }
    return out


def _feature_view(case: dict) -> dict:
    return {key: _norm(case.get(key)) for key in EXTRACTED_FEATURE_FIELDS if key in case}


def exercise(storage) -> dict:
    case = _pipeline_case()
    assert storage.store_case(case)
    loaded = storage.get_case("parity_case")
    listed = storage.get_all_cases(include_raw_data=False)
    by_id = storage.get_cases_by_ids(["parity_case"], include_raw_data=False)
    slim = storage.get_cases_slim_chunk(0, 10)
    assertions = storage.get_case_assertions("parity_case")
    run_id, stored = storage.load_case_assertions("parity_case")
    storage.append_resolutions("parity_case", run_id, processing.assertions_module.resolve(stored))
    disagreements = storage.get_field_disagreements(field="age")
    return {
        "get_case": _feature_view(loaded or {}),
        "get_all_cases": _feature_view(next(c for c in listed if c["id"] == "parity_case")),
        "get_cases_by_ids": _feature_view(by_id[0]),
        "get_cases_slim_chunk": _feature_view(next(c for c in slim if c["id"] == "parity_case")),
        "assertions": _logical_assertions(assertions),
        "resolutions": _logical_resolutions(storage.get_case_assertions("parity_case")),
        "disagreement_ids": sorted(item["case_id"] for item in disagreements["items"]),
        "gender": {
            "get_case": (loaded or {}).get("perpetrator_gender"),
            "get_all_cases": next(c for c in listed if c["id"] == "parity_case").get("perpetrator_gender"),
            "get_cases_by_ids": by_id[0].get("perpetrator_gender"),
            "get_cases_slim_chunk": next(c for c in slim if c["id"] == "parity_case").get("perpetrator_gender"),
        },
    }


def _sqlite(tmp_path: Path):
    from storage import CaseStorage
    return CaseStorage(str(tmp_path / "parity.db"))


def _postgres():
    _forbid_remote(LOCAL_URL)
    import psycopg2
    admin = psycopg2.connect("postgresql://127.0.0.1:5432/postgres")
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'caselinker_parity'")
    if cur.fetchone() is None:
        cur.execute("CREATE DATABASE caselinker_parity")
    cur.close()
    admin.close()
    os.environ["DATABASE_URL"] = LOCAL_URL
    import storage_postgres
    storage_postgres._pool = None
    storage = storage_postgres.CaseStorage()
    conn = storage_postgres.get_connection()
    try:
        cur = conn.cursor()
        for table in ("review_queue", "field_resolutions", "field_assertions", "prosecution_outcomes",
                      "perpetrator_demographics", "victim_demographics", "cases"):
            cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        conn.commit()
    finally:
        cur.close()
        storage_postgres.return_connection(conn)
    return storage


def test_sqlite_loaders_share_the_field_list(tmp_path: Path):
    snap = exercise(_sqlite(tmp_path))
    assert snap["gender"] == {
        "get_case": "male",
        "get_all_cases": "male",
        "get_cases_by_ids": "male",
        "get_cases_slim_chunk": "male",
    }
    assert snap["get_case"]["perpetrator_age"] == [30]
    assert snap["assertions"]
    assert snap["resolutions"]["age"]["final_value"]["victims"] == [12]


def test_postgres_matches_sqlite(tmp_path: Path):
    try:
        import psycopg2
        probe = psycopg2.connect("postgresql://127.0.0.1:5432/postgres")
        probe.close()
    except Exception as exc:
        pytest.skip(f"local postgres is not accepting connections: {exc}")
    left = exercise(_sqlite(tmp_path))
    right = exercise(_postgres())
    assert left == right
