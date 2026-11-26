"""Run the committed AfH build and harm release against the frozen corpus (SNAPSHOT.md), writing
only under the run's output folder (afh_inputs.py) and the gitignored afh_manifest/data/. Read-only on the DB.

  DATABASE_URL='' REDIS_URL='' .venv/bin/python ontology/platform_affordance_evidence/afh_manifest/numbers/run_afh.py

Writes:
  build/        build.build() outputs (Q1 evidence base, harm.json, inventory, records.csv ...)
  public/       the text-free public snapshot build.build() rewrites
  full-text snapshot: afh_manifest/data/ for AfH 2.0, <out>/data/ otherwise (gitignored, never shipped)
  harm_closed/  harm_release.build() as committed: affordance x harm rows closed at registry end dates
  harm_open/    the same with CLOSE_AT_END = False, for comparison
"""
import functools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import afh_inputs as AI  # noqa: E402
OUT = AI.out_dir()
REPO = AI.REPO
AFH = REPO / "ontology" / "platform_affordance_evidence" / "afh_manifest"
sys.path.insert(0, str(AFH))

from afhq1 import snapshot as snap  # noqa: E402

snap_path = AI.full_snapshot_path(OUT)
snap_path.parent.mkdir(parents=True, exist_ok=True)
ident = snap.export_snapshot(AI.DB, snap_path)

from afhq1 import build, harm_release  # noqa: E402
from afhq1 import pipeline as pl  # noqa: E402

build.connect = functools.partial(snap.connect, snap_path)
snap.connect = build.connect
build.OUT = OUT / "build"
build.PUBLIC = OUT / "public"
snap.PUBLIC = build.PUBLIC
_inputs = {k: v for k, v in AI.run_inputs(OUT).items() if k != "afh_2_0_reference"}
build.INPUTS = harm_release.INPUTS = _inputs     # every output records what it was computed from
build_ident = build.build(log=lambda *_: None)

harm_release.CLOSE_AT_END = False                 # comparison only: rows not closed at registry `ended`
harm_release.OUT = OUT / "harm_open"
open_summary = harm_release.build(AI.DB, log=lambda *_: None)

harm_release.CLOSE_AT_END = True                  # the AfH 2.0 rule (committed default)
harm_release.OUT = OUT / "harm_closed"
closed_summary = harm_release.build(AI.DB, log=lambda *_: None)

print(json.dumps({"snapshot": ident, "codebook": pl.Codebook.load().version,
                  "registry": pl.load_yaml("platforms.yaml")["version"]}, indent=1, default=str)[:1500])
