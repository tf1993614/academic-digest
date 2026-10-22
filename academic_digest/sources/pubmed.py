"""PubMed adapter: XML ``efetch`` parsing plus a recorded-fixture mode.

The spec is explicit that PubMed abstracts must come from XML; the JSON mode
silently degrades abstracts to plain text. Both live and fixture retrieval feed
the same parser.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

from ..config import Config
from ..errors import ConfigError, SourceError
from ..models import Paper, normalize_doi, paper_id
from .base import SourceResult

NAME = "pubmed"
FIXTURE_SEARCH = "pubmed/esearch.xml"
FIXTURE_FETCH = "pubmed/efetch.xml"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EINFO_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi"
USER_AGENT = "academic-digest/0.1 (PubMed collector)"

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_WHITESPACE = re.compile(r"\s+")


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> SourceResult:
    try:
        if fixtures_root is not None:
            xml = _read_fixture(fixtures_root, FIXTURE_FETCH)
        else:
            xml = _fetch_live(config, now)
        papers = parse_articles(xml)
    except (SourceError, OSError) as exc:
        return SourceResult.failed(NAME, str(exc))
    return SourceResult.ok(NAME, papers)


def check_fixture(root: Path) -> str:
    """Validate the recorded PubMed search + fetch pair for ``doctor``."""

    search_xml = _read_fixture(root, FIXTURE_SEARCH)
    fetch_xml = _read_fixture(root, FIXTURE_FETCH)
    try:
        search_root = ET.fromstring(search_xml)
    except ET.ParseError as exc:
        raise SourceError(f"invalid {FIXTURE_SEARCH}: {exc}") from exc
    count_text = _text(search_root.find("Count"))
    try:
        search_count = int(count_text) if count_text else 0
    except ValueError as exc:
        raise SourceError(f"invalid {FIXTURE_SEARCH}: Count is not a number") from exc
    papers = parse_articles(fetch_xml)
    return f"{FIXTURE_SEARCH} + {FIXTURE_FETCH}; search count {search_count}, {len(papers)} records"


def check_network() -> str:
    """Make one lightweight request so doctor can diagnose connectivity."""

    try:
        import requests
    except ImportError as exc:  # pragma: no cover - requests is a declared dependency
        raise SourceError("requests is not installed") from exc

    try:
        response = requests.get(
            EINFO_URL,
            params={"db": "pubmed", "retmode": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:  # requests raises several unrelated subclasses
        raise SourceError(f"cannot reach PubMed E-utilities: {exc}") from exc
    return "PubMed E-utilities reachable"


def parse_articles(xml_text: str) -> list[Paper]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SourceError(f"invalid PubMed XML: {exc}") from exc

    if _local(root.tag) == "PubmedArticle":
        articles = [root]
    else:
        articles = [el for el in root.iter() if _local(el.tag) == "PubmedArticle"]

    papers: list[Paper] = []
    for article in articles:
        paper = _parse_article(article)
        if paper is not None:
            papers.append(paper)
    return papers


def _parse_article(article: ET.Element) -> Paper | None:
    citation = _child(article, "MedlineCitation")
    if citation is None:
        return None
    pmid = _text(_child(citation, "PMID"))
    body = _child(citation, "Article")
    if body is None:
        return None

    title = _element_text(_child(body, "ArticleTitle"))
    if not title:
        return None

    abstract_parts: list[str] = []
    abstract_node = _child(body, "Abstract")
    if abstract_node is not None:
        for part in _children(abstract_node, "AbstractText"):
            text = _element_text(part)
            if not text:
                continue
            label = (part.get("Label") or "").strip()
            abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(abstract_parts).strip()

    journal = _child(body, "Journal")
    venue = _element_text(_child(journal, "Title")) if journal is not None else ""

    authors: list[str] = []
    author_list = _child(body, "AuthorList")
    if author_list is not None:
        for author in _children(author_list, "Author"):
            collective = _element_text(_child(author, "CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            fore = _element_text(_child(author, "ForeName")) or _element_text(
                _child(author, "Initials")
            )
            last = _element_text(_child(author, "LastName"))
            name = " ".join(part for part in (fore, last) if part)
            if name:
                authors.append(name)

    date = _publication_date(body)
    doi = _doi(article, body)
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

    return Paper(
        id=paper_id(doi=doi, pmid=pmid, title=title, year=date[:4]),
        source=NAME,
        title=title,
        abstract=abstract,
        authors=authors,
        venue=venue,
        date=date,
        doi=doi,
        pmid=pmid,
        url=url,
        abstract_missing=not bool(abstract),
    )


def _publication_date(body: ET.Element) -> str:
    for node in _children(body, "ArticleDate"):
        parsed = _date_parts(node)
        if parsed:
            return parsed
    journal = _child(body, "Journal")
    issue = _child(journal, "JournalIssue") if journal is not None else None
    pub_date = _child(issue, "PubDate") if issue is not None else None
    if pub_date is not None:
        parsed = _date_parts(pub_date)
        if parsed:
            return parsed
        medline_date = _text(_child(pub_date, "MedlineDate"))
        match = re.search(r"\b(\d{4})\b", medline_date)
        if match:
            return match.group(1)
    return ""


def _date_parts(node: ET.Element) -> str:
    year = _text(_child(node, "Year"))
    if not year.isdigit():
        return ""
    month = _month(_text(_child(node, "Month")))
    day = _text(_child(node, "Day"))
    if month and day and day.isdigit():
        return f"{int(year):04d}-{month:02d}-{int(day):02d}"
    if month:
        return f"{int(year):04d}-{month:02d}"
    return f"{int(year):04d}"


def _month(value: str) -> int | None:
    if not value:
        return None
    if value.isdigit():
        number = int(value)
        return number if 1 <= number <= 12 else None
    return _MONTHS.get(value.strip().lower()[:3])


def _doi(article: ET.Element, body: ET.Element) -> str:
    pubmed_data = _child(article, "PubmedData")
    article_ids = _child(pubmed_data, "ArticleIdList") if pubmed_data is not None else None
    if article_ids is not None:
        for node in _children(article_ids, "ArticleId"):
            if (node.get("IdType") or "").lower() == "doi":
                value = normalize_doi(_element_text(node))
                if value:
                    return value
    for node in _children(body, "ELocationID"):
        if (node.get("EIdType") or "").lower() == "doi":
            value = normalize_doi(_element_text(node))
            if value:
                return value
    return ""


def _read_fixture(root: Path, relative: str) -> str:
    path = Path(root) / relative
    if not path.is_file():
        raise SourceError(f"missing fixture: {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceError(f"cannot read fixture {relative}: {exc}") from exc


def _fetch_live(config: Config, now: datetime) -> str:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - requests is a declared dependency
        raise SourceError("requests is not installed") from exc

    lookback = config.lookback.get("pubmed", 2)
    start_date = now.date() - timedelta(days=lookback)
    params = {
        "db": "pubmed",
        "term": build_query(config),
        "datetype": "edat",
        "mindate": start_date.strftime("%Y/%m/%d"),
        "maxdate": now.date().strftime("%Y/%m/%d"),
        "retmode": "json",
        "retmax": "100",
    }
    try:
        search = requests.get(
            ESEARCH_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
        )
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return "<PubmedArticleSet></PubmedArticleSet>"
        fetch = requests.get(
            EFETCH_URL,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        fetch.raise_for_status()
    except Exception as exc:  # requests raises several unrelated subclasses
        raise SourceError(f"PubMed request failed: {exc}") from exc
    return fetch.text


def build_query(config: Config) -> str:
    clauses: list[str] = []
    seen: set[str] = set()
    for topic in config.topics:
        for term in topic.terms:
            if term in seen:
                continue
            seen.add(term)
            clauses.append(f'"{term}"[tiab]')
    if not clauses:
        raise ConfigError("topics", "no searchable terms")
    return " OR ".join(clauses)


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return _WHITESPACE.sub(" ", node.text).strip()


def _element_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return _WHITESPACE.sub(" ", "".join(node.itertext())).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    for child in node:
        if _local(child.tag) == name:
            return child
    return None


def _children(node: ET.Element | None, name: str) -> list[ET.Element]:
    if node is None:
        return []
    return [child for child in node if _local(child.tag) == name]
