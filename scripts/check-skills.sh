#!/usr/bin/env bash
# Verify the committed client copies still match the canonical skill.
#
# The byte-for-byte comparison lives in tests/test_skill_copies.py so the
# pre-commit hook, CI, and this script share one implementation.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
exec python3 -m pytest -q tests/test_skill_copies.py
