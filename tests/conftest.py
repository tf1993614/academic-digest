import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "academic-digest"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = "2026-10-22T08:00:00+08:00"

# The package lives inside the skill, not at the repository root. Tests that
# import internals (the CLI seam never does) need the same path a user's entry
# script would add; the repository is not an installed distribution here.
sys.path.insert(0, str(SKILL))


@pytest.fixture
def cli():
    """Run the CLI as a user would: a fresh subprocess, never imported internals."""

    def run(*args, cwd=ROOT, env=None):
        command = str(args[0])
        script = SKILL / "scripts" / f"{command}.py"
        child_env = os.environ.copy()
        child_env.pop("PYTHONPATH", None)
        if env:
            child_env.update(env)
        return subprocess.run(
            [sys.executable, str(script), *map(str, args[1:])],
            cwd=cwd,
            env=child_env,
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


def collect_options(root, *, out, state_db, config=None, now=NOW):
    """The fixture-collect arguments, shared by the CLI seam and copy tests."""

    root = Path(root)
    return [
        "--config",
        config or root / "config.yaml",
        "--fixtures",
        root,
        "--now",
        now,
        "--out",
        out,
        "--state-db",
        state_db,
    ]


def run_collect(
    cli, paths, fixture, *, config=None, out=None, fixtures_dir=None, now=NOW, env=None
):
    """Run ``collect`` against a fixture tree through the CLI seam."""

    root = Path(fixtures_dir) if fixtures_dir else FIXTURES / fixture
    return cli(
        "collect",
        *collect_options(
            root,
            out=out or paths["out"],
            state_db=paths["db"],
            config=config,
            now=now,
        ),
        env=env,
    )


def run_fulltext(cli, paths, fixture, *args, config=None, out=None):
    """Run ``fulltext`` against one fixture scenario through the CLI seam."""

    root = FIXTURES / "fulltext" / fixture
    return cli(
        "fulltext",
        "--config",
        config or FIXTURES / "fulltext" / "config.yaml",
        "--fixtures",
        root,
        *args,
        "--out",
        out or paths["out"],
    )


def run_digest(cli, case):
    """Run ``digest check`` against a fixture directory through the CLI seam."""

    root = Path(case)
    return cli(
        "digest",
        "check",
        "--candidates",
        root / "candidates.json",
        "--selection",
        root / "selection.json",
        "--digest",
        root / "digest.md",
    )


def run_push(
    cli,
    case,
    *,
    config,
    fixtures=None,
    state_db=None,
    now=NOW,
    dry_run=False,
    out=None,
    extra=(),
    env=None,
):
    """Run ``push`` against a digest case directory through the CLI seam."""

    root = Path(case)
    args = [
        "push",
        "--config",
        config,
        "--candidates",
        root / "candidates.json",
        "--selection",
        root / "selection.json",
        "--digest",
        root / "digest.md",
        "--now",
        now,
    ]
    if state_db is not None:
        args += ["--state-db", state_db]
    if fixtures is not None:
        args += ["--fixtures", fixtures]
    if dry_run:
        args += ["--dry-run"]
    if out is not None:
        args += ["--out", out]
    args.extend(extra)
    return cli(*args, env=env)


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
