#!/usr/bin/env bash
# One deterministic check run for the local pre-commit hook and CI.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m mypy academic_digest
python3 -m pyflakes academic_digest scripts tests
python3 -m pytest -q
