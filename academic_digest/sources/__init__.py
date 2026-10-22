"""Source registry. Later issues add Europe PMC, arXiv, GitHub, and more."""

from . import pubmed
from .base import SourceResult

SOURCES = {pubmed.NAME: pubmed}

__all__ = ["SOURCES", "SourceResult"]
