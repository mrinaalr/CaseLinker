"""The /api/stats feature count covers every value extraction reads from a case and stores.

Until 2026-11-24 the count was a hand-kept list from March 2026: fields added later were stored but
never counted, and "unknown" placeholders were counted as values. Every stored attribute must now
be counted, counted through its span-checked assertions, or excluded with a reason.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "run"))

from feature_count import (  # noqa: E402
    ASSERTED_COPIES, COUNTED, EXCLUDED, EXCLUDED_ROLES, count_case_attributes, count_extracted_features,
)


def test_every_attribute_has_exactly_one_disposition():
    groups = [set(COUNTED), set(EXCLUDED), set(ASSERTED_COPIES)]
    assert all(not (a & b) for i, a in enumerate(groups) for b in groups[i + 1:])
    assert all(reason.strip() for reason in list(EXCLUDED.values()) + list(EXCLUDED_ROLES.values()))


def test_every_stored_attribute_is_counted_or_excluded():
    db = ROOT / "caselinker.db"
    if not db.is_file():
        pytest.skip("caselinker.db is local-only")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    stored = set()
    for (blob,) in conn.execute("SELECT extracted_features FROM cases"):
        stored |= set(json.loads(blob or "{}"))
    unclassified = stored - set(COUNTED) - set(EXCLUDED) - set(ASSERTED_COPIES)
    assert not unclassified, f"stored but neither counted nor excluded: {sorted(unclassified)}"


def test_fields_added_after_march_2026_are_counted():
    case = {
        "investigation_technology": ["PhotoDNA"],
        "locations": ["Ohio", "Columbus"],
        "perpetrator_admissions": ["admitted downloading", "admitted chatting"],
        "perpetrator_admission_themes": ["possession"],
        "anonymization_network": ["Tor"],
        "p2p_clients": ["BitTorrent"],
        "multi_defendant_operation": True,
        "prosecution_outcome": {"status": "sentenced",
                                "charges": json.dumps([{"count": 1, "charge": "receipt"}, {"count": 2, "charge": "possession"}]),
                                "sentences": json.dumps(["10 years"])},
        "evidence_volume": {"images": 1100, "videos": 12, "storage_size": None},
    }
    # theme 1 + network 1 + client 1 + places 2 + flag 1 + status 1 + charges 2 + evidence 2 = 11.
    # Labels count; the quoted spans behind them (perpetrator_admissions) are listed, not counted.
    # Not counted either: investigation_technology (program boilerplate); sentences come from assertions.
    assert count_case_attributes(case) == 11


def test_placeholders_and_empty_values_do_not_count():
    case = {"multi_defendant_operation": False, "relationship_to_victim": "unknown", "perpetrator_gender": "Unknown",
            "platforms_used": ["unknown", ""], "prosecution_outcome": {"status": "unknown", "charges": "[]"},
            "evidence_volume": {"images": None}, "case_demographics": {"age_range": "", "victim_gender": "unknown"}}
    assert count_case_attributes(case) == 0


def test_asserted_fields_are_not_counted_twice():
    case = {"perpetrator_age": [34, 35], "investigation_types": ["cybertip"], "legal_context": {"statutes": ["x"]},
            "previous_conviction": {"has_prior_conviction": True}, "cybertip_reporter": {"reporter": "esp"}}
    assert count_case_attributes(case) == 0
    assert count_extracted_features([case], {"age": 2, "investigation_type": 1, "legal_context": 1}) == 4


def test_nested_extracted_features_are_read_like_top_level():
    flat = {"perpetrator_admission_themes": ["possession"], "p2p_clients": ["eMule"]}
    assert count_case_attributes({"extracted_features": json.dumps(flat)}) == count_case_attributes(flat) == 2


def test_boilerplate_roles_are_left_out_of_the_assertion_count(tmp_path):
    sys.path.insert(0, str(ROOT / "src" / "Storage Layer"))
    from assertion_store import count_assertion_feature_values
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.executescript("""
        CREATE TABLE cases (id TEXT, extraction_run_id TEXT);
        CREATE TABLE field_assertions (case_id TEXT, run_id TEXT, field TEXT, role TEXT, value_json TEXT);
        INSERT INTO cases VALUES ('c1', 'r2');
        INSERT INTO field_assertions VALUES
          ('c1','r2','date','event','"2024-01-02"'), ('c1','r2','date','publication','"2024-03-01"'),
          ('c1','r2','date','event','"2024-01-02"'),                       -- same value twice: one feature
          ('c1','r2','date','program_boilerplate','"1998"'),               -- about the program
          ('c1','r1','date','event','"2020-05-05"'),                       -- an old run
          ('c1','r2','age','statutory_threshold','18'), ('c1','r2','age','unknown','34');
    """)
    assert count_assertion_feature_values(conn.cursor(), EXCLUDED_ROLES) == {"date": 2, "age": 1}


def test_api_stats_reports_the_full_count(monkeypatch):
    if not (ROOT / "caselinker.db").is_file():
        pytest.skip("caselinker.db is local-only")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("SKIP_STARTUP_WARMUP", "1")
    import importlib.util
    from fastapi.testclient import TestClient
    spec = importlib.util.spec_from_file_location("caselinker_run_main_feature_count", ROOT / "run" / "main.py")
    mod = sys.modules.get("caselinker_run_main_feature_count")
    if mod is None:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["caselinker_run_main_feature_count"] = mod
        spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "get_cached", lambda key: None)
    monkeypatch.setattr(mod, "set_cached", lambda *a, **k: None)
    cases = mod.storage.get_all_cases(include_raw_data=False)
    expected = count_extracted_features(cases, mod.storage.count_assertion_feature_values(EXCLUDED_ROLES))
    assert TestClient(mod.app).get("/api/stats").json()["unique_features"] == expected
