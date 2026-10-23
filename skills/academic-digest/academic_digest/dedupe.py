"""Cross-source dedupe and field merging for the candidate pool.

Two records belong to the same paper when they share *any* strong identifier
(DOI, PMID, or arXiv ID). The normalized title plus year is only a fallback
for records with no strong identifier, so an unlinked preprint is not collapsed
into its published version.

Each group is merged in preference order: published records before preprints,
then PubMed before other sources. The primary record supplies the source and
every field it fills; later records only fill gaps. A group is marked as a
preprint only when every version is one, so a published version wins. The
merged record gets a fresh id in the spec's priority order.
"""

from __future__ import annotations

from dataclasses import replace
from typing import AbstractSet, Any, Iterable

from .models import Paper, normalize_arxiv_id, normalize_doi, paper_id


def identifier_keys(*, doi: str = "", pmid: str = "", arxiv_id: str = "") -> frozenset[str]:
    """All strong dedupe keys a record carries, normalized."""

    keys: set[str] = set()
    if doi:
        keys.add(f"doi:{normalize_doi(doi)}")
    if pmid:
        keys.add(f"pmid:{pmid.strip()}")
    if arxiv_id:
        keys.add(f"arxiv:{normalize_arxiv_id(arxiv_id)}")
    return frozenset(keys)


def dedupe_keys(paper: Paper) -> frozenset[str]:
    keys = identifier_keys(doi=paper.doi, pmid=paper.pmid, arxiv_id=paper.arxiv_id)
    if keys:
        return keys
    return frozenset({paper_id(title=paper.title, year=paper.date[:4])})


def is_pushed(paper: Paper, pushed_keys: AbstractSet[str]) -> bool:
    """Match strong keys plus the title-year fallback.

    The fallback keeps a title-only item excluded when a later source adds a
    DOI: the pushed id is a title hash, while the new candidate has a DOI.
    """

    keys = set(dedupe_keys(paper))
    keys.add(paper_id(title=paper.title, year=paper.date[:4]))
    return bool(keys & pushed_keys)


def pushed_item_keys(
    rows: Iterable[tuple[str, str, str, str]],
) -> frozenset[str]:
    """Expand stored pushed rows into every key they can match.

    A row is ``(item_id, doi, pmid, arxiv_id)``; the identifier columns come
    from the paper record when it exists, which covers id drift such as a
    PMID-only item that later gains a DOI.
    """

    keys: set[str] = set()
    for item_id, doi, pmid, arxiv_id in rows:
        keys.add(item_id)
        keys.update(identifier_keys(doi=doi, pmid=pmid, arxiv_id=arxiv_id))
    return frozenset(keys)


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
                pair[1].is_preprint,
                pair[1].source != "pubmed",
                pair[0],
            ),
        )
    ]
    primary = ordered[0]
    title = _preferred_value(ordered, "title")
    date = _preferred_value(ordered, "date")
    doi = _preferred_value(ordered, "doi")
    pmid = _preferred_value(ordered, "pmid")
    arxiv_id = _preferred_value(ordered, "arxiv_id")
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
        abstract=_preferred_value(ordered, "abstract"),
        authors=list(_preferred_value(ordered, "authors")),
        venue=_preferred_value(ordered, "venue"),
        date=date,
        doi=doi,
        pmid=pmid,
        arxiv_id=arxiv_id,
        url=_preferred_value(ordered, "url"),
        oa_url=_preferred_value(ordered, "oa_url"),
        is_preprint=all(record.is_preprint for record in ordered),
    )


def _preferred_value(records: list[Paper], field: str) -> Any:
    """First non-empty value in preference order, else the primary's value."""

    for record in records:
        value = getattr(record, field)
        if value:
            return value
    return getattr(records[0], field)
