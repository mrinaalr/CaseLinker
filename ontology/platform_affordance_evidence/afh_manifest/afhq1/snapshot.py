"""Pinned, read-only corpus snapshot for the Q1 reconstruction.

``export_snapshot`` copies the columns the analysis needs from a CaseLinker
SQLite database, opened read-only, into ``ontology/platform_affordance_evidence/afh_manifest/data/snapshot.sqlite``
(gitignored: it holds source text). Every later step reads only the snapshot,
so a rerun against the same snapshot is byte-identical. The live corpus is not
touched.

``dataset_identity`` hashes, per case, the id, the content fingerprint, a hash
of the case text, and the fields the analysis reads. Two snapshots with the
same identity give the same outputs.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
REPO = RESEARCH.parents[2]
DATA = RESEARCH / "data"
SNAPSHOT = DATA / "snapshot.sqlite"
# Text-free public snapshot, committed: case metadata, fingerprints, every record's classification,
# exclusions and date roles. Every output except legacy_afh1_exemplars.json rebuilds from it exactly.
PUBLIC = RESEARCH / "public"
PUBLIC_CASE_FIELDS = ("id", "fingerprint", "source", "source_url", "pub_year", "platforms", "topics")

# The main checkout holds the corpus DB; a worktree does not (gitignored).
DEFAULT_SOURCE_DB = Path(
    os.environ.get("AFH_Q1_SOURCE_DB", str(REPO.parent / "CaseLinker" / "caselinker.db"))
)

_SCHEMA = """
CREATE TABLE cases (
    id TEXT PRIMARY KEY,
    source TEXT,
    source_url TEXT,
    pub_year INTEGER,
    case_text TEXT,
    text_sha256 TEXT,
    platforms_used TEXT,
    case_topics TEXT,
    person_spans TEXT,
    extraction_run_id TEXT
);
CREATE TABLE fingerprints (case_id TEXT PRIMARY KEY, fingerprint TEXT, normalization_version TEXT);
CREATE TABLE stored_dates (case_id TEXT, value TEXT, role TEXT, span_start INTEGER, span_end INTEGER, span_text TEXT);
CREATE TABLE snapshot_meta (key TEXT PRIMARY KEY, value TEXT);
"""


def sha256_text(text: Optional[str]) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def open_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def export_snapshot(source_db: Path = DEFAULT_SOURCE_DB, out: Path = SNAPSHOT) -> Dict[str, Any]:
    """Copy the analysis columns from ``source_db`` (read-only) into ``out``."""
    src = open_readonly(source_db)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    dst = sqlite3.connect(tmp)
    dst.executescript(_SCHEMA)
    rows = src.execute(
        "SELECT id, source, source_url, json_extract(raw_data,'$.year'), "
        "json_extract(raw_data,'$.case_text'), platforms_used, case_topics, "
        "json_extract(extracted_features,'$.person_spans'), extraction_run_id FROM cases ORDER BY id"
    )
    for cid, source, url, year, text, plats, topics, spans, run in rows:
        dst.execute(
            "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, source, url, int(year) if year not in (None, "") else None, text or "",
             sha256_text(text), plats or "[]", topics or "[]", spans, run),
        )
    dst.executemany(
        "INSERT INTO fingerprints VALUES (?,?,?)",
        src.execute("SELECT case_id, fingerprint, normalization_version FROM case_fingerprints ORDER BY case_id"),
    )
    # Date rows from each case's latest run that wrote dates: the stored state before the fix.
    dst.executemany(
        "INSERT INTO stored_dates VALUES (?,?,?,?,?,?)",
        src.execute(
            """
            WITH latest AS (
              SELECT case_id, run_id FROM (
                SELECT case_id, run_id, MAX(created_at) AS t FROM field_assertions
                WHERE field='date' GROUP BY case_id, run_id
              ) a WHERE t = (SELECT MAX(created_at) FROM field_assertions b
                             WHERE b.case_id=a.case_id AND b.field='date')
            )
            SELECT f.case_id, f.value_json, f.role, f.span_start, f.span_end, f.span_text
            FROM field_assertions f JOIN latest l ON l.case_id=f.case_id AND l.run_id=f.run_id
            WHERE f.field='date' ORDER BY f.case_id, f.span_start, f.id
            """
        ),
    )
    src.close()
    identity = dataset_identity(dst)
    dst.executemany(
        "INSERT INTO snapshot_meta VALUES (?,?)",
        [("dataset_identity", identity["dataset_identity"]),
         ("case_count", str(identity["case_count"])),
         ("source_db_name", source_db.name)],
    )
    dst.commit()
    dst.close()
    tmp.replace(out)
    return identity


def dataset_identity(conn: sqlite3.Connection) -> Dict[str, Any]:
    h = hashlib.sha256()
    n = 0
    fps = dict(conn.execute("SELECT case_id, fingerprint FROM fingerprints"))
    for cid, source, url, year, tsha, plats, topics in conn.execute(
        "SELECT id, source, source_url, pub_year, text_sha256, platforms_used, case_topics FROM cases ORDER BY id"
    ):
        h.update("\t".join([cid, fps.get(cid, ""), source or "", url or "", str(year), tsha,
                            plats or "", topics or ""]).encode("utf-8"))
        h.update(b"\n")
        n += 1
    return {"dataset_identity": h.hexdigest(), "case_count": n}


def connect(path: Path = SNAPSHOT) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} missing. Run: python ontology/platform_affordance_evidence/afh_manifest/run_all.py --export"
        )
    return open_readonly(path)


def snapshot_meta(conn: sqlite3.Connection) -> Dict[str, str]:
    return dict(conn.execute("SELECT key, value FROM snapshot_meta"))


def iter_cases(conn: sqlite3.Connection) -> Iterator[Dict[str, Any]]:
    for row in conn.execute(
        "SELECT id, source, source_url, pub_year, case_text, platforms_used, case_topics, person_spans "
        "FROM cases ORDER BY id"
    ):
        cid, source, url, year, text, plats, topics, spans = row
        yield {
            "id": cid, "source": source, "source_url": url, "pub_year": year, "text": text or "",
            "platforms": json.loads(plats or "[]"), "topics": json.loads(topics or "[]"),
            "person_spans": json.loads(spans) if spans else None,
        }


def _jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_public(out: Path, meta: Dict[str, str], cases, fingerprints: Dict[str, str],
                 records, excluded, dates: Dict[str, dict]) -> None:
    """Write the text-free public snapshot. ``records`` are pipeline.Record objects."""
    from dataclasses import asdict

    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(
        {"dataset_identity": meta["dataset_identity"], "case_count": int(meta["case_count"])},
        indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _jsonl(out / "cases.jsonl", ({"id": c["id"], "fingerprint": fingerprints.get(c["id"], ""), "source": c["source"],
                                 "source_url": c["source_url"], "pub_year": c["pub_year"], "platforms": c["platforms"],
                                 "topics": c["topics"], "dates": dates[c["id"]]} for c in cases))
    _jsonl(out / "records.jsonl", (asdict(r) for r in records))
    _jsonl(out / "excluded.jsonl", excluded)


def load_public(src: Path = PUBLIC):
    """(meta, cases, fingerprints, records, excluded, dates) from the public snapshot."""
    from . import pipeline as pl

    if not (src / "meta.json").is_file():
        raise FileNotFoundError(f"{src} has no public snapshot. Build once from data/snapshot.sqlite to write it.")
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    rows = _read_jsonl(src / "cases.jsonl")
    cases = [{k: r[k] for k in PUBLIC_CASE_FIELDS if k != "fingerprint"} | {"text": None, "person_spans": None}
             for r in rows]
    fingerprints = {r["id"]: r["fingerprint"] for r in rows if r["fingerprint"]}
    dates = {r["id"]: r["dates"] for r in rows}
    records = []
    for d in _read_jsonl(src / "records.jsonl"):
        d["sentence_spans"] = [tuple(x) for x in d["sentence_spans"]]
        d["instrumental_span"] = {k: tuple(v) for k, v in d["instrumental_span"].items()}
        records.append(pl.Record(**d))
    excluded = _read_jsonl(src / "excluded.jsonl")
    return ({"dataset_identity": meta["dataset_identity"], "case_count": str(meta["case_count"])},
            cases, fingerprints, records, excluded, dates)
