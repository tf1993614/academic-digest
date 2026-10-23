"""Shared source helpers: result shape, fixture reads, query terms."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from ..config import Config
from ..errors import SourceError
from ..models import Paper

# Live GETs go through proxies and CDNs that occasionally drop a TLS
# connection. A retry keeps one transient error from failing a whole source
# (and with it the day's GitHub/G6 block); fixtures never reach this code.
_HTTP_ATTEMPTS = 3
_HTTP_BACKOFF_SECONDS = 1.0


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


def _fixture_path(root: Path, relative: str) -> Path:
    path = Path(root) / relative
    if not path.is_file():
        raise SourceError(f"missing fixture: {relative}")
    return path


def read_fixture(root: Path, relative: str) -> str:
    """Read a recorded response, turning a missing file into a source failure."""

    path = _fixture_path(root, relative)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceError(f"cannot read fixture {relative}: {exc}") from exc


def read_fixture_bytes(root: Path, relative: str) -> bytes:
    """Read a recorded binary response (a PDF, for example)."""

    path = _fixture_path(root, relative)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SourceError(f"cannot read fixture {relative}: {exc}") from exc


def read_or_fetch(
    fixtures_root: Path | None, relative: str, fetch: Callable[[], str]
) -> str:
    """Read a recorded response, or call the live fetcher when none was given."""

    if fixtures_root is not None:
        return read_fixture(fixtures_root, relative)
    return fetch()


def read_or_fetch_bytes(
    fixtures_root: Path | None, relative: str, fetch: Callable[[], bytes]
) -> bytes:
    """Binary sibling of ``read_or_fetch``."""

    if fixtures_root is not None:
        return read_fixture_bytes(fixtures_root, relative)
    return fetch()


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


def lookback_window(config: Config, source: str, now: datetime) -> tuple[date, date]:
    """Inclusive publication-date window for one source."""

    days = config.lookback[source]
    return now.date() - timedelta(days=days), now.date()


def in_window(day: date | None, start: date, end: date) -> bool:
    """Whether a record date falls inside the window (unknown dates pass)."""

    return day is None or start <= day <= end


def get_text(
    url: str,
    params: Mapping[str, str],
    *,
    timeout: int,
    user_agent: str,
    error: str,
    headers: Mapping[str, str] | None = None,
) -> str:
    """GET a URL and return its body, turning network failures into source errors."""

    return _request(
        url,
        params,
        timeout=timeout,
        user_agent=user_agent,
        error=error,
        headers=headers,
    ).text


def get_bytes(
    url: str,
    params: Mapping[str, str],
    *,
    timeout: int,
    user_agent: str,
    error: str,
) -> bytes:
    """Binary sibling of ``get_text``, for PDFs and other downloads."""

    return _request(
        url,
        params,
        timeout=timeout,
        user_agent=user_agent,
        error=error,
    ).content


def _request(
    url: str,
    params: Mapping[str, str],
    *,
    timeout: int,
    user_agent: str,
    error: str,
    headers: Mapping[str, str] | None = None,
) -> Any:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - requests is a declared dependency
        raise SourceError("requests is not installed") from exc

    request_headers = {"User-Agent": user_agent}
    if headers:
        request_headers.update(headers)
    last_error: Exception | None = None
    for attempt in range(1, _HTTP_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers=request_headers,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt == _HTTP_ATTEMPTS:
                break
            time.sleep(_HTTP_BACKOFF_SECONDS * (2 ** (attempt - 1)))
            continue
        if response.status_code >= 500 or response.status_code == 429:
            if attempt < _HTTP_ATTEMPTS:
                time.sleep(_HTTP_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                continue
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise SourceError(f"{error}: {exc}") from exc
        return response
    assert last_error is not None
    raise SourceError(f"{error}: {last_error}") from last_error
