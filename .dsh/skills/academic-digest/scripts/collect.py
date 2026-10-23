#!/usr/bin/env python3
"""Run the collect command from this skill directory without installing the package."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academic_digest.cli import main  # noqa: E402

raise SystemExit(main(["collect", *sys.argv[1:]]))
