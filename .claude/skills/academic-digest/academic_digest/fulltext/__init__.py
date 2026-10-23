"""Open-access full-text lookup: source resolution plus section extraction."""

from .fetch import fetch
from .models import Attempt, Extracted, FullText, FullTextError

__all__ = ["Attempt", "Extracted", "FullText", "FullTextError", "fetch"]
