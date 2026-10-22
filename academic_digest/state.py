"""SQLite state: seen and pushed papers, unsent messages, and each run's audit row.

``papers`` keeps first/last-seen timestamps, ``pushes`` records items that were
successfully sent so they never re-enter the candidate pool, ``pending`` holds
messages that still have to be delivered, and ``runs`` is the audit trail the
task board and doctor rely on.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from .dedupe import pushed_item_keys
from .models import Paper, SelectedItem

SCHEMA_VERSION = 3
# Columns added to ``runs`` in schema version 3; old databases get them through
# ``ALTER TABLE`` so an existing audit trail is never dropped.
_RUN_EXTRA_COLUMNS = {
    "selected_count": "INTEGER NOT NULL DEFAULT 0",
    "pushed_count": "INTEGER NOT NULL DEFAULT 0",
    "pending_count": "INTEGER NOT NULL DEFAULT 0",
}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    doi TEXT NOT NULL DEFAULT '',
    pmid TEXT NOT NULL DEFAULT '',
    arxiv_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_pmid ON papers(pmid);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    command TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    selected_count INTEGER NOT NULL DEFAULT 0,
    pushed_count INTEGER NOT NULL DEFAULT 0,
    pending_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pushes (
    item_id TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    digest_date TEXT NOT NULL DEFAULT '',
    pushed_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (item_id, topic, channel, digest_date)
);
CREATE TABLE IF NOT EXISTS pending (
    channel TEXT NOT NULL,
    digest_date TEXT NOT NULL,
    part INTEGER NOT NULL,
    parts INTEGER NOT NULL,
    title TEXT NOT NULL,
    desp TEXT NOT NULL,
    items_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (channel, digest_date, part)
);
"""


@dataclass(frozen=True)
class PendingRow:
    """One undelivered ServerChan message, persisted across runs."""

    channel: str
    digest_date: str
    part: int
    parts: int
    title: str
    desp: str
    items_json: str
    created_at: str
    attempts: int
    last_error: str


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        columns = {
            str(row[1]) for row in self._conn.execute("PRAGMA table_info(runs)")
        }
        for name, definition in _RUN_EXTRA_COLUMNS.items():
            if name not in columns:
                self._conn.execute(
                    f"ALTER TABLE runs ADD COLUMN {name} {definition}"
                )
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._conn.close()

    def pushed_keys(self) -> frozenset[str]:
        """Every identifier of an already-pushed item, expanded through papers.

        A candidate is excluded when any of its keys matches. Expanding the
        stored paper row covers id drift, for example when an item pushed as
        ``pmid:...`` later gains a DOI.
        """

        rows = self._conn.execute(
            """
            SELECT pushes.item_id, papers.doi, papers.pmid, papers.arxiv_id
            FROM pushes
            LEFT JOIN papers ON papers.id = pushes.item_id
            """
        ).fetchall()
        return pushed_item_keys(
            (
                str(item_id),
                doi or "",
                pmid or "",
                arxiv_id or "",
            )
            for item_id, doi, pmid, arxiv_id in rows
        )

    def record_papers(self, papers: list[Paper], seen_at: datetime) -> None:
        stamp = seen_at.isoformat()
        with self._conn:
            for paper in papers:
                self._conn.execute(
                    """
                    INSERT INTO papers
                        (id, doi, pmid, arxiv_id, title, source, group_name,
                         first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        doi = excluded.doi,
                        pmid = excluded.pmid,
                        arxiv_id = excluded.arxiv_id,
                        title = excluded.title,
                        source = excluded.source,
                        group_name = excluded.group_name,
                        last_seen = excluded.last_seen
                    """,
                    (
                        paper.id,
                        paper.doi,
                        paper.pmid,
                        paper.arxiv_id,
                        paper.title,
                        paper.source,
                        paper.group,
                        stamp,
                        stamp,
                    ),
                )

    def record_run(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        command: str,
        sources: Mapping[str, object],
        candidate_count: int,
        error: str = "",
        selected_count: int = 0,
        pushed_count: int = 0,
        pending_count: int = 0,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO runs
                    (started_at, finished_at, status, command, sources_json,
                     candidate_count, error, selected_count, pushed_count,
                     pending_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    status,
                    command,
                    json.dumps(sources, ensure_ascii=False, sort_keys=True),
                    candidate_count,
                    error,
                    selected_count,
                    pushed_count,
                    pending_count,
                ),
            )

    def record_pushes(
        self,
        items: Sequence[SelectedItem],
        *,
        channel: str,
        digest_date: str,
        pushed_at: datetime,
    ) -> int:
        """Insert one ``pushes`` row per item; return how many were new."""

        inserted = 0
        with self._conn:
            for item in items:
                cursor = self._conn.execute(
                    """
                    INSERT OR IGNORE INTO pushes
                        (item_id, topic, channel, digest_date, pushed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item.item_id,
                        item.topic,
                        channel,
                        digest_date,
                        pushed_at.isoformat(),
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def pending_rows(self, channel: str) -> list[PendingRow]:
        rows = self._conn.execute(
            """
            SELECT channel, digest_date, part, parts, title, desp, items_json,
                   created_at, attempts, last_error
            FROM pending
            WHERE channel = ?
            ORDER BY digest_date, part
            """,
            (channel,),
        ).fetchall()
        return [
            PendingRow(
                channel=str(row[0]),
                digest_date=str(row[1]),
                part=int(row[2]),
                parts=int(row[3]),
                title=str(row[4]),
                desp=str(row[5]),
                items_json=str(row[6]),
                created_at=str(row[7]),
                attempts=int(row[8]),
                last_error=str(row[9]),
            )
            for row in rows
        ]

    def pending_count(self, channel: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM pending WHERE channel = ?", (channel,)
        ).fetchone()
        return int(row[0]) if row else 0

    def save_pending(self, rows: Sequence[PendingRow]) -> None:
        with self._conn:
            for row in rows:
                self._conn.execute(
                    """
                    INSERT INTO pending
                        (channel, digest_date, part, parts, title, desp,
                         items_json, created_at, attempts, last_error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel, digest_date, part) DO UPDATE SET
                        parts = excluded.parts,
                        title = excluded.title,
                        desp = excluded.desp,
                        items_json = excluded.items_json,
                        created_at = excluded.created_at,
                        attempts = excluded.attempts,
                        last_error = excluded.last_error
                    """,
                    (
                        row.channel,
                        row.digest_date,
                        row.part,
                        row.parts,
                        row.title,
                        row.desp,
                        row.items_json,
                        row.created_at,
                        row.attempts,
                        row.last_error,
                    ),
                )

    def update_pending_attempt(
        self,
        *,
        channel: str,
        digest_date: str,
        part: int,
        attempts: int,
        last_error: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE pending
                SET attempts = ?, last_error = ?
                WHERE channel = ? AND digest_date = ? AND part = ?
                """,
                (attempts, last_error, channel, digest_date, part),
            )

    def delete_pending(self, *, channel: str, digest_date: str, part: int) -> None:
        with self._conn:
            self._conn.execute(
                """
                DELETE FROM pending
                WHERE channel = ? AND digest_date = ? AND part = ?
                """,
                (channel, digest_date, part),
            )

    def delete_pending_group(self, *, channel: str, digest_date: str) -> int:
        """Drop one logical digest's remaining parts; return the row count."""

        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM pending WHERE channel = ? AND digest_date = ?",
                (channel, digest_date),
            )
            return cursor.rowcount


@contextmanager
def open_state(path: Path) -> Iterator[StateStore]:
    store = StateStore(path)
    try:
        yield store
    finally:
        store.close()
