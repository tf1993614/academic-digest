"""Orchestrate sources into the candidate pool and persist the run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config
from .matching import enrich
from .models import Paper
from .sources import SOURCES, SourceResult
from .state import open_state


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


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> CollectResult:
    results: list[SourceResult] = []
    for name in config.enabled_sources:
        module = SOURCES[name]
        results.append(module.collect(config, fixtures_root, now))

    candidates: dict[str, Paper] = {}
    for result in results:
        for raw in result.papers:
            paper = enrich(raw, config.topics)
            if paper is None:
                continue
            current = candidates.get(paper.id)
            if current is None or paper.score > current.score:
                candidates[paper.id] = paper

    papers = sorted(candidates.values(), key=_sort_key)[: config.pool_max_items]
    return CollectResult(now=now, papers=papers, sources=results)


def build_payload(config: Config, result: CollectResult) -> dict[str, Any]:
    local_now = result.now.astimezone(config.zone())
    return {
        "schema_version": 1,
        "generated_at": result.now.isoformat(),
        "date": local_now.date().isoformat(),
        "timezone": config.timezone,
        "lookback_days": dict(config.lookback),
        "sources": {source.name: source.to_dict() for source in result.sources},
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


def record_state(path: Path, result: CollectResult) -> None:
    sources = {source.name: source.to_dict() for source in result.sources}
    error = "; ".join(
        f"{source.name}: {source.error}" for source in result.sources if source.error
    )
    with open_state(path) as store:
        store.record_papers(result.papers, result.now)
        store.record_run(
            started_at=result.now,
            finished_at=result.now,
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
    result = collect(config, fixtures_root, now)
    write_payload(out_path, build_payload(config, result))
    record_state(state_db, result)
    return result


def _sort_key(paper: Paper) -> tuple[int, int, str]:
    # Higher score first, then newer publication date, then a stable id tie-break.
    digits = paper.date.replace("-", "")
    date_key = int(digits) if digits.isdigit() else 0
    return (-paper.score, -date_key, paper.id)
