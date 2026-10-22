"""Direct tests for the ServerChan details an offline CLI run cannot see.

Fixture runs never build a URL, read a SendKey, or sleep, so endpoint selection,
key redaction, the retry/sanitize wiring, and the transport-only defaults are
pinned here instead of through the CLI seam (the one documented exception).
"""

from datetime import datetime, timezone

import pytest
import requests
import yaml

from academic_digest import push as push_module
from academic_digest.config import load_config
from academic_digest.push import (
    Message,
    SendError,
    ServerChanSender,
    endpoint_for,
    redact,
)
from academic_digest.state import PendingRow, StateStore


def _config(tmp_path):
    data = {
        "timezone": "Asia/Shanghai",
        "lookback": {"pubmed": 2},
        "topics": [
            {"name": "G1", "label": "老化", "terms": ["aging"], "max_items": 6}
        ],
        "sources": {"pubmed": True},
        "paths": {"state_db": str(tmp_path / "state.sqlite3")},
    }
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def test_push_defaults_match_the_documented_values(tmp_path):
    push = load_config(_config(tmp_path)).push

    assert push.sendkey_env == "SERVERCHAN_SENDKEY"
    assert push.channel == "serverchan"
    assert push.send_empty is True
    assert push.split_bytes == 30000
    assert push.max_bytes == 32768
    assert push.max_messages == 2
    assert push.title_max == 32
    assert push.retries == 2
    assert push.backoff_seconds == 1
    assert push.timeout == 30
    assert push.pending_days == 2


def test_endpoint_for_routes_sctp_uid_keys_to_the_user_host():
    assert (
        endpoint_for("sctp42tabc")
        == "https://42.push.ft07.com/send/sctp42tabc.send"
    )
    assert endpoint_for("sctp42t") == "https://42.push.ft07.com/send/sctp42t.send"
    assert endpoint_for("SCT42tabc") == "https://sctapi.ftqq.com/SCT42tabc.send"
    assert endpoint_for("sctpabc") == "https://sctapi.ftqq.com/sctpabc.send"


def test_redact_removes_the_key():
    assert (
        redact("https://sctapi.ftqq.com/SECRET.send", "SECRET")
        == "https://sctapi.ftqq.com/***.send"
    )
    assert redact("boom", "") == "boom"


def test_the_live_sender_sanitizes_with_its_own_key():
    sender = ServerChanSender("sctp42tSECRET", 30)

    assert sender.sanitize("failed for sctp42tSECRET") == "failed for ***"


class _LeakySender:
    """A sender whose error text contains a secret that sanitize must remove."""

    def __init__(self, secret):
        self.secret = secret

    def send(self, title, desp):
        raise SendError(f"boom {self.secret}")

    def sanitize(self, text):
        return text.replace(self.secret, "***")


def test_the_live_sender_redacts_a_request_error(monkeypatch):
    key = "sctp42tSECRET"

    def boom(*args, **kwargs):
        raise requests.RequestException(
            f"POST https://sctapi.ftqq.com/{key}.send failed"
        )

    monkeypatch.setattr(requests, "post", boom)

    with pytest.raises(SendError) as excinfo:
        ServerChanSender(key, 30).send("标题", "正文")

    message = str(excinfo.value)
    assert key not in message
    assert "***" in message


def test_a_retry_returns_only_the_sanitized_error(tmp_path):
    push = load_config(_config(tmp_path)).push

    ok, attempts, error = push_module._send_with_retries(
        _LeakySender("SECRET"),
        push,
        Message(part=1, parts=1, title="t", desp="d"),
        playback=True,
    )

    assert ok is False
    assert attempts == 3
    assert error == "boom ***"


def test_a_pending_retry_stores_only_the_sanitized_error(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        store.save_pending(
            [
                PendingRow(
                    channel="serverchan",
                    digest_date="2026-10-22",
                    part=1,
                    parts=1,
                    title="t",
                    desp="d",
                    items_json="[]",
                    created_at="2026-10-22T08:00:00+08:00",
                    attempts=0,
                    last_error="",
                )
            ]
        )
        errors: list[str] = []
        sent, pushed, failed = push_module._retry_pending(
            store,
            _LeakySender("SECRET"),
            channel="serverchan",
            now=datetime(2026, 10, 22, 8, tzinfo=timezone.utc),
            errors=errors,
        )
        row = store.pending_rows("serverchan")[0]
    finally:
        store.close()

    assert (sent, pushed, failed) == (0, 0, True)
    assert row.last_error == "boom ***"
    assert errors == ["pending 2026-10-22 part 1/1: boom ***"]
