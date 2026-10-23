"""Transport tests for the shared source GET helper.

Fixture runs read recorded files and never reach ``_request``, so the retry
loop cannot be exercised at the CLI seam. Like ``test_push_transport.py`` this
is a deliberate transport-level exception: every HTTP call is faked, no
network is touched, and no sleeping happens.
"""

from __future__ import annotations

import pytest
import requests

from academic_digest.errors import SourceError
from academic_digest.sources import base


class _Response:
    def __init__(self, status_code: int = 200, text: str = "body") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _call(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(base.time, "sleep", lambda seconds: None)
    return base.get_text(
        "https://example.test/api",
        {"q": "x"},
        timeout=1,
        user_agent="test-agent",
        error="request failed",
    )


def test_get_text_retries_a_dropped_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_get(*args: object, **kwargs: object) -> _Response:
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectionError("connection reset")
        return _Response(text="recovered")

    monkeypatch.setattr(requests, "get", fake_get)
    assert _call(monkeypatch) == "recovered"
    assert len(calls) == 3


def test_get_text_gives_up_after_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_get(*args: object, **kwargs: object) -> _Response:
        calls.append(1)
        raise requests.ConnectionError("connection reset")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(SourceError, match="request failed"):
        _call(monkeypatch)
    assert len(calls) == 3


def test_get_text_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = [429, 503, 200]

    def fake_get(*args: object, **kwargs: object) -> _Response:
        return _Response(status_code=statuses.pop(0))

    monkeypatch.setattr(requests, "get", fake_get)
    assert _call(monkeypatch) == "body"
    assert statuses == []


def test_get_text_does_not_retry_a_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_get(*args: object, **kwargs: object) -> _Response:
        calls.append(1)
        return _Response(status_code=404)

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(SourceError, match="404"):
        _call(monkeypatch)
    assert len(calls) == 1
