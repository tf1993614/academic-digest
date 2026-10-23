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


def _call(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sleep_calls: list[float] | None = None,
) -> str:
    if sleep_calls is None:
        monkeypatch.setattr(base, "_sleep", lambda seconds: None)
    else:
        monkeypatch.setattr(base, "_sleep", sleep_calls.append)
    return base.get_text(
        "https://example.test/api",
        {"q": "x"},
        timeout=1,
        user_agent="test-agent",
        error="request failed",
    )


def _fake_get(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[object],
) -> list[int]:
    """Patch ``requests.get`` with a sequence of responses or exceptions."""

    calls: list[int] = []

    def fake_get(*args: object, **kwargs: object) -> _Response:
        calls.append(1)
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def test_get_text_retries_a_dropped_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_get(
        monkeypatch,
        [
            requests.ConnectionError("connection reset"),
            requests.ConnectionError("connection reset"),
            _Response(text="recovered"),
        ],
    )
    assert _call(monkeypatch) == "recovered"
    assert len(calls) == 3


def test_get_text_uses_one_and_two_second_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []
    _fake_get(
        monkeypatch,
        [
            requests.ConnectionError("connection reset"),
            requests.ConnectionError("connection reset"),
            _Response(),
        ],
    )
    assert _call(monkeypatch, sleep_calls=sleep_calls) == "body"
    assert sleep_calls == [1.0, 2.0]


def test_get_text_gives_up_after_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_get(
        monkeypatch,
        [
            requests.ConnectionError("connection reset"),
            requests.ConnectionError("connection reset"),
            requests.ConnectionError("connection reset"),
        ],
    )
    with pytest.raises(SourceError, match="request failed"):
        _call(monkeypatch)
    assert len(calls) == 3


def test_get_text_does_not_retry_a_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_get(monkeypatch, [requests.ReadTimeout("read timed out")])
    with pytest.raises(SourceError, match="read timed out"):
        _call(monkeypatch)
    assert len(calls) == 1


def test_get_text_waits_two_seconds_before_retrying_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []
    calls = _fake_get(
        monkeypatch,
        [_Response(status_code=429), _Response(status_code=429), _Response()],
    )
    assert _call(monkeypatch, sleep_calls=sleep_calls) == "body"
    assert len(calls) == 3
    assert sleep_calls == [2.0, 2.0]


def test_get_text_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_get(
        monkeypatch,
        [_Response(status_code=429), _Response(status_code=503), _Response()],
    )
    assert _call(monkeypatch) == "body"
    assert len(calls) == 3


def test_get_text_wraps_an_unexpected_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_get(monkeypatch, [ValueError("bad URL")])
    with pytest.raises(SourceError, match="bad URL"):
        _call(monkeypatch)
    assert len(calls) == 1


def test_get_text_does_not_retry_a_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_get(monkeypatch, [_Response(status_code=404)])
    with pytest.raises(SourceError, match="404"):
        _call(monkeypatch)
    assert len(calls) == 1
