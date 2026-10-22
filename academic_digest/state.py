"""SQLite state: which papers we have seen, pushed, and what each run did.

``papers`` keeps first/last-seen timestamps, ``pushes`` records items that were
successfully sent so they never re-enter the candidate pool, and ``runs`` is the
audit trail the task board and doctor rely on.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Mapping

from .dedupe import pushed_item_keys
from .models import Paper

SCHEMA_VERSION = 2
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
    error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pushes (
    item_id TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    digest_date TEXT NOT NULL DEFAULT '',
    pushed_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (item_id, topic, channel, digest_date)
);
"""


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        if self._conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

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
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO runs
                    (started_at, finished_at, status, command, sources_json,
                     candidate_count, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    status,
                    command,
                    json.dumps(sources, ensure_ascii=False, sort_keys=True),
                    candidate_count,
                    error,
                ),
            )


@contextmanager
def open_state(path: Path) -> Iterator[StateStore]:
    store = StateStore(path)
    try:
        yield store
    finally:
        store.close()
