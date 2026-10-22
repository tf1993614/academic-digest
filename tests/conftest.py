import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


def run_collect(cli, paths, fixture, *, config=None, out=None, fixtures_dir=None, now=NOW):
    """Run ``collect`` against a fixture tree through the CLI seam."""

    root = Path(fixtures_dir) if fixtures_dir else FIXTURES / fixture
    return cli(
        "collect",
        "--config",
        config or root / "config.yaml",
        "--fixtures",
        root,
        "--now",
        now,
        "--out",
        out or paths["out"],
        "--state-db",
        paths["db"],
    )


def enable_sources(root: Path, *names: str) -> None:
    """Turn sources on in a copied fixture's config before running the CLI."""

    config_path = Path(root) / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for name in names:
        config["sources"][name] = True
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
