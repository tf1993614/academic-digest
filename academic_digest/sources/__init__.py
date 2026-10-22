"""Source registry. Later issues add arXiv, GitHub, and more."""

from . import europepmc, pubmed
from .base import SourceResult

SOURCES = {pubmed.NAME: pubmed, europepmc.NAME: europepmc}

__all__ = ["SOURCES", "SourceResult"]
