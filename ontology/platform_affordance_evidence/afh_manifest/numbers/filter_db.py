"""Analysis DB: the collected corpus DB minus config/exclusions.csv, as a read-only copy. The collected DB is never written.

  python ontology/platform_affordance_evidence/afh_manifest/numbers/filter_db.py   (run_all.sh runs it after afh_inputs.py)

Reads AFH_DB_COLLECTED (or AFH_DB) with SQLite mode=ro, copies it with the backup API, and in the copy only drops
the append-only triggers so the listed records can be deleted from `cases` and every table keyed by case_id.
VACUUM makes the file deterministic, and the copy is set read-only. Writes the analysis DB to afh_manifest/data/
(gitignored) for an AfH 2.0 run, else into the run's data/ folder, and records in RUN_INPUTS.json the label
"AfH 2.0 frozen DB minus exclusions v1", the manifest hash, the records excluded and the analysis DB hash.
Prints the analysis DB path for run_all.sh.
"""
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402

VERSION = "v1"
CASE_TABLES = ("case_fingerprints", "field_assertions", "field_resolutions", "perpetrator_demographics",
               "prosecution_outcomes", "review_queue", "victim_demographics")


def exclusions(path: Path = AI.EXCLUSIONS) -> list:
    rows = [line for line in path.read_text().splitlines() if line and not line.startswith("#")]
    return [r["case_id"] for r in csv.DictReader(rows)]


def build(collected: Path, dest: Path, ids: list) -> dict:
    tmp = dest.with_suffix(".tmp")
    for p in (tmp, dest):
        if p.exists():
            p.chmod(0o644)
            p.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{collected}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    src.close()
    present = [i for (i,) in dst.execute(f"select id from cases where id in ({','.join('?' * len(ids))})", ids)] if ids else []
    for (name,) in dst.execute("select name from sqlite_master where type='trigger'").fetchall():
        dst.execute(f'drop trigger "{name}"')           # the copy only: lets the listed rows be deleted
    marks = ",".join("?" * len(present))
    if present:
        tables = {t for (t,) in dst.execute("select name from sqlite_master where type='table'")}
        for t in CASE_TABLES:
            if t in tables:
                dst.execute(f"delete from {t} where case_id in ({marks})", present)
        dst.execute(f"delete from cases where id in ({marks})", present)
    dst.commit()
    dst.execute("vacuum")
    cases = dst.execute("select count(*) from cases").fetchone()[0]
    dst.close()
    tmp.rename(dest)
    dest.chmod(0o444)
    return {"listed": len(ids), "excluded_records": len(present), "analysis_db_cases": cases}


if __name__ == "__main__":
    out = AI.out_dir()
    run = AI.run_inputs(out)
    dest = (AI.AFH / "data" if out.resolve() == HERE else out / "data") / f"caselinker_analysis_{VERSION}.db"
    ids = exclusions()
    info = build(AI.COLLECTED, dest, ids)
    run["analysis_db"] = {
        "label": ("AfH 2.0 frozen DB minus exclusions " if run.get("afh_2_0_snapshot") else "inputs minus exclusions ") + VERSION,
        "exclusions_file": "afh_manifest/config/exclusions.csv",
        "exclusions_sha256": AI.sha256_file(AI.EXCLUSIONS),
        **info,
        "analysis_db_sha256": AI.sha256_file(dest),
    }
    (out / "RUN_INPUTS.json").write_text(json.dumps(run, indent=1) + "\n")
    print(dest)
