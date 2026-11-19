#!/usr/bin/env bash
# Load a PACER release into a throwaway local Oxigraph and verify it against its manifest,
# for both graph selections (evidence + trajectories, evidence only). Touches no shared store.
#
#   scripts/run/verify_pacer_release.sh <release_id>
#
# Environment: OXIGRAPH_CLI (oxigraph binary, default `oxigraph`), PYTHON, PORT (default 7899).
set -euo pipefail
cd "$(dirname "$0")/../.."
RELEASE="${1:?release id}"
PY="${PYTHON:-python3}"; CLI="${OXIGRAPH_CLI:-oxigraph}"; PORT="${PORT:-7899}"
WORK="local/oxi-verify"; mkdir -p "$WORK"
export PYTHONPATH=. DATABASE_URL=''
printf '<urn:s> <urn:p> "o" <https://w3id.org/caselinker/resource/case/stub_001> .\n' > "$WORK/stub.nq"
status=0
for sel in all evidence; do
  store="$WORK/store-$sel"; rm -rf "$store"
  "$CLI" serve --location "$store" --bind "127.0.0.1:$PORT" > "$WORK/oxigraph-$sel.log" 2>&1 &
  pid=$!
  for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$PORT/" -o /dev/null && break; sleep 0.25; done
  if "$PY" scripts/oxigraph/rebuild_oxigraph.py --skip-build --output "$WORK/stub.nq" --pacer-release "$RELEASE" \
       --pacer-graphs "$sel" --oxigraph-url "http://127.0.0.1:$PORT" --verify --min-case-graphs 1; then
    echo "verified: $RELEASE ($sel)"
  else
    echo "FAILED: $RELEASE ($sel)"; status=1
  fi
  kill "$pid"; wait "$pid" 2>/dev/null || true
  rm -rf "$store"
done
exit $status
