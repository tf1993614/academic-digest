"""bioRxiv adapter: date-range JSON pages, filtered locally by keyword group.

``api.biorxiv.org`` has no free-text search, so the daily job pulls every record
in the lookback window (30 per page) and lets ``collect`` keep the ones that
match configured topics. The same endpoint serves medRxiv; a ``Server`` value
carries the name, label, API slug, and site for each.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any

from ..config import Config
from ..errors import SourceError
from ..models import Paper, normalize_doi, paper_id
from .base import (
    SourceResult,
    get_text,
    in_window,
    lookback_window,
    read_fixture,
    read_or_fetch,
)
from .rss import split_authors

FIXTURE_PAGE = "{source}/details-{cursor}.json"
API_URL = "https://api.biorxiv.org/details/{server}/{start}/{end}/{cursor}"
USER_AGENT = "academic-digest/0.1 (bioRxiv/medRxiv collector)"
PAGE_SIZE = 30
MAX_PAGES = 200
PAGE_INTERVAL = 1.0

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


@dataclass(frozen=True)
class Server:
    name: str
    display: str
    api_name: str
    site: str


BIORXIV = Server(
    name="biorxiv",
    display="bioRxiv",
    api_name="biorxiv",
    site="https://www.biorxiv.org",
)
MEDRXIV = Server(
    name="medrxiv",
    display="medRxiv",
    api_name="medrxiv",
    site="https://www.medrxiv.org",
)

NAME = BIORXIV.name


@dataclass(frozen=True)
class Page:
    records: list[dict[str, Any]]
    count: int
    total: int


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> SourceResult:
    return collect_server(BIORXIV, config, fixtures_root, now)


def collect_server(
    server: Server,
    config: Config,
    fixtures_root: Path | None,
    now: datetime,
) -> SourceResult:
    try:
        start, end = lookback_window(config, server.name, now)
        records = _records(server, config, fixtures_root, start, end)
        papers = [
            paper
            for paper in (
                _to_paper(record, server, start, end) for record in records
            )
            if paper is not None
        ]
    except (SourceError, OSError, ValueError) as exc:
        return SourceResult.failed(server.name, str(exc))
    return SourceResult.ok(server.name, papers)


def check(config: Config, fixtures_root: Path | None) -> str:
    return check_server(BIORXIV, fixtures_root)


def check_server(server: Server, fixtures_root: Path | None) -> str:
    if fixtures_root is not None:
        relative = FIXTURE_PAGE.format(source=server.name, cursor=0)
        page = _parse_page(read_fixture(fixtures_root, relative), server.name)
        return f"{relative}; {len(page.records)} records"
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=7)
    page = _parse_page(
        _fetch_live(server.api_name, start.isoformat(), end.isoformat(), 0),
        server.name,
    )
    return f"{server.display} API reachable ({page.total} records in the last week)"


def _records(
    server: Server,
    config: Config,
    fixtures_root: Path | None,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor = 0
    for _ in range(MAX_PAGES):
        text = read_or_fetch(
            fixtures_root,
            FIXTURE_PAGE.format(source=server.name, cursor=cursor),
            partial(
                _fetch_live,
                server.api_name,
                start.isoformat(),
                end.isoformat(),
                cursor,
            ),
        )
        page = _parse_page(text, server.name)
        records.extend(page.records)

        next_cursor = cursor + page.count
        if page.count == 0 or page.count < PAGE_SIZE or next_cursor >= page.total:
            break
        cursor = next_cursor
        if fixtures_root is None:
            time.sleep(PAGE_INTERVAL)
    return records


def _parse_page(text: str, label: str) -> Page:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceError(f"invalid {label} JSON: expected a JSON object")
    collection = payload.get("collection")
    if not isinstance(collection, list):
        raise SourceError(f"invalid {label} JSON: missing collection")
    if not all(isinstance(record, dict) for record in collection):
        raise SourceError(f"invalid {label} JSON: collection entries must be objects")

    messages = payload.get("messages")
    message = (
        messages[0]
        if isinstance(messages, list) and messages and isinstance(messages[0], dict)
        else {}
    )
    status = _text(message.get("status"))
    if status and status.lower() not in ("ok", "no posts found"):
        raise SourceError(f"invalid {label} JSON: {status}")

    default = len(collection)
    return Page(
        records=collection,
        count=_int_or(message.get("count"), default),
        total=_int_or(message.get("total"), default),
    )


def _to_paper(
    record: dict[str, Any],
    server: Server,
    start: date,
    end: date,
) -> Paper | None:
    title = _text(record.get("title"))
    if not title:
        return None

    published = _iso_date(_text(record.get("date")))
    if not in_window(published, start, end):
        return None

    doi = normalize_doi(_text(record.get("doi")))
    version = _text(record.get("version"))
    published_date = published.isoformat() if published is not None else ""
    url = (
        f"{server.site}/content/{doi}v{version}"
        if doi and version
        else (f"{server.site}/content/{doi}" if doi else "")
    )

    return Paper(
        id=paper_id(doi=doi, title=title, year=published_date[:4]),
        source=server.name,
        title=title,
        abstract=_text(record.get("abstract")),
        authors=list(
            split_authors(_text(record.get("authors")), separator=r";\s*")
        ),
        venue=server.display,
        date=published_date,
        doi=doi,
        url=url,
        is_preprint=True,
        oa_url=f"{url}.full.pdf" if url else None,
    )


def _fetch_live(server: str, start: str, end: str, cursor: int) -> str:
    return get_text(
        API_URL.format(server=server, start=start, end=end, cursor=cursor),
        {},
        timeout=90,
        user_agent=USER_AGENT,
        error=f"{server} API request failed",
    )


def _iso_date(value: str) -> date | None:
    match = _ISO_DATE.match(value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _int_or(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, int):
        return str(value)
    return ""
