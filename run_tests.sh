#!/usr/bin/env bash
set -e

# This project requires Python >=3.12,<3.14 (see pyproject.toml).
# Plain `python3` on your machine may resolve to 3.14 or newer, which
# these pinned dependencies do not support - so we pick an interpreter
# explicitly instead of trusting `python3`.
PYTHON=""
for candidate in python3.13 python3.12; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: need Python 3.12 or 3.13 on PATH (found: $(python3 --version 2>&1))." >&2
    echo "macOS:   brew install python@3.12" >&2
    echo "Ubuntu:  sudo apt install python3.12 python3.12-venv" >&2
    exit 1
fi

echo "Using $($PYTHON --version) at $(command -v "$PYTHON")"

rm -rf venv
"$PYTHON" -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
python -m spacy download en_core_web_md

pytest tests/ -q --cov=app --cov-report=term-missing
