#!/bin/bash

# CaseLinker Setup Script
# Creates virtual environment and installs all dependencies

set -e  # Exit on error

echo "============================================================"
echo "CaseLinker - Environment Setup"
echo "============================================================"

# Python 3.10–3.14. Tries $PYTHON first, then 3.12 (tested), 3.13, 3.14, 3.11, 3.10, python3, python.
# A candidate that cannot create a venv with a working pip (a broken install) is skipped.
venv_python() {  # path of the venv's interpreter: .venv/bin (macOS, Linux, WSL) or .venv/Scripts (Windows)
    if [ -x ".venv/bin/python" ]; then echo ".venv/bin/python"; else echo ".venv/Scripts/python.exe"; fi
}
supported() {
    "$1" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)' 2>/dev/null
}

if [ -d ".venv" ] && "$(venv_python)" -m pip --version &> /dev/null && supported "$(venv_python)"; then
    echo "✓ Using existing .venv ($("$(venv_python)" --version))"
else
    rm -rf .venv
    TRIED=""
    for PY in ${PYTHON:-} python3.12 python3.13 python3.14 python3.11 python3.10 python3 python; do
        command -v "$PY" &> /dev/null || continue
        supported "$PY" || { TRIED="$TRIED\n   $PY: $("$PY" --version 2>&1) (needs 3.10–3.14)"; continue; }
        if "$PY" -m venv .venv &> /dev/null && "$(venv_python)" -m pip --version &> /dev/null; then
            echo "✓ Created .venv with $("$PY" --version) ($PY)"
            break
        fi
        echo "   Skipping $PY ($("$PY" --version 2>&1)): it cannot create a venv with a working pip."
        TRIED="$TRIED\n   $PY: $("$PY" --version 2>&1) cannot create a venv with pip (broken install)"
        rm -rf .venv
    done
    if [ ! -d ".venv" ] && command -v uv &> /dev/null; then
        echo "No usable Python on PATH; uv is fetching Python 3.12..."
        uv venv --seed --python 3.12 .venv
    fi
    if [ ! -d ".venv" ]; then
        printf "❌ No usable Python 3.10–3.14 found.%b\n" "$TRIED"
        echo "   Install Python 3.12 from https://www.python.org/downloads/ (macOS: brew install python@3.12),"
        echo "   or set PYTHON=/path/to/python and rerun ./setup.sh."
        exit 1
    fi
fi
VPY="$(venv_python)"

# Upgrade pip
echo ""
echo "Upgrading pip..."
"$VPY" -m pip install --upgrade pip --quiet

# Install dependencies: requirements.txt (the web app, API, MCP and tests; what Railway installs)
# and requirements-sdk.txt (ingest NER/ML, translation, CASE-UCO SDK). --core: requirements.txt only.
REQS="-r requirements.txt -r requirements-sdk.txt"
if [ "${1:-}" = "--core" ]; then
    REQS="-r requirements.txt"
fi
echo ""
echo "Installing dependencies ($REQS)..."
"$VPY" -m pip install $REQS

# Download spaCy English model (required for NER)
echo ""
echo "Downloading spaCy English model (en_core_web_sm)..."
"$VPY" -m spacy download en_core_web_sm || echo "⚠️  Warning: Could not download spaCy model. NER will not work until you run: python -m spacy download en_core_web_sm"

echo ""
echo "============================================================"
echo "✓ Setup Complete!"
echo "============================================================"
echo ""
echo "To activate the virtual environment, run:"
echo "  source .venv/bin/activate        (Windows Git Bash: source .venv/Scripts/activate)"
echo ""
echo ""
echo "Then you can run:"
echo "  DATABASE_URL='' python3 -m pytest -q   # full test suite"
echo "  python3 -m src.main          # Process PDF and store cases"
echo "  python3 run/main.py          # Start API server for visualization"
echo ""
echo "API Server:"
echo "  - Backend: http://localhost:8000"
echo "  - Visualization: http://localhost:8000/visualization"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
echo "To deactivate, run:"
echo "  deactivate"
echo ""
