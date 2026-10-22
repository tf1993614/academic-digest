"""Command line boundary: ``collect`` and ``doctor``.

Tests and the daily skill drive these subcommands as subprocesses, so every
diagnostic must be readable from stdout/stderr and every failure must have a
non-zero exit code.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import __version__
from .collect import run as run_collect
from .config import Config, load_config
from .errors import ConfigError, SourceError
from .sources import SOURCES

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    if args.command == "doctor":
        return _doctor(args)
    parser.error("a command is required")
    return EXIT_CONFIG


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="academic-digest",
        description="Collect papers from configured sources into a candidate pool.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="fetch new papers into the candidate pool")
    _add_common(collect)
    collect.add_argument("--out", type=Path, help="candidate JSON path")
    collect.add_argument("--state-db", type=Path, help="SQLite state path")

    doctor = subparsers.add_parser("doctor", help="check configuration, sources, and paths")
    _add_common(doctor)
    doctor.add_argument("--out", type=Path, help="candidate JSON path to check")
    doctor.add_argument("--state-db", type=Path, help="SQLite state path to check")
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--fixtures",
        type=Path,
        help="directory of recorded source responses; no network is touched",
    )
    parser.add_argument(
        "--now",
        help="logical clock as ISO-8601 (tests pass a fixed value)",
    )


def _collect(args: argparse.Namespace) -> int:
    config = _load(args.config)
    if config is None:
        return EXIT_CONFIG
    try:
        now = _resolve_now(args.now, config.zone())
    except ValueError as exc:
        _fail(f"--now: {exc}")
        return EXIT_CONFIG

    out_path = args.out or config.candidates_path
    state_db = args.state_db or config.state_db
    try:
        result = run_collect(
            config,
            fixtures_root=args.fixtures,
            now=now,
            out_path=out_path,
            state_db=state_db,
        )
    except (OSError, sqlite3.Error) as exc:
        _fail(f"cannot write output or state: {exc}")
        return EXIT_FAILURE

    for source in result.sources:
        if source.status == "ok":
            print(f"[ok] {source.name}: {source.count} records")
        else:
            _fail(f"{source.name}: {source.error}")
    print(f"collected {len(result.papers)} candidates -> {out_path}")
    if result.all_failed:
        _fail("all enabled sources failed; candidate pool is empty")
        return EXIT_FAILURE
    return EXIT_OK


def _doctor(args: argparse.Namespace) -> int:
    config = _load(args.config)
    if config is None:
        return EXIT_CONFIG
    logical_now = None
    if args.now:
        try:
            logical_now = _resolve_now(args.now, config.zone())
        except ValueError as exc:
            _fail(f"--now: {exc}")
            return EXIT_CONFIG

    failures = 0

    def ok(message: str) -> None:
        print(f"[ok] {message}")

    def fail(message: str) -> None:
        nonlocal failures
        failures += 1
        _fail(message)

    ok(f"config: {config.path}")
    ok(f"timezone: {config.timezone}")
    if logical_now is not None:
        ok(f"clock: {logical_now.isoformat()}")
    ok(f"topics: {', '.join(topic.name for topic in config.topics)}")
    for topic in config.topics:
        ok(
            f"topic {topic.name} ({topic.label}): {len(topic.terms)} terms, "
            f"max {topic.max_items}"
        )

    for name in config.enabled_sources:
        try:
            ok(f"source {name}: {SOURCES[name].check(config, args.fixtures)}")
        except (SourceError, OSError) as exc:
            fail(f"source {name}: {exc}")

    state_db = args.state_db or config.state_db
    out_path = args.out or config.candidates_path
    _check_writable_path(state_db, "state", ok, fail)
    _check_writable_path(out_path, "candidates", ok, fail)

    if failures:
        print(f"doctor found {failures} problem(s)", file=sys.stderr)
        return EXIT_FAILURE
    print("doctor: all checks passed")
    return EXIT_OK


def _check_writable_path(
    path: Path,
    label: str,
    ok: Callable[[str], None],
    fail: Callable[[str], None],
) -> None:
    if path.exists() and path.is_dir():
        fail(f"{label}: {path} is a directory, expected a file")
        return
    if path.exists():
        if os.access(path, os.W_OK):
            ok(f"{label}: {path} is writable")
        else:
            fail(f"{label}: {path} is not writable")
        return
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if parent.exists() and os.access(parent, os.W_OK):
        ok(f"{label}: {path} can be created")
    else:
        fail(f"{label}: parent directory is not writable: {parent}")


def _load(path: Path) -> Config | None:
    try:
        return load_config(path)
    except ConfigError as exc:
        _fail(f"{exc.field}: {exc.message}")
        return None


def _resolve_now(value: str | None, zone: ZoneInfo) -> datetime:
    if not value:
        return datetime.now(zone)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed


def _fail(message: str) -> None:
    print(f"[fail] {message}", file=sys.stderr)
