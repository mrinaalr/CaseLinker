#!/usr/bin/env bash
# AfH numbers, end to end. On the frozen inputs in ../SNAPSHOT.md this reproduces AfH 2.0. Run from the repo root.
#   bash ontology/platform_affordance_evidence/afh_manifest/numbers/run_all.sh
# Needs .venv (requirements.txt) and .venv-afh (requirements-afh.txt, BiCM). Read-only on the DB.
#   bash .../run_all.sh --other-inputs   # any other DB / PACER release; numbers will not match AfH 2.0
set -euo pipefail
case "${1:-}" in
  --other-inputs) export AFH_ALLOW_OTHER_INPUTS=1 ;;
  "") ;;
  *) echo "usage: run_all.sh [--other-inputs]" >&2; exit 2 ;;
esac
export DATABASE_URL='' REDIS_URL=''
PY=${PY:-.venv/bin/python}
BICM_PY=${BICM_PY:-.venv-afh/bin/python}
N=ontology/platform_affordance_evidence/afh_manifest/numbers

# Inputs: AFH_DB (default caselinker.db), AFH_PACER (default state_machines/data/pacer-v2), AFH_OUT.
# Default: the inputs must be the AfH 2.0 snapshot (SNAPSHOT.md), or the run stops. With --other-inputs
# any DB / PACER release runs in full; outputs go to local/afh-runs/<db sha>/ unless AFH_OUT is set,
# and every output is labelled afh_2_0_snapshot: false.
export AFH_DB=${AFH_DB:-caselinker.db}
export CASELINKER_DB="$AFH_DB"          # run/main.py and storage helpers read the same DB
AFH_OUT=$($PY $N/afh_inputs.py)          # checks the inputs; writes RUN_INPUTS.json (hashes, snapshot match)
export AFH_OUT
echo "AfH run -> $AFH_OUT" >&2

$PY $N/run_afh.py                       # build/, public/, harm_open/, harm_closed/
$PY $N/year_evidence.py                 # year_evidence.json: publication-year corrections and flags
$PY $N/year_sensitivity.py              # year_sensitivity.json: year-dependent results without the flagged records
mkdir -p "$AFH_OUT/task_forces"
$PY scripts/verify/icac_tf_verify.py --db "$AFH_DB" \
  --cross-csv "$AFH_OUT/task_forces/tf_cross.csv" --aggregator-only-csv "$AFH_OUT/task_forces/tf_aggregator_only.csv" \
  > "$AFH_OUT/task_forces/icac_tf_verify.out"
# the log names its output files; keep them relative so no machine path (or user name) ships
$PY -c 'import sys,pathlib; p=pathlib.Path(sys.argv[1]); p.write_text(p.read_text().replace(sys.argv[2].rstrip("/")+"/", ""))' \
  "$AFH_OUT/task_forces/icac_tf_verify.out" "$AFH_OUT"
$PY $N/cooc/build_matrix.py             # cooc/matrix_{stated,all}.json
$PY $N/data_checks.py                   # data_checks.json (boilerplate app lists, Facebook double tag, BiCM power)
$PY $N/cooc/build_variants.py           # cooc/matrix_{stated_fbfix,all_fbfix,all_clean}.json
$BICM_PY $N/cooc/bicm_run.py            # cooc/bicm_results.json
$BICM_PY $N/cooc/summarize.py          # cooc/cooccurrence.json
$PY $N/compute_numbers.py               # numbers.json, sections 1-9
$PY $N/prevalence.py                    # prevalence.json
$PY $N/merge_sections.py                # numbers.json, sections 10-12
$PY $N/write_md.py                      # numbers.md
$PY $N/afh_inputs.py --check-unchanged  # the DB and PACER release must hash exactly as before the run
