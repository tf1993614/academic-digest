"""Assign each paper to one keyword group and explain the hit with tags."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .config import Topic
from .models import Paper

_MISSING_ABSTRACT_TAG = "无摘要"
_PREPRINT_TAG = "预印本"


@dataclass(frozen=True)
class TopicMatch:
    topic: Topic
    terms: tuple[str, ...]
    relevance: int


@lru_cache(maxsize=None)
def _term_pattern(term: str) -> re.Pattern[str]:
    # Word-ish boundaries keep ``aging`` out of ``imaging`` while still
    # matching Chinese phrases and hyphenated technical terms.
    return re.compile(rf"(?<![0-9A-Za-z]){re.escape(term)}(?![0-9A-Za-z])", re.IGNORECASE)


def _hits(text: str, term: str) -> bool:
    return bool(text and _term_pattern(term).search(text))


def match_topic(paper: Paper, topics: tuple[Topic, ...]) -> TopicMatch | None:
    """Return the best-matching topic, its matched terms, and a relevance score.

    Title hits weigh more than abstract hits. Ties go to the first configured
    topic so that a fixed fixture always yields the same group. A topic whose
    ``exclude`` term appears is skipped entirely.
    """

    title = paper.title or ""
    abstract = paper.abstract or ""
    haystack = f"{title}\n{abstract}"

    best: TopicMatch | None = None
    for topic in topics:
        if any(_hits(haystack, term) for term in topic.exclude):
            continue
        matched = [term for term in topic.terms if _hits(haystack, term)]
        if not matched:
            continue
        relevance = sum(3 if _hits(title, term) else 1 for term in matched)
        if best is None or relevance > best.relevance:
            best = TopicMatch(topic=topic, terms=tuple(matched), relevance=relevance)
    return best


def attach_topic(paper: Paper, topics: tuple[Topic, ...]) -> Paper | None:
    """Attach group, tags, relevance score, and the missing-abstract marker in place.

    Returns ``None`` when no configured group matches, so irrelevant records
    never enter the candidate pool.
    """

    matched = match_topic(paper, topics)
    if matched is None:
        return None

    tags = list(matched.terms)
    if paper.is_preprint:
        tags.append(_PREPRINT_TAG)
    abstract = (paper.abstract or "").strip()
    paper.abstract = abstract
    paper.abstract_missing = not bool(abstract)
    if paper.abstract_missing:
        tags.append(_MISSING_ABSTRACT_TAG)

    paper.group = matched.topic.name
    paper.tags = tags
    paper.relevance = matched.relevance
    return paper
