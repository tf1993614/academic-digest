"""Load and validate the YAML configuration before any network request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .errors import ConfigError

DEFAULT_MAX_ITEMS = 30
DEFAULT_STATE_DB = "state/academic-digest.sqlite3"
DEFAULT_CANDIDATES = "out/candidates.json"

KNOWN_SOURCES = ("pubmed", "europepmc")
_TOP_LEVEL_KEYS = {"timezone", "lookback", "topics", "sources", "pool", "paths"}
_TOPIC_KEYS = {"name", "label", "terms", "exclude", "max_items"}
_POOL_KEYS = {"max_items"}
_PATH_KEYS = {"state_db", "candidates"}


@dataclass(frozen=True)
class Topic:
    name: str
    label: str
    terms: tuple[str, ...]
    exclude: tuple[str, ...]
    max_items: int


@dataclass(frozen=True)
class Config:
    path: Path
    timezone: str
    lookback: Mapping[str, int]
    topics: tuple[Topic, ...]
    sources: Mapping[str, bool]
    pool_max_items: int
    state_db: Path
    candidates_path: Path

    @property
    def enabled_sources(self) -> tuple[str, ...]:
        return tuple(name for name in KNOWN_SOURCES if self.sources.get(name))

    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


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
    topics = _parse_topics(raw.get("topics"))
    pool_max_items = _parse_pool(raw.get("pool"))
    state_db, candidates_path = _parse_paths(raw.get("paths"), path.parent)

    return Config(
        path=path,
        timezone=timezone,
        lookback=lookback,
        topics=topics,
        sources=sources,
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
    if not sources:
        raise ConfigError("sources", "at least one source must be configured")
    if not any(sources.values()):
        raise ConfigError("sources", "at least one source must be enabled")
    return sources


def _parse_lookback(value: Any, sources: Mapping[str, bool]) -> dict[str, int]:
    mapping = _require_mapping(value, "lookback")
    lookback: dict[str, int] = {}
    for name, days in mapping.items():
        field = f"lookback.{name}"
        if not isinstance(name, str) or name not in KNOWN_SOURCES:
            raise ConfigError(field, f"unknown source (known: {', '.join(KNOWN_SOURCES)})")
        lookback[name] = _positive_int(days, field)
    for name, enabled in sources.items():
        if enabled and name not in lookback:
            raise ConfigError(f"lookback.{name}", f"is required when the {name} source is enabled")
    return lookback


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


def _parse_pool(value: Any) -> int:
    if value is None:
        return DEFAULT_MAX_ITEMS
    mapping = _require_mapping(value, "pool")
    _reject_unknown(mapping, _POOL_KEYS, "pool")
    return _positive_int(mapping.get("max_items", DEFAULT_MAX_ITEMS), "pool.max_items")


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
