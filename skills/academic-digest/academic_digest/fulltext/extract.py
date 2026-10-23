"""Extract methods, results, and limitations from JATS XML, HTML, or PDF text.

The goal is evidence for the digest, not a full-text mirror: each section is
deduplicated, capped by paragraph count and characters, and truncated at a
sentence boundary in the second half of the budget when one exists (a word
boundary otherwise) so a quoted sentence never stops mid-word.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable

from .models import Extracted, FullTextError

_WS = re.compile(r"\s+")
_NUMBER_PREFIX = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s*")
_LIMITATION_WORD = re.compile(r"\blimitations?\b|\bcaveats?\b", re.IGNORECASE)
_LINE_BREAK_HYPHEN = re.compile(r"(?<=[A-Za-z])-\n(?=[a-z])")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "limitations",
        re.compile(
            r"^(?:(?:study|key|main|important)\s+)?limitations?"
            r"(?:\s+of\s+(?:the|this)\s+study)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "methods",
        re.compile(
            r"^(?:materials?(?:\s+and\s+methods?)?|methods?|methodology"
            r"|patients?\s+and\s+methods?|subjects?\s+and\s+methods?"
            r"|experimental\s+(?:procedures?|section)|study\s+design"
            r"|data\s+and\s+methods?)\b",
            re.IGNORECASE,
        ),
    ),
    ("results", re.compile(r"^(?:results?|findings)\b", re.IGNORECASE)),
    (
        "discussion",
        re.compile(r"^(?:discussion|conclusions?)\b", re.IGNORECASE),
    ),
)

_TARGETS = ("methods", "results", "limitations", "discussion")
_HTML_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_RESET_HEADING = re.compile(
    r"^(?:(?:references?|bibliography)(?:\s+and\s+notes)?"
    r"|acknowledg(?:e)?ments?|funding|competing\s+interests?"
    r"|conflicts?\s+of\s+interest|author\s+contributions?"
    r"|data\s+availability|supplementary(?:\s+(?:materials?|information))?"
    r"|figure\s+legends?)\b",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"^(?:downloaded\s+from|https?://|doi\s*:|biorxiv\s+preprint"
    r"|medrxiv\s+preprint|research\s+square\s+preprint|page\s+\d+"
    r"|this\s+article\s+is\s+protected|all\s+rights\s+reserved)",
    re.IGNORECASE,
)

# Keep the digest readable: a methods section can otherwise run to thousands of
# words, and the writer only needs the few paragraphs that explain the design.
_MAX_METHODS = 4
_MAX_RESULTS = 3
_MAX_LIMITATIONS = 4
_METHODS_CHARS = 4000
_RESULTS_CHARS = 3000
_LIMITATIONS_CHARS = 2000
_MIN_PARAGRAPH_CHARS = 40
_PDF_PARAGRAPH_CHARS = 700


@dataclass
class Sections:
    """Mutable section buckets plus the one place that caps and assembles them."""

    values: dict[str, list[str]] = field(
        default_factory=lambda: {label: [] for label in _TARGETS}
    )

    def add(self, label: str, paragraphs: list[str]) -> None:
        if label not in self.values:
            raise ValueError(f"unknown section: {label}")
        self.values[label].extend(paragraphs)

    def build(self) -> Extracted:
        limitations = self.values["limitations"]
        if not limitations:
            # Only discussion/conclusion prose can supply an author-declared
            # limitation; methods or results prose that merely mentions a
            # limitation is not promoted to the "author limitations" field.
            limitations = [
                paragraph
                for paragraph in self.values["discussion"]
                if _LIMITATION_WORD.search(paragraph)
            ]
        return Extracted(
            methods=_limit(
                _paragraphs(self.values["methods"]), _MAX_METHODS, _METHODS_CHARS
            ),
            results=_limit(
                _paragraphs(self.values["results"]), _MAX_RESULTS, _RESULTS_CHARS
            ),
            limitations=_limit(
                _paragraphs(limitations), _MAX_LIMITATIONS, _LIMITATIONS_CHARS
            ),
        )


def extract_xml(text: str) -> Extracted:
    """Extract sections from a JATS full-text XML document (Europe PMC)."""

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise FullTextError(f"invalid JATS XML: {exc}") from exc

    sections = Sections()

    for element in root.iter():
        if _local_name(element.tag) != "sec":
            continue
        label = _xml_label(element)
        if label is None:
            continue
        sections.add(label, _xml_section_paragraphs(element, label))

    return sections.build()


def extract_html(text: str) -> Extracted:
    """Extract sections from an HTML full text (arXiv's LaTeXML pages, for one)."""

    try:
        from bs4 import BeautifulSoup, Tag
    except ImportError as exc:  # pragma: no cover - bs4 is a declared dependency
        raise FullTextError("beautifulsoup4 is not installed") from exc

    try:
        soup = BeautifulSoup(text, "lxml")
    except Exception as exc:
        raise FullTextError(f"cannot parse HTML: {exc}") from exc

    for element in soup(
        ["script", "style", "nav", "header", "footer", "form", "figure", "table", "noscript"]
    ):
        element.decompose()

    sections = Sections()
    stack: list[tuple[int, str | None]] = []

    for element in soup.descendants:
        if not isinstance(element, Tag):
            continue
        name = (element.name or "").lower()
        if name in _HTML_HEADINGS:
            level = int(name[1])
            label = _heading_label(element.get_text(" ", strip=True))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, label))
            continue
        if name not in ("p", "li"):
            continue
        paragraph = _clean(element.get_text(" ", strip=True))
        if not paragraph:
            continue
        label = _nearest_target(stack)
        if label is not None:
            sections.add(label, [paragraph])

    return sections.build()


def extract_pdf(data: bytes) -> Extracted:
    """Extract sections from a PDF, using PyMuPDF's text layer."""

    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - PyMuPDF is a declared dependency
        raise FullTextError("PyMuPDF is not installed") from exc

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise FullTextError(f"cannot open PDF: {exc}") from exc
    try:
        pages = [page.get_text("text") for page in document]
    except Exception as exc:
        raise FullTextError(f"cannot read PDF text: {exc}") from exc
    finally:
        document.close()

    return _extract_pdf_text("\n".join(pages))


def _paragraphs(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    paragraphs: list[str] = []
    for item in items:
        text = _clean(item)
        if len(text) < _MIN_PARAGRAPH_CHARS:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        paragraphs.append(text)
    return paragraphs


def _limit(paragraphs: list[str], max_paragraphs: int, max_chars: int) -> list[str]:
    kept: list[str] = []
    total = 0
    for paragraph in paragraphs:
        if len(kept) >= max_paragraphs:
            break
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(paragraph) > remaining:
            paragraph = _truncate(paragraph, remaining)
            if len(paragraph) < _MIN_PARAGRAPH_CHARS:
                break
        kept.append(paragraph)
        total += len(paragraph)
    return kept


def _truncate(text: str, limit: int) -> str:
    """Cut at a sentence boundary in the second half of the budget, else a word.

    Requiring the sentence break to fall in the second half avoids keeping only
    a token fragment when the first sentence is much longer than the budget.
    """

    window = text[:limit]
    cut = max(
        window.rfind(". "),
        window.rfind("? "),
        window.rfind("! "),
    )
    if cut >= limit // 2:
        return window[: cut + 1].strip()
    cut = window.rfind(" ")
    return (window[:cut] if cut > 0 else window).strip()


def _clean(text: str) -> str:
    return _WS.sub(" ", text.replace("\u00ad", "")).strip()


def _heading_label(text: str) -> str | None:
    cleaned = _clean(text).strip(":;.")
    cleaned = _NUMBER_PREFIX.sub("", cleaned).strip()
    if not cleaned or len(cleaned) > 90:
        return None
    for label, pattern in _PATTERNS:
        if pattern.match(cleaned):
            return label
    return None


def _nearest_target(stack: list[tuple[int, str | None]]) -> str | None:
    for _, label in reversed(stack):
        if label in _TARGETS:
            return label
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _xml_label(sec: ET.Element) -> str | None:
    sec_type = (sec.get("sec-type") or "").lower()
    for keyword, label in (
        ("method", "methods"),
        ("result", "results"),
        ("limit", "limitations"),
        ("discuss", "discussion"),
        ("conclusion", "discussion"),
    ):
        if keyword in sec_type:
            return label
    for child in sec:
        if _local_name(child.tag) == "title":
            return _heading_label("".join(child.itertext()))
    return None


def _xml_section_paragraphs(sec: ET.Element, own_label: str) -> list[str]:
    """Paragraphs under a section, skipping a nested section with another role.

    A ``Methods`` section may contain unlabelled subsections (``2.1
    Participants``), so those are included. A ``Limitations`` subsection under
    ``Discussion`` is skipped here and collected by its own iteration, which
    keeps the paragraph out of the discussion fallback twice.
    """

    paragraphs: list[str] = []
    for child in sec:
        tag = _local_name(child.tag)
        if tag == "sec":
            child_label = _xml_label(child)
            if child_label is not None and child_label != own_label:
                continue
            paragraphs.extend(_xml_section_paragraphs(child, own_label))
        elif tag == "p":
            text = _clean("".join(child.itertext()))
            if text:
                paragraphs.append(text)
        else:
            paragraphs.extend(_descendant_paragraphs(child))
    return paragraphs


def _descendant_paragraphs(element: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for child in element.iter():
        if _local_name(child.tag) != "p":
            continue
        text = _clean("".join(child.itertext()))
        if text:
            paragraphs.append(text)
    return paragraphs


def _extract_pdf_text(text: str) -> Extracted:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _LINE_BREAK_HYPHEN.sub("", text)

    sections = Sections()
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if current is not None and buffer:
            section = _clean(" ".join(buffer))
            if section:
                sections.add(current, _split_pdf_paragraphs(section))
        buffer = []

    for raw in text.split("\n"):
        line = _clean(raw)
        if not line or _NOISE.match(line) or line.isdigit():
            flush()
            continue
        is_heading, heading = _pdf_heading(line)
        if is_heading:
            flush()
            current = heading
            continue
        if current is not None:
            buffer.append(line)
    flush()

    return sections.build()


def _pdf_heading(line: str) -> tuple[bool, str | None]:
    """Classify a PDF line: ``(is_heading, target_label)``.

    A heading with a target label opens that section; a non-target heading
    (References, Acknowledgements, ...) returns ``(True, None)`` and closes the
    current section; body text returns ``(False, None)``.
    """

    if len(line) > 90 or len(line.split()) > 9:
        return False, None
    if line.endswith((".", ";", ",")):
        return False, None
    label = _heading_label(line)
    if label is not None:
        return True, label
    stripped = _NUMBER_PREFIX.sub("", line).strip().strip(":;.")
    if _RESET_HEADING.match(stripped):
        return True, None
    return False, None


def _split_pdf_paragraphs(text: str) -> list[str]:
    """Split a PDF section into readable paragraph-sized chunks."""

    sentences = [sentence.strip() for sentence in _SENTENCE_BREAK.split(text)]
    paragraphs: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if not sentence:
            continue
        if current and length + len(sentence) > _PDF_PARAGRAPH_CHARS:
            paragraphs.append(" ".join(current))
            current = []
            length = 0
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        paragraphs.append(" ".join(current))
    return [paragraph for paragraph in paragraphs if len(paragraph) >= _MIN_PARAGRAPH_CHARS]
