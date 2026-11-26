"""Where an AfH numbers run reads from and writes to, and whether its inputs are the AfH 2.0 snapshot.

By default a run must use the frozen AfH 2.0 inputs (../SNAPSHOT.md, afh_2_0_snapshot.json), so it
reproduces the published numbers. Other inputs (a newer corpus, a corpus built from other records)
run only with AFH_ALLOW_OTHER_INPUTS=1 (run_all.sh --other-inputs). They are computed in full by the
same code, and labelled `afh_2_0_snapshot: false` in RUN_INPUTS.json, numbers.json and numbers.md.

  AFH_DB      corpus database (default: <repo>/caselinker.db)
  AFH_PACER   PACER release folder (default: state_machines/data/pacer-v2)
  AFH_OUT     output folder. Default: this folder when the inputs are the AfH 2.0 snapshot, else
              local/afh-runs/<db sha256[:12]>/ (gitignored), so a new corpus never overwrites the
              published AfH 2.0 outputs.
  AFH_ALLOW_OTHER_INPUTS=1   run on inputs that are not the AfH 2.0 snapshot (warns; outputs labelled)
"""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
AFH = HERE.parent
SNAPSHOT_FILE = HERE / "afh_2_0_snapshot.json"

DB = Path(os.environ.get("AFH_DB") or REPO / "caselinker.db").resolve()
PACER = Path(os.environ.get("AFH_PACER") or REPO / "state_machines" / "data" / "pacer-v2").resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> str:
    """SHA-256 of the `shasum -a 256` listing of every file under root (./-relative, byte-sorted).
    Same value as SNAPSHOT.md's verify command."""
    files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: ("./" + p.relative_to(root).as_posix()).encode())
    listing = "".join(f"{sha256_file(p)}  ./{p.relative_to(root).as_posix()}\n" for p in files)
    return hashlib.sha256(listing.encode()).hexdigest()


def identity(db: Path = DB, pacer: Path = PACER, snapshot_file: Path = SNAPSHOT_FILE) -> dict:
    """Hashes of the inputs and whether each matches the AfH 2.0 snapshot."""
    ref = json.loads(snapshot_file.read_text())
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cases = con.execute("select count(*) from cases").fetchone()[0]
    finally:
        con.close()
    db_sha, pacer_sha = sha256_file(db), sha256_tree(pacer)
    manifest = json.loads((pacer / "manifest.json").read_text())
    out = {
        "db": str(db), "db_sha256": db_sha, "db_cases": cases,
        "pacer": str(pacer), "pacer_release": manifest.get("release_id"), "pacer_sha256": pacer_sha,
        "db_matches_afh_2_0": db_sha == ref["db_sha256"],
        "pacer_matches_afh_2_0": pacer_sha == ref["pacer_sha256"],
        "pacer_is_public_subset": pacer_sha == ref.get("pacer_public_sha256"),
    }
    out["afh_2_0_snapshot"] = out["db_matches_afh_2_0"] and out["pacer_matches_afh_2_0"]
    out["afh_2_0_reference"] = ref
    return out


def default_out(ident: dict) -> Path:
    if ident["afh_2_0_snapshot"]:
        return HERE
    return REPO / "local" / "afh-runs" / ident["db_sha256"][:12]


def out_dir(ident: Optional[dict] = None) -> Path:
    """The run's output folder. run_all.sh exports AFH_OUT, so every step agrees."""
    env = os.environ.get("AFH_OUT")
    return Path(env).resolve() if env else default_out(ident or identity())


def full_snapshot_path(out: Path) -> Path:
    """The full-text snapshot (never shipped). An AfH 2.0 run uses the shared afh_manifest/data/ copy;
    any other run keeps its own inside its output folder, so it cannot replace the AfH 2.0 one."""
    return AFH / "data" / "snapshot.sqlite" if out.resolve() == HERE else out / "data" / "snapshot.sqlite"


def allow_other_inputs() -> bool:
    return os.environ.get("AFH_ALLOW_OTHER_INPUTS") == "1"


def run_inputs(out: Path) -> dict:
    """RUN_INPUTS.json written by `python afh_inputs.py` at the start of run_all.sh."""
    return json.loads((out / "RUN_INPUTS.json").read_text())


def inputs_label(out: Optional[Path] = None):
    """What every output records about its inputs: RUN_INPUTS.json without the reference block."""
    try:
        return {k: v for k, v in run_inputs(out or out_dir()).items() if k != "afh_2_0_reference"}
    except FileNotFoundError:
        return "unknown: run outside numbers/run_all.sh, inputs not identified"


def check_unchanged(out: Path, db: Path = DB, pacer: Path = PACER) -> list:
    """Names of inputs whose hash changed since RUN_INPUTS.json was written (empty = untouched)."""
    before = run_inputs(out)
    changed = []
    if sha256_file(db) != before["db_sha256"]:
        changed.append("db")
    if sha256_tree(pacer) != before["pacer_sha256"]:
        changed.append("pacer")
    return changed


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--check-unchanged"]:
        bad = check_unchanged(out_dir())
        if bad:
            print(f"INPUTS CHANGED DURING THE RUN: {', '.join(bad)} (sha256 differs from RUN_INPUTS.json)", file=sys.stderr)
            sys.exit(4)
        print("inputs unchanged", file=sys.stderr)
        sys.exit(0)
    ident = identity()
    if not ident["afh_2_0_snapshot"] and not allow_other_inputs():
        print("These inputs are not the AfH 2.0 snapshot (SNAPSHOT.md): "
              f"db match {ident['db_matches_afh_2_0']}, PACER match {ident['pacer_matches_afh_2_0']}.\n"
              "To reproduce AfH 2.0, use the frozen caselinker.db and pacer-v2. To analyse other records, "
              "rerun with --other-inputs (numbers will not match AfH 2.0).", file=sys.stderr)
        if ident.get("pacer_is_public_subset"):
            print("Your pacer-v2 is the public subset git ships (no cases/ bundles). Download pacer-v2.zip from "
                  f"https://doi.org/{ident['afh_2_0_reference'].get('data_doi')} (restricted) and unzip it over "
                  "state_machines/data/pacer-v2.", file=sys.stderr)
        sys.exit(3)
    out = out_dir(ident)
    if not ident["afh_2_0_snapshot"] and out.resolve() == HERE:
        print("Refusing to write non-AfH-2.0 outputs into the shipped numbers/ folder; set AFH_OUT elsewhere.", file=sys.stderr)
        sys.exit(3)
    out.mkdir(parents=True, exist_ok=True)
    (out / "RUN_INPUTS.json").write_text(json.dumps({k: v for k, v in ident.items() if k not in ("db", "pacer")}, indent=1) + "\n")
    if not ident["afh_2_0_snapshot"]:
        print("WARNING: these inputs are NOT the AfH 2.0 snapshot "
              f"(db match {ident['db_matches_afh_2_0']}, PACER match {ident['pacer_matches_afh_2_0']}). "
              "The numbers will not match AfH 2.0; every output is labelled afh_2_0_snapshot: false.", file=sys.stderr)
    print(out)
