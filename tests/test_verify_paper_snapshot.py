"""Snapshot emit + drift attribution tests for verify_paper.py (PR B)."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "scripts" / "verify" / "paper"
if str(PAPER) not in sys.path:
    sys.path.insert(0, str(PAPER))

from claim_snapshot import (  # noqa: E402
    compare_against_snapshot,
    emit_claim_snapshot,
    load_pinned_snapshot,
    pin_corpus,
    source_versions_changed,
)
from verify_paper import main as verify_paper_main  # noqa: E402


@dataclass
class _Result:
    claim_id: str
    status: str
    detail: str
    observed: str = ""
    expected: str = ""
    source: str = ""
    notes: list[str] = field(default_factory=list)


def _create_cases_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            source TEXT,
            source_url TEXT,
            date_start TEXT,
            date_end TEXT,
            victim_count INTEGER,
            perpetrator_count INTEGER,
            relationship_to_victim TEXT,
            platforms_used TEXT,
            severity_indicators TEXT,
            case_topics TEXT,
            tags TEXT,
            notes TEXT,
            raw_data TEXT,
            extracted_features TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _insert_case(conn: sqlite3.Connection, case_id: str, source: str = "agency") -> None:
    conn.execute(
        """
        INSERT INTO cases (
            id, source, source_url, date_start, platforms_used,
            raw_data, extracted_features
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            source,
            f"https://example.gov/{case_id}",
            "2020-01-01",
            json.dumps(["Kik"]),
            json.dumps({"source_file": "fixture.pdf"}),
            json.dumps({"agencies_involved": ["Example PD"]}),
        ),
    )


def _tiny_db(path: Path, n: int = 2) -> Path:
    conn = sqlite3.connect(str(path))
    _create_cases_table(conn)
    for index in range(n):
        _insert_case(conn, f"case-{index:03d}")
    conn.commit()
    conn.close()
    return path


def _install_version_hashes(
    conn: sqlite3.Connection, links: list[tuple[str, str, str]]
) -> None:
    """Synthetic PR A tables — probe-only; this branch does not import capture code."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_document_versions (
            version_id TEXT PRIMARY KEY,
            document_id TEXT,
            content_sha256 TEXT NOT NULL
        )
        """
    )
    case_cols = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
    if "document_version_id" not in case_cols:
        conn.execute("ALTER TABLE cases ADD COLUMN document_version_id TEXT")
    for case_id, version_id, digest in links:
        conn.execute(
            "INSERT OR REPLACE INTO source_document_versions "
            "(version_id, document_id, content_sha256) VALUES (?, ?, ?)",
            (version_id, f"doc_{case_id}", digest),
        )
        conn.execute(
            "UPDATE cases SET document_version_id=? WHERE id=?",
            (version_id, case_id),
        )


class CorpusPinTests(unittest.TestCase):
    def test_corpus_digest_is_stable_and_grows_with_a_case(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "pin.db"
            _tiny_db(db, n=2)
            conn = sqlite3.connect(str(db))
            first = pin_corpus(conn)
            second = pin_corpus(conn)
            self.assertEqual(first, second)
            self.assertEqual(first["case_count"], 2)
            self.assertIsNone(first["source_versions"])
            _insert_case(conn, "case-002")
            conn.commit()
            grown = pin_corpus(conn)
            conn.close()
            self.assertEqual(grown["case_count"], 3)
            self.assertNotEqual(grown["content_digest"], first["content_digest"])
            self.assertIn("case-002", grown["case_ids"])

    def test_source_versions_absent_until_hashes_exist(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "hash.db"
            _tiny_db(db, n=1)
            conn = sqlite3.connect(str(db))
            self.assertIsNone(pin_corpus(conn)["source_versions"])
            conn.execute(
                """
                CREATE TABLE source_document_versions (
                    version_id TEXT PRIMARY KEY,
                    document_id TEXT,
                    content_sha256 TEXT NOT NULL
                )
                """
            )
            conn.execute("ALTER TABLE cases ADD COLUMN document_version_id TEXT")
            conn.execute(
                "INSERT INTO source_document_versions "
                "(version_id, document_id, content_sha256) VALUES (?, ?, ?)",
                ("docv_aaa", "doc_aaa", "a" * 64),
            )
            conn.execute(
                "UPDATE cases SET document_version_id=? WHERE id=?",
                ("docv_aaa", "case-000"),
            )
            conn.commit()
            pinned = pin_corpus(conn)
            self.assertTrue(pinned["source_versions"]["available"])
            conn.execute(
                "UPDATE source_document_versions SET content_sha256=?",
                ("b" * 64,),
            )
            conn.commit()
            live = pin_corpus(conn)
            conn.close()
            self.assertTrue(
                source_versions_changed(pinned["source_versions"], live["source_versions"])
            )


class VerifyPaperSnapshotTests(unittest.TestCase):
    def test_default_verify_paper_writes_reports_only(self) -> None:
        """No snapshot flags: today's path. No pin, no snapshot/, no claim-drift.json."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            db = _tiny_db(root / "cases.db", n=2)
            out = root / "out"
            with patch(
                "verify_paper.pin_corpus",
                side_effect=AssertionError("pin_corpus must not run on the default path"),
            ):
                verify_paper_main(["--db", str(db), "--out", str(out)])
            self.assertTrue((out / "claims.md").is_file())
            self.assertTrue((out / "paper_tested.md").is_file())
            self.assertFalse((out / "snapshot").exists())
            self.assertFalse((out / "claim-drift.json").exists())

    def test_snapshot_bytes_are_stable_on_repeat_runs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            db = _tiny_db(root / "cases.db", n=2)
            out_a = root / "out-a"
            out_b = root / "out-b"
            recorded = "2026-08-20T00:00:00Z"
            revision = "deadbeef" * 5
            common = [
                "--db",
                str(db),
                "--recorded-at",
                recorded,
                "--code-revision",
                revision,
            ]
            verify_paper_main([*common, "--out", str(out_a), "--snapshot"])
            verify_paper_main([*common, "--out", str(out_b), "--snapshot"])
            man_a = (out_a / "snapshot" / "manifest.json").read_bytes()
            man_b = (out_b / "snapshot" / "manifest.json").read_bytes()
            self.assertEqual(man_a, man_b)
            manifest = json.loads(man_a)
            self.assertEqual(manifest["code_revision"], revision)
            self.assertEqual(manifest["recorded_at"], recorded)
            self.assertTrue(manifest["snapshot_id"].startswith("snap_claim_"))
            kinds = {item["kind"]: item for item in manifest["components"]}
            self.assertEqual(kinds["corpus"]["status"], "included")
            self.assertEqual(kinds["code"]["status"], "included")
            self.assertEqual(kinds["outputs"]["status"], "included")
            self.assertEqual(kinds["source_versions"]["status"], "not_applicable")

    def test_against_snapshot_attributes_one_added_case(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            db = _tiny_db(root / "cases.db", n=2)
            out = root / "out"
            recorded = "2026-08-20T00:00:00Z"
            revision = "cafef00d" * 5
            verify_paper_main(
                [
                    "--db",
                    str(db),
                    "--out",
                    str(out),
                    "--snapshot",
                    "--recorded-at",
                    recorded,
                    "--code-revision",
                    revision,
                ]
            )
            manifest = out / "snapshot" / "manifest.json"
            conn = sqlite3.connect(str(db))
            _insert_case(conn, "case-added")
            conn.commit()
            conn.close()
            drift_out = root / "drift"
            verify_paper_main(
                [
                    "--db",
                    str(db),
                    "--out",
                    str(drift_out),
                    "--against-snapshot",
                    str(manifest),
                    "--code-revision",
                    revision,
                ]
            )
            report = json.loads((drift_out / "claim-drift.json").read_text(encoding="utf-8"))
            self.assertEqual(report["pinned_case_count"], 2)
            self.assertEqual(report["live_case_count"], 3)
            self.assertEqual(report["new_case_ids"], ["case-added"])
            self.assertFalse(report["source_versions_available"])
            self.assertFalse(report["source_versions_changed"])
            deltas = {item["claim_id"]: item for item in report["deltas"]}
            self.assertIn("cover.corpus_cases", deltas)
            self.assertEqual(deltas["cover.corpus_cases"]["attribution"], ["corpus_growth"])
            self.assertEqual(deltas["cover.corpus_cases"]["pinned"]["observed"], "2")
            self.assertEqual(deltas["cover.corpus_cases"]["live"]["observed"], "3")
            for item in report["deltas"]:
                self.assertEqual(item["attribution"], ["corpus_growth"])
                self.assertNotIn("source_change", item["attribution"])
                self.assertNotIn("extraction_change", item["attribution"])

    def test_against_snapshot_attributes_source_change_when_hashes_differ(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            db = _tiny_db(root / "cases.db", n=2)
            conn = sqlite3.connect(str(db))
            _install_version_hashes(
                conn,
                [
                    ("case-000", "docv_aaa", "a" * 64),
                    ("case-001", "docv_bbb", "c" * 64),
                ],
            )
            conn.commit()
            conn.close()
            out = root / "out"
            recorded = "2026-08-20T00:00:00Z"
            revision = "baddcafe" * 5
            verify_paper_main(
                [
                    "--db",
                    str(db),
                    "--out",
                    str(out),
                    "--snapshot",
                    "--recorded-at",
                    recorded,
                    "--code-revision",
                    revision,
                ]
            )
            kinds = {
                item["kind"]: item
                for item in json.loads((out / "snapshot" / "manifest.json").read_text())[
                    "components"
                ]
            }
            self.assertEqual(kinds["source_versions"]["status"], "included")

            conn = sqlite3.connect(str(db))
            conn.execute(
                "UPDATE source_document_versions SET content_sha256=? WHERE version_id=?",
                ("b" * 64, "docv_aaa"),
            )
            # Shift a claim observation so there is a delta to attribute.
            conn.execute(
                "UPDATE cases SET extracted_features=? WHERE id=?",
                (
                    json.dumps({"agencies_involved": ["Example PD", "Other PD"]}),
                    "case-000",
                ),
            )
            conn.commit()
            conn.close()

            drift_out = root / "drift"
            verify_paper_main(
                [
                    "--db",
                    str(db),
                    "--out",
                    str(drift_out),
                    "--against-snapshot",
                    str(out / "snapshot" / "manifest.json"),
                    "--code-revision",
                    revision,
                ]
            )
            report = json.loads((drift_out / "claim-drift.json").read_text(encoding="utf-8"))
            self.assertEqual(report["new_case_ids"], [])
            self.assertTrue(report["source_versions_available"])
            self.assertTrue(report["source_versions_changed"])
            self.assertGreater(len(report["deltas"]), 0)
            for item in report["deltas"]:
                self.assertIn("source_change", item["attribution"])
                self.assertNotIn("corpus_growth", item["attribution"])
                self.assertNotIn("extraction_change", item["attribution"])


class DriftAttributionTests(unittest.TestCase):
    def test_extraction_and_source_change_are_independent_causes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            db = _tiny_db(root / "cases.db", n=1)
            conn = sqlite3.connect(str(db))
            corpus = pin_corpus(conn)
            conn.close()
            results = [_Result("cover.corpus_cases", "fail", "cases.count=1", "1", "7426")]
            written = emit_claim_snapshot(
                snapshot_dir=root / "snap",
                corpus=corpus,
                results=results,
                code_revision="rev-1",
                recorded_at="2026-08-20T00:00:00Z",
            )
            pinned = load_pinned_snapshot(written)
            changed = [_Result("cover.corpus_cases", "fail", "cases.count=1", "99", "7426")]
            extraction = compare_against_snapshot(
                pinned=pinned,
                live_corpus=corpus,
                live_results=changed,
                live_code_revision="rev-2",
            )
            self.assertEqual(len(extraction["deltas"]), 1)
            self.assertEqual(extraction["deltas"][0]["attribution"], ["extraction_change"])
            none = compare_against_snapshot(
                pinned=pinned,
                live_corpus=corpus,
                live_results=results,
                live_code_revision="rev-1",
            )
            self.assertEqual(none["deltas"], [])


if __name__ == "__main__":
    unittest.main()
