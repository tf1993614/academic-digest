"""Orchestrate sources into the candidate pool and persist the run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AbstractSet, Any

from .config import Config
from .dedupe import is_excluded, merge_duplicates
from .matching import attach_topic
from .models import Paper
from .sources import SOURCES, SourceResult
from .state import StateStore, open_state


@dataclass
class CollectResult:
    now: datetime
    papers: list[Paper]
    sources: list[SourceResult]

    @property
    def all_failed(self) -> bool:
        return bool(self.sources) and all(source.status == "failed" for source in self.sources)

    @property
    def status(self) -> str:
        return "failed" if self.all_failed else "ok"


def collect(
    config: Config,
    fixtures_root: Path | None,
    now: datetime,
    *,
    excluded_keys: AbstractSet[str] = frozenset(),
) -> CollectResult:
    results: list[SourceResult] = []
    for name in config.enabled_sources:
        module = SOURCES[name]
        results.append(module.collect(config, fixtures_root, now))

    raw = [paper for result in results for paper in result.papers]
    candidates: list[Paper] = []
    for paper in merge_duplicates(raw):
        enriched = attach_topic(paper, config.topics)
        if enriched is None or is_excluded(enriched, excluded_keys):
            continue
        candidates.append(enriched)

    papers = sorted(candidates, key=_sort_key)[: config.pool_max_items]
    return CollectResult(now=now, papers=papers, sources=results)


def build_payload(config: Config, result: CollectResult) -> dict[str, Any]:
    local_now = result.now.astimezone(config.zone())
    return {
        "schema_version": 1,
        "generated_at": result.now.isoformat(),
        "date": local_now.date().isoformat(),
        "timezone": config.timezone,
        "lookback_days": dict(config.lookback),
        "sources": sources_payload(result),
        "candidate_count": len(result.papers),
        "papers": [paper.to_dict() for paper in result.papers],
    }


def write_payload(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def sources_payload(result: CollectResult) -> dict[str, Any]:
    return {source.name: source.to_dict() for source in result.sources}


def record_state(
    store: StateStore,
    result: CollectResult,
    *,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    sources = sources_payload(result)
    error = "; ".join(
        f"{source.name}: {source.error}" for source in result.sources if source.error
    )
    store.record_papers(result.papers, result.now)
    store.record_run(
        started_at=started_at,
        finished_at=finished_at,
        status=result.status,
        command="collect",
        sources=sources,
        candidate_count=len(result.papers),
        error=error,
    )


def run(
    config: Config,
    *,
    fixtures_root: Path | None,
    now: datetime,
    out_path: Path,
    state_db: Path,
) -> CollectResult:
    started_at = datetime.now(timezone.utc)
    with open_state(state_db) as store:
        result = collect(
            config,
            fixtures_root,
            now,
            excluded_keys=store.pushed_keys(),
        )
        write_payload(out_path, build_payload(config, result))
        record_state(
            store,
            result,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
    return result


def _sort_key(paper: Paper) -> tuple[int, int, str]:
    # Higher score first, then newer publication date, then a stable id tie-break.
    digits = paper.date.replace("-", "")
    date_key = int(digits) if digits.isdigit() else 0
    return (-paper.score, -date_key, paper.id)
