"""Research Square adapter: the public RSS feed, never the official API.

Research Square's JSON API needs an application token (and its ``robots.txt``
disallows ``/api/``), but the public RSS feed carries the full ``<abstract>``,
``<authors>``, and ``<doi>`` for roughly the last three days. The feed's
``created on`` timestamp is used for the lookback window; the source keeps the
paper's own DOI so Europe PMC or PubMed can merge into it later.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

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
from .rss import FeedItem, parse_feed

NAME = "researchsquare"
FIXTURE_RSS = "researchsquare/rss.xml"
RSS_URL = "https://www.researchsquare.com/rss.xml"
USER_AGENT = "academic-digest/0.1 (Research Square RSS collector)"

_CREATED_ON = re.compile(r"created on (\d{4}-\d{2}-\d{2})")


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> SourceResult:
    try:
        start, end = lookback_window(config, NAME, now)
        text = read_or_fetch(fixtures_root, FIXTURE_RSS, _fetch_live)
        papers = [
            paper
            for paper in (
                _to_paper(item, start, end)
                for item in parse_feed(text, "Research Square RSS")
            )
            if paper is not None
        ]
    except (SourceError, OSError) as exc:
        return SourceResult.failed(NAME, str(exc))
    return SourceResult.ok(NAME, papers)


def check(config: Config, fixtures_root: Path | None) -> str:
    if fixtures_root is not None:
        text = read_fixture(fixtures_root, FIXTURE_RSS)
        items = parse_feed(text, "Research Square RSS")
        return f"{FIXTURE_RSS}; {len(items)} records"
    items = parse_feed(_fetch_live(), "Research Square RSS")
    return f"Research Square RSS reachable ({len(items)} records)"


def _to_paper(item: FeedItem, start: date, end: date) -> Paper | None:
    if not item.title:
        return None
    published = _created_on(item) or item.date
    if not in_window(published, start, end):
        return None

    doi = normalize_doi(item.doi)
    published_date = published.isoformat() if published is not None else ""
    url = item.link or (f"https://doi.org/{doi}" if doi else "")

    return Paper(
        id=paper_id(doi=doi, title=item.title, year=published_date[:4]),
        source=NAME,
        title=item.title,
        abstract=item.abstract,
        authors=list(item.authors),
        venue="Research Square",
        date=published_date,
        doi=doi,
        url=url,
        is_preprint=True,
    )


def _created_on(item) -> date | None:
    match = _CREATED_ON.search(item.description)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _fetch_live() -> str:
    return get_text(
        RSS_URL,
        {},
        timeout=60,
        user_agent=USER_AGENT,
        error="Research Square RSS request failed",
    )
