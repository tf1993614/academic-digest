#!/usr/bin/env python3
"""Static consistency checks for the docs that steer the digest workflow.

These are the machine-checkable claims the review kept catching by hand: the
canonical skill path (and the retired repo-root pointer), relative Markdown
links in the README and skill docs, the setup quota table, the transport retry
wording, the candidate-pool key contract, and the review-patch contract. Run
from ``scripts/check.sh`` so a doc that drifts from its code/default fails before
commit.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills/academic-digest"
SKILL = SKILL_DIR / "SKILL.md"
SETUP = SKILL_DIR / "references/setup.md"
README = ROOT / "README.md"
STANDARDS = ROOT / "CODING_STANDARDS.md"
CONFIG = ROOT / "config.example.yaml"
BASE = SKILL_DIR / "academic_digest/sources/base.py"
MODELS = SKILL_DIR / "academic_digest/models.py"
SPEC = ROOT / ".scratch/academic-digest/spec.md"
REVIEW_SCRIPT = ROOT / "scripts/review-patch.sh"
REVIEW_DOC = ROOT / "docs/agents/code-review.md"

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"[fail] docs: cannot read {path}: {exc}") from exc


def _require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _check_skill_source(failures: list[str]) -> None:
    _require(failures, SKILL.is_file(), "missing skills/academic-digest/SKILL.md")
    pointer = ROOT / "SKILL.md"
    _require(
        failures,
        not pointer.is_symlink() and not pointer.exists(),
        "repo-root SKILL.md must stay deleted; the source lives in skills/academic-digest/",
    )
    _require(
        failures,
        "](skills/academic-digest/SKILL.md)" in _text(README),
        "README must link the canonical skill path",
    )
    for name in ("collect", "digest", "doctor", "fulltext", "push"):
        _require(
            failures,
            (SKILL_DIR / "scripts" / f"{name}.py").is_file(),
            f"missing skills/academic-digest/scripts/{name}.py",
        )
        _require(
            failures,
            not (ROOT / "scripts" / f"{name}.py").exists(),
            f"scripts/{name}.py must live inside the skill, not at the repository root",
        )
    _require(
        failures,
        (SKILL_DIR / "scripts" / "setup-secrets.sh").is_file(),
        "missing skills/academic-digest/scripts/setup-secrets.sh",
    )
    _require(
        failures,
        (SKILL_DIR / "academic_digest" / "cli.py").is_file(),
        "missing skills/academic-digest/academic_digest/cli.py",
    )
    _require(
        failures,
        not (ROOT / "academic_digest").exists(),
        "the academic_digest package must live inside the skill for a copy to run alone",
    )


def _relative_links(text: str) -> list[str]:
    """Markdown link targets in prose, ignoring fenced and inline code."""

    links: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r"`[^`]*`", "", line)
        links.extend(match.group(1).strip() for match in MARKDOWN_LINK.finditer(line))
    return links


def _link_target(raw: str) -> str:
    if raw.startswith("<"):
        end = raw.find(">")
        return raw[1:end] if end >= 0 else raw[1:]
    return raw.split(None, 1)[0]


def _check_markdown_links(failures: list[str]) -> None:
    docs = [README, *sorted((ROOT / "skills" / "academic-digest").rglob("*.md"))]
    for path in docs:
        for raw in _relative_links(_text(path)):
            target = _link_target(raw)
            if not target or target.startswith("#") or URL_SCHEME.match(target):
                continue
            target = target.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            base = ROOT if target.startswith("/") else path.parent
            if not (base / target.lstrip("/")).exists():
                failures.append(f"{path.relative_to(ROOT)}: broken relative link {raw!r}")


def _paper_dict_keys() -> list[str]:
    """The candidate-pool keys, read from ``Paper.to_dict`` without importing it."""

    try:
        tree = ast.parse(_text(MODELS))
    except SyntaxError as exc:
        raise ValueError(f"cannot parse {MODELS}: {exc}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Paper":
            continue
        for member in node.body:
            if not isinstance(member, ast.FunctionDef) or member.name != "to_dict":
                continue
            for statement in ast.walk(member):
                if (
                    isinstance(statement, ast.Return)
                    and isinstance(statement.value, ast.Dict)
                ):
                    keys = [
                        key.value
                        for key in statement.value.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    ]
                    if keys:
                        return keys
    raise ValueError("Paper.to_dict must return a string-keyed dict literal")


def _readme_sample_keys(readme: str) -> list[str]:
    """The key order of the README's candidate JSON example."""

    marker = "每篇论文至少包含"
    start = readme.find(marker)
    if start < 0:
        raise ValueError("README must introduce the candidate sample with '每篇论文至少包含'")
    fence = readme.find("```json", start)
    if fence < 0:
        raise ValueError("README candidate sample must be a ```json block")
    body_start = fence + len("```json")
    end = readme.find("```", body_start)
    if end < 0:
        raise ValueError("README candidate sample is missing its closing fence")
    try:
        sample = json.loads(readme[body_start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"README candidate sample is not valid JSON: {exc}") from exc
    if not isinstance(sample, dict):
        raise ValueError("README candidate sample must be a JSON object")
    return list(sample)


def _check_candidate_keys(failures: list[str], readme: str) -> None:
    """Keep ``Paper.to_dict`` and the documented candidate contract in lockstep."""

    try:
        keys = _paper_dict_keys()
        sample_keys = _readme_sample_keys(readme)
    except ValueError as exc:
        failures.append(f"candidate contract: {exc}")
        return
    _require(
        failures,
        sample_keys == keys,
        f"README candidate sample keys {sample_keys} != Paper.to_dict keys {keys}",
    )

    spec = _text(SPEC)
    heading = "### 候选池与模型契约"
    start = spec.find(heading)
    if start < 0:
        failures.append(f"spec.md must have a '{heading}' section")
        return
    next_heading = spec.find("\n### ", start + len(heading))
    section = spec[start:] if next_heading < 0 else spec[start:next_heading]
    missing = [
        key
        for key in keys
        if re.search(rf"(?<![0-9A-Za-z_]){re.escape(key)}(?![0-9A-Za-z_])", section)
        is None
    ]
    _require(
        failures,
        not missing,
        f"spec.md candidate contract is missing keys: {', '.join(missing)}",
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
    _require(
        failures,
        "--verify" in script,
        "scripts/review-patch.sh must support --verify",
    )
    _require(
        failures,
        "--include-generated" in script,
        "scripts/review-patch.sh must keep generated copies opt-in",
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
    _require(
        failures,
        "review-patch.sh --verify" in doc,
        "docs/agents/code-review.md must tell reviewers to run --verify",
    )
    _require(
        failures,
        "check-skills.sh" in doc,
        "docs/agents/code-review.md must point reviewers at check-skills.sh",
    )


def main() -> int:
    failures: list[str] = []
    _check_skill_source(failures)
    _check_markdown_links(failures)
    _check_quotas(failures, _text(SETUP))
    readme = _text(README)
    _check_candidate_keys(failures, readme)
    _check_retry_docs(failures, readme)
    _check_review_patch(failures)
    if failures:
        for failure in failures:
            print(f"[fail] docs: {failure}", file=sys.stderr)
        print(f"docs check found {len(failures)} problem(s)", file=sys.stderr)
        return 1
    print(
        "[ok] docs: skill source, markdown links, quotas, retry wording, "
        "candidate keys, transport tests, review patch"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
