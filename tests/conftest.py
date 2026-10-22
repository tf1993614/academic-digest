import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = "2026-10-22T08:00:00+08:00"


@pytest.fixture
def cli():
    """Run the CLI as a user would: a fresh subprocess, never imported internals."""

    def run(*args, cwd=ROOT):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        return subprocess.run(
            [sys.executable, "-m", "academic_digest", *map(str, args)],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    return run


@pytest.fixture
def paths(tmp_path):
    return {
        "out": tmp_path / "candidates.json",
        "db": tmp_path / "state.sqlite3",
        "tmp": tmp_path,
    }
