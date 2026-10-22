"""Paper records and the candidate-pool contract.

This module is deliberately free of retrieval logic: sources produce ``Paper``
objects, ``collect`` enriches and ranks them, and the JSON writer serializes
them. Keeping the contract in one place lets later sources (Europe PMC,
arXiv, ...) target the same shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any

_WHITESPACE = re.compile(r"\s+")
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_ARXIV_VERSION = re.compile(r"v\d+$")


def normalize_doi(value: str) -> str:
    return _DOI_PREFIX.sub("", value.strip()).strip().lower()


def normalize_arxiv_id(value: str) -> str:
    return _ARXIV_VERSION.sub("", value.strip())


def normalize_title(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


def paper_id(
    *,
    doi: str = "",
    pmid: str = "",
    arxiv_id: str = "",
    title: str = "",
    year: str = "",
) -> str:
    """Return the stable dedupe key in the spec's priority order.

    DOI > PMID > arXiv ID > normalized-title-plus-year hash.
    """

    if doi:
        return f"doi:{normalize_doi(doi)}"
    if pmid:
        return f"pmid:{pmid.strip()}"
    if arxiv_id:
        return f"arxiv:{normalize_arxiv_id(arxiv_id)}"
    digest = sha1(f"{normalize_title(title)}|{year}".encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}"


@dataclass
class Paper:
    """One normalized paper, before or after keyword enrichment."""

    id: str
    source: str
    title: str
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    date: str = ""
    doi: str = ""
    pmid: str = ""
    arxiv_id: str = ""
    url: str = ""
    is_preprint: bool = False
    oa_url: str | None = None
    tags: list[str] = field(default_factory=list)
    group: str = ""
    # Relevance comes from keyword matching; score adds the freshness bonus.
    relevance: int = 0
    score: int = 0
    abstract_missing: bool = False

    def to_dict(self) -> dict[str, Any]:
        """The candidate-pool entry. Keep the key order stable for humans."""

        return {
            "id": self.id,
            "group": self.group,
            "source": self.source,
            "title": self.title,
            "authors": self.authors,
            "venue": self.venue,
            "date": self.date,
            "doi": self.doi,
            "pmid": self.pmid,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "abstract": self.abstract,
            "abstract_missing": self.abstract_missing,
            "tags": self.tags,
            "relevance": self.relevance,
            "score": self.score,
            "is_preprint": self.is_preprint,
            "oa_url": self.oa_url,
        }


@dataclass
class Repo:
    """One GitHub repository candidate for the new, active, or G6 block.

    ``positioning`` is the one-line what-it-is summary (description, or the
    README's opening paragraph when the description is empty), and ``why``
    names the query and matched keywords, so the digest never has to guess why
    a repository was selected.
    """

    full_name: str
    url: str
    description: str
    positioning: str
    why: str
    stars: int
    language: str
    created_at: str
    pushed_at: str
    topics: list[str]
    group: str
    query: str
    tags: list[str]
    relevance: int
    score: int
    readme_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "url": self.url,
            "description": self.description,
            "positioning": self.positioning,
            "why": self.why,
            "stars": self.stars,
            "language": self.language,
            "created_at": self.created_at,
            "pushed_at": self.pushed_at,
            "topics": self.topics,
            "group": self.group,
            "query": self.query,
            "tags": self.tags,
            "relevance": self.relevance,
            "score": self.score,
            "readme_url": self.readme_url,
        }
