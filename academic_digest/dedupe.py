"""Cross-source dedupe and field merging for the candidate pool.

Two records belong to the same paper when they share *any* strong identifier
(DOI, PMID, or arXiv ID). The normalized title plus year is only a fallback
for records with no strong identifier, so a preprint is never silently
collapsed into its published version.

When records are merged, PubMed wins for the fields it owns (notably the
abstract and journal) and later records only fill gaps. The merged record gets
a fresh id in the spec's priority order.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import AbstractSet, Any, Iterable

from .models import Paper, normalize_doi, paper_id

_ARXIV_VERSION = re.compile(r"v\d+$")
_SOURCE_RANK = {"pubmed": 0}
_DEFAULT_SOURCE_RANK = 1


def identifier_keys(*, doi: str = "", pmid: str = "", arxiv_id: str = "") -> frozenset[str]:
    """All strong dedupe keys a record carries, normalized."""

    keys: set[str] = set()
    if doi:
        keys.add(f"doi:{normalize_doi(doi)}")
    if pmid:
        keys.add(f"pmid:{pmid.strip()}")
    if arxiv_id:
        keys.add(f"arxiv:{_ARXIV_VERSION.sub('', arxiv_id.strip())}")
    return frozenset(keys)


def dedupe_keys(paper: Paper) -> frozenset[str]:
    keys = identifier_keys(doi=paper.doi, pmid=paper.pmid, arxiv_id=paper.arxiv_id)
    if keys:
        return keys
    return frozenset({paper_id(title=paper.title, year=paper.date[:4])})


def is_excluded(paper: Paper, excluded_keys: AbstractSet[str]) -> bool:
    return bool(dedupe_keys(paper) & excluded_keys)


def merge_duplicates(papers: Iterable[Paper]) -> list[Paper]:
    """Group records that share a key, then merge each group into one paper."""

    items = list(papers)
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    owner: dict[str, int] = {}
    for index, paper in enumerate(items):
        for key in dedupe_keys(paper):
            if key in owner:
                union(index, owner[key])
            else:
                owner[key] = index

    groups: dict[int, list[Paper]] = {}
    for index, paper in enumerate(items):
        groups.setdefault(find(index), []).append(paper)
    return [_merge_group(group) for group in groups.values()]


def _merge_group(group: list[Paper]) -> Paper:
    ordered = [
        paper
        for _, paper in sorted(
            enumerate(group),
            key=lambda pair: (
                _SOURCE_RANK.get(pair[1].source, _DEFAULT_SOURCE_RANK),
                pair[1].is_preprint,
                pair[0],
            ),
        )
    ]
    primary = ordered[0]
    title = _first(ordered, "title")
    date = _first(ordered, "date")
    doi = _first(ordered, "doi")
    pmid = _first(ordered, "pmid")
    arxiv_id = _first(ordered, "arxiv_id")
    return replace(
        primary,
        id=paper_id(
            doi=doi,
            pmid=pmid,
            arxiv_id=arxiv_id,
            title=title,
            year=date[:4],
        ),
        title=title,
        abstract=_first(ordered, "abstract"),
        authors=list(_first(ordered, "authors")),
        venue=_first(ordered, "venue"),
        date=date,
        doi=doi,
        pmid=pmid,
        arxiv_id=arxiv_id,
        url=_first(ordered, "url"),
        oa_url=_first(ordered, "oa_url"),
    )


def _first(records: list[Paper], field: str) -> Any:
    for record in records:
        value = getattr(record, field)
        if value:
            return value
    return getattr(records[0], field)
