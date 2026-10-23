"""Resolve a DOI, arXiv ID, or title to an OA full text and extract sections.

Source order follows the spec: Europe PMC OA XML, arXiv HTML/PDF, the
bioRxiv/medRxiv/Research Square preprint PDF, then Unpaywall's best OA
location. Every source failure is recorded as an attempt and the next source is
tried; when nothing yields text the result is a ``no_oa`` status rather than an
exception, because full text is an enhancement and must never block the daily
digest.

An optional ``title`` widens the resolution order for the day's must-read
papers: a DOI that is itself an arXiv DOI maps directly to its arXiv ID, while
a title is matched verbatim against the arXiv API and Europe PMC to discover a
preprint version with a different DOI or an arXiv ID. The alternate DOIs are
tried before Unpaywall and never add a new output key.

Unpaywall needs a contact email. When none is configured its attempt is
skipped, and a live lookup failure is reported without the request URL: that
URL carries ``email=...`` and must never reach the candidate or digest output.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable

from ..config import Config
from ..errors import SourceError
from ..models import normalize_arxiv_id, normalize_doi, normalize_title
from ..sources.base import (
    get_bytes,
    get_text,
    read_or_fetch,
    read_or_fetch_bytes,
)
from ..sources.rss import child, children, element_text, local_name
from .extract import extract_html, extract_pdf, extract_xml
from .models import Attempt, Extracted, FullText, FullTextError

USER_AGENT = "academic-digest/0.1 (OA full-text reader)"
EPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EPMC_FULLTEXT_URL = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
)
EPMC_ARTICLE_URL = "https://europepmc.org/articles/{pmcid}"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_HTML_URL = "https://arxiv.org/html/{arxiv_id}"
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"
UNPAYWALL_URL = "https://api.unpaywall.org/v2/{doi}"
BIORXIV_PDF_URL = "https://www.biorxiv.org/content/{doi}.full.pdf"
MEDRXIV_PDF_URL = "https://www.medrxiv.org/content/{doi}.full.pdf"
RESEARCHSQUARE_PDF_URL = (
    "https://www.researchsquare.com/article/{article}/latest.pdf"
)
ARXIV_DOI_PREFIX = "10.48550/arxiv."
TITLE_LOOKUP_RESULTS = 5

_FIXTURE_EPMC_SEARCH = "europepmc/doi-search.json"
_FIXTURE_EPMC_TITLE_SEARCH = "europepmc/title-search.json"
_FIXTURE_EPMC_FULLTEXT = "europepmc/fulltext.xml"
_FIXTURE_ARXIV_HTML = "arxiv/fulltext.html"
_FIXTURE_ARXIV_PDF = "arxiv/fulltext.pdf"
_FIXTURE_ARXIV_TITLE_SEARCH = "arxiv/title-search.atom"
_FIXTURE_UNPAYWALL = "unpaywall/location.json"

_ABS_PATH = re.compile(r"/abs/([^/?#\s]+)")
_TRAILING_PUNCTUATION = re.compile(r"[\s.。]+$")


@dataclass(frozen=True)
class PreprintServer:
    """A DOI-prefixed preprint server and the PDF URL template it exposes."""

    name: str
    doi_prefixes: tuple[str, ...]
    pdf_template: str
    article_pattern: re.Pattern[str] | None = None

    def matches(self, doi: str) -> bool:
        return any(doi.startswith(prefix) for prefix in self.doi_prefixes)

    def pdf_url(self, doi: str) -> str:
        if self.article_pattern is None:
            return self.pdf_template.format(doi=doi)
        match = self.article_pattern.search(doi)
        if not match:
            raise FullTextError(
                f"cannot derive a {self.name} article id from the DOI"
            )
        return self.pdf_template.format(article=match.group(1).lower())


# Adding a server means adding one row; lookup order is table order. bioRxiv and
# medRxiv share the 10.1101 prefix, so both are tried for the same DOI.
_PREPRINT_SERVERS = (
    PreprintServer("biorxiv", ("10.1101/",), BIORXIV_PDF_URL),
    PreprintServer("medrxiv", ("10.1101/",), MEDRXIV_PDF_URL),
    PreprintServer(
        "researchsquare",
        ("10.21203/",),
        RESEARCHSQUARE_PDF_URL,
        re.compile(r"(rs-\d+)", re.IGNORECASE),
    ),
)


def fetch(
    *,
    doi: str = "",
    arxiv_id: str = "",
    title: str = "",
    config: Config,
    fixtures_root: Path | None,
) -> FullText:
    """Look up one paper, trying every applicable source in the spec's order."""

    doi = normalize_doi(doi)
    arxiv_id = normalize_arxiv_id(arxiv_id)
    title = (title or "").strip()
    attempts: list[Attempt] = []

    # A DOI may itself name an arXiv paper; that is a free DOI→arXiv match.
    if not arxiv_id:
        arxiv_id = _arxiv_id_from_doi(doi)

    alternate_dois: list[str] = []
    if title:
        if not arxiv_id:
            arxiv_id = _arxiv_id_by_title(title, fixtures_root)
        alternate_dois = _alternate_dois_by_title(title, doi, fixtures_root)
        if not arxiv_id:
            for alternate in alternate_dois:
                derived = _arxiv_id_from_doi(alternate)
                if derived:
                    arxiv_id = derived
                    break

    if doi:
        result = _attempt(
            "europepmc", attempts, partial(_europepmc, doi, fixtures_root)
        )
        if result is not None:
            return result

    if arxiv_id:
        result = _attempt(
            "arxiv", attempts, partial(_arxiv, arxiv_id, fixtures_root)
        )
        if result is not None:
            return result

    preprint_dois = _preprint_dois(doi, alternate_dois)
    for server in _preprint_servers(preprint_dois):
        result = _attempt(
            server.name,
            attempts,
            partial(_preprint_pdfs, server, preprint_dois, fixtures_root),
        )
        if result is not None:
            return result

    unpaywall_doi = doi or (preprint_dois[0] if preprint_dois else "")
    if unpaywall_doi:
        email = config.fulltext.unpaywall_email
        if email:
            result = _attempt(
                "unpaywall",
                attempts,
                partial(_unpaywall, unpaywall_doi, email, fixtures_root),
            )
            if result is not None:
                return result

    return _no_oa(doi, arxiv_id, attempts)


def _arxiv_id_from_doi(doi: str) -> str:
    if not doi.startswith(ARXIV_DOI_PREFIX):
        return ""
    return normalize_arxiv_id(doi[len(ARXIV_DOI_PREFIX) :])


def _title_key(value: str) -> str:
    return _TRAILING_PUNCTUATION.sub("", normalize_title(value))


def _arxiv_id_by_title(title: str, fixtures_root: Path | None) -> str:
    """Exact-title arXiv lookup, used for the DOI→arXiv cross-search.

    arXiv's API has no DOI field, so the title is the bridge. Only an entry
    whose normalized title matches verbatim is accepted, so a fuzzy result
    cannot be mistaken for the paper.
    """

    try:
        text = read_or_fetch(
            fixtures_root,
            _FIXTURE_ARXIV_TITLE_SEARCH,
            partial(
                _fetch_text,
                ARXIV_API_URL,
                {
                    "search_query": f'ti:"{title}"',
                    "start": "0",
                    "max_results": str(TITLE_LOOKUP_RESULTS),
                },
                timeout=30,
                error="arXiv title lookup failed",
            ),
        )
    except (SourceError, OSError):
        return ""

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ""
    if local_name(root.tag) != "feed":
        return ""
    key = _title_key(title)
    for entry in children(root, "entry"):
        entry_title = element_text(child(entry, "title"))
        if not entry_title or _title_key(entry_title) != key:
            continue
        match = _ABS_PATH.search(element_text(child(entry, "id")))
        if match:
            return normalize_arxiv_id(match.group(1))
    return ""


def _alternate_dois_by_title(
    title: str, current_doi: str, fixtures_root: Path | None
) -> list[str]:
    """DOIs of title-matching Europe PMC records, best preprint versions first."""

    try:
        text = read_or_fetch(
            fixtures_root,
            _FIXTURE_EPMC_TITLE_SEARCH,
            partial(
                _fetch_text,
                EPMC_SEARCH_URL,
                {
                    "query": f'TITLE:"{title}"',
                    "format": "json",
                    "resultType": "core",
                    "pageSize": "10",
                },
                timeout=30,
                error="Europe PMC title lookup failed",
            ),
        )
    except (SourceError, OSError):
        return []

    try:
        payload = _json_object(text, "Europe PMC title search")
    except FullTextError:
        return []
    result_list = payload.get("resultList")
    records = result_list.get("result") if isinstance(result_list, dict) else None
    if not isinstance(records, list):
        return []

    key = _title_key(title)
    found: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if _title_key(str(record.get("title") or "")) != key:
            continue
        value = normalize_doi(str(record.get("doi") or ""))
        if value and value != current_doi and value not in found:
            found.append(value)
    return found


def _preprint_dois(doi: str, alternate_dois: list[str]) -> list[str]:
    candidates: list[str] = []
    for value in ([doi] if doi else []) + alternate_dois:
        if value and value not in candidates and _is_preprint_doi(value):
            candidates.append(value)
    return candidates


def _is_preprint_doi(doi: str) -> bool:
    return any(server.matches(doi) for server in _PREPRINT_SERVERS)


def _preprint_servers(dois: list[str]) -> list[PreprintServer]:
    return [
        server
        for server in _PREPRINT_SERVERS
        if any(server.matches(doi) for doi in dois)
    ]


def _preprint_pdfs(
    server: PreprintServer, dois: list[str], fixtures_root: Path | None
) -> FullText:
    """Try one server for every matching DOI and keep one attempt per server."""

    problems: list[str] = []
    for doi in dois:
        if not server.matches(doi):
            continue
        try:
            return _preprint_pdf(doi, server, fixtures_root)
        except (FullTextError, SourceError, OSError) as exc:
            problems.append(f"{doi}: {exc}")
    raise FullTextError("; ".join(problems) or f"no {server.name} DOI to try")


def _attempt(
    source: str,
    attempts: list[Attempt],
    operation: Callable[[], FullText],
) -> FullText | None:
    try:
        result = operation()
    except (FullTextError, SourceError, OSError) as exc:
        attempts.append(Attempt(source=source, status="miss", reason=str(exc)))
        return None
    attempts.append(Attempt(source=source, status="ok", url=result.url))
    result.attempts = list(attempts)
    return result


def _no_oa(doi: str, arxiv_id: str, attempts: list[Attempt]) -> FullText:
    details = "; ".join(
        f"{attempt.source}: {attempt.reason}"
        for attempt in attempts
        if attempt.reason
    )
    reason = "no open-access full text available"
    if details:
        reason = f"{reason} ({details})"
    return FullText(
        status="no_oa",
        doi=doi,
        arxiv_id=arxiv_id,
        attempts=list(attempts),
        reason=reason,
    )


def _oa(
    *,
    source: str,
    url: str,
    format: str,
    extracted: Extracted,
    doi: str = "",
    arxiv_id: str = "",
) -> FullText:
    return FullText(
        status="oa",
        doi=doi,
        arxiv_id=arxiv_id,
        source=source,
        format=format,
        url=url,
        extracted=extracted,
    )


def _require_sections(extracted: Extracted, label: str) -> Extracted:
    if extracted.empty:
        raise FullTextError(f"{label} has no methods/results/limitations sections")
    return extracted


def _europepmc(doi: str, fixtures_root: Path | None) -> FullText:
    search_text = read_or_fetch(
        fixtures_root,
        _FIXTURE_EPMC_SEARCH,
        partial(
            _fetch_text,
            EPMC_SEARCH_URL,
            {
                "query": f'DOI:"{doi}"',
                "format": "json",
                "resultType": "core",
                # A DOI query can still return a neighbouring record; ask for
                # a small page so the DOI guard can see and skip it.
                "pageSize": "10",
            },
            timeout=30,
            error="Europe PMC full-text lookup failed",
        ),
    )
    pmcid = _epmc_pmcid(search_text, doi)
    xml_text = read_or_fetch(
        fixtures_root,
        _FIXTURE_EPMC_FULLTEXT,
        partial(
            _fetch_text,
            EPMC_FULLTEXT_URL.format(pmcid=pmcid),
            {},
            timeout=60,
            error="Europe PMC full-text download failed",
        ),
    )
    extracted = _require_sections(extract_xml(xml_text), "Europe PMC OA XML")
    return _oa(
        source="europepmc",
        format="xml",
        url=EPMC_ARTICLE_URL.format(pmcid=pmcid),
        extracted=extracted,
        doi=doi,
    )


def _json_object(text: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FullTextError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise FullTextError(f"invalid {label} JSON: expected an object")
    return payload


def _epmc_pmcid(text: str, doi: str) -> str:
    payload = _json_object(text, "Europe PMC")
    result_list = payload.get("resultList")
    records = result_list.get("result") if isinstance(result_list, dict) else None
    if not isinstance(records, list):
        raise FullTextError("invalid Europe PMC JSON: missing resultList.result")

    for record in records:
        if not isinstance(record, dict):
            continue
        record_doi = normalize_doi(str(record.get("doi") or ""))
        if record_doi != doi:
            # A fuzzy DOI query can return a neighbouring record (or a record
            # with no DOI at all); taking its PMC id would label another
            # paper's sections with this DOI.
            continue
        pmcid = str(record.get("pmcid") or "").strip()
        if not pmcid:
            identifier = str(record.get("id") or "").strip()
            source = str(record.get("source") or "").strip().upper()
            if source == "PMC" and identifier.upper().startswith("PMC"):
                pmcid = identifier
        if pmcid:
            return pmcid
    raise FullTextError("Europe PMC has no PMC full-text record for this DOI")


def _arxiv(arxiv_id: str, fixtures_root: Path | None) -> FullText:
    problems: list[str] = []
    html_url = ARXIV_HTML_URL.format(arxiv_id=arxiv_id)
    try:
        html_text = read_or_fetch(
            fixtures_root,
            _FIXTURE_ARXIV_HTML,
            partial(
                _fetch_text,
                html_url,
                {},
                timeout=60,
                error="arXiv HTML download failed",
            ),
        )
        extracted = extract_html(html_text)
        if not extracted.empty:
            return _oa(
                source="arxiv",
                format="html",
                url=html_url,
                extracted=extracted,
                arxiv_id=arxiv_id,
            )
        problems.append("HTML has no methods/results/limitations sections")
    except (FullTextError, SourceError, OSError) as exc:
        problems.append(f"HTML: {exc}")

    pdf_url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    try:
        data = read_or_fetch_bytes(
            fixtures_root,
            _FIXTURE_ARXIV_PDF,
            partial(
                _fetch_bytes,
                pdf_url,
                timeout=90,
                error="arXiv PDF download failed",
            ),
        )
        extracted = extract_pdf(data)
        if not extracted.empty:
            return _oa(
                source="arxiv",
                format="pdf",
                url=pdf_url,
                extracted=extracted,
                arxiv_id=arxiv_id,
            )
        problems.append("PDF has no methods/results/limitations sections")
    except (FullTextError, SourceError, OSError) as exc:
        problems.append(f"PDF: {exc}")

    raise FullTextError("; ".join(problems))


def _preprint_pdf(
    doi: str, server: PreprintServer, fixtures_root: Path | None
) -> FullText:
    url = server.pdf_url(doi)
    data = read_or_fetch_bytes(
        fixtures_root,
        f"{server.name}/fulltext.pdf",
        partial(
            _fetch_bytes,
            url,
            timeout=90,
            error=f"{server.name} PDF download failed",
        ),
    )
    extracted = _require_sections(extract_pdf(data), f"{server.name} PDF")
    return _oa(
        source=server.name,
        format="pdf",
        url=url,
        extracted=extracted,
        doi=doi,
    )


def _unpaywall(doi: str, email: str, fixtures_root: Path | None) -> FullText:
    try:
        location_text = read_or_fetch(
            fixtures_root,
            _FIXTURE_UNPAYWALL,
            partial(
                _fetch_text,
                UNPAYWALL_URL.format(doi=doi),
                {"email": email},
                timeout=30,
                error="Unpaywall lookup failed",
                user_agent=f"{USER_AGENT} (mailto:{email})",
            ),
        )
    except SourceError as exc:
        if fixtures_root is not None:
            raise
        # requests puts the full URL, including email=..., in its exception
        # text; keep it out of attempts and the digest's no_oa reason.
        raise FullTextError(
            "Unpaywall lookup failed; request details withheld because they "
            "contain the contact email"
        ) from exc

    locations = _oa_locations(location_text)
    problems: list[str] = []

    for url, expected in locations:
        relative = (
            "unpaywall/fulltext.pdf"
            if expected == "pdf"
            else "unpaywall/fulltext.html"
        )
        try:
            data = read_or_fetch_bytes(
                fixtures_root,
                relative,
                partial(
                    _fetch_bytes,
                    url,
                    timeout=90,
                    error="OA full-text download failed",
                ),
            )
        except (SourceError, OSError) as exc:
            problems.append(f"{url}: {exc}")
            continue

        try:
            if data.lstrip().startswith(b"%PDF"):
                extracted = _require_sections(extract_pdf(data), "OA full text")
                actual_format = "pdf"
            else:
                extracted = _require_sections(
                    extract_html(data.decode("utf-8", errors="replace")),
                    "OA full text",
                )
                actual_format = "html"
        except FullTextError as exc:
            problems.append(f"{url}: {exc}")
            continue

        return _oa(
            source="unpaywall",
            format=actual_format,
            url=url,
            extracted=extracted,
            doi=doi,
        )

    raise FullTextError("; ".join(problems) or "Unpaywall has no usable OA location")


def _oa_locations(text: str) -> list[tuple[str, str]]:
    payload = _json_object(text, "Unpaywall")
    if not payload.get("is_oa"):
        raise FullTextError("Unpaywall reports no open-access version")

    locations: list[dict[str, Any]] = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    others = payload.get("oa_locations")
    if isinstance(others, list):
        locations.extend(item for item in others if isinstance(item, dict))

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for location in locations:
        pdf_url = location.get("url_for_pdf")
        page_url = location.get("url")
        if isinstance(pdf_url, str) and pdf_url.strip():
            _add_candidate(candidates, seen, pdf_url.strip(), "pdf")
        if isinstance(page_url, str) and page_url.strip():
            _add_candidate(
                candidates,
                seen,
                page_url.strip(),
                _expected_format(page_url),
            )
    if not candidates:
        raise FullTextError("Unpaywall reports OA but no location URL")
    return candidates


def _add_candidate(
    candidates: list[tuple[str, str]],
    seen: set[str],
    url: str,
    expected: str,
) -> None:
    if url in seen:
        return
    seen.add(url)
    candidates.append((url, expected))


def _expected_format(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    return "pdf" if path.endswith(".pdf") or "/pdf/" in path else "html"


def _fetch_text(
    url: str,
    params: dict[str, str],
    *,
    timeout: int,
    error: str,
    user_agent: str = USER_AGENT,
) -> str:
    """Pin the full-text User-Agent while letting each caller set timeout/error."""

    return get_text(
        url,
        params,
        timeout=timeout,
        user_agent=user_agent,
        error=error,
    )


def _fetch_bytes(url: str, *, timeout: int, error: str) -> bytes:
    """Binary sibling of ``_fetch_text``; pins the same User-Agent."""

    return get_bytes(
        url,
        {},
        timeout=timeout,
        user_agent=USER_AGENT,
        error=error,
    )
