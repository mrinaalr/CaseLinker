#!/bin/sh
# Ingest every PDF in the CaseLinker repo root into the DB via src/main.py
# (use after clearing Railway/Postgres or local SQLite). Does not recurse into
# subfolders (ontology/, scripts/, tmp/, etc.).
#
# POSIX sh (macOS /bin/sh, Railway); no bash-4 mapfile.
#
# Usage (from repo root):
#   ./scripts/run/ingest_all_pdfs.sh
#   ./scripts/run/ingest_all_pdfs.sh --no-aggregate
#   DATABASE_URL=... ./scripts/run/ingest_all_pdfs.sh   # Railway Postgres
#
# --no-aggregate: skip aggregate federal reports so you can load state/ICAC PDFs
# first, then ingest NCMEC / DOJ separately. Skips when the PDF basename (case-
# insensitive) matches:
#   NCMEC / CyberTipline: *ncmec*, *cybertipline*, *cyber*tipline*
#   DOJ CEOS / AI-CSAM / Archives / PSC: *doj*ceos*, *doj*ai*csam*, *doj*archiv*, *doj*safe*childhood*
#
set -e

NO_AGGREGATE=0
for arg in "$@"; do
  case "$arg" in
    --no-aggregate) NO_AGGREGATE=1 ;;
    -h | --help)
      cat <<'EOF' >&2
Usage: scripts/run/ingest_all_pdfs.sh [--no-aggregate]

  (default)       Ingest every PDF in the repo root only (including NCMEC / DOJ).
  --no-aggregate  Skip PDFs whose basename looks like NCMEC/CyberTipline or
                  DOJ CEOS/Archives (see header comment in this script).
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --help)" >&2
      exit 1
      ;;
  esac
done

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT" || exit 1

if [ -d .venv ]; then
  # shellcheck source=/dev/null
  . .venv/bin/activate
fi

# Pattern layer modules (ai_extraction_patterns, etc.) live beside processing.py
PATTERN_LAYER="$REPO_ROOT/src/Processing Layer/Pattern Processing Layer"
export PYTHONPATH="$PATTERN_LAYER:$REPO_ROOT/src/Processing Layer:$REPO_ROOT/src/Ingestion Layer:$REPO_ROOT/src/Storage Layer:$REPO_ROOT/src:$PYTHONPATH"

# Write one path per line (sorted) to stdout — repo root *.pdf only.
filtered_sorted_pdf_paths() {
  for f in "$REPO_ROOT"/*.pdf; do
    [ -f "$f" ] || continue
    if [ "$NO_AGGREGATE" -eq 1 ]; then
      bn=$(basename "$f" | tr '[:upper:]' '[:lower:]')
      case "$bn" in
        *ncmec* | *cybertipline* | *cyber*tipline*) continue ;;
        *doj*ceos* | *doj*ai*csam* | *doj*archiv* | *doj*safe*childhood*) continue ;;
      esac
    fi
    printf '%s\n' "$f"
  done | sort
}

LIST=$(mktemp "${TMPDIR:-/tmp}/ingest_pdf_list.XXXXXX")
trap 'rm -f "$LIST"' EXIT

filtered_sorted_pdf_paths >"$LIST"

COUNT=$(wc -l <"$LIST" | tr -d '[:space:]')
if [ "$COUNT" -eq 0 ]; then
  if [ "$NO_AGGREGATE" -eq 1 ]; then
    echo "No PDFs left after --no-aggregate filter in $REPO_ROOT" >&2
  else
    echo "No PDFs found in $REPO_ROOT" >&2
  fi
  exit 1
fi

echo "Found $COUNT PDF(s); running pipeline..." >&2
while IFS= read -r f; do
  echo "  - $f" >&2
done <"$LIST"

# Avoid xargs-only pipelines (ARG_MAX-safe for typical ingest sizes; POSIX sh).
set --
while IFS= read -r f; do
  [ -n "$f" ] || continue
  set -- "$@" "$f"
done <"$LIST"
python3 src/main.py "$@"
