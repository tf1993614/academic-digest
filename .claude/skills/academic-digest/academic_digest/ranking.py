"""Rank matched papers and cut the candidate pool by group quota.

The ranking is a pure function of its inputs, so a fixed fixture and clock
always produce the same pool:

1. rule score, descending — keyword relevance (a title hit weighs 3, an
   abstract hit 1) plus the freshness bonus (published today +2, yesterday +1)
   plus the journal whitelist bonus (a matching venue adds 2);
2. publication date, descending — the newer paper wins an equal score;
3. candidate id, ascending — the stable tie-break for otherwise identical papers.

An id cap alone lets a broad group fill every slot, so selection first reserves
one paper per group (in the order of each group's best rank), then fills the
remaining slots in rank order while no group exceeds its ``max_items``. A short
candidate list is returned as-is; the pool is never padded.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date

from .config import Topic
from .models import Paper, normalize_journal

FRESHNESS_TODAY = 2
FRESHNESS_YESTERDAY = 1
JOURNAL_BONUS = 2


def select_candidates(
    papers: list[Paper],
    topics: tuple[Topic, ...],
    *,
    pool_max: int,
    today: date,
    journal_filter: tuple[str, ...],
) -> list[Paper]:
    """Return at most ``pool_max`` papers in rank order, balanced by group."""

    quotas = {topic.name: topic.max_items for topic in topics}
    whitelist = frozenset(normalize_journal(name) for name in journal_filter)
    ranked = sorted(
        (_score_paper(paper, today, whitelist) for paper in papers),
        key=_rank_key,
    )

    chosen: list[Paper] = []
    taken_ids: set[str] = set()
    per_group_counts: Counter[str] = Counter()

    def take(paper: Paper) -> None:
        chosen.append(paper)
        taken_ids.add(paper.id)
        per_group_counts[paper.group] += 1

    # Reserve one paper per non-empty group before the global fill, so a broad
    # group that also has the top scores cannot crowd a narrow group out.
    reserved_groups: set[str] = set()
    for paper in ranked:
        if len(chosen) >= pool_max:
            break
        if paper.group not in reserved_groups:
            reserved_groups.add(paper.group)
            take(paper)

    for paper in ranked:
        if len(chosen) >= pool_max:
            break
        if paper.id in taken_ids:
            continue
        if per_group_counts[paper.group] >= quotas[paper.group]:
            continue
        take(paper)

    return sorted(chosen, key=_rank_key)


def _score_paper(paper: Paper, today: date, whitelist: frozenset[str]) -> Paper:
    """Set ``score`` and the whitelist marker before ranking.

    The whitelist matches the full journal title as reported by the source,
    case-insensitively and with internal whitespace collapsed. An empty
    whitelist leaves every paper's score and marker untouched.
    """

    match = bool(whitelist) and normalize_journal(paper.venue) in whitelist
    return replace(
        paper,
        score=(
            paper.relevance
            + _freshness_bonus(paper.date, today)
            + (JOURNAL_BONUS if match else 0)
        ),
        journal_match=match,
    )


def _freshness_bonus(published: str, today: date) -> int:
    """Bonus for a paper published today (2) or yesterday (1); else 0."""

    published_date = _parse_date(published)
    if published_date is None:
        return 0
    days = (today - published_date).days
    if days == 0:
        return FRESHNESS_TODAY
    if days == 1:
        return FRESHNESS_YESTERDAY
    return 0


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _rank_key(paper: Paper) -> tuple[int, int, str]:
    published = _parse_date(paper.date)
    date_key = published.toordinal() if published else 0
    return (-paper.score, -date_key, paper.id)
