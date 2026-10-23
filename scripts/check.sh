#!/usr/bin/env bash
# One deterministic check run for the local pre-commit hook and CI.
# Usage: scripts/check.sh [DIR]   # DIR defaults to this repository's root
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$root"

python3 -m mypy skills/academic-digest/academic_digest
python3 -m pyflakes skills/academic-digest/academic_digest skills/academic-digest/scripts scripts tests
python3 scripts/check-docs.py
python3 -m pytest -q
