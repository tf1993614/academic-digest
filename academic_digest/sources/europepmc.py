"""Europe PMC adapter: JSON ``search`` with core metadata and preprints.

Europe PMC supplements PubMed with preprints (``SRC:PPR``) and missing
abstracts. Its ``core`` result type carries ``abstractText``, authors, venue,
and the preprint flag in one response, so a single recorded JSON fixture covers
the whole source.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Config
from ..errors import SourceError
from ..models import Paper, normalize_doi, paper_id
from .base import (
    SourceResult,
    get_text,
    lookback_window,
    read_fixture,
    search_terms,
)

NAME = "europepmc"
FIXTURE_SEARCH = "europepmc/search.json"
SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
USER_AGENT = "academic-digest/0.1 (Europe PMC collector)"
PAGE_SIZE = 1000

_WHITESPACE = re.compile(r"\s+")
_HTML_TAG = re.compile(r"<[^>]+>")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_YEAR = re.compile(r"^(\d{4})")
_AUTHOR_SEPARATOR = re.compile(r",\s*")


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> SourceResult:
    try:
        if fixtures_root is not None:
            payload = read_fixture(fixtures_root, FIXTURE_SEARCH)
        else:
            payload = _fetch_live(config, now)
        papers = parse_search(payload)
    except (SourceError, OSError) as exc:
        return SourceResult.failed(NAME, str(exc))
    return SourceResult.ok(NAME, papers)


def check(fixtures_root: Path | None) -> str:
    """Run the doctor check for this source, offline when fixtures are given."""

    if fixtures_root is not None:
        return validate_fixture(fixtures_root)
    return check_network()


def validate_fixture(root: Path) -> str:
    payload = read_fixture(root, FIXTURE_SEARCH)
    papers = parse_search(payload)
    return f"{FIXTURE_SEARCH}; {len(papers)} records"


def check_network() -> str:
    """Make one lightweight request so doctor can diagnose connectivity."""

    payload = get_text(
        SEARCH_URL,
        {
            "query": "CRISPR",
            "format": "json",
            "resultType": "lite",
            "pageSize": "1",
        },
        timeout=10,
        user_agent=USER_AGENT,
        error="cannot reach Europe PMC REST API",
    )
    parse_search(payload)
    return "Europe PMC REST API reachable"


def parse_search(payload_text: str) -> list[Paper]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid Europe PMC JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceError("invalid Europe PMC JSON: expected a JSON object")
    result_list = payload.get("resultList")
    if not isinstance(result_list, dict):
        raise SourceError("invalid Europe PMC JSON: missing resultList")
    records = result_list.get("result") or []
    if not isinstance(records, list):
        raise SourceError("invalid Europe PMC JSON: resultList.result must be a list")

    papers: list[Paper] = []
    for record in records:
        if not isinstance(record, dict):
            raise SourceError("invalid Europe PMC JSON: result entries must be objects")
        paper = _parse_record(record)
        if paper is not None:
            papers.append(paper)
    return papers


def _parse_record(record: dict[str, Any]) -> Paper | None:
    title = _clean_html(record.get("title"))
    if not title:
        return None

    source_code = _text(record.get("source")).upper()
    doi = normalize_doi(_text(record.get("doi")))
    pmid = _text(record.get("pmid"))
    identifier = _text(record.get("id"))
    if not pmid and source_code == "MED" and identifier.isdigit():
        pmid = identifier
    is_preprint = _is_preprint(record, source_code)

    venue = _venue(record)
    if is_preprint and not venue:
        venue = "Preprint"

    date = _normalize_date(record.get("firstPublicationDate"))
    if not date:
        date = _normalize_date(record.get("pubYear"))

    return Paper(
        id=paper_id(doi=doi, pmid=pmid, title=title, year=date[:4]),
        source=NAME,
        title=title,
        abstract=_clean_html(record.get("abstractText")),
        authors=_authors(record),
        venue=venue,
        date=date,
        doi=doi,
        pmid=pmid,
        url=_record_url(source_code, _text(record.get("id")), doi),
        is_preprint=is_preprint,
    )


def _is_preprint(record: dict[str, Any], source_code: str) -> bool:
    if source_code == "PPR":
        return True
    if "preprint" in _text(record.get("pubType")).lower():
        return True
    type_list = record.get("pubTypeList")
    if isinstance(type_list, dict):
        values = type_list.get("pubType")
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            return any("preprint" in _text(value).lower() for value in values)
    return False


def _venue(record: dict[str, Any]) -> str:
    venue = _text(record.get("journalTitle"))
    if venue:
        return venue
    journal_info = record.get("journalInfo")
    if isinstance(journal_info, dict):
        journal = journal_info.get("journal")
        if isinstance(journal, dict):
            venue = _text(journal.get("title"))
            if venue:
                return venue
    details = record.get("bookOrReportDetails")
    if isinstance(details, dict):
        return _text(details.get("publisher"))
    return ""


def _authors(record: dict[str, Any]) -> list[str]:
    author_list = record.get("authorList")
    if isinstance(author_list, dict):
        entries = author_list.get("author")
        if isinstance(entries, list):
            names: list[str] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = _text(entry.get("fullName"))
                if not name:
                    fore = _text(entry.get("firstName")) or _text(entry.get("initials"))
                    last = _text(entry.get("lastName"))
                    name = " ".join(part for part in (fore, last) if part)
                if name:
                    names.append(name)
            if names:
                return names

    author_string = _text(record.get("authorString"))
    if not author_string:
        return []
    return [
        name.rstrip(".")
        for name in (part.strip() for part in _AUTHOR_SEPARATOR.split(author_string))
        if name
    ]


def _record_url(source_code: str, identifier: str, doi: str) -> str:
    if source_code and identifier:
        return f"https://europepmc.org/article/{source_code}/{identifier}"
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def _normalize_date(value: Any) -> str:
    text = _text(value)
    match = _ISO_DATE.match(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    match = _YEAR.match(text)
    return match.group(1) if match else ""


def _clean_html(value: Any) -> str:
    # Europe PMC returns abstracts with markup such as <h4>Background</h4>;
    # replace tags with a space so section labels stay readable.
    return _WHITESPACE.sub(" ", html.unescape(_HTML_TAG.sub(" ", _text(value)))).strip()


def _text(value: Any) -> str:
    if isinstance(value, str):
        return _WHITESPACE.sub(" ", value).strip()
    if isinstance(value, int):
        return str(value)
    return ""


def _fetch_live(config: Config, now: datetime) -> str:
    return get_text(
        SEARCH_URL,
        {
            "query": build_query(config, now),
            "format": "json",
            "resultType": "core",
            "pageSize": str(PAGE_SIZE),
            "sort": "P_PDATE_D desc",
        },
        timeout=30,
        user_agent=USER_AGENT,
        error="Europe PMC request failed",
    )


def build_query(config: Config, now: datetime) -> str:
    start, end = lookback_window(config, "europepmc", now)
    term_clause = " OR ".join(f'"{term}"' for term in search_terms(config))
    return (
        f"({term_clause}) AND (FIRST_PDATE:[{start.isoformat()} TO {end.isoformat()}]) "
        "AND (SRC:MED OR SRC:PPR)"
    )
