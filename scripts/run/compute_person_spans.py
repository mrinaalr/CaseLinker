#!/usr/bin/env python3
"""
Compute person-name offsets for stored cases (CaseLinker 3.x, ``people_mask``).

For each case, runs Stanza NER (tokenize, ner) over the case text and writes one
JSON line: ``{case_id, text_sha256, ner_person, person_spans}``. Values are
character offsets only. No name strings are written. ``text_sha256`` ties the
offsets to the exact text they were computed on, so applying them to a database
whose text differs is refused (``migrate_person_names.py --spans``).

Resumable: case ids already in ``--out`` are skipped.

Usage:
  python3 scripts/run/compute_person_spans.py --sqlite caselinker.db --out person_spans.jsonl
  python3 scripts/run/compute_person_spans.py --sqlite caselinker.db --out spans.jsonl --ids-with-admissions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src" / "Processing Layer" / "field_assertions"))

import people_mask  # noqa: E402


def text_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def case_text(raw) -> str:
    raw = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return (raw or {}).get("case_text") or ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids-with-admissions", action="store_true", help="only cases with perpetrator_admissions")
    args = ap.parse_args()

    import stanza
    nlp = stanza.Pipeline("en", processors="tokenize,ner", download_method=None, verbose=False)

    out = Path(args.out)
    done = set()
    if out.exists():
        done = {json.loads(line)["case_id"] for line in out.read_text().splitlines() if line.strip()}

    db = sqlite3.connect(args.sqlite)
    where = "WHERE extracted_features LIKE '%\"perpetrator_admissions\": [{%'" if args.ids_with_admissions else ""
    rows = [(cid, case_text(rd)) for cid, rd in db.execute(f"SELECT id, raw_data FROM cases {where} ORDER BY id")]
    rows = [(cid, t) for cid, t in rows if cid not in done and t.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(done)} done, {len(rows)} to go", flush=True)

    t0 = time.time()
    with out.open("a") as fh:
        for i in range(0, len(rows), args.batch):
            chunk = rows[i : i + args.batch]
            docs = nlp.bulk_process([stanza.Document([], text=t) for _, t in chunk])
            for (cid, text), doc in zip(chunk, docs):
                ner = [[e.start_char, e.end_char] for e in doc.ents if e.type == "PERSON"]
                fh.write(json.dumps({
                    "case_id": cid,
                    "text_sha256": text_sha256(text),
                    "ner_person": ner,
                    "person_spans": people_mask.person_spans(text, ner),
                }) + "\n")
            fh.flush()
            n = i + len(chunk)
            rate = n / max(time.time() - t0, 1e-6)
            print(f"{n}/{len(rows)} cases  {rate:.1f}/s  eta {(len(rows) - n) / max(rate, 1e-6) / 60:.0f} min", flush=True)


if __name__ == "__main__":
    main()
