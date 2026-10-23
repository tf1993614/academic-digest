"""arXiv adapter: RSS announcements plus API keyword history.

The RSS feed answers "what was announced today": every item carries an
announcement type, so ``replace`` (new version) and ``cross`` (duplicate
cross-list) entries are dropped. The API cannot label announcements, but it is
the only way to backfill the configured lookback after a missed run. Its query
is narrowed by the configured categories and topic terms, and entries whose
``updated`` timestamp differs from ``published`` are skipped as new versions.

Both paths feed one map keyed by arXiv ID. The API fills gaps (DOI, journal
reference) when the same paper also appeared in today's RSS. The configured
lookback must be at least four days so a Friday-Monday announcement batch is not
lost. Live requests run sequentially, three seconds apart, per arXiv's terms of
use.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from functools import partial
from pathlib import Path

from ..config import Config
from ..errors import SourceError
from ..models import Paper, normalize_arxiv_id, normalize_doi, paper_id
from .base import (
    SourceResult,
    get_text,
    in_window,
    lookback_window,
    read_fixture,
    read_or_fetch,
    search_terms,
)
from .rss import (
    FeedItem,
    child,
    children,
    element_text,
    local_name,
    parse_feed,
)

NAME = "arxiv"
FIXTURE_RSS = "arxiv/rss/{category}.xml"
FIXTURE_QUERY = "arxiv/query.atom"
RSS_URL = "https://rss.arxiv.org/rss/{category}"
API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "academic-digest/0.1 (arXiv collector)"
REQUEST_INTERVAL = 3.0
API_RESULTS = 200

_ANNOUNCE_PREFIX = re.compile(
    r"^\s*arXiv:\S+\s+Announce Type:\s*\S+\s*", re.IGNORECASE
)
_ABSTRACT_LABEL = re.compile(r"^Abstract:\s*", re.IGNORECASE)
_ABS_PATH = re.compile(r"/abs/([^/?#\s]+)")
_DESCRIPTION_ID = re.compile(r"arXiv:(\S+)")
_last_request_at = 0.0


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> SourceResult:
    try:
        start, end = lookback_window(config, NAME, now)
        papers: dict[str, Paper] = {}
        for category in config.arxiv_categories:
            text = read_or_fetch(
                fixtures_root,
                FIXTURE_RSS.format(category=category),
                partial(_fetch_rss, category),
            )
            for item in parse_feed(text, "arXiv RSS"):
                _remember(papers, _rss_paper(item, start, end))

        text = read_or_fetch(
            fixtures_root,
            FIXTURE_QUERY,
            partial(_fetch_api, config, now),
        )
        for paper in _api_papers(text, start, end):
            _remember(papers, paper)
    except (SourceError, OSError) as exc:
        return SourceResult.failed(NAME, str(exc))
    return SourceResult.ok(NAME, list(papers.values()))


def check(config: Config, fixtures_root: Path | None) -> str:
    if fixtures_root is not None:
        return validate_fixture(config, fixtures_root)
    if not config.arxiv_categories:
        raise SourceError("arxiv.categories is empty")
    category = config.arxiv_categories[0]
    items = parse_feed(_fetch_rss(category), "arXiv RSS")
    new_items = sum(1 for item in items if item.announce_type == "new")
    return f"arXiv RSS reachable ({new_items} new items in {category})"


def validate_fixture(config: Config, root: Path) -> str:
    parts: list[str] = []
    new_total = 0
    for category in config.arxiv_categories:
        text = read_fixture(root, FIXTURE_RSS.format(category=category))
        items = parse_feed(text, "arXiv RSS")
        new_items = sum(1 for item in items if item.announce_type == "new")
        new_total += new_items
        parts.append(f"{category}: {new_items}/{len(items)} new")
    api = _api_papers(read_fixture(root, FIXTURE_QUERY), date.min, date.max)
    return (
        f"arXiv RSS: {'; '.join(parts)}; API: {len(api)} new entries; "
        f"{new_total} new item(s)"
    )


def build_query(config: Config, now: datetime) -> str:
    """Keyword + category + date query for the API history backfill."""

    start, end = lookback_window(config, NAME, now)
    categories = " OR ".join(f"cat:{category}" for category in config.arxiv_categories)
    terms = " OR ".join(f'all:"{term}"' for term in search_terms(config))
    return (
        f"({categories}) AND ({terms}) AND "
        f"submittedDate:[{start.strftime('%Y%m%d')}0000 TO {end.strftime('%Y%m%d')}2359]"
    )


def _rss_paper(item: FeedItem, start: date, end: date) -> Paper | None:
    if item.announce_type != "new" or not item.title:
        return None
    if not in_window(item.date, start, end):
        return None

    arxiv_id = _rss_arxiv_id(item)
    published_date = item.date.isoformat() if item.date is not None else ""
    url = item.link or _abs_url(arxiv_id)

    return Paper(
        id=paper_id(arxiv_id=arxiv_id, title=item.title, year=published_date[:4]),
        source=NAME,
        title=item.title,
        abstract=_rss_abstract(item),
        authors=list(item.authors),
        venue="arXiv",
        date=published_date,
        arxiv_id=arxiv_id,
        url=url,
        is_preprint=True,
        oa_url=_pdf_url(arxiv_id),
    )


def _api_papers(text: str, start: date, end: date) -> list[Paper]:
    root = _atom_root(text)
    papers: list[Paper] = []
    for entry in children(root, "entry"):
        published_text = element_text(child(entry, "published"))
        updated_text = element_text(child(entry, "updated"))
        if published_text and updated_text and published_text != updated_text:
            continue

        published = _atom_date(published_text)
        if not in_window(published, start, end):
            continue

        title = element_text(child(entry, "title"))
        if not title:
            continue

        arxiv_id = _arxiv_id(element_text(child(entry, "id")))
        doi = normalize_doi(element_text(child(entry, "doi")))
        journal_ref = element_text(child(entry, "journal_ref"))
        published_date = published.isoformat() if published is not None else ""
        authors = [
            element_text(child(author, "name"))
            for author in children(entry, "author")
        ]

        papers.append(
            Paper(
                id=paper_id(
                    doi=doi,
                    arxiv_id=arxiv_id,
                    title=title,
                    year=published_date[:4],
                ),
                source=NAME,
                title=title,
                abstract=element_text(child(entry, "summary")),
                authors=[name for name in authors if name],
                venue=journal_ref or "arXiv",
                date=published_date,
                doi=doi,
                arxiv_id=arxiv_id,
                url=_alternate_link(entry) or _abs_url(arxiv_id),
                is_preprint=True,
                oa_url=_pdf_url(arxiv_id),
            )
        )
    return papers


def _remember(papers: dict[str, Paper], paper: Paper | None) -> None:
    """Keep one record per arXiv ID, filling gaps from the later duplicate."""

    if paper is None:
        return
    key = paper.arxiv_id or paper.id
    existing = papers.get(key)
    if existing is None:
        papers[key] = paper
        return
    if not existing.doi and paper.doi:
        existing.doi = paper.doi
    if not existing.abstract and paper.abstract:
        existing.abstract = paper.abstract
    if not existing.authors and paper.authors:
        existing.authors = paper.authors
    if existing.venue == "arXiv" and paper.venue != "arXiv":
        existing.venue = paper.venue


def _rss_arxiv_id(item: FeedItem) -> str:
    for value in (item.link, item.description):
        found = _arxiv_id(value)
        if found:
            return found
    match = _DESCRIPTION_ID.search(item.description)
    return normalize_arxiv_id(match.group(1)) if match else ""


def _rss_abstract(item: FeedItem) -> str:
    text = item.abstract or item.description
    text = _ANNOUNCE_PREFIX.sub("", text)
    return _ABSTRACT_LABEL.sub("", text).strip()


def _atom_root(text: str) -> ET.Element:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SourceError(f"invalid arXiv API Atom: {exc}") from exc
    if local_name(root.tag) != "feed":
        raise SourceError("invalid arXiv API Atom: expected a feed")
    return root


def _atom_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _arxiv_id(value: str) -> str:
    match = _ABS_PATH.search(value)
    return normalize_arxiv_id(match.group(1)) if match else ""


def _alternate_link(entry: ET.Element) -> str:
    for link in children(entry, "link"):
        href = (link.get("href") or "").strip()
        if href and (link.get("rel") or "alternate") == "alternate":
            return href
    return ""


def _abs_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""


def _pdf_url(arxiv_id: str) -> str | None:
    return f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None


def _fetch_rss(category: str) -> str:
    return _throttled_get(
        RSS_URL.format(category=category),
        {},
        error=f"arXiv RSS request failed for {category}",
    )


def _fetch_api(config: Config, now: datetime) -> str:
    return _throttled_get(
        API_URL,
        {
            "search_query": build_query(config, now),
            "start": "0",
            "max_results": str(API_RESULTS),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        error="arXiv API request failed",
    )


def _throttled_get(url: str, params: dict[str, str], *, error: str) -> str:
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
        )
    finally:
        _last_request_at = time.monotonic()
