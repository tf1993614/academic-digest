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


def normalize_doi(value: str) -> str:
    return _DOI_PREFIX.sub("", value.strip()).strip().lower()


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
        stripped = re.sub(r"v\d+$", "", arxiv_id.strip())
        return f"arxiv:{stripped}"
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
            "score": self.score,
            "is_preprint": self.is_preprint,
            "oa_url": self.oa_url,
        }
