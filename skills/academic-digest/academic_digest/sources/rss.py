"""Minimal RSS 2.0 reader shared by the arXiv and Research Square sources.

Both feeds are RSS 2.0 with a handful of extra namespaced fields
(``arxiv:announce_type``, ``dc:creator``, ``doi``, ``abstract``). Matching by
local tag name keeps the reader independent of prefix spelling.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime

from ..errors import SourceError

_WHITESPACE = re.compile(r"\s+")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_ANNOUNCE_TYPE = re.compile(r"Announce Type:\s*([A-Za-z-]+)", re.IGNORECASE)


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    description: str
    abstract: str
    doi: str
    authors: tuple[str, ...]
    announce_type: str
    date: date | None


def parse_feed(text: str, label: str) -> tuple[FeedItem, ...]:
    """Parse an RSS document, raising ``SourceError`` with the feed's name."""

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SourceError(f"invalid {label}: {exc}") from exc
    if local_name(root.tag) != "rss":
        raise SourceError(f"invalid {label}: expected an RSS document")
    channel = child(root, "channel")
    if channel is None:
        raise SourceError(f"invalid {label}: missing channel")

    feed_date = _parse_rfc822(element_text(child(channel, "pubDate"))) or _parse_rfc822(
        element_text(child(channel, "lastBuildDate"))
    )
    return tuple(_parse_item(item, feed_date) for item in children(channel, "item"))


def split_authors(value: str, *, separator: str = r"[,;]\s*") -> tuple[str, ...]:
    """Split an author string, dropping empties.

    arXiv and Research Square separate authors with commas. bioRxiv separates
    them with semicolons because each name itself is ``Last, First``, so it
    passes its own separator.
    """

    return tuple(
        name.strip() for name in re.split(separator, value) if name.strip()
    )


def _parse_item(node: ET.Element, feed_date: date | None) -> FeedItem:
    description = _clean(element_text(child(node, "description")))
    announce_type = _clean(element_text(child(node, "announce_type")))
    if not announce_type:
        match = _ANNOUNCE_TYPE.search(description)
        announce_type = match.group(1) if match else ""

    author_text = ""
    for name in ("authors", "creator", "author"):
        author_text = element_text(child(node, name))
        if author_text:
            break

    return FeedItem(
        title=_clean(element_text(child(node, "title"))),
        link=element_text(child(node, "link")),
        description=description,
        abstract=_clean(element_text(child(node, "abstract"))),
        doi=element_text(child(node, "doi")),
        authors=split_authors(author_text),
        announce_type=announce_type.lower(),
        date=_parse_rfc822(element_text(child(node, "pubDate"))) or feed_date,
    )


def _parse_rfc822(value: str) -> date | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.date() if parsed is not None else None


def _clean(value: str) -> str:
    return _WHITESPACE.sub(" ", html.unescape(_HTML_TAG.sub(" ", value))).strip()


def element_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return _WHITESPACE.sub(" ", "".join(node.itertext())).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(node: ET.Element | None, name: str) -> ET.Element | None:
    if node is None:
        return None
    for child in node:
        if local_name(child.tag) == name:
            return child
    return None


def children(node: ET.Element | None, name: str) -> list[ET.Element]:
    if node is None:
        return []
    return [child for child in node if local_name(child.tag) == name]
