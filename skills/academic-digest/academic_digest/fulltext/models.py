"""The full-text result contract shared by extraction and the CLI.

A lookup never signals "no OA" with an exception: the result carries a
``no_oa`` status and the attempts that failed, so the daily digest can fall
back to the abstract and say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AttemptStatus = Literal["ok", "miss"]
FullTextStatus = Literal["oa", "no_oa"]


class FullTextError(Exception):
    """A full text could not be fetched or parsed; the caller records a miss."""


@dataclass
class Attempt:
    """One source tried during a lookup, kept for the digest footer and audits."""

    source: str
    status: AttemptStatus
    reason: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {"source": self.source, "status": self.status}
        if self.reason:
            payload["reason"] = self.reason
        if self.url:
            payload["url"] = self.url
        return payload


@dataclass
class Extracted:
    """Methods, results, and limitations paragraphs taken from the full text."""

    methods: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.methods or self.results or self.limitations)

    @property
    def length(self) -> int:
        return sum(
            len(paragraph)
            for paragraph in [*self.methods, *self.results, *self.limitations]
        )


@dataclass
class FullText:
    """One lookup result, serialized as the full-text JSON contract."""

    status: FullTextStatus
    doi: str = ""
    arxiv_id: str = ""
    source: str = ""
    format: str = ""
    url: str = ""
    extracted: Extracted = field(default_factory=Extracted)
    reason: str = ""
    attempts: list[Attempt] = field(default_factory=list)

    def summary(self) -> str:
        """One human-readable line for the CLI; never includes request secrets."""

        if self.status != "oa":
            return self.reason
        return (
            f"oa from {self.source} ({self.format}): "
            f"{len(self.extracted.methods)} methods, "
            f"{len(self.extracted.results)} results, "
            f"{len(self.extracted.limitations)} limitations, "
            f"{self.extracted.length} chars"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "oa": self.status == "oa",
            "source": self.source,
            "format": self.format,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "length": self.extracted.length,
            "methods": self.extracted.methods,
            "results": self.extracted.results,
            "limitations": self.extracted.limitations,
            "reason": self.reason,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }
