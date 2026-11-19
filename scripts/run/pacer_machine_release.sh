#!/usr/bin/env bash
# Code the PACER cases with the two pinned local models, resolve, release as machine-coded, report.
# Resumable: every coded case is cached and skipped on rerun. Court text stays on this machine.
#
#   scripts/run/pacer_machine_release.sh <release_id> [case ...]      (default: every case under the text root)
#
# Environment: CASELINKER_PACER_TEXT (page text store), PYTHON (interpreter with the research deps),
# OLLAMA_PARALLEL (requests in flight, default 2), SELECTIVE=1 (second coder reads only pages where the first found acts),
# OBSERVATIONS=1 (also publish what each record names as a third graph per case),
# PILOT (folder of reference bundles of real cases to compare the release with, optional). Benchmark scores in the report are read from
# state_machines/benchmark/results (written by `pipeline bench --record`). Starts the dedicated Ollama server from
# state_machines/coding/models.json if it is not running.
set -euo pipefail
cd "$(dirname "$0")/../.."
RELEASE="${1:?release id}"; shift || true
PY="${PYTHON:-python3}"
TEXT="${CASELINKER_PACER_TEXT:-local/pacer_text}"
export CASELINKER_PACER_TEXT="$TEXT" PYTHONPATH=. DATABASE_URL=''
CASES=("$@")
if [ ${#CASES[@]} -eq 0 ]; then
  while IFS= read -r c; do CASES+=("$c"); done < <(ls "$TEXT")
fi
LOG="local/auto/run.$RELEASE.log"; mkdir -p local/auto

URL=$("$PY" -c "import json;print(json.load(open('state_machines/coding/models.json'))['runtime']['base_url'])")
if ! curl -sf "$URL/api/version" >/dev/null; then
  eval "$("$PY" -c "
import json; e=json.load(open('state_machines/coding/models.json'))['runtime']['env']
e['OLLAMA_NUM_PARALLEL']='${OLLAMA_PARALLEL:-2}'
print(' '.join(f'export {k}={v};' for k,v in e.items()))")"
  nohup ollama serve > local/ollama-pipeline.log 2>&1 &
  sleep 5
fi

{
  echo "== $(date -u +%FT%TZ) code ${#CASES[@]} cases"
  "$PY" -m state_machines.coding.pipeline code "${CASES[@]}" --text-root "$TEXT" ${SELECTIVE:+--selective}
  echo "== $(date -u +%FT%TZ) resolve"
  "$PY" -m state_machines.coding.pipeline resolve "${CASES[@]}" --text-root "$TEXT"
  echo "== $(date -u +%FT%TZ) release $RELEASE"
  "$PY" -m state_machines.coding.pipeline release "$RELEASE" "${CASES[@]}" --text-root "$TEXT" ${OBSERVATIONS:+--observations}
  echo "== $(date -u +%FT%TZ) report"
  "$PY" -m state_machines.coding.report "$RELEASE" ${PILOT:+--pilot "$PILOT"}
  echo "== $(date -u +%FT%TZ) done"
} 2>&1 | tee -a "$LOG"
