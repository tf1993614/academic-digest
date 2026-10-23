#!/usr/bin/env python3
"""Static consistency checks for the docs that steer the digest workflow.

These are the machine-checkable claims the review kept catching by hand: the
repo-root skill pointer, the setup quota table, the transport retry wording,
and the review-patch contract. Run from ``scripts/check.sh`` so a doc that
drifts from its code/default fails before commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".dsh/skills/academic-digest/SKILL.md"
SETUP = ROOT / ".dsh/skills/academic-digest/references/setup.md"
README = ROOT / "README.md"
STANDARDS = ROOT / "CODING_STANDARDS.md"
CONFIG = ROOT / "config.example.yaml"
BASE = ROOT / "academic_digest/sources/base.py"
REVIEW_SCRIPT = ROOT / "scripts/review-patch.sh"
REVIEW_DOC = ROOT / "docs/agents/code-review.md"


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"[fail] docs: cannot read {path}: {exc}") from exc


def _require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _check_skill_pointer(failures: list[str]) -> None:
    _require(failures, SKILL.is_file(), "missing .dsh/skills/academic-digest/SKILL.md")
    pointer = ROOT / "SKILL.md"
    _require(failures, pointer.is_symlink(), "repo-root SKILL.md must be a symlink")
    if pointer.is_symlink():
        _require(
            failures,
            pointer.resolve() == SKILL.resolve(),
            "repo-root SKILL.md must point at .dsh/skills/academic-digest/SKILL.md",
        )
    _require(
        failures,
        "](.dsh/skills/academic-digest/SKILL.md)" in _text(README),
        "README must link the canonical skill path",
    )


def _check_quotas(failures: list[str], setup: str) -> None:
    match = re.search(r"G2 ≤ (\d+)，G6 (\d+)，其它 (\d+)", setup)
    if match is None:
        failures.append("setup.md must state 'G2 ≤ 4，G6 2，其它 6'")
        return
    g2, g6, others = (int(value) for value in match.groups())
    try:
        config = yaml.safe_load(_text(CONFIG))
    except yaml.YAMLError as exc:
        failures.append(f"config.example.yaml is not valid YAML: {exc}")
        return
    topics = config.get("topics") if isinstance(config, dict) else None
    if not isinstance(topics, list):
        failures.append("config.example.yaml topics must be a list")
        return
    quotas: dict[str, int] = {}
    for topic in topics:
        if not isinstance(topic, dict) or not topic.get("name"):
            continue
        try:
            quotas[str(topic["name"])] = int(topic.get("max_items", 6))
        except (TypeError, ValueError):
            failures.append(
                f"config.example.yaml topic {topic['name']} has a non-integer max_items"
            )
    _require(
        failures,
        quotas.get("G2") == g2,
        f"config.example.yaml G2 max_items {quotas.get('G2')} != setup.md {g2}",
    )
    _require(
        failures,
        quotas.get("G6") == g6,
        f"config.example.yaml G6 max_items {quotas.get('G6')} != setup.md {g6}",
    )
    for name, value in quotas.items():
        if name in {"G2", "G6"}:
            continue
        _require(
            failures,
            value == others,
            f"config.example.yaml {name} max_items {value} != setup.md other-group {others}",
        )


def _check_retry_docs(failures: list[str], readme: str) -> None:
    base = _text(BASE)
    attempts_match = re.search(r"^_HTTP_ATTEMPTS = (\d+)$", base, re.MULTILINE)
    backoff_match = re.search(
        r"^_HTTP_BACKOFF_SECONDS = ([\d.]+)$", base, re.MULTILINE
    )
    if attempts_match is None or backoff_match is None:
        failures.append("base.py must define _HTTP_ATTEMPTS and _HTTP_BACKOFF_SECONDS")
        return
    attempts = int(attempts_match.group(1))
    backoff = float(backoff_match.group(1))
    backoff_text = f"{backoff:g}s/{backoff * 2:g}s"
    standards = _text(STANDARDS)
    _require(
        failures,
        f"最多 {attempts} 次尝试" in readme,
        f"README must say '最多 {attempts} 次尝试'",
    )
    _require(
        failures,
        f"{attempts - 1} 次重试" in readme,
        f"README must say '{attempts - 1} 次重试'",
    )
    _require(failures, backoff_text in readme, f"README must say '{backoff_text}'")
    _require(
        failures,
        f"up to {attempts} attempts" in standards,
        f"CODING_STANDARDS must say 'up to {attempts} attempts'",
    )
    _require(
        failures,
        backoff_text in standards,
        f"CODING_STANDARDS must say '{backoff_text}'",
    )
    _require(
        failures,
        "429" in readme and "2s" in readme,
        "README must document the 429 2s floor",
    )
    _require(
        failures,
        "429" in standards and "2s" in standards,
        "CODING_STANDARDS must document the 429 2s floor",
    )
    for name in ("tests/test_push_transport.py", "tests/test_source_http.py"):
        _require(
            failures,
            name in standards,
            f"CODING_STANDARDS must name {name}",
        )


def _check_review_patch(failures: list[str]) -> None:
    script = _text(REVIEW_SCRIPT)
    _require(
        failures,
        'git diff "$base"...HEAD' in script,
        'scripts/review-patch.sh --base must diff "$base"...HEAD',
    )
    _require(
        failures,
        "git status --porcelain" in script,
        "scripts/review-patch.sh --base must reject a dirty working tree",
    )
    doc = _text(REVIEW_DOC)
    _require(
        failures,
        "out/review/current.diff.head" in doc,
        "docs/agents/code-review.md must tell reviewers to check .head",
    )
    _require(
        failures,
        "git rev-parse HEAD" in doc,
        "docs/agents/code-review.md must show the HEAD check",
    )


def main() -> int:
    failures: list[str] = []
    _check_skill_pointer(failures)
    _check_quotas(failures, _text(SETUP))
    readme = _text(README)
    _check_retry_docs(failures, readme)
    _check_review_patch(failures)
    if failures:
        for failure in failures:
            print(f"[fail] docs: {failure}", file=sys.stderr)
        print(f"docs check found {len(failures)} problem(s)", file=sys.stderr)
        return 1
    print(
        "[ok] docs: skill pointer, quotas, retry wording, transport tests, review patch"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
