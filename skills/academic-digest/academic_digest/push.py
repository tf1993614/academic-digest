"""Server酱 delivery: payload construction, splitting, retries, and accounting.

``push`` is the last step of the daily pipeline. It re-validates the digest
contract with :mod:`academic_digest.digest`, turns ``digest.md`` into one
ServerChan message (or at most ``push.max_messages`` section-aligned messages),
and records what happened in the state database.

The payload is split on top-level ``## `` section boundaries only; a paper is
never cut in half. Fixture runs replay recorded ServerChan responses, so tests
stay offline and deterministic.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

import requests

from .config import Config, PushConfig
from .models import SelectedItem
from .state import PendingRow, StateStore

TITLE_PREFIX = "学术速递 · "
EMPTY_NOTICE = "今日没有匹配的检索条目"
UNPUSHED_PREFIX = "未推送数："
PAYLOAD_SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2

_ENDPOINT_UID = re.compile(r"^sctp(\d+)t")


class PushFailure(Exception):
    """A push stopped before or during delivery; ``exit_code`` is the CLI code."""

    def __init__(self, message: str, exit_code: int = EXIT_FAILURE) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class SendError(Exception):
    """One ServerChan delivery attempt failed."""


@dataclass(frozen=True)
class DigestInputs:
    """The three validated digest files, reduced to what the push needs."""

    digest_date: str
    candidate_count: int
    selected: tuple[SelectedItem, ...]
    empty: bool
    body: str


@dataclass(frozen=True)
class Message:
    """One ServerChan message: order, total, title, and Markdown body."""

    part: int
    parts: int
    title: str
    desp: str


@dataclass(frozen=True)
class PlannedMessages:
    """What one logical digest will send; ``skipped_empty`` means send nothing."""

    messages: tuple[Message, ...]
    skipped_empty: bool = False


@dataclass(frozen=True)
class Blocks:
    """``digest.md`` split at top-level section boundaries."""

    prefix: tuple[str, ...]
    sections: tuple[tuple[str, tuple[str, ...]], ...]
    footer: tuple[str, ...]


def load_inputs(
    candidates_path: Path,
    selection_path: Path,
    digest_path: Path,
    *,
    github_items: int,
) -> DigestInputs:
    """Read the validated files; the caller has already run ``digest check``.

    ``github_items`` comes from that same check so the empty-digest rule has
    one implementation rather than a second copy here.
    """

    candidates = _read_json(candidates_path)
    selection = _read_json(selection_path)
    digest_text = Path(digest_path).read_text(encoding="utf-8")

    papers = selection.get("papers")
    if not isinstance(papers, list):
        papers = []
    selected: list[SelectedItem] = []
    for paper in papers:
        if isinstance(paper, Mapping):
            selected.append(
                SelectedItem(
                    item_id=str(paper.get("id", "")),
                    topic=str(paper.get("group", "")),
                )
            )

    return DigestInputs(
        digest_date=str(candidates.get("date", "")),
        candidate_count=_int_or_zero(candidates.get("candidate_count")),
        selected=tuple(selected),
        empty=not selected and github_items == 0,
        body=_digest_body(digest_text),
    )


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, Mapping) else {}


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _digest_body(text: str) -> str:
    """``digest.md`` without its title line, with LF newlines."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return ""
    body_lines = lines[first + 1 :]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    return "\n".join(body_lines).rstrip()


def split_blocks(body: str) -> Blocks:
    """Split a digest body at ``## `` sections and its footer separator."""

    lines = body.split("\n")
    footer_index = next(
        (index for index in range(len(lines) - 1, -1, -1) if lines[index].strip() == "---"),
        None,
    )
    if footer_index is None:
        raise PushFailure("digest body has no footer separator")
    starts = [
        index for index in range(footer_index) if lines[index].startswith("## ")
    ]
    prefix_end = starts[0] if starts else footer_index
    sections: list[tuple[str, tuple[str, ...]]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else footer_index
        name = lines[start][3:].strip()
        sections.append((name, tuple(lines[start:end])))
    return Blocks(
        prefix=tuple(lines[:prefix_end]),
        sections=tuple(sections),
        footer=tuple(lines[footer_index:]),
    )


def plan_messages(
    inputs: DigestInputs,
    push: PushConfig,
    *,
    pending_count: int = 0,
    dry_run: bool = False,
) -> PlannedMessages:
    """Build the messages for one digest; empty digests may be skipped."""

    if inputs.empty and not push.send_empty:
        return PlannedMessages(messages=(), skipped_empty=True)

    title = _title_for(inputs.digest_date, push)
    blocks = split_blocks(inputs.body)
    pending = 0 if dry_run else pending_count
    desp = _render(blocks, notice=inputs.empty, pending=pending)
    if _bytes(desp) <= push.split_bytes:
        return PlannedMessages(
            messages=(Message(part=1, parts=1, title=title, desp=desp),)
        )
    return PlannedMessages(
        messages=_split(
            blocks, push, title, notice=inputs.empty, pending=pending
        )
    )


def payload(plan: PlannedMessages) -> dict[str, Any]:
    """The fixed dry-run JSON shape."""

    if plan.skipped_empty:
        return {
            "schema_version": PAYLOAD_SCHEMA_VERSION,
            "messages": [],
            "skipped": "empty",
        }
    return {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "messages": [
            {
                "part": message.part,
                "parts": message.parts,
                "title": message.title,
                "desp": message.desp,
            }
            for message in plan.messages
        ],
    }


def _render(blocks: Blocks, *, notice: bool, pending: int) -> str:
    """The whole body: preface, notice (empty digest), sections, footer."""

    lines = _prefix_lines(blocks, notice=notice)
    for _, section_lines in blocks.sections:
        lines.extend(section_lines)
    lines.extend(_footer_lines(blocks, pending=pending))
    return _clean(lines)


def _prefix_lines(blocks: Blocks, *, notice: bool) -> list[str]:
    lines = list(blocks.prefix)
    if notice:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([EMPTY_NOTICE, ""])
    return lines


def _footer_lines(blocks: Blocks, *, pending: int) -> list[str]:
    lines = list(blocks.footer)
    if pending > 0:
        lines.append(f"{UNPUSHED_PREFIX}{pending}")
    return lines


def _split(
    blocks: Blocks,
    push: PushConfig,
    title: str,
    *,
    notice: bool,
    pending: int,
) -> tuple[Message, ...]:
    """Pack whole sections into at most ``max_messages`` byte-limited messages."""

    prefix = _prefix_lines(blocks, notice=notice)
    footer = _footer_lines(blocks, pending=pending)
    sections = list(blocks.sections)
    if not sections:
        raise PushFailure(
            "digest body is over push.split_bytes but has no '## ' section to split at"
        )
    if _block_size(prefix) > push.max_bytes:
        raise PushFailure(
            f"the digest preface is {_block_size(prefix)} bytes, "
            f"over push.max_bytes {push.max_bytes}"
        )

    chunks: list[list[str]] = []
    current = prefix
    has_section = False
    for name, raw_lines in sections:
        section_lines = list(raw_lines)
        if _block_size(section_lines) > push.max_bytes:
            raise PushFailure(
                f"section '## {name}' is {_block_size(section_lines)} bytes, "
                f"over push.max_bytes {push.max_bytes}"
            )
        if _block_size(current + section_lines) <= push.max_bytes:
            current.extend(section_lines)
            has_section = True
            continue
        if not has_section:
            # The preface alone already fills this message; start the section
            # in a new one so the preface still travels first.
            chunks.append(current)
            current = section_lines
            has_section = True
            continue
        chunks.append(current)
        current = section_lines
        has_section = True
    chunks.append(current)

    # The final message carries the footer; move whole sections down when it
    # no longer fits, and fail rather than cut a section in half.
    while _block_size(chunks[-1] + footer) > push.max_bytes:
        last = chunks[-1]
        split_at = _last_section_start(last)
        if split_at <= 0:
            raise PushFailure(
                f"section '## {_section_name(last)}' plus the footer is "
                f"{_block_size(last + footer)} bytes, over push.max_bytes "
                f"{push.max_bytes}"
            )
        chunks[-1] = last[:split_at]
        chunks.append(last[split_at:])

    # ``desp`` is over split_bytes, so a single-packet layout is still split
    # once at the last top-level boundary. Without a boundary (a lone section
    # that opens the body) the body cannot be split without cutting a paper.
    if len(chunks) == 1:
        split_at = _last_section_start(chunks[0])
        if split_at > 0:
            chunks = [chunks[0][:split_at], chunks[0][split_at:]]
        else:
            raise PushFailure(
                "digest body is over push.split_bytes but has no top-level "
                "section boundary to split at"
            )

    if len(chunks) > push.max_messages:
        raise PushFailure(
            f"digest needs {len(chunks)} messages, "
            f"push.max_messages is {push.max_messages}"
        )

    messages: list[Message] = []
    parts = len(chunks)
    for index, chunk in enumerate(chunks):
        lines = list(chunk)
        if index == parts - 1:
            lines.extend(footer)
        desp = _clean(lines)
        if _bytes(desp) > push.max_bytes:
            raise PushFailure(
                f"message {index + 1} is {_bytes(desp)} bytes, "
                f"over push.max_bytes {push.max_bytes}"
            )
        part_title = title if parts == 1 else f"{title}（{index + 1}/{parts}）"
        _require_title_length(part_title, push)
        messages.append(
            Message(part=index + 1, parts=parts, title=part_title, desp=desp)
        )
    return tuple(messages)


def _last_section_start(lines: Sequence[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith("## "):
            return index
    return -1


def _section_name(lines: Sequence[str]) -> str:
    start = _last_section_start(lines)
    return lines[start][3:].strip() if start >= 0 else "?"


def _clean(lines: Sequence[str]) -> str:
    return "\n".join(lines).strip("\n").rstrip()


def _block_size(lines: Sequence[str]) -> int:
    return _bytes(_clean(lines))


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _title_for(digest_date: str, push: PushConfig) -> str:
    title = f"{TITLE_PREFIX}{digest_date}"
    _require_title_length(title, push)
    return title


def _require_title_length(title: str, push: PushConfig) -> None:
    if len(title) > push.title_max:
        raise PushFailure(
            f"title {title!r} is {len(title)} characters, "
            f"over push.title_max {push.title_max}",
            EXIT_CONFIG,
        )


class Sender(Protocol):
    """One delivery transport: raise ``SendError`` when a send fails."""

    def send(self, title: str, desp: str) -> None: ...

    def sanitize(self, text: str) -> str: ...


class FixtureSender:
    """Replay ``<fixtures>/serverchan/send-<n>.json``; no network, no SendKey."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.requests = 0

    def sanitize(self, text: str) -> str:
        return text

    def send(self, title: str, desp: str) -> None:
        self.requests += 1
        path = self.root / "serverchan" / f"send-{self.requests}.json"
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SendError(f"missing ServerChan fixture: {path.name}") from None
        except (OSError, UnicodeDecodeError):
            raise SendError(
                f"unreadable ServerChan fixture: {path.name}"
            ) from None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise SendError(f"{path.name}: response is not JSON") from None
        if not isinstance(payload, dict):
            raise SendError(f"{path.name}: response is not a JSON object")
        status = payload.pop("http_status", 200)
        _check_response(status if isinstance(status, int) else 200, payload)


class ServerChanSender:
    """POST ``title`` and ``desp`` to ServerChan; the URL carries the SendKey."""

    def __init__(self, key: str, timeout: int) -> None:
        self._key = key
        self._timeout = timeout

    @property
    def endpoint(self) -> str:
        return endpoint_for(self._key)

    def sanitize(self, text: str) -> str:
        return redact(text, self._key)

    def send(self, title: str, desp: str) -> None:
        try:
            response = requests.post(
                self.endpoint,
                data={"title": title, "desp": desp},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SendError(
                redact(f"{type(exc).__name__}: {exc}", self._key)
            ) from None
        try:
            payload = response.json()
        except ValueError:
            raise SendError("response is not JSON") from None
        if not isinstance(payload, dict):
            raise SendError("response is not a JSON object")
        _check_response(response.status_code, payload)


def endpoint_for(key: str) -> str:
    """ServerChan's endpoint; ``sctp<uid>t...`` keys use the per-user host."""

    match = _ENDPOINT_UID.match(key)
    if match is not None:
        return f"https://{match.group(1)}.push.ft07.com/send/{key}.send"
    return f"https://sctapi.ftqq.com/{key}.send"


def redact(text: str, key: str) -> str:
    """Remove a SendKey from anything that could reach stdout, stderr, or state."""

    if not key:
        return text
    return text.replace(key, "***")


def _check_response(status_code: int, payload: Mapping[str, Any]) -> None:
    if not 200 <= status_code < 300:
        raise SendError(f"HTTP {status_code}")
    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, int) or code != 0:
        raise SendError(f"ServerChan code {code!r}")


@dataclass(frozen=True)
class PushOutcome:
    """What one live push did, plus the exit code the CLI returns."""

    status: str
    sent: int
    pushed: int
    skipped_empty: bool
    error: str
    exit_code: int


def run_live(
    config: Config,
    inputs: DigestInputs,
    now: datetime,
    store: StateStore,
    sender: Sender,
    *,
    playback: bool,
) -> PushOutcome:
    """Retry pending, send the current digest, and record runs/pushes/pending."""

    push = config.push
    channel = push.channel
    sent = 0
    pushed = 0
    status = "ok"
    exit_code = EXIT_OK
    skipped_empty = False
    errors: list[str] = []

    try:
        _require_title_length(
            f"{TITLE_PREFIX}{inputs.digest_date}", push
        )

        expired = _expired_pending_dates(
            store.pending_rows(channel),
            today=config.local_date(now),
            days=push.pending_days,
            zone=config.zone(),
        )
        for digest_date in expired:
            store.delete_pending_group(channel=channel, digest_date=digest_date)
        if expired:
            errors.append(
                f"dropped {len(expired)} pending digest(s) older than "
                f"{push.pending_days} days: {', '.join(expired)}"
            )

        retried, retried_pushed, pending_failed = _retry_pending(
            store, sender, channel=channel, now=now, errors=errors
        )
        sent += retried
        # Pending pushes are already in the database, whatever the current
        # digest does next.
        pushed += retried_pushed

        plan = plan_messages(
            inputs,
            push,
            pending_count=store.pending_count(channel),
            dry_run=False,
        )
        if plan.skipped_empty:
            skipped_empty = True
            if pending_failed:
                status = "failed"
                exit_code = EXIT_FAILURE
            else:
                # Delivering a pending digest is work even when today is empty.
                status = "ok" if retried > 0 else "skipped_empty"
                exit_code = EXIT_OK
        else:
            current_ok = True
            for index, message in enumerate(plan.messages):
                ok, attempts, error = _send_with_retries(
                    sender, push, message, playback=playback
                )
                if ok:
                    sent += 1
                    continue
                current_ok = False
                if not inputs.empty:
                    store.save_pending(
                        [
                            PendingRow(
                                channel=channel,
                                digest_date=inputs.digest_date,
                                part=unsent.part,
                                parts=unsent.parts,
                                title=unsent.title,
                                desp=unsent.desp,
                                items_json=_items_json(inputs.selected),
                                created_at=now.isoformat(),
                                attempts=attempts if unsent.part == message.part else 0,
                                last_error=error if unsent.part == message.part else "",
                            )
                            for unsent in plan.messages[index:]
                        ]
                    )
                errors.append(
                    f"message {message.part}/{message.parts}: {error}"
                )
                status = "failed"
                exit_code = EXIT_FAILURE
                break
            if current_ok:
                pushed += store.record_pushes(
                    inputs.selected,
                    channel=channel,
                    digest_date=inputs.digest_date,
                    pushed_at=now,
                )
                status = "ok"
                exit_code = EXIT_OK
    except PushFailure as exc:
        status = "failed"
        exit_code = exc.exit_code
        errors.append(exc.message)
    except sqlite3.Error as exc:
        status = "failed"
        exit_code = EXIT_FAILURE
        errors.append(f"state database: {exc}")

    pending_count = store.pending_count(channel)
    store.record_run(
        started_at=now,
        finished_at=now,
        status=status,
        command="push",
        sources={},
        candidate_count=inputs.candidate_count,
        error="; ".join(errors),
        selected_count=len(inputs.selected),
        pushed_count=pushed,
        pending_count=pending_count,
    )
    return PushOutcome(
        status=status,
        sent=sent,
        pushed=pushed,
        skipped_empty=skipped_empty,
        error="; ".join(errors),
        exit_code=exit_code,
    )


def _retry_pending(
    store: StateStore,
    sender: Sender,
    *,
    channel: str,
    now: datetime,
    errors: list[str],
) -> tuple[int, int, bool]:
    """Retry the earliest pending digest once per part; return (sent, pushed, failed)."""

    rows = store.pending_rows(channel)
    if not rows:
        return 0, 0, False
    digest_date = rows[0].digest_date
    group = [row for row in rows if row.digest_date == digest_date]
    items = _items_from_json(group[0].items_json)
    sent = 0
    failed = False
    for row in group:
        try:
            sender.send(row.title, row.desp)
        except SendError as exc:
            failed = True
            message = sender.sanitize(str(exc))
            store.update_pending_attempt(
                channel=channel,
                digest_date=row.digest_date,
                part=row.part,
                attempts=row.attempts + 1,
                last_error=message,
            )
            errors.append(
                f"pending {row.digest_date} part {row.part}/{row.parts}: {message}"
            )
        else:
            sent += 1
            store.delete_pending(
                channel=channel, digest_date=row.digest_date, part=row.part
            )
    pushed = 0
    if not failed:
        pushed = store.record_pushes(
            items, channel=channel, digest_date=digest_date, pushed_at=now
        )
    return sent, pushed, failed


def _send_with_retries(
    sender: Sender, push: PushConfig, message: Message, *, playback: bool
) -> tuple[bool, int, str]:
    """Try one message up to ``1 + retries`` times; fixture runs never sleep."""

    attempts = 0
    error = ""
    for attempt in range(1, push.retries + 2):
        attempts = attempt
        try:
            sender.send(message.title, message.desp)
            return True, attempts, ""
        except SendError as exc:
            error = sender.sanitize(str(exc))
            if (
                attempt <= push.retries
                and not playback
                and push.backoff_seconds > 0
            ):
                time.sleep(push.backoff_seconds * (2 ** (attempt - 1)))
    return False, attempts, error


def _expired_pending_dates(
    rows: Sequence[PendingRow], *, today: date, days: int, zone: ZoneInfo
) -> list[str]:
    """Digest groups whose oldest stored message is older than ``days``.

    Age is measured from ``created_at`` in the configured timezone (D created,
    D+2 kept, D+3 dropped); the whole logical digest is keyed by
    ``digest_date`` so that is what the caller deletes.
    """

    oldest: dict[str, date | None] = {}
    for row in rows:
        created = _created_date(row.created_at, zone)
        if row.digest_date not in oldest:
            oldest[row.digest_date] = created
            continue
        current = oldest[row.digest_date]
        if current is None or created is None:
            oldest[row.digest_date] = None
        else:
            oldest[row.digest_date] = min(current, created)
    expired = [
        digest_date
        for digest_date, created in oldest.items()
        if created is None or (today - created).days > days
    ]
    return sorted(expired)


def _created_date(value: str, zone: ZoneInfo) -> date | None:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    return moment.astimezone(zone).date()


def _items_json(items: Sequence[SelectedItem]) -> str:
    return json.dumps(
        [{"id": item.item_id, "topic": item.topic} for item in items],
        ensure_ascii=False,
    )


def _items_from_json(raw: str) -> list[SelectedItem]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    items: list[SelectedItem] = []
    for entry in payload:
        if not isinstance(entry, Mapping):
            continue
        item_id = str(entry.get("id", ""))
        if not item_id:
            continue
        items.append(
            SelectedItem(item_id=item_id, topic=str(entry.get("topic", "")))
        )
    return items
