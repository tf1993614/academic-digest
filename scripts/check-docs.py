#!/usr/bin/env python3
"""Static consistency checks for the docs that steer the digest workflow.

These are the machine-checkable claims the review kept catching by hand: the
docs layout (a short root README that defers to ``docs/``), the MIT license and
its ``pyproject`` field, the command/config references indexed by
``docs/README.md``, the canonical skill path (and the retired repo-root
pointer), relative Markdown links across ``docs/``, the README-side history, the
setup quota table, the transport retry wording, the candidate-pool key
contract, and the review-patch contract. Run from ``scripts/check.sh`` so a doc
that drifts from its code/default fails before commit.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills/academic-digest"
SKILL = SKILL_DIR / "SKILL.md"
SETUP = SKILL_DIR / "references/setup.md"
DOCS = ROOT / "docs"
DOCS_INDEX = DOCS / "README.md"
CLI_DOC = DOCS / "cli.md"
CONFIG_DOC = DOCS / "configuration.md"
DEVELOPMENT_LOG = DOCS / "development-log.md"
README = ROOT / "README.md"
LICENSE = ROOT / "LICENSE"
PYPROJECT = ROOT / "pyproject.toml"
STANDARDS = ROOT / "CODING_STANDARDS.md"
CONFIG = ROOT / "config.example.yaml"
CONFIG_MODULE = SKILL_DIR / "academic_digest/config.py"
BASE = SKILL_DIR / "academic_digest/sources/base.py"
MODELS = SKILL_DIR / "academic_digest/models.py"
SPEC = ROOT / ".scratch/academic-digest/spec.md"
REVIEW_SCRIPT = ROOT / "scripts/review-patch.sh"
REVIEW_DOC = DOCS / "agents/code-review.md"

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
        "](../skills/academic-digest/SKILL.md)" in _text(DEVELOPMENT_LOG),
        "docs/development-log.md must link the canonical skill path",
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
        not (ROOT / "scripts" / "setup-secrets.sh").exists(),
        "scripts/setup-secrets.sh must live inside the skill, not at the repository root",
    )
    wrapper = SKILL_DIR / "scripts" / "run-daily.sh"
    _require(
        failures,
        wrapper.is_file(),
        "missing skills/academic-digest/scripts/run-daily.sh",
    )
    _require(
        failures,
        wrapper.is_file() and os.access(wrapper, os.X_OK),
        "skills/academic-digest/scripts/run-daily.sh must be executable",
    )
    _require(
        failures,
        not (ROOT / "scripts" / "run-daily.sh").exists(),
        "scripts/run-daily.sh must live inside the skill, not at the repository root",
    )
    _require(
        failures,
        (SKILL_DIR / "scripts" / "run-daily-lock.py").is_file(),
        "missing skills/academic-digest/scripts/run-daily-lock.py",
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


def _link_targets(path: Path) -> set[str]:
    """The local link targets of a Markdown file, fragment and query stripped."""

    targets: set[str] = set()
    for raw in _relative_links(_text(path)):
        target = _link_target(raw)
        target = target.split("#", 1)[0].split("?", 1)[0]
        if target:
            targets.add(target)
    return targets


def _require_link(
    failures: list[str], links: set[str], target: str, message: str
) -> None:
    """Require a local link target, accepting both ``x.md`` and ``./x.md``."""

    _require(failures, target in links or f"./{target}" in links, message)


def _check_docs_layout(failures: list[str]) -> None:
    """The visitor-facing surface: a short README pointing at an indexed docs tree."""

    for path in (README, DOCS_INDEX, CLI_DOC, CONFIG_DOC, DEVELOPMENT_LOG):
        _require(
            failures,
            path.is_file(),
            f"missing {path.relative_to(ROOT)}",
        )
    if README.is_file():
        readme = _text(README)
        _require(
            failures,
            {"docs/README.md", "docs/"} & _link_targets(README),
            "README.md must point at docs/README.md (the docs index)",
        )
        _require(
            failures,
            len(readme.splitlines()) <= 30,
            "README.md must stay a short pointer to docs/, not the development log",
        )
        _require(
            failures,
            "```" not in readme,
            "README.md must not repeat the command blocks that now live in docs/",
        )
    if not DOCS_INDEX.is_file():
        return
    index_links = _link_targets(DOCS_INDEX)
    _require_link(failures, index_links, "cli.md", "docs/README.md must link docs/cli.md")
    _require_link(
        failures,
        index_links,
        "configuration.md",
        "docs/README.md must link docs/configuration.md",
    )
    _require_link(
        failures,
        index_links,
        "development-log.md",
        "docs/README.md must link docs/development-log.md",
    )


def _check_cli_doc(failures: list[str]) -> None:
    """The command reference covers every entry point and the exit codes."""

    if not CLI_DOC.is_file():
        return
    text = _text(CLI_DOC)
    for name in ("collect", "fulltext", "digest check", "push", "doctor"):
        _require(
            failures,
            f"## `{name}`" in text,
            f"docs/cli.md must document `{name}`",
        )
    _require(failures, "## 退出码" in text, "docs/cli.md must document the exit codes")
    for code in ("0", "1", "2"):
        _require(
            failures,
            f"| `{code}` |" in text,
            f"docs/cli.md exit-code table must list {code}",
        )


def _config_top_level_keys() -> list[str]:
    """``_TOP_LEVEL_KEYS`` from the config module, without importing it."""

    try:
        tree = ast.parse(_text(CONFIG_MODULE))
    except SyntaxError as exc:
        raise ValueError(f"cannot parse {CONFIG_MODULE}: {exc}") from exc
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_TOP_LEVEL_KEYS"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Set):
            return [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    raise ValueError("config.py must define _TOP_LEVEL_KEYS as a string set literal")


def _check_config_doc(failures: list[str]) -> None:
    """Every accepted top-level config key appears in the configuration reference."""

    if not CONFIG_DOC.is_file():
        return
    text = _text(CONFIG_DOC)
    try:
        keys = _config_top_level_keys()
    except ValueError as exc:
        failures.append(str(exc))
        return
    missing = [
        key
        for key in keys
        if re.search(rf"(?<![0-9A-Za-z_]){re.escape(key)}(?![0-9A-Za-z_])", text)
        is None
    ]
    _require(
        failures,
        not missing,
        f"docs/configuration.md is missing config keys: {', '.join(missing)}",
    )
    _require(
        failures,
        "默认" in text,
        "docs/configuration.md must state the defaults next to the config keys",
    )


def _config_default_constants() -> dict[str, object]:
    """The module-level ``DEFAULT_*`` scalar values from the config module."""

    try:
        tree = ast.parse(_text(CONFIG_MODULE))
    except SyntaxError as exc:
        raise ValueError(f"cannot parse {CONFIG_MODULE}: {exc}") from exc
    constants: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("DEFAULT_"):
                constants[target.id] = node.value.value
    return constants


# Every row in docs/configuration.md's default table that mirrors a config.py
# constant. A value change in the code therefore fails the docs check until the
# documented default follows.
DOCUMENTED_DEFAULTS = {
    "github.token_env": "DEFAULT_GITHUB_TOKEN_ENV",
    "github.new.days": "DEFAULT_NEW_DAYS",
    "github.new.min_stars": "DEFAULT_NEW_MIN_STARS",
    "github.new.max_items": "DEFAULT_NEW_MAX_ITEMS",
    "github.active.days": "DEFAULT_ACTIVE_DAYS",
    "github.active.min_stars": "DEFAULT_ACTIVE_MIN_STARS",
    "github.active.max_items": "DEFAULT_ACTIVE_MAX_ITEMS",
    "github.g6.max_items": "DEFAULT_G6_MAX_ITEMS",
    "github.readme_limit": "DEFAULT_README_LIMIT",
    "github.releases.days": "DEFAULT_RELEASE_DAYS",
    "github.releases.max_items": "DEFAULT_STARRED_RELEASE_MAX_ITEMS",
    "push.sendkey_env": "DEFAULT_PUSH_SENDKEY_ENV",
    "push.channel": "DEFAULT_PUSH_CHANNEL",
    "push.send_empty": "DEFAULT_PUSH_SEND_EMPTY",
    "push.split_bytes": "DEFAULT_PUSH_SPLIT_BYTES",
    "push.max_bytes": "DEFAULT_PUSH_MAX_BYTES",
    "push.max_messages": "DEFAULT_PUSH_MAX_MESSAGES",
    "push.title_max": "DEFAULT_PUSH_TITLE_MAX",
    "push.retries": "DEFAULT_PUSH_RETRIES",
    "push.backoff_seconds": "DEFAULT_PUSH_BACKOFF_SECONDS",
    "push.timeout": "DEFAULT_PUSH_TIMEOUT",
    "push.pending_days": "DEFAULT_PUSH_PENDING_DAYS",
    "pool.max_items": "DEFAULT_MAX_ITEMS",
    "paths.state_db": "DEFAULT_STATE_DB",
    "paths.candidates": "DEFAULT_CANDIDATES",
}


def _documented_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _check_config_defaults(failures: list[str]) -> None:
    """The defaults table matches the constants the parser actually falls back to."""

    if not CONFIG_DOC.is_file():
        return
    text = _text(CONFIG_DOC)
    try:
        constants = _config_default_constants()
    except ValueError as exc:
        failures.append(str(exc))
        return
    for field, constant in DOCUMENTED_DEFAULTS.items():
        if constant not in constants:
            failures.append(f"config.py must define {constant} for {field}")
            continue
        value = _documented_value(constants[constant])
        row = rf"^\| `{re.escape(field)}` \| `{re.escape(value)}` \|"
        _require(
            failures,
            re.search(row, text, re.MULTILINE) is not None,
            f"docs/configuration.md must show {field} default `{value}` "
            f"({constant})",
        )


def _check_license(failures: list[str]) -> None:
    """A usable MIT license, named in the package metadata."""

    if not LICENSE.is_file():
        failures.append("missing LICENSE (MIT, tf1993614)")
    else:
        text = _text(LICENSE)
        _require(
            failures,
            text.startswith("MIT License"),
            "LICENSE must be the MIT license text",
        )
        _require(
            failures,
            "tf1993614" in text,
            "LICENSE must name tf1993614 as the copyright holder",
        )
    try:
        project = tomllib.loads(_text(PYPROJECT)).get("project", {})
    except tomllib.TOMLDecodeError as exc:
        failures.append(f"pyproject.toml is not valid TOML: {exc}")
        return
    license_field = project.get("license")
    declared = license_field == "MIT" or (
        isinstance(license_field, dict) and license_field.get("text") == "MIT"
    )
    _require(
        failures,
        declared,
        "pyproject.toml [project] must declare license = MIT",
    )


def _check_markdown_links(failures: list[str]) -> None:
    docs = [
        README,
        *sorted(DOCS.rglob("*.md")),
        *sorted((ROOT / "skills" / "academic-digest").rglob("*.md")),
    ]
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


def _candidate_sample_keys(text: str, label: str) -> list[str]:
    """The key order of a doc's candidate JSON example."""

    marker = "每篇论文至少包含"
    start = text.find(marker)
    if start < 0:
        raise ValueError(
            f"{label} must introduce the candidate sample with '每篇论文至少包含'"
        )
    fence = text.find("```json", start)
    if fence < 0:
        raise ValueError(f"{label} candidate sample must be a ```json block")
    body_start = fence + len("```json")
    end = text.find("```", body_start)
    if end < 0:
        raise ValueError(f"{label} candidate sample is missing its closing fence")
    try:
        sample = json.loads(text[body_start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} candidate sample is not valid JSON: {exc}") from exc
    if not isinstance(sample, dict):
        raise ValueError(f"{label} candidate sample must be a JSON object")
    return list(sample)


def _check_candidate_keys(failures: list[str], log: str) -> None:
    """Keep ``Paper.to_dict`` and the documented candidate contract in lockstep."""

    try:
        keys = _paper_dict_keys()
    except ValueError as exc:
        failures.append(f"candidate contract: {exc}")
        return
    documented = [(DEVELOPMENT_LOG, log)]
    if CLI_DOC.is_file():
        documented.append((CLI_DOC, _text(CLI_DOC)))
    for path, text in documented:
        label = str(path.relative_to(ROOT))
        try:
            sample_keys = _candidate_sample_keys(text, label)
        except ValueError as exc:
            failures.append(f"candidate contract: {exc}")
            return
        _require(
            failures,
            sample_keys == keys,
            f"{label} candidate sample keys {sample_keys} != Paper.to_dict keys {keys}",
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


def _check_retry_docs(failures: list[str], log: str) -> None:
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
        f"最多 {attempts} 次尝试" in log,
        f"docs/development-log.md must say '最多 {attempts} 次尝试'",
    )
    _require(
        failures,
        f"{attempts - 1} 次重试" in log,
        f"docs/development-log.md must say '{attempts - 1} 次重试'",
    )
    _require(
        failures,
        backoff_text in log,
        f"docs/development-log.md must say '{backoff_text}'",
    )
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
        "429" in log and "2s" in log,
        "docs/development-log.md must document the 429 2s floor",
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
    _check_docs_layout(failures)
    _check_cli_doc(failures)
    _check_config_doc(failures)
    _check_config_defaults(failures)
    _check_license(failures)
    _check_skill_source(failures)
    _check_markdown_links(failures)
    _check_quotas(failures, _text(SETUP))
    log = _text(DEVELOPMENT_LOG)
    _check_candidate_keys(failures, log)
    _check_retry_docs(failures, log)
    _check_review_patch(failures)
    if failures:
        for failure in failures:
            print(f"[fail] docs: {failure}", file=sys.stderr)
        print(f"docs check found {len(failures)} problem(s)", file=sys.stderr)
        return 1
    print(
        "[ok] docs: layout, license, cli/config references, skill source, "
        "markdown links, quotas, retry wording, candidate keys, transport tests, "
        "review patch"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
