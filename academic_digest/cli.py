"""Command line boundary: ``collect``, ``fulltext``, ``digest``, ``push``, and ``doctor``.

Tests and the daily skill drive these subcommands as subprocesses, so every
diagnostic must be readable from stdout/stderr and every failure must have a
non-zero exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import __version__, digest, github, push
from .collect import run as run_collect, write_payload
from .config import Config, load_config
from .errors import ConfigError, SourceError
from .fulltext import fetch as fetch_fulltext
from .fulltext.models import FullText
from .sources import SOURCES
from .state import open_state

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    if args.command == "fulltext":
        return _fulltext(args)
    if args.command == "digest":
        return _digest(args)
    if args.command == "push":
        return _push(args)
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

    fulltext = subparsers.add_parser(
        "fulltext",
        help="fetch an OA full text and extract methods/results/limitations",
    )
    fulltext.add_argument("--config", type=Path, default=Path("config.yaml"))
    fulltext.add_argument(
        "--fixtures",
        type=Path,
        help="directory of recorded responses; no network is touched",
    )
    fulltext.add_argument("--doi", help="DOI of the paper")
    fulltext.add_argument("--arxiv", dest="arxiv_id", help="arXiv ID of the paper")
    fulltext.add_argument(
        "--title",
        help="paper title used to match a preprint version by title",
    )
    fulltext.add_argument(
        "--out",
        type=Path,
        help="full-text JSON path (default: standard output)",
    )

    digest_command = subparsers.add_parser(
        "digest",
        help="validate the model-written selection and daily digest",
    )
    digest_subparsers = digest_command.add_subparsers(
        dest="digest_command", required=True
    )
    check = digest_subparsers.add_parser(
        "check", help="check selection.json and digest.md against the candidate pool"
    )
    check.add_argument(
        "--candidates", type=Path, required=True, help="candidate pool JSON"
    )
    check.add_argument(
        "--selection", type=Path, required=True, help="selection.json written by the model"
    )
    check.add_argument(
        "--digest", type=Path, required=True, help="digest.md written by the model"
    )

    push_command = subparsers.add_parser(
        "push",
        help="send the daily digest to WeChat through Server酱",
    )
    _add_common(
        push_command,
        fixtures_help="directory of recorded ServerChan responses; no network is used",
    )
    push_command.add_argument(
        "--candidates", type=Path, required=True, help="candidate pool JSON"
    )
    push_command.add_argument(
        "--selection", type=Path, required=True, help="selection.json written by the model"
    )
    push_command.add_argument(
        "--digest", type=Path, required=True, help="digest.md written by the model"
    )
    push_command.add_argument("--state-db", type=Path, help="SQLite state path")
    push_command.add_argument(
        "--dry-run",
        action="store_true",
        help="print the ServerChan payload without reading the SendKey or state",
    )
    push_command.add_argument(
        "--out",
        type=Path,
        help="write the dry-run payload here instead of standard output",
    )
    return parser


def _add_common(
    parser: argparse.ArgumentParser,
    *,
    fixtures_help: str = "directory of recorded source responses; no network is touched",
) -> None:
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--fixtures",
        type=Path,
        help=fixtures_help,
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


def _fulltext(args: argparse.Namespace) -> int:
    config = _load(args.config)
    if config is None:
        return EXIT_CONFIG
    doi = (args.doi or "").strip()
    arxiv_id = (args.arxiv_id or "").strip()
    title = (args.title or "").strip()
    if not doi and not arxiv_id and not title:
        _fail("one of --doi, --arxiv or --title is required")
        return EXIT_CONFIG

    result = fetch_fulltext(
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        config=config,
        fixtures_root=args.fixtures,
    )
    payload = result.to_dict()
    if args.out:
        try:
            write_payload(args.out, payload)
        except OSError as exc:
            _fail(f"cannot write full-text output: {exc}")
            return EXIT_FAILURE
        print(_fulltext_summary(result, args.out))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(_fulltext_summary(result, None), file=sys.stderr)
    return EXIT_OK


def _fulltext_summary(result: FullText, path: Path | None) -> str:
    detail = result.summary()
    location = f" -> {path}" if path is not None else ""
    return f"[{result.status}] {detail}{location}"


def _digest(args: argparse.Namespace) -> int:
    try:
        result = digest.check_files(
            args.candidates, args.selection, args.digest
        )
    except digest.CheckError as exc:
        _fail(f"{exc.area}: {exc.message}")
        return EXIT_FAILURE
    print(
        "[ok] digest: "
        f"{result.papers} papers ({result.must_read} must_read + "
        f"{result.quick_scan} quick_scan), {result.github_items} GitHub items"
    )
    return EXIT_OK


def _push(args: argparse.Namespace) -> int:
    config = _load(args.config)
    if config is None:
        return EXIT_CONFIG
    try:
        now = _resolve_now(args.now, config.zone())
    except ValueError as exc:
        _fail(f"--now: {exc}")
        return EXIT_CONFIG
    if args.out is not None and not args.dry_run:
        _fail("--out can only be used with --dry-run")
        return EXIT_CONFIG

    try:
        checked = digest.check_files(args.candidates, args.selection, args.digest)
        inputs = push.load_inputs(
            args.candidates,
            args.selection,
            args.digest,
            github_items=checked.github_items,
        )
    except digest.CheckError as exc:
        _fail(f"{exc.area}: {exc.message}")
        return EXIT_FAILURE
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"push: cannot read inputs: {exc}")
        return EXIT_FAILURE

    if not args.dry_run:
        return _push_live(args, config, inputs, now)

    try:
        plan = push.plan_messages(inputs, config.push, dry_run=True)
    except push.PushFailure as exc:
        _fail(f"push: {exc.message}")
        return exc.exit_code
    if args.out is not None:
        try:
            write_payload(args.out, push.payload(plan))
        except (OSError, sqlite3.Error) as exc:
            _fail(f"push: cannot write payload: {exc}")
            return EXIT_FAILURE
        return EXIT_OK
    print(json.dumps(push.payload(plan), ensure_ascii=False, indent=2))
    return EXIT_OK


def _push_live(
    args: argparse.Namespace,
    config: Config,
    inputs: push.DigestInputs,
    now: datetime,
) -> int:
    playback = args.fixtures is not None
    sender: push.Sender
    if playback:
        sender = push.FixtureSender(args.fixtures)
    else:
        key = os.environ.get(config.push.sendkey_env, "").strip()
        if not key:
            _fail(
                f"push: {config.push.sendkey_env} is not set; "
                "a live push needs the Server酱 SendKey"
            )
            return EXIT_CONFIG
        sender = push.ServerChanSender(key, config.push.timeout)

    state_db = args.state_db or config.state_db
    try:
        with open_state(state_db) as store:
            outcome = push.run_live(
                config, inputs, now, store, sender, playback=playback
            )
    except (OSError, sqlite3.Error) as exc:
        _fail(f"push: cannot open or write the state database: {exc}")
        return EXIT_FAILURE

    if outcome.status == "failed":
        _fail(f"push: {outcome.error or 'send failed'}")
        return outcome.exit_code
    if outcome.skipped_empty and outcome.sent == 0:
        print("[ok] push: skipped empty digest")
    else:
        print(
            f"[ok] push: sent {outcome.sent} message(s), "
            f"recorded {outcome.pushed} paper(s)"
        )
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
            if name == github.NAME:
                message = github.check(config, args.fixtures)
            else:
                message = SOURCES[name].check(config, args.fixtures)
            ok(f"source {name}: {message}")
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
