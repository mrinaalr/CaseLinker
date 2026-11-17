"""The Big Bang selector parses each case once.

The bridge scan used to call json.loads on every greedy step. Cached bridges
must stay equal to the live function, and that function must not run again
inside the bucket loops.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))
sys.path.insert(0, str(ROOT / "ontology" / "pools"))

import big_bang  # noqa: E402


def _case(case_id: str, source: str, platform: str) -> tuple:
    text = (
        f"The defendant used {platform} to solicit a child. "
        "He was charged and pleaded guilty. Victim was 12."
    )
    features = {
        "platforms_used": [platform],
        "agencies_involved": [source],
        "prosecution_outcome": {"charges": ["possession"], "booking_status": "convicted"},
        "investigation_type": "proactive",
    }
    return (
        case_id,
        source,
        json.dumps([platform]),
        json.dumps(["possession"]),
        json.dumps(["hands_on"]),
        json.dumps(features),
        json.dumps({"case_text": text}),
        1,
        1,
        "stranger",
    )


def _write_db(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE cases (
            id TEXT, source TEXT, platforms_used TEXT, case_topics TEXT,
            severity_indicators TEXT, extracted_features TEXT, raw_data TEXT,
            victim_count INTEGER, perpetrator_count INTEGER,
            relationship_to_victim TEXT
        )
        """
    )
    rows = [
        _case("bb_cache_001", "DOJ CEOS", "Discord"),
        _case("bb_cache_002", "GBI", "Kik"),
        _case("bb_cache_003", "TBI", "Instagram"),
        _case("bb_cache_004", "ALEA", "Facebook"),
    ]
    conn.executemany(
        "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return [row[0] for row in rows]


def test_bridge_parse_runs_once_per_case_plus_the_picked_row(tmp_path, monkeypatch):
    db = tmp_path / "mini.db"
    ids = _write_db(db)
    out = tmp_path / "out"
    (out / "pools").mkdir(parents=True)
    monkeypatch.setattr(big_bang, "ONTOLOGY", out)

    calls = {"n": 0}
    real = big_bang.predicted_bridges

    def counted(case):
        calls["n"] += 1
        return real(case)

    monkeypatch.setattr(big_bang, "predicted_bridges", counted)
    monkeypatch.setattr(sys, "argv", ["big_bang.py", "--db", str(db), "--target", "4"])
    big_bang.main()

    picked = [
        line.strip()
        for line in (out / "pools" / "big_bang_ids.txt").read_text().splitlines()
        if line.strip()
    ]
    assert picked
    assert set(picked) <= set(ids)
    # Cache pass: spine_node_counts and the bridge map each call it once.
    # record() calls spine_node_counts once per picked case. The bucket
    # scans must not add another call per candidate.
    assert calls["n"] == 2 * len(ids) + len(picked)
