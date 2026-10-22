"""Shared source result shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
