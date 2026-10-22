"""GitHub repository discovery: new repos, active repos, and the G6 block.

Discovery runs the configured server-side queries twice: once for repositories
created inside the new window with at least ``github.new.min_stars`` stars, and
once for repositories pushed inside the active window with at least
``github.active.min_stars`` stars. Both passes ask for ``sort=updated`` and
read only the first page, because ``sort=updated`` reorders entries while
paging. Requests are serial, roughly one every two seconds (the authenticated
search limit is 30 per minute), and each carries a User-Agent plus the token
from ``github.token_env``.

Results are scored locally. Terms of the query's keyword group weigh three when
they hit the full name, description, or topics, and one when they hit the
README; ``round(2 * log10(stars))`` plus a push-recency bonus (today +2,
yesterday +1) decides the ordering. A README comes from
``raw.githubusercontent.com`` so it costs no API quota, and only the top
``github.readme_limit`` candidates are read so a run stays inside the quota
budget. The three sections are then capped (new 1, active 2, G6 2 by default)
and never padded.

The module exports ``NAME``, ``discover`` and ``check``. It deliberately does
not have the paper-source ``collect`` shape: repositories are not papers and
never enter the paper candidate pool.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .config import Config, DiscoveryWindow, GithubConfig, Topic
from .errors import SourceError
from .matching import matches
from .models import Repo
from .sources.base import SourceResult, get_text, read_fixture

NAME = "github"
SEARCH_URL = "https://api.github.com/search/repositories"
RATE_LIMIT_URL = "https://api.github.com/rate_limit"
RAW_README_URL = "https://raw.githubusercontent.com/{full_name}/{branch}/README.md"
USER_AGENT = "academic-digest/0.1 (GitHub discovery)"
# Authenticated search allows 30 requests per minute; serialise with a margin.
REQUEST_INTERVAL = 2.0
PER_PAGE = 100
SORT = "updated"
FIXTURE_SEARCH = "github/search/{pass_name}/{index}.json"
FIXTURE_README = "github/readme/{slug}.md"
SECTIONS = ("new", "active", "g6")
PASS_FIELDS = {"new": "created", "active": "pushed"}
RECENCY_TODAY = 2
RECENCY_YESTERDAY = 1
POPULARITY_WEIGHT = 2
README_MAX_CHARS = 200
# Each section offers a few more candidates than it can show, so a README hit
# can move a repository into a slot.
README_SLACK = 3

_last_request_at = 0.0


@dataclass
class SearchPass:
    """One discovery pass: its window, the queries it ran, and its raw count."""

    name: str
    window: DiscoveryWindow
    since: date
    queries: list[str] = field(default_factory=list)
    results: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "since": self.since.isoformat(),
            "min_stars": self.window.min_stars,
            "params": {"sort": SORT, "order": "desc", "per_page": PER_PAGE},
            "queries": self.queries,
            "results": self.results,
        }


@dataclass
class Discovery:
    """Everything the digest needs from GitHub discovery for one run."""

    result: SourceResult
    passes: list[SearchPass]
    limits: dict[str, int]
    found: dict[str, int]
    new: list[Repo]
    active: list[Repo]
    g6: list[Repo]

    @classmethod
    def failed(
        cls, config: Config, message: str, passes: list[SearchPass]
    ) -> "Discovery":
        return cls(
            result=SourceResult.failed(NAME, message),
            passes=passes,
            limits=limits_for(config.github),
            found={section: 0 for section in SECTIONS},
            new=[],
            active=[],
            g6=[],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passes": {
                search_pass.name: search_pass.to_dict()
                for search_pass in self.passes
            },
            "limits": self.limits,
            "found": self.found,
            "new": [repo.to_dict() for repo in self.new],
            "active": [repo.to_dict() for repo in self.active],
            "g6": [repo.to_dict() for repo in self.g6],
        }


@dataclass
class _Candidate:
    """A repository that passed the pass filters, before its README is read."""

    full_name: str
    url: str
    description: str
    stars: int
    language: str
    created_at: str
    pushed_at: str
    topics: list[str]
    default_branch: str
    group: str
    label: str
    terms: tuple[str, ...]
    base_query: str
    query: str
    metadata_terms: list[str]
    metadata_score: int


def discover(
    config: Config, fixtures_root: Path | None, now: datetime
) -> Discovery:
    """Run every discovery query and return the capped selections."""

    passes: list[SearchPass] = []
    try:
        passes = _build_passes(config, now)
        return _discover(config, fixtures_root, now, passes)
    except (SourceError, OSError) as exc:
        # The passes carry the queries that ran, so a failed run is still
        # auditable (``github.passes`` is never empty).
        return Discovery.failed(config, str(exc), passes)


def _build_passes(config: Config, now: datetime) -> list[SearchPass]:
    """Construct both passes and their full queries before any request."""

    github = config.github
    today = config.local_date(now)
    pairs = github.query_pairs(config.topics)
    passes: list[SearchPass] = []
    for name, window in (("new", github.new), ("active", github.active)):
        field = PASS_FIELDS[name]
        since = today - timedelta(days=window.days)
        passes.append(
            SearchPass(
                name=name,
                window=window,
                since=since,
                queries=[
                    build_query(
                        base_query,
                        field=field,
                        since=since,
                        min_stars=window.min_stars,
                    )
                    for _, base_query in pairs
                ],
            )
        )
    return passes


def check(config: Config, fixtures_root: Path | None) -> str:
    """Doctor check: replay recorded searches offline, or ping the live API."""

    if fixtures_root is not None:
        return validate_fixture(config, fixtures_root)
    return check_network(config)


def validate_fixture(config: Config, root: Path) -> str:
    pairs = config.github.query_pairs(config.topics)
    total = 0
    for pass_name in PASS_FIELDS:
        for index in range(len(pairs)):
            payload = _parse_search(
                read_fixture(
                    root,
                    FIXTURE_SEARCH.format(pass_name=pass_name, index=index),
                )
            )
            total += len(_items(payload))
    return (
        f"github search: {len(pairs)} queries x {len(PASS_FIELDS)} passes, "
        f"{total} recorded items"
    )


def check_network(config: Config) -> str:
    text = _throttled_get(
        RATE_LIMIT_URL,
        {},
        config,
        error="cannot reach the GitHub API",
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid GitHub rate_limit JSON: {exc}") from exc
    resources = data.get("resources") if isinstance(data, dict) else None
    search = resources.get("search") if isinstance(resources, dict) else None
    remaining = search.get("remaining") if isinstance(search, dict) else None
    if isinstance(remaining, int):
        return f"GitHub API reachable ({remaining} search requests remaining)"
    return "GitHub API reachable"


def build_query(
    base_query: str, *, field: str, since: date, min_stars: int
) -> str:
    """Add the pass date window and star floor to one configured query."""

    return f"{base_query} {field}:>{since.isoformat()} stars:>={min_stars}"


def limits_for(github: GithubConfig) -> dict[str, int]:
    return {
        "new": github.new.max_items,
        "active": github.active.max_items,
        "g6": github.g6_max_items,
    }


def _discover(
    config: Config,
    fixtures_root: Path | None,
    now: datetime,
    passes: list[SearchPass],
) -> Discovery:
    github = config.github
    topics = {topic.name: topic for topic in config.topics}
    limits = limits_for(github)
    today = config.local_date(now)
    pairs = github.query_pairs(config.topics)

    candidates: dict[str, _Candidate] = {}
    membership: dict[str, set[str]] = {section: set() for section in SECTIONS}
    for search_pass in passes:
        for index, (group, base_query) in enumerate(pairs):
            query = search_pass.queries[index]
            payload = _search_payload(
                config, fixtures_root, search_pass.name, index, query
            )
            items = _items(payload)
            search_pass.results += len(items)
            section = "g6" if group == github.g6_topic else search_pass.name
            topic = topics[group]
            for item in items:
                candidate = _candidate(
                    item,
                    search_pass=search_pass,
                    topic=topic,
                    base_query=base_query,
                    query=query,
                    today=today,
                    config=config,
                )
                if candidate is None:
                    continue
                membership[section].add(candidate.full_name)
                existing = candidates.get(candidate.full_name)
                # The first occurrence wins, so a repo found by the new pass is
                # explained by its new-pass query even when it is also active.
                # A G6 hit wins instead, so the G6 block explains its own repo.
                if existing is None or (
                    section == "g6" and existing.group != github.g6_topic
                ):
                    candidates[candidate.full_name] = candidate

    # Every eligible candidate stays selectable; the README budget only decides
    # which ones get README evidence on top of their metadata score.
    enriched = {
        candidate.full_name for candidate in _shortlist(candidates, membership, github)
    }
    repos = {
        name: _repo(
            candidate,
            _readme(config, fixtures_root, candidate) if name in enriched else "",
            today,
            config,
        )
        for name, candidate in candidates.items()
    }

    g6_names = membership["g6"]
    selected_new = _select(
        [
            repos[name]
            for name in membership["new"]
            if name in repos and name not in g6_names
        ],
        limits["new"],
    )
    new_names = {repo.full_name for repo in selected_new}
    selected_active = _select(
        [
            repos[name]
            for name in membership["active"]
            if name in repos and name not in new_names and name not in g6_names
        ],
        limits["active"],
    )
    selected_g6 = _select(
        [repos[name] for name in g6_names if name in repos],
        limits["g6"],
    )

    result = SourceResult(
        name=NAME,
        status="ok",
        count=len(selected_new) + len(selected_active) + len(selected_g6),
    )
    return Discovery(
        result=result,
        passes=passes,
        limits=limits,
        found={section: len(names) for section, names in membership.items()},
        new=selected_new,
        active=selected_active,
        g6=selected_g6,
    )


def _search_payload(
    config: Config,
    fixtures_root: Path | None,
    pass_name: str,
    index: int,
    query: str,
) -> dict[str, Any]:
    if fixtures_root is not None:
        text = read_fixture(
            fixtures_root,
            FIXTURE_SEARCH.format(pass_name=pass_name, index=index),
        )
    else:
        text = _throttled_get(
            SEARCH_URL,
            {
                "q": query,
                "sort": SORT,
                "order": "desc",
                "per_page": str(PER_PAGE),
            },
            config,
            error=f"GitHub {pass_name} search request failed",
        )
    return _parse_search(text)


def _parse_search(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid GitHub search JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceError("invalid GitHub search JSON: expected an object")
    _items(payload)
    return payload


def _items(payload: Mapping[str, Any]) -> list[Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise SourceError("invalid GitHub search JSON: items must be a list")
    return items


def _candidate(
    item: Any,
    *,
    search_pass: SearchPass,
    topic: Topic,
    base_query: str,
    query: str,
    today: date,
    config: Config,
) -> _Candidate | None:
    if not isinstance(item, dict):
        raise SourceError("invalid GitHub search JSON: items must be objects")
    full_name = _text(item.get("full_name"))
    if not full_name or item.get("fork") or item.get("archived"):
        return None

    stars = _int(item.get("stargazers_count"))
    if stars < search_pass.window.min_stars:
        return None
    created_at = _text(item.get("created_at"))
    pushed_at = _text(item.get("pushed_at"))
    created = _local_date(created_at, config)
    pushed = _local_date(pushed_at, config)
    if search_pass.name == "new":
        if created is None or created <= search_pass.since:
            return None
    elif pushed is None or pushed <= search_pass.since:
        return None

    description = _text(item.get("description"))
    repo_topics = _strings(item.get("topics"))
    haystack = "\n".join((full_name, description, " ".join(repo_topics)))
    metadata_terms = _matched_terms(haystack, topic.terms)
    score = (
        3 * len(metadata_terms)
        + _popularity(stars)
        + _recency(pushed_at, today, config)
    )

    return _Candidate(
        full_name=full_name,
        url=_text(item.get("html_url")) or f"https://github.com/{full_name}",
        description=description,
        stars=stars,
        language=_text(item.get("language")),
        created_at=created_at,
        pushed_at=pushed_at,
        topics=repo_topics,
        default_branch=_text(item.get("default_branch")),
        group=topic.name,
        label=topic.label,
        terms=topic.terms,
        base_query=base_query,
        query=query,
        metadata_terms=metadata_terms,
        metadata_score=score,
    )


def _shortlist(
    candidates: Mapping[str, _Candidate],
    membership: Mapping[str, set[str]],
    github: GithubConfig,
) -> list[_Candidate]:
    """Pick which candidates get a README read, one section at a time.

    Each section offers its best ``max_items + README_SLACK`` candidates, and
    the ``readme_limit`` budget is handed out round-robin. A plain global
    shortlist would let high-star active repositories crowd the new and G6
    sections out of their README evidence entirely.
    """

    limits = limits_for(github)
    g6_names = membership["g6"]
    offered = {}
    for section in SECTIONS:
        names = membership[section]
        if section != "g6":
            # A G6 hit is shown only in the G6 block, so it must not consume
            # another section's README slot either.
            names = names - g6_names
        offered[section] = _ordered(
            candidates[name]
            for name in names
            if name in candidates and limits[section] > 0
        )[: limits[section] + README_SLACK]
    selected: list[_Candidate] = []
    seen: set[str] = set()
    rank = 0
    while len(selected) < github.readme_limit:
        progressed = False
        for section in SECTIONS:
            if rank >= len(offered[section]):
                continue
            progressed = True
            candidate = offered[section][rank]
            if candidate.full_name not in seen:
                seen.add(candidate.full_name)
                selected.append(candidate)
            if len(selected) >= github.readme_limit:
                break
        if not progressed:
            break
        rank += 1
    return selected


def _ordered(candidates: Iterable[_Candidate]) -> list[_Candidate]:
    return sorted(
        candidates,
        key=lambda candidate: _rank_key(
            candidate.metadata_score,
            candidate.stars,
            candidate.pushed_at,
            candidate.full_name,
        ),
    )


def _rank_key(
    score: int, stars: int, pushed_at: str, full_name: str
) -> tuple[int, int, int, str]:
    return (-score, -stars, -_timestamp(pushed_at), full_name)


def _repo(candidate: _Candidate, readme: str, today: date, config: Config) -> Repo:
    # A term weighs three when it appears in the name, description, or topics,
    # and one when it appears only in the README.
    readme_terms = [
        term
        for term in _matched_terms(readme, candidate.terms)
        if term not in candidate.metadata_terms
    ]
    tags = list(candidate.metadata_terms)
    tags.extend(readme_terms)
    relevance = 3 * len(candidate.metadata_terms) + len(readme_terms)
    score = (
        relevance
        + _popularity(candidate.stars)
        + _recency(candidate.pushed_at, today, config)
    )

    why = f"由 {candidate.group}（{candidate.label}）检索 {candidate.base_query} 返回"
    if tags:
        why += f"；匹配关键词：{'、'.join(tags)}"

    branch = candidate.default_branch or "main"
    return Repo(
        full_name=candidate.full_name,
        url=candidate.url,
        description=candidate.description,
        positioning=(
            candidate.description
            or _readme_summary(readme)
            or f"{candidate.full_name}（无描述）"
        ),
        why=why,
        stars=candidate.stars,
        language=candidate.language,
        created_at=candidate.created_at,
        pushed_at=candidate.pushed_at,
        topics=candidate.topics,
        group=candidate.group,
        query=candidate.query,
        tags=tags,
        relevance=relevance,
        score=score,
        readme_url=RAW_README_URL.format(
            full_name=candidate.full_name, branch=branch
        ),
    )


def _select(repos: list[Repo], limit: int) -> list[Repo]:
    """Rank repositories and keep at most ``limit``; never pad."""

    ordered = sorted(
        repos,
        key=lambda repo: _rank_key(
            repo.score, repo.stars, repo.pushed_at, repo.full_name
        ),
    )
    return ordered[:limit]


def _readme(
    config: Config, fixtures_root: Path | None, candidate: _Candidate
) -> str:
    """Read a README, treating an absent file as "no README".

    Unlike a recorded search response, a repository may simply not have a
    README, so a missing raw fixture is not a source failure.
    """

    branch = candidate.default_branch or "main"
    url = RAW_README_URL.format(full_name=candidate.full_name, branch=branch)
    if fixtures_root is None:
        try:
            return get_text(
                url,
                {},
                timeout=15,
                user_agent=USER_AGENT,
                error=f"cannot read the README of {candidate.full_name}",
            )
        except SourceError:
            return ""

    relative = FIXTURE_README.format(slug=candidate.full_name.replace("/", "__"))
    path = Path(fixtures_root) / relative
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SourceError(f"cannot read fixture {relative}: {exc}") from exc


def _readme_summary(readme: str) -> str:
    """The README's first paragraph, for when the description is empty."""

    in_fence = False
    for raw_line in readme.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith("#") or line.startswith("<") or line.startswith("["):
            continue
        return _text(line)[:README_MAX_CHARS]
    return ""


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if matches(text, term)]


def _popularity(stars: int) -> int:
    """Log-scaled star bonus, so a 10k repo does not bury everything else."""

    return int(round(POPULARITY_WEIGHT * math.log10(max(stars, 1))))


def _recency(pushed_at: str, today: date, config: Config) -> int:
    pushed = _local_date(pushed_at, config)
    if pushed is None:
        return 0
    days = (today - pushed).days
    if days == 0:
        return RECENCY_TODAY
    if days == 1:
        return RECENCY_YESTERDAY
    return 0


def _local_date(value: str, config: Config) -> date | None:
    moment = _parse_timestamp(value)
    if moment is None:
        return None
    return moment.astimezone(config.zone()).date()


def _timestamp(value: str) -> int:
    moment = _parse_timestamp(value)
    return int(moment.timestamp()) if moment is not None else 0


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _throttled_get(
    url: str, params: Mapping[str, str], config: Config, *, error: str
) -> str:
    global _last_request_at
    wait = REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    try:
        return get_text(
            url,
            params,
            timeout=30,
            user_agent=USER_AGENT,
            error=error,
            headers=_auth_headers(config),
        )
    finally:
        _last_request_at = time.monotonic()


def _auth_headers(config: Config) -> dict[str, str]:
    token = os.environ.get(config.github.token_env, "").strip()
    if not token:
        # Config validation rejects this earlier; guard the direct API seam.
        raise SourceError(f"{config.github.token_env} is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
