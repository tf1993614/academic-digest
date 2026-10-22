"""Shared source helpers: result shape, fixture reads, query terms."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Config
from ..errors import SourceError
from ..models import Paper


@dataclass
class SourceResult:
    name: str
    status: str = "ok"
    papers: list[Paper] = field(default_factory=list)
    count: int = 0
    error: str = ""

    @classmethod
    def ok(cls, name: str, papers: list[Paper]) -> "SourceResult":
        return cls(name=name, status="ok", papers=papers, count=len(papers))

    @classmethod
    def failed(cls, name: str, error: str) -> "SourceResult":
        return cls(name=name, status="failed", error=error)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status, "count": self.count}
        if self.error:
            payload["error"] = self.error
        return payload


def read_fixture(root: Path, relative: str) -> str:
    """Read a recorded response, turning a missing file into a source failure."""

    path = Path(root) / relative
    if not path.is_file():
        raise SourceError(f"missing fixture: {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceError(f"cannot read fixture {relative}: {exc}") from exc


def search_terms(config: Config) -> list[str]:
    """All configured terms once, in configuration order.

    Sources wrap these in their own query syntax; keeping the ordering stable
    makes recorded requests reproducible.
    """

    seen: set[str] = set()
    terms: list[str] = []
    for topic in config.topics:
        for term in topic.terms:
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms
