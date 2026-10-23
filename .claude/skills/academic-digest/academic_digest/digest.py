"""Validate the model-written selection record and daily digest.

``digest check`` is the contract gate between the writing step and the push
step. It reads three files — the candidate pool that ``collect`` produced, the
model's ``selection.json``, and the rendered ``digest.md`` — and rejects the
first violation. It never reads configuration, secrets, the state database, or
the network, so the same command can run before ``push``.

The checks are structural first (the fixed Markdown shape and its literal field
labels), then cross-file: every selected id must be in the candidate pool with
the same group, the 3 + 7 targets must hold unless the G2 quota makes them
impossible, every paper title in the digest must match a candidate title
verbatim, every GitHub/G6 item must mirror ``candidates.github`` exactly, and
the footer must report the pool counts and every source status without leaking
a secret.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MUST_READ_LIMIT = 3
QUICK_SCAN_LIMIT = 7
SELECTION_LIMIT = MUST_READ_LIMIT + QUICK_SCAN_LIMIT
G2_MAX_ITEMS = 4
G6_MAX_PAPERS = 1
DEFAULT_G6_MAX_ITEMS = 2
NO_OA_MARKER = "无 OA 全文，仅基于摘要"

SECTIONS = ("今日必读", "其它速览", "GitHub", "AI 工具 / Agent Harness")
GITHUB_SUBSECTIONS = {
    "新项目": "new",
    "活跃项目": "active",
    "关注项目的新 release": "starred",
}

_TITLE = re.compile(r"^#\s*学术速递\s*·\s*(.+?)\s*$")
_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_MUST_HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
_SUBSECTION = re.compile(r"^###\s+(.+?)\s*$")
_FIELD = re.compile(r"^-\s*(标签|摘要|局限性|方法精读)：(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_LINK = re.compile(r"\[[^\]]+\]\([^)\s]+\)")
_TAG = re.compile(r"`[^`]+`")
_SOURCE_LINE = re.compile(r"^来源：", re.MULTILINE)
_CANDIDATE_COUNT = re.compile(r"候选：\s*(\d+)")
_SELECTED_COUNT = re.compile(r"入选：\s*(\d+)")
_GENERATED_AT = re.compile(r"生成：\s*(\S+)")
_SECRET = re.compile(r"(?i)(sctp|sendkey|github_token|authorization)")
_SECRET_KEY = re.compile(r"\bSCT[A-Z0-9]{6,}\b")

_FIELD_ATTRS = {
    "标签": "labels",
    "摘要": "summary",
    "局限性": "limitations",
    "方法精读": "methods",
}


class CheckError(Exception):
    """One contract violation, tagged with the file family that broke it."""

    def __init__(self, area: str, message: str) -> None:
        super().__init__(f"{area}: {message}")
        self.area = area
        self.message = message


@dataclass(frozen=True)
class CheckResult:
    """Counts for the CLI's success line."""

    papers: int
    must_read: int
    quick_scan: int
    github_items: int


@dataclass(frozen=True)
class CandidatePool:
    date: str
    timezone: str
    zone: ZoneInfo
    candidate_count: int
    papers: tuple[Mapping[str, Any], ...]
    sources: Mapping[str, Mapping[str, Any]]
    github: Mapping[str, Any]
    by_id: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class SelectedPaper:
    paper_id: str
    group: str
    section: str
    reason: str
    fulltext: str
    limitations_source: tuple[str, ...]
    candidate: Mapping[str, Any]

    @property
    def title(self) -> str:
        return str(self.candidate["title"]).strip()


@dataclass
class MustReadEntry:
    number: int
    title: str
    labels: str = ""
    summary: str = ""
    limitations: str = ""
    methods: str = ""
    link: str = ""


@dataclass
class QuickScanEntry:
    title: str
    line: str


@dataclass
class ParsedDigest:
    date: str
    must_read: list[MustReadEntry] = field(default_factory=list)
    quick_scan: list[QuickScanEntry] = field(default_factory=list)
    github_subsections: dict[str, list[str]] = field(default_factory=dict)
    github_present: bool = False
    g6_lines: list[str] = field(default_factory=list)
    g6_present: bool = False
    footer: str = ""


def check_files(
    candidates_path: Path, selection_path: Path, digest_path: Path
) -> CheckResult:
    """Validate the three files, raising ``CheckError`` on the first violation."""

    candidates = _load_json(candidates_path, "candidates")
    selection = _load_json(selection_path, "selection")
    digest_text = _read_text(digest_path, "digest")

    pool = _read_pool(candidates)
    selected = _validate_selection(pool, selection)
    parsed = _parse_digest(digest_text)
    _validate_digest(pool, selected, parsed)

    must_read = sum(1 for paper in selected if paper.section == "must_read")
    return CheckResult(
        papers=len(selected),
        must_read=must_read,
        quick_scan=len(selected) - must_read,
        github_items=_github_item_count(pool),
    )


def _load_json(path: Path, area: str) -> Mapping[str, Any]:
    text = _read_text(path, area)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CheckError(area, f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CheckError(area, f"{path} must contain a JSON object")
    return payload


def _read_text(path: Path, area: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(area, f"cannot read {path}: {exc}") from exc


def _read_pool(payload: Mapping[str, Any]) -> CandidatePool:
    if _int(payload.get("schema_version"), "candidates", "schema_version") != 1:
        raise CheckError("candidates", "schema_version must be 1")

    date = _text(payload.get("date"), "candidates", "date")
    timezone_name = _text(payload.get("timezone"), "candidates", "timezone")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CheckError(
            "candidates", f"timezone is not a known IANA zone: {timezone_name!r}"
        ) from exc

    raw_papers = payload.get("papers")
    if not isinstance(raw_papers, list):
        raise CheckError("candidates", "papers must be a list")
    papers: list[Mapping[str, Any]] = []
    for index, item in enumerate(raw_papers):
        field_name = f"papers[{index}]"
        paper = _object(item, "candidates", field_name)
        _text(paper.get("id"), "candidates", f"{field_name}.id")
        _text(paper.get("title"), "candidates", f"{field_name}.title")
        _text(paper.get("group"), "candidates", f"{field_name}.group")
        papers.append(paper)

    candidate_count = _int(
        payload.get("candidate_count"), "candidates", "candidate_count"
    )
    if candidate_count != len(papers):
        raise CheckError(
            "candidates",
            "candidate_count does not match the number of papers "
            f"({candidate_count} != {len(papers)})",
        )

    sources = _read_sources(payload.get("sources"))
    github = _read_github(payload.get("github"))
    by_id = {str(paper["id"]): paper for paper in papers}
    return CandidatePool(
        date=date,
        timezone=timezone_name,
        zone=zone,
        candidate_count=candidate_count,
        papers=tuple(papers),
        sources=sources,
        github=github,
        by_id=by_id,
    )


def _read_sources(value: Any) -> Mapping[str, Mapping[str, Any]]:
    if value is None:
        return {}
    sources = _object(value, "candidates", "sources")
    result: dict[str, Mapping[str, Any]] = {}
    for name, raw in sources.items():
        field_name = f"sources.{name}"
        if not isinstance(name, str) or not name:
            raise CheckError("candidates", "sources keys must be non-empty strings")
        entry = _object(raw, "candidates", field_name)
        status = _text(entry.get("status"), "candidates", f"{field_name}.status")
        if status not in {"ok", "failed"}:
            raise CheckError(
                "candidates", f"{field_name}.status must be 'ok' or 'failed'"
            )
        result[name] = entry
    return result


def _read_github(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    github = _object(value, "candidates", "github")

    limits = github.get("limits")
    if limits is None:
        g6_limit = DEFAULT_G6_MAX_ITEMS
    else:
        limit_map = _object(limits, "candidates", "github.limits")
        g6_limit = _int(
            limit_map.get("g6", DEFAULT_G6_MAX_ITEMS),
            "candidates",
            "github.limits.g6",
        )
        if g6_limit < 0:
            raise CheckError("candidates", "github.limits.g6 must not be negative")

    for section in ("new", "active", "g6"):
        items = _github_list(github, section)
        for index, repo in enumerate(items):
            _read_repo(repo, f"github.{section}[{index}]")
    g6 = _github_list(github, "g6")
    if len(g6) > g6_limit:
        raise CheckError(
            "candidates",
            f"github.g6 has {len(g6)} items, github.limits.g6 is {g6_limit}",
        )

    releases = github.get("releases")
    if releases is not None:
        release_map = _object(releases, "candidates", "github.releases")
        starred = release_map.get("starred", [])
        if not isinstance(starred, list):
            raise CheckError("candidates", "github.releases.starred must be a list")
        for index, release in enumerate(starred):
            _read_release(release, f"github.releases.starred[{index}]")

    g6_releases = github.get("g6_releases", [])
    if not isinstance(g6_releases, list):
        raise CheckError("candidates", "github.g6_releases must be a list")
    seen_repos: set[str] = set()
    for index, release in enumerate(g6_releases):
        _read_release(release, f"github.g6_releases[{index}]")
        repo_name = str(release["repo"])
        if repo_name in seen_repos:
            raise CheckError(
                "candidates",
                f"github.g6_releases has more than one release for {repo_name}",
            )
        seen_repos.add(repo_name)
    return github


def _github_list(github: Mapping[str, Any], section: str) -> list[Mapping[str, Any]]:
    items = github.get(section, [])
    if not isinstance(items, list):
        raise CheckError("candidates", f"github.{section} must be a list")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise CheckError(
                "candidates", f"github.{section}[{index}] must be an object"
            )
        result.append(item)
    return result


def _read_repo(value: Any, field_name: str) -> None:
    repo = _object(value, "candidates", field_name)
    for key in (
        "full_name",
        "url",
        "created_at",
        "pushed_at",
        "positioning",
        "why",
    ):
        _text(repo.get(key), "candidates", f"{field_name}.{key}")
    # GitHub reports no language as null; collect serializes that as "".
    language = repo.get("language")
    if not isinstance(language, str):
        raise CheckError(
            "candidates", f"{field_name}.language must be a string"
        )
    stars = _int(repo.get("stars"), "candidates", f"{field_name}.stars")
    if stars < 0:
        raise CheckError("candidates", f"{field_name}.stars must not be negative")


def _read_release(value: Any, field_name: str) -> None:
    release = _object(value, "candidates", field_name)
    for key in ("repo", "tag", "date", "highlights", "url"):
        _text(release.get(key), "candidates", f"{field_name}.{key}")


def _validate_selection(
    pool: CandidatePool, payload: Mapping[str, Any]
) -> list[SelectedPaper]:
    schema_version = _int(payload.get("schema_version"), "selection", "schema_version")
    if schema_version != 1:
        raise CheckError("selection", "schema_version must be 1")
    date = _text(payload.get("date"), "selection", "date")
    timezone_name = _text(payload.get("timezone"), "selection", "timezone")
    if date != pool.date:
        raise CheckError(
            "selection", f"date {date} does not match candidates.date {pool.date}"
        )
    if timezone_name != pool.timezone:
        raise CheckError(
            "selection",
            f"timezone {timezone_name} does not match candidates.timezone "
            f"{pool.timezone}",
        )

    raw_papers = payload.get("papers")
    if not isinstance(raw_papers, list):
        raise CheckError("selection", "papers must be a list")

    selected: list[SelectedPaper] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_papers):
        field_name = f"papers[{index}]"
        entry = _object(item, "selection", field_name)
        paper_id = _text(entry.get("id"), "selection", f"{field_name}.id")
        candidate = pool.by_id.get(paper_id)
        if candidate is None:
            raise CheckError(
                "selection",
                f"{field_name}.id {paper_id!r} is not in candidates.papers",
            )
        if paper_id in seen_ids:
            raise CheckError(
                "selection", f"{field_name}.id {paper_id!r} is selected twice"
            )
        seen_ids.add(paper_id)

        group = _text(entry.get("group"), "selection", f"{field_name}.group")
        if group != str(candidate["group"]):
            raise CheckError(
                "selection",
                f"{field_name}.group {group!r} does not match candidate group "
                f"{candidate['group']!r}",
            )
        section = _text(entry.get("section"), "selection", f"{field_name}.section")
        if section not in {"must_read", "quick_scan"}:
            raise CheckError(
                "selection",
                f"{field_name}.section must be 'must_read' or 'quick_scan'",
            )
        reason = _text(entry.get("reason"), "selection", f"{field_name}.reason")
        fulltext = _text(entry.get("fulltext"), "selection", f"{field_name}.fulltext")
        if fulltext not in {"oa", "abstract_only"}:
            raise CheckError(
                "selection",
                f"{field_name}.fulltext must be 'oa' or 'abstract_only'",
            )
        if section == "quick_scan" and fulltext != "abstract_only":
            raise CheckError(
                "selection",
                f"{field_name}.fulltext must be 'abstract_only' for quick_scan",
            )

        raw_sources = entry.get("limitations_source")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise CheckError(
                "selection",
                f"{field_name}.limitations_source must be a non-empty list",
            )
        sources: list[str] = []
        for source_index, raw_source in enumerate(raw_sources):
            if not isinstance(raw_source, str) or raw_source not in {
                "author",
                "model",
            }:
                raise CheckError(
                    "selection",
                    f"{field_name}.limitations_source[{source_index}] must be "
                    "'author' or 'model'",
                )
            if raw_source in sources:
                raise CheckError(
                    "selection",
                    f"{field_name}.limitations_source repeats {raw_source!r}",
                )
            sources.append(raw_source)
        if section == "must_read" and "model" not in sources:
            raise CheckError(
                "selection",
                f"{field_name}.limitations_source must include 'model' for "
                "must_read",
            )

        selected.append(
            SelectedPaper(
                paper_id=paper_id,
                group=group,
                section=section,
                reason=reason,
                fulltext=fulltext,
                limitations_source=tuple(sources),
                candidate=candidate,
            )
        )

    must_read = [paper for paper in selected if paper.section == "must_read"]
    quick_scan = [paper for paper in selected if paper.section == "quick_scan"]
    total = len(pool.papers)
    must_target = min(MUST_READ_LIMIT, total)
    quick_target = min(QUICK_SCAN_LIMIT, total - len(must_read))

    if len(must_read) > must_target:
        raise CheckError(
            "selection",
            f"must_read has {len(must_read)} papers, expected {must_target}",
        )
    if len(must_read) < must_target and _can_add_must_read(pool, selected):
        raise CheckError(
            "selection",
            f"must_read has {len(must_read)} papers, expected {must_target}",
        )
    if len(quick_scan) > quick_target:
        raise CheckError(
            "selection",
            f"quick_scan has {len(quick_scan)} papers, expected {quick_target}",
        )
    if len(quick_scan) < quick_target and _can_add_quick_scan(
        pool, selected
    ):
        raise CheckError(
            "selection",
            f"quick_scan has {len(quick_scan)} papers, expected {quick_target}",
        )

    g2 = sum(1 for paper in selected if paper.group == "G2")
    if g2 > G2_MAX_ITEMS:
        raise CheckError(
            "selection", f"G2 has {g2} papers, the maximum is {G2_MAX_ITEMS}"
        )

    g6 = [paper for paper in selected if paper.group == "G6"]
    if len(g6) > G6_MAX_PAPERS:
        raise CheckError(
            "selection",
            f"G6 has {len(g6)} papers, the maximum is {G6_MAX_PAPERS}",
        )
    for paper in g6:
        if paper.section != "quick_scan":
            raise CheckError(
                "selection",
                f"G6 paper {paper.paper_id!r} must be in quick_scan",
            )

    selected_groups = {paper.group for paper in selected}
    for group in _candidate_groups(pool):
        if group in {"G2", "G6"}:
            continue
        if group not in selected_groups:
            raise CheckError(
                "selection", f"group {group} has no paper in the selection"
            )
    return selected


def _can_add_must_read(
    pool: CandidatePool, selected: Sequence[SelectedPaper]
) -> bool:
    """Whether another non-G6 candidate could legally become a must-read.

    G6 papers may only appear in quick_scan, so a short pool with fewer than
    three non-G6 candidates legitimately produces a shorter must-read section.
    """

    must_ids = {
        paper.paper_id for paper in selected if paper.section == "must_read"
    }
    selected_ids = {paper.paper_id for paper in selected}
    g2 = sum(1 for paper in selected if paper.group == "G2")
    for paper in pool.papers:
        paper_id = str(paper["id"])
        if paper_id in must_ids:
            continue
        group = str(paper["group"])
        if group == "G6":
            continue
        # Moving an already-selected G2 paper to must_read keeps the total G2
        # count unchanged; adding a new one would break the four-paper cap.
        if group == "G2" and g2 >= G2_MAX_ITEMS and paper_id not in selected_ids:
            continue
        return True
    return False


def _can_add_quick_scan(
    pool: CandidatePool, selected: Sequence[SelectedPaper]
) -> bool:
    """Whether another candidate could legally join quick_scan.

    A shortfall is allowed only when a quota blocks every remaining candidate:
    G2 is already at four or G6 already has its one paper. Otherwise the writer
    simply left a usable candidate out.
    """

    selected_ids = {paper.paper_id for paper in selected}
    g2 = sum(1 for paper in selected if paper.group == "G2")
    g6 = sum(1 for paper in selected if paper.group == "G6")
    for paper in pool.papers:
        if str(paper["id"]) in selected_ids:
            continue
        group = str(paper["group"])
        if group == "G2" and g2 >= G2_MAX_ITEMS:
            continue
        if group == "G6" and g6 >= G6_MAX_PAPERS:
            continue
        return True
    return False


def _candidate_groups(pool: CandidatePool) -> set[str]:
    return {str(paper["group"]) for paper in pool.papers}


def _parse_digest(text: str) -> ParsedDigest:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        raise CheckError("digest", "is empty")
    title = _TITLE.match(lines[first].strip())
    if title is None:
        raise CheckError(
            "digest", "first line must be '# 学术速递 · <date>'"
        )
    parsed_date = title.group(1).strip()

    separator = next(
        (
            index
            for index in range(len(lines) - 1, first, -1)
            if lines[index].strip() == "---"
        ),
        None,
    )
    if separator is None:
        raise CheckError("digest", "missing the footer separator '---'")

    bodies = _section_bodies(lines[first + 1 : separator])

    result = ParsedDigest(date=parsed_date)
    result.must_read = _parse_must_read(bodies.get("今日必读", []))
    result.quick_scan = _parse_quick_scan(bodies.get("其它速览", []))
    result.github_present = "GitHub" in bodies
    result.github_subsections = _parse_github(bodies.get("GitHub", []))
    result.g6_present = "AI 工具 / Agent Harness" in bodies
    result.g6_lines = _parse_items(
        bodies.get("AI 工具 / Agent Harness", []), "AI 工具 / Agent Harness"
    )
    result.footer = "\n".join(lines[separator + 1 :])
    return result


def _section_bodies(lines: Sequence[str]) -> dict[str, list[str]]:
    """Collect each level-2 section's lines, rejecting unknown headings."""

    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for raw in lines:
        heading = _SECTION.match(raw.strip())
        if heading is not None:
            name = heading.group(1).strip()
            if name not in SECTIONS:
                raise CheckError("digest", f"unknown section: {name}")
            if name in bodies:
                raise CheckError("digest", f"duplicate section: {name}")
            current = name
            bodies[name] = []
            continue
        if current is not None:
            bodies[current].append(raw)
    return bodies


def _parse_must_read(lines: Sequence[str]) -> list[MustReadEntry]:
    entries: list[MustReadEntry] = []
    current: MustReadEntry | None = None
    current_field: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        heading = _MUST_HEADING.match(line)
        if heading is not None:
            current = MustReadEntry(
                number=int(heading.group(1)), title=heading.group(2).strip()
            )
            entries.append(current)
            current_field = None
            continue
        if line.startswith("###"):
            raise CheckError(
                "digest",
                "must-read heading must look like '### 1. <title>'",
            )
        if current is None:
            raise CheckError("digest", "must-read content before the first entry")

        field_match = _FIELD.match(line)
        if field_match is not None:
            name = field_match.group(1)
            attr = _FIELD_ATTRS[name]
            if getattr(current, attr):
                raise CheckError(
                    "digest", f"must-read {current.number} repeats '- {name}：'"
                )
            setattr(current, attr, field_match.group(2).strip())
            current_field = attr
            continue
        if line.startswith("- "):
            if _MD_LINK.search(line):
                if current.link:
                    raise CheckError(
                        "digest", f"must-read {current.number} has two link lines"
                    )
                current.link = line
                current_field = None
                continue
            if current_field is not None:
                setattr(
                    current,
                    current_field,
                    _join(getattr(current, current_field), line),
                )
                continue
            raise CheckError(
                "digest",
                f"must-read {current.number} has an unexpected line: {line}",
            )
        if current_field is None:
            raise CheckError(
                "digest",
                f"must-read {current.number} has an unexpected line: {line}",
            )
        setattr(current, current_field, _join(getattr(current, current_field), line))

    if entries and [entry.number for entry in entries] != list(
        range(1, len(entries) + 1)
    ):
        raise CheckError("digest", "must-read entries must be numbered 1..N in order")

    for entry in entries:
        label = f"must-read {entry.number}"
        for name, attr in _FIELD_ATTRS.items():
            value = getattr(entry, attr)
            if not value:
                raise CheckError("digest", f"{label} is missing '- {name}：'")
        if not _TAG.search(entry.labels):
            raise CheckError("digest", f"{label} '- 标签：' has no backticked tag")
        if not _MD_LINK.search(entry.link):
            raise CheckError("digest", f"{label} is missing its 原文 link")
        if not _has_link_label(entry.link, "原文"):
            raise CheckError("digest", f"{label} is missing '[原文](…)'")
    return entries


def _has_link_label(line: str, label: str) -> bool:
    return re.search(rf"\[{re.escape(label)}\]\(", line) is not None


def _parse_quick_scan(lines: Sequence[str]) -> list[QuickScanEntry]:
    entries: list[QuickScanEntry] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("- "):
            raise CheckError(
                "digest",
                "each quick-scan entry must be one line starting with '- **title**'",
            )
        bold = _BOLD.search(line)
        if bold is None:
            raise CheckError(
                "digest",
                "each quick-scan entry must start with '- **<title>**'",
            )
        title = bold.group(1).strip()
        if not _field_text(line, "摘要"):
            raise CheckError("digest", f"quick-scan '{title}' is missing 摘要：")
        if not _field_text(line, "局限性"):
            raise CheckError(
                "digest", f"quick-scan '{title}' is missing 局限性："
            )
        if _MD_LINK.search(line) is None:
            raise CheckError("digest", f"quick-scan '{title}' is missing its link")
        if _TAG.search(line) is None:
            raise CheckError("digest", f"quick-scan '{title}' has no backticked tag")
        entries.append(QuickScanEntry(title=title, line=line))
    return entries


def _field_text(line: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}：\s*(.+?)(?:\s*·|\s*\[|$)", line)
    return match.group(1).strip() if match else ""


def _parse_github(lines: Sequence[str]) -> dict[str, list[str]]:
    subsections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        heading = _SUBSECTION.match(line)
        if heading is not None:
            name = heading.group(1).strip()
            if name not in GITHUB_SUBSECTIONS:
                raise CheckError("digest", f"unknown GitHub subsection: {name}")
            if name in subsections:
                raise CheckError("digest", f"duplicate GitHub subsection: {name}")
            current = name
            subsections[name] = []
            continue
        if current is None:
            raise CheckError("digest", "GitHub item outside a subsection")
        if not line.startswith("- "):
            raise CheckError("digest", f"GitHub item must be a bullet: {line}")
        subsections[current].append(line)
    return subsections


def _parse_items(lines: Sequence[str], label: str) -> list[str]:
    items: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("- "):
            raise CheckError("digest", f"{label} item must be a bullet: {line}")
        items.append(line)
    return items


def _validate_digest(
    pool: CandidatePool, selected: Sequence[SelectedPaper], parsed: ParsedDigest
) -> None:
    if parsed.date != pool.date:
        raise CheckError(
            "digest",
            f"title date {parsed.date} does not match candidates.date {pool.date}",
        )

    must_read = [paper for paper in selected if paper.section == "must_read"]
    quick_scan = [paper for paper in selected if paper.section == "quick_scan"]
    _compare_titles(
        "今日必读",
        [entry.title for entry in parsed.must_read],
        [paper.title for paper in must_read],
    )
    _compare_titles(
        "其它速览",
        [entry.title for entry in parsed.quick_scan],
        [paper.title for paper in quick_scan],
    )
    _check_fulltext_markers(must_read, parsed.must_read)
    _validate_footer(pool, selected, parsed.footer)
    _validate_github(pool, parsed)


def _compare_titles(
    section: str, parsed_titles: Sequence[str], selected_titles: Sequence[str]
) -> None:
    duplicates = _duplicates(parsed_titles)
    if duplicates:
        raise CheckError(
            "digest", f"{section} repeats the paper title {duplicates[0]!r}"
        )
    parsed_set = set(parsed_titles)
    selected_set = set(selected_titles)
    missing = selected_set - parsed_set
    if missing:
        raise CheckError(
            "digest", f"{section} is missing the paper {sorted(missing)[0]!r}"
        )
    unexpected = parsed_set - selected_set
    if unexpected:
        raise CheckError(
            "digest",
            f"{section} contains a paper that is not in selection: "
            f"{sorted(unexpected)[0]!r}",
        )


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


def _check_fulltext_markers(
    must_read: Sequence[SelectedPaper], entries: Sequence[MustReadEntry]
) -> None:
    by_title = {entry.title: entry for entry in entries}
    for paper in must_read:
        entry = by_title.get(paper.title)
        if entry is None:
            continue
        has_marker = NO_OA_MARKER in entry.methods
        if paper.fulltext == "abstract_only" and not has_marker:
            raise CheckError(
                "digest",
                f"must-read {paper.title!r} is abstract_only but 方法精读 does not "
                f"say {NO_OA_MARKER!r}",
            )
        if paper.fulltext == "oa" and has_marker:
            raise CheckError(
                "digest",
                f"must-read {paper.title!r} is oa but 方法精读 says there is no OA "
                "full text",
            )


def _validate_footer(
    pool: CandidatePool, selected: Sequence[SelectedPaper], footer: str
) -> None:
    if _SECRET.search(footer) or _SECRET_KEY.search(footer):
        raise CheckError("digest", "contains a secret-like token")
    if _SOURCE_LINE.search(footer) is None:
        raise CheckError("digest", "footer is missing '来源：'")
    candidate_match = _CANDIDATE_COUNT.search(footer)
    if candidate_match is None:
        raise CheckError("digest", "footer is missing '候选：N'")
    if int(candidate_match.group(1)) != pool.candidate_count:
        raise CheckError(
            "digest",
            f"footer 候选：{candidate_match.group(1)} does not match "
            f"candidate_count {pool.candidate_count}",
        )
    selected_match = _SELECTED_COUNT.search(footer)
    if selected_match is None:
        raise CheckError("digest", "footer is missing '入选：M'")
    if int(selected_match.group(1)) != len(selected):
        raise CheckError(
            "digest",
            f"footer 入选：{selected_match.group(1)} does not match the "
            f"selection's {len(selected)} papers",
        )
    generated_match = _GENERATED_AT.search(footer)
    if generated_match is None:
        raise CheckError("digest", "footer is missing '生成：'")
    raw_generated = generated_match.group(1).strip()
    try:
        datetime.fromisoformat(raw_generated.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CheckError(
            "digest", f"footer 生成： is not an ISO-8601 timestamp: {raw_generated!r}"
        ) from exc

    source_start = footer.find("来源：")
    counts_start = footer.find("候选：", source_start + 1)
    source_text = (
        footer[source_start:counts_start]
        if counts_start != -1
        else footer[source_start:]
    )
    for name, source in pool.sources.items():
        status = str(source["status"])
        pattern = rf"{re.escape(name)}\s+{re.escape(status)}\b"
        if re.search(pattern, source_text) is None:
            raise CheckError(
                "digest",
                f"footer 来源： does not report {name} {status}",
            )


def _validate_github(pool: CandidatePool, parsed: ParsedDigest) -> None:
    new = _github_list(pool.github, "new")
    active = _github_list(pool.github, "active")
    g6 = _github_list(pool.github, "g6")
    starred = _starred_releases(pool.github)
    g6_releases = _g6_releases(pool.github)

    has_github_block = bool(new or active or starred)
    if has_github_block and not parsed.github_present:
        raise CheckError("digest", "missing the '## GitHub' section")
    if not has_github_block and parsed.github_present:
        raise CheckError(
            "digest",
            "'## GitHub' must be omitted when candidates has no new, active, or "
            "starred-release items",
        )

    has_g6_block = bool(g6 or g6_releases)
    if has_g6_block and not parsed.g6_present:
        raise CheckError("digest", "missing the '## AI 工具 / Agent Harness' section")
    if not has_g6_block and parsed.g6_present:
        raise CheckError(
            "digest",
            "'## AI 工具 / Agent Harness' must be omitted when candidates has no "
            "G6 items",
        )

    expected: list[tuple[str, list[Mapping[str, Any]], list[str], str]] = [
        ("新项目", new, parsed.github_subsections.get("新项目", []), "repo"),
        ("活跃项目", active, parsed.github_subsections.get("活跃项目", []), "repo"),
        (
            "关注项目的新 release",
            starred,
            parsed.github_subsections.get("关注项目的新 release", []),
            "release",
        ),
    ]
    for name, items, lines, kind in expected:
        if not items:
            if name in parsed.github_subsections:
                raise CheckError(
                    "digest",
                    f"GitHub subsection {name!r} must be omitted when its "
                    "candidate list is empty",
                )
            continue
        if name not in parsed.github_subsections:
            raise CheckError("digest", f"missing GitHub subsection: {name}")
        _match_all(name, items, lines, kind, pool.zone)

    # G6 repos and official releases share one section; match repos by their
    # bare bold name so a release line never counts as the repository item.
    remaining = list(parsed.g6_lines)
    _match_expected("AI 工具 / Agent Harness", g6, remaining, "repo", pool.zone)
    _match_expected(
        "AI 工具 / Agent Harness", g6_releases, remaining, "release", pool.zone
    )
    if remaining:
        raise CheckError(
            "digest",
            "AI 工具 / Agent Harness has an unexpected item: "
            f"{remaining[0]}",
        )


def _starred_releases(github: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    releases = github.get("releases")
    if releases is None:
        return []
    release_map = _object(releases, "candidates", "github.releases")
    starred = release_map.get("starred", [])
    if not isinstance(starred, list):
        raise CheckError("candidates", "github.releases.starred must be a list")
    return [item for item in starred if isinstance(item, dict)]


def _g6_releases(github: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = github.get("g6_releases", [])
    if not isinstance(items, list):
        raise CheckError("candidates", "github.g6_releases must be a list")
    return [item for item in items if isinstance(item, dict)]


def _match_all(
    label: str,
    items: Sequence[Mapping[str, Any]],
    lines: list[str],
    kind: str,
    zone: ZoneInfo,
) -> None:
    remaining = list(lines)
    _match_expected(label, items, remaining, kind, zone)
    if remaining:
        raise CheckError("digest", f"{label} has an unexpected item: {remaining[0]}")


def _match_expected(
    label: str,
    items: Sequence[Mapping[str, Any]],
    remaining: list[str],
    kind: str,
    zone: ZoneInfo,
) -> None:
    for item in items:
        name = _item_name(item, kind)
        match = next(
            (line for line in remaining if _line_matches(item, line, kind)), None
        )
        if match is None:
            raise CheckError("digest", f"{label} is missing {name}")
        remaining.remove(match)
        if kind == "repo":
            _check_repo_line(item, match, zone)
        else:
            _check_release_line(item, match)


def _item_name(item: Mapping[str, Any], kind: str) -> str:
    if kind == "repo":
        return str(item["full_name"])
    return f"{item['repo']} {item['tag']}"


def _line_matches(item: Mapping[str, Any], line: str, kind: str) -> bool:
    bold = _BOLD.search(line)
    if bold is None:
        return False
    text = bold.group(1).strip()
    if kind == "repo":
        return text == str(item["full_name"])
    repo = str(item["repo"])
    tag = str(item["tag"])
    return text.startswith(f"{repo} ") and tag in text[len(repo) :]


def _check_repo_line(
    repo: Mapping[str, Any], line: str, zone: ZoneInfo
) -> None:
    full_name = str(repo["full_name"])
    stars = int(repo["stars"])
    if re.search(rf"⭐\s*{stars}\b", line) is None:
        raise CheckError(
            "digest", f"GitHub item {full_name} is missing ⭐ {stars}"
        )
    language = str(repo["language"]).strip()
    if language and language not in line:
        raise CheckError(
            "digest", f"GitHub item {full_name} is missing its language"
        )
    dates = _repo_dates(repo, zone)
    if dates and not any(day in line for day in dates):
        raise CheckError(
            "digest", f"GitHub item {full_name} is missing its 最近更新 date"
        )
    if _has_url(line, str(repo["url"])) is False:
        raise CheckError("digest", f"GitHub item {full_name} is missing its link")
    parts = [part.strip() for part in line.split("·")]
    minimum = 6 if language else 5
    if len(parts) < minimum or any(not part for part in parts):
        raise CheckError(
            "digest",
            f"GitHub item {full_name} must include 定位 and why",
        )


def _check_release_line(release: Mapping[str, Any], line: str) -> None:
    name = _item_name(release, "release")
    date = str(release["date"])
    if date not in line:
        raise CheckError("digest", f"release {name} is missing its date")
    if _has_url(line, str(release["url"])) is False:
        raise CheckError("digest", f"release {name} is missing its link")
    parts = [part.strip() for part in line.removeprefix("- ").split("·")]
    if len(parts) < 3 or any(not part for part in parts):
        raise CheckError(
            "digest", f"release {name} must include 更新要点 and a link"
        )
    if not _release_highlights(parts, date):
        raise CheckError("digest", f"release {name} is missing its 更新要点")


def _release_highlights(parts: Sequence[str], date: str) -> bool:
    """Whether one bullet part is the update notes.

    The repository/tag part and the link part are never notes; the part that
    carries the release date is not either. A G6 line may put the date in the
    repository part while the starred format gives it its own part.
    """

    for part in parts:
        if not part or date in part:
            continue
        if part.startswith("**") and part.endswith("**"):
            continue
        if _MD_LINK.fullmatch(part):
            continue
        return True
    return False


def _repo_dates(repo: Mapping[str, Any], zone: ZoneInfo) -> set[str]:
    """The local date a digest may cite for 最近更新.

    That is the last push. The creation date is only a fallback for a payload
    whose ``pushed_at`` is missing or unparseable, so an active repository
    cannot pass by citing an old creation date.
    """

    dates: set[str] = set()
    for key in ("pushed_at", "created_at"):
        raw = str(repo.get(key) or "").strip()
        if not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        dates.add(moment.astimezone(zone).date().isoformat())
        break
    return dates


def _has_url(line: str, url: str) -> bool:
    if not url:
        return False
    return re.search(r"\]\(\s*" + re.escape(url) + r"\s*\)", line) is not None


def _github_item_count(pool: CandidatePool) -> int:
    return (
        len(_github_list(pool.github, "new"))
        + len(_github_list(pool.github, "active"))
        + len(_github_list(pool.github, "g6"))
        + len(_starred_releases(pool.github))
        + len(_g6_releases(pool.github))
    )


def _join(current: str, line: str) -> str:
    return f"{current} {line}".strip() if current else line.strip()


def _object(value: Any, area: str, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CheckError(area, f"{field_name} must be an object")
    return value


def _text(value: Any, area: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckError(area, f"{field_name} must be a non-empty string")
    return value.strip()


def _int(value: Any, area: str, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CheckError(area, f"{field_name} must be an integer")
    return value
