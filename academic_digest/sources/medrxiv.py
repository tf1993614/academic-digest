"""medRxiv adapter. Shares the bioRxiv date-range reader with its own identity."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import Config
from . import biorxiv
from .base import SourceResult

NAME = biorxiv.MEDRXIV.name


def collect(config: Config, fixtures_root: Path | None, now: datetime) -> SourceResult:
    return biorxiv.collect_server(
        biorxiv.MEDRXIV, config, fixtures_root, now
    )


def check(config: Config, fixtures_root: Path | None) -> str:
    return biorxiv.check_server(biorxiv.MEDRXIV, fixtures_root)
