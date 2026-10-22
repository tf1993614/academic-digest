"""Load and validate the YAML configuration before any network request."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .errors import ConfigError

DEFAULT_MAX_ITEMS = 30
DEFAULT_STATE_DB = "state/academic-digest.sqlite3"
DEFAULT_CANDIDATES = "out/candidates.json"

# GitHub's discovery recipe, split by keyword group. These are the 22 queries
# that feed the new/active repository passes; ``DEFAULT_G6_QUERIES`` feeds the
# AI-tool block. A config may override either list.
DEFAULT_GITHUB_QUERIES: Mapping[str, tuple[str, ...]] = {
    "G1": (
        "topic:aging",
        "topic:multi-omics",
    ),
    "G2": (
        "topic:single-cell",
        "topic:spatial-transcriptomics",
        "topic:single-cell-analysis",
        '"spatial transcriptomics" in:name,description,readme',
        '"cell type annotation" in:name,description,readme',
        '"batch effect correction" in:name,description,readme',
        "MERFISH in:name,description,readme",
        "CITE-seq in:name,description,readme",
        '"cell-cell communication" in:name,description,readme',
    ),
    "G3": (
        '"single-cell foundation model" in:name,description,readme',
        "CellVQ in:name,description,readme",
        "ESM-2 in:name,description,readme",
    ),
    "G4": (
        "topic:gene-regulatory-network",
        '"perturbation prediction" in:name,description,readme',
        '"protein imputation" in:name,description,readme',
    ),
    "G5": (
        "topic:knowledge-graph",
        "topic:graph-neural-network",
        '"virtual cell" in:name,description,readme',
        "LLM single-cell in:name,description,readme",
        "GraphRAG in:name,description,readme",
    ),
}
DEFAULT_G6_QUERIES: tuple[str, ...] = (
    "topic:claude-code",
    '"claude code" in:name,description,readme',
    "topic:codex",
    '"codex cli" in:name,description,readme',
    '"openai codex" in:name,description,readme',
    "topic:deepseek-harness",
    '"deepseek harness" in:name,description,readme',
    '"DSH harness" in:name,description,readme',
    "topic:ai-coding-agent",
    "topic:coding-agent",
    '"agent harness" in:name,description,readme',
    '"terminal agent" in:name,description,readme',
)
DEFAULT_G6_TOPIC = "G6"
DEFAULT_GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
DEFAULT_NEW_DAYS = 7
DEFAULT_NEW_MIN_STARS = 5
DEFAULT_NEW_MAX_ITEMS = 1
DEFAULT_ACTIVE_DAYS = 7
DEFAULT_ACTIVE_MIN_STARS = 30
DEFAULT_ACTIVE_MAX_ITEMS = 2
DEFAULT_G6_MAX_ITEMS = 2
DEFAULT_README_LIMIT = 20

KNOWN_SOURCES = (
    "pubmed",
    "europepmc",
    "arxiv",
    "researchsquare",
    "biorxiv",
    "medrxiv",
    "github",
)
# arXiv merges Friday-Monday submissions into one announcement, so a window
# shorter than four days silently loses the weekend batch. GitHub carries its
# own new/active windows under ``github.new.days`` and ``github.active.days``.
MIN_LOOKBACK = {"arxiv": 4}
_SOURCES_WITHOUT_LOOKBACK = {"github"}
_TOP_LEVEL_KEYS = {
    "timezone",
    "lookback",
    "topics",
    "sources",
    "pool",
    "paths",
    "arxiv",
    "github",
    "fulltext",
}
_TOPIC_KEYS = {"name", "label", "terms", "exclude", "max_items"}
_POOL_KEYS = {"max_items"}
_PATH_KEYS = {"state_db", "candidates"}
_ARXIV_KEYS = {"categories"}
_FULLTEXT_KEYS = {"unpaywall"}
_UNPAYWALL_KEYS = {"email"}
_GITHUB_KEYS = {
    "token_env",
    "g6_topic",
    "new",
    "active",
    "g6",
    "readme_limit",
    "queries",
    "g6_queries",
}
_GITHUB_WINDOW_KEYS = {"days", "min_stars", "max_items"}
_GITHUB_G6_KEYS = {"max_items"}


@dataclass(frozen=True)
class Topic:
    name: str
    label: str
    terms: tuple[str, ...]
    exclude: tuple[str, ...]
    max_items: int


@dataclass(frozen=True)
class DiscoveryWindow:
    """One GitHub discovery pass: how far back, how many stars, how many slots."""

    days: int
    min_stars: int
    max_items: int


@dataclass(frozen=True)
class GithubConfig:
    token_env: str
    g6_topic: str
    new: DiscoveryWindow
    active: DiscoveryWindow
    g6_max_items: int
    readme_limit: int
    # Keyword group -> server-side discovery queries, in configuration order.
    queries: Mapping[str, tuple[str, ...]]
    g6_queries: tuple[str, ...]

    def query_pairs(self, topics: tuple[Topic, ...]) -> list[tuple[str, str]]:
        """Every discovery query with the group it belongs to.

        Groups follow the configured topic order so a reordered YAML mapping
        still records and replays its requests in the same order.
        """

        pairs = [
            (topic.name, query)
            for topic in topics
            for query in self.queries.get(topic.name, ())
        ]
        pairs.extend((self.g6_topic, query) for query in self.g6_queries)
        return pairs


@dataclass(frozen=True)
class FullTextConfig:
    """OA full-text lookup settings; the email is optional."""

    unpaywall_email: str


@dataclass(frozen=True)
class Config:
    path: Path
    timezone: str
    lookback: Mapping[str, int]
    topics: tuple[Topic, ...]
    sources: Mapping[str, bool]
    arxiv_categories: tuple[str, ...]
    github: GithubConfig
    fulltext: FullTextConfig
    pool_max_items: int
    state_db: Path
    candidates_path: Path

    @property
    def enabled_sources(self) -> tuple[str, ...]:
        return tuple(name for name in KNOWN_SOURCES if self.sources.get(name))

    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def local_date(self, moment: datetime) -> date:
        """The calendar date in the configured timezone."""

        return moment.astimezone(self.zone()).date()


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError("config", f"file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError("config", f"cannot read YAML: {exc}") from exc

    raw = _require_mapping(raw, "config")
    _reject_unknown(raw, _TOP_LEVEL_KEYS, "config")

    timezone = _require_string(raw.get("timezone"), "timezone")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError("timezone", f"unknown timezone: {timezone!r}") from exc

    sources = _parse_sources(raw.get("sources"))
    lookback = _parse_lookback(raw.get("lookback"), sources)
    arxiv_categories = _parse_arxiv(raw.get("arxiv"), sources)
    topics = _parse_topics(raw.get("topics"))
    github = _parse_github(raw.get("github"), topics)
    fulltext = _parse_fulltext(raw.get("fulltext"))
    pool_max_items = _parse_pool(raw.get("pool"), len(topics))
    state_db, candidates_path = _parse_paths(raw.get("paths"), path.parent)
    if sources.get("github"):
        _require_github_token(github.token_env)

    return Config(
        path=path,
        timezone=timezone,
        lookback=lookback,
        topics=topics,
        sources=sources,
        arxiv_categories=arxiv_categories,
        github=github,
        fulltext=fulltext,
        pool_max_items=pool_max_items,
        state_db=state_db,
        candidates_path=candidates_path,
    )


def _parse_sources(value: Any) -> dict[str, bool]:
    mapping = _require_mapping(value, "sources")
    sources: dict[str, bool] = {}
    for name, enabled in mapping.items():
        field = f"sources.{name}"
        if not isinstance(name, str) or name not in KNOWN_SOURCES:
            raise ConfigError(field, f"unknown source (known: {', '.join(KNOWN_SOURCES)})")
        if not isinstance(enabled, bool):
            raise ConfigError(field, "must be true or false")
        sources[name] = enabled
    if "pubmed" not in sources:
        raise ConfigError("sources.pubmed", "is required (set true or false)")
    if not any(sources.values()):
        raise ConfigError("sources", "at least one source must be enabled")
    return sources


def _parse_lookback(value: Any, sources: Mapping[str, bool]) -> dict[str, int]:
    mapping = _require_mapping(value if value is not None else {}, "lookback")
    lookback: dict[str, int] = {}
    for name, days in mapping.items():
        field = f"lookback.{name}"
        if not isinstance(name, str) or name not in KNOWN_SOURCES:
            raise ConfigError(field, f"unknown source (known: {', '.join(KNOWN_SOURCES)})")
        days = _positive_int(days, field)
        minimum = MIN_LOOKBACK.get(name)
        if sources.get(name) and minimum is not None and days < minimum:
            raise ConfigError(
                field,
                f"must be at least {minimum} days for {name} "
                "(announcements merge over weekends and holidays)",
            )
        lookback[name] = days
    for name, enabled in sources.items():
        if enabled and name not in lookback and name not in _SOURCES_WITHOUT_LOOKBACK:
            raise ConfigError(f"lookback.{name}", f"is required when the {name} source is enabled")
    return lookback


def _parse_arxiv(value: Any, sources: Mapping[str, bool]) -> tuple[str, ...]:
    """The arXiv categories whose RSS feeds the daily job reads."""

    if value is None:
        if sources.get("arxiv"):
            raise ConfigError(
                "arxiv.categories",
                "is required when the arxiv source is enabled "
                "(for example cs.LG, q-bio.QM)",
            )
        return ()
    mapping = _require_mapping(value, "arxiv")
    _reject_unknown(mapping, _ARXIV_KEYS, "arxiv")
    categories = _string_list(
        mapping.get("categories"), "arxiv.categories", allow_empty=False
    )
    return tuple(dict.fromkeys(categories))


def _parse_github(value: Any, topics: tuple[Topic, ...]) -> GithubConfig:
    """Parse the optional ``github`` section, filling the documented defaults."""

    topic_names = tuple(topic.name for topic in topics)
    mapping = _require_mapping(value if value is not None else {}, "github")
    _reject_unknown(mapping, _GITHUB_KEYS, "github")

    token_env = _require_string(
        mapping.get("token_env", DEFAULT_GITHUB_TOKEN_ENV), "github.token_env"
    )
    g6_topic = _require_string(
        mapping.get("g6_topic", DEFAULT_G6_TOPIC), "github.g6_topic"
    )
    new = _parse_github_window(
        mapping.get("new"),
        "github.new",
        DiscoveryWindow(
            days=DEFAULT_NEW_DAYS,
            min_stars=DEFAULT_NEW_MIN_STARS,
            max_items=DEFAULT_NEW_MAX_ITEMS,
        ),
    )
    active = _parse_github_window(
        mapping.get("active"),
        "github.active",
        DiscoveryWindow(
            days=DEFAULT_ACTIVE_DAYS,
            min_stars=DEFAULT_ACTIVE_MIN_STARS,
            max_items=DEFAULT_ACTIVE_MAX_ITEMS,
        ),
    )
    g6_max_items = _parse_g6_max_items(mapping.get("g6"))
    readme_limit = _positive_int(
        mapping.get("readme_limit", DEFAULT_README_LIMIT), "github.readme_limit"
    )
    queries = _parse_github_queries(mapping.get("queries"), topic_names)
    g6_queries = _parse_g6_queries(
        mapping.get("g6_queries"), g6_topic, topic_names
    )

    return GithubConfig(
        token_env=token_env,
        g6_topic=g6_topic,
        new=new,
        active=active,
        g6_max_items=g6_max_items,
        readme_limit=readme_limit,
        queries=queries,
        g6_queries=g6_queries,
    )


def _parse_github_window(
    value: Any, field: str, default: DiscoveryWindow
) -> DiscoveryWindow:
    if value is None:
        return default
    mapping = _require_mapping(value, field)
    _reject_unknown(mapping, _GITHUB_WINDOW_KEYS, field)
    return DiscoveryWindow(
        days=_positive_int(mapping.get("days", default.days), f"{field}.days"),
        min_stars=_non_negative_int(
            mapping.get("min_stars", default.min_stars), f"{field}.min_stars"
        ),
        max_items=_non_negative_int(
            mapping.get("max_items", default.max_items), f"{field}.max_items"
        ),
    )


def _parse_g6_max_items(value: Any) -> int:
    if value is None:
        return DEFAULT_G6_MAX_ITEMS
    mapping = _require_mapping(value, "github.g6")
    _reject_unknown(mapping, _GITHUB_G6_KEYS, "github.g6")
    return _non_negative_int(
        mapping.get("max_items", DEFAULT_G6_MAX_ITEMS), "github.g6.max_items"
    )


def _parse_github_queries(
    value: Any, topic_names: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    if value is None:
        # Only groups the config actually defines can be discovered.
        return {
            group: queries
            for group, queries in DEFAULT_GITHUB_QUERIES.items()
            if group in topic_names
        }
    mapping = _require_mapping(value, "github.queries")
    queries: dict[str, tuple[str, ...]] = {}
    for group, items in mapping.items():
        field = f"github.queries.{group}"
        if not isinstance(group, str) or group not in topic_names:
            raise ConfigError(
                field,
                f"unknown topic (known: {', '.join(topic_names)})",
            )
        queries[group] = tuple(
            _string_list(items, field, allow_empty=False)
        )
    return queries


def _parse_g6_queries(
    value: Any, g6_topic: str, topic_names: tuple[str, ...]
) -> tuple[str, ...]:
    if value is None:
        # Without an AI-tool group the G6 section has nowhere to go.
        return DEFAULT_G6_QUERIES if g6_topic in topic_names else ()
    queries = tuple(_string_list(value, "github.g6_queries", allow_empty=True))
    if queries and g6_topic not in topic_names:
        raise ConfigError(
            "github.g6_topic",
            f"must name a configured topic (known: {', '.join(topic_names)})",
        )
    return queries


def _require_github_token(token_env: str) -> None:
    if not os.environ.get(token_env, "").strip():
        raise ConfigError(
            "github.token",
            f"{token_env} is not set; a GitHub token is required for repository "
            "discovery (put it in the local secrets file and export it before running)",
        )


def _parse_fulltext(value: Any) -> FullTextConfig:
    """Parse the optional ``fulltext`` section.

    The Unpaywall email is optional so fixture runs and Europe PMC/arXiv-only
    setups do not need one; without it the Unpaywall lookup is skipped and the
    digest falls back to the abstract.
    """

    if value is None:
        return FullTextConfig(unpaywall_email="")
    mapping = _require_mapping(value, "fulltext")
    _reject_unknown(mapping, _FULLTEXT_KEYS, "fulltext")
    unpaywall = mapping.get("unpaywall")
    if unpaywall is None:
        return FullTextConfig(unpaywall_email="")
    email_mapping = _require_mapping(unpaywall, "fulltext.unpaywall")
    _reject_unknown(email_mapping, _UNPAYWALL_KEYS, "fulltext.unpaywall")
    email = email_mapping.get("email", "")
    if email is None:
        return FullTextConfig(unpaywall_email="")
    if not isinstance(email, str):
        raise ConfigError("fulltext.unpaywall.email", "must be a string")
    email = email.strip()
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        raise ConfigError("fulltext.unpaywall.email", "must be an email address")
    return FullTextConfig(unpaywall_email=email)


def _parse_topics(value: Any) -> tuple[Topic, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("topics", "must be a non-empty list")
    topics: list[Topic] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        field = f"topics[{index}]"
        mapping = _require_mapping(item, field)
        _reject_unknown(mapping, _TOPIC_KEYS, field)

        name = _require_string(mapping.get("name"), f"{field}.name")
        if name in seen:
            raise ConfigError(f"{field}.name", f"duplicate topic name: {name!r}")
        seen.add(name)

        label = mapping.get("label", name)
        if not isinstance(label, str) or not label.strip():
            raise ConfigError(f"{field}.label", "must be a non-empty string")

        terms = _string_list(mapping.get("terms"), f"{field}.terms", allow_empty=False)
        exclude = _string_list(mapping.get("exclude", []), f"{field}.exclude", allow_empty=True)
        max_items = _positive_int(mapping.get("max_items", 6), f"{field}.max_items")

        topics.append(
            Topic(
                name=name,
                label=label.strip(),
                terms=tuple(terms),
                exclude=tuple(exclude),
                max_items=max_items,
            )
        )
    return tuple(topics)


def _parse_pool(value: Any, topic_count: int) -> int:
    if value is None:
        pool_max = DEFAULT_MAX_ITEMS
    else:
        mapping = _require_mapping(value, "pool")
        _reject_unknown(mapping, _POOL_KEYS, "pool")
        pool_max = _positive_int(mapping.get("max_items", DEFAULT_MAX_ITEMS), "pool.max_items")
    if pool_max < topic_count:
        raise ConfigError(
            "pool.max_items",
            f"must be at least the number of topics ({topic_count}) "
            "so every non-empty group can keep a paper",
        )
    return pool_max


def _parse_paths(value: Any, base: Path) -> tuple[Path, Path]:
    if value is None:
        value = {}
    mapping = _require_mapping(value, "paths")
    _reject_unknown(mapping, _PATH_KEYS, "paths")

    state_db = mapping.get("state_db", DEFAULT_STATE_DB)
    candidates = mapping.get("candidates", DEFAULT_CANDIDATES)
    for field, item in (("paths.state_db", state_db), ("paths.candidates", candidates)):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(field, "must be a non-empty path string")

    return (_resolve(base, state_db), _resolve(base, candidates))


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(field, "must be a mapping")
    return value


def _reject_unknown(mapping: Mapping[str, Any], allowed: set[str], field: str) -> None:
    for key in mapping:
        if not isinstance(key, str) or key not in allowed:
            raise ConfigError(f"{field}.{key}", "unknown key")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(field, "must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(field, "must be a positive integer")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(field, "must be a non-negative integer")
    return value


def _string_list(value: Any, field: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "" if allow_empty else " non-empty"
        raise ConfigError(field, f"must be a{qualifier} list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{field}[{index}]", "must be a non-empty string")
        result.append(item.strip())
    return result
