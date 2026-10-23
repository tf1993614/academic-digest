"""Source registry. GitHub sources arrive in later issues."""

from . import arxiv, biorxiv, europepmc, medrxiv, pubmed, researchsquare
from .base import SourceResult

SOURCES = {
    pubmed.NAME: pubmed,
    europepmc.NAME: europepmc,
    arxiv.NAME: arxiv,
    researchsquare.NAME: researchsquare,
    biorxiv.NAME: biorxiv,
    medrxiv.NAME: medrxiv,
}

__all__ = ["SOURCES", "SourceResult"]
