"""Content extractor registry.

Provides a registry of source-specific extractors and a factory function
to get the appropriate extractor for a given URL.

Usage:
    from argus.enrichment.extractors import get_extractor

    extractor = get_extractor(url)
    result = extractor.extract(html_content, url)
"""

from argus.enrichment.extractors.base import BaseExtractor, ExtractedArticle
from argus.enrichment.extractors.cnbc import CNBCExtractor
from argus.enrichment.extractors.generic import GenericExtractor
from argus.enrichment.extractors.nasdaq import NasdaqExtractor
from argus.enrichment.extractors.newspaper import NewspaperExtractor

__all__ = [
    "BaseExtractor",
    "ExtractedArticle",
    "NewspaperExtractor",
    "CNBCExtractor",
    "NasdaqExtractor",
    "GenericExtractor",
    "get_extractor",
]

# Extractor registry - order matters!
# NewspaperExtractor is primary (uses newspaper4k + common patterns)
# Site-specific extractors are fallbacks if newspaper4k fails
# GenericExtractor is last resort
_EXTRACTORS: list[BaseExtractor] = [
    NewspaperExtractor(),  # Primary: newspaper4k + common metadata patterns
    CNBCExtractor(),  # Fallback for CNBC if newspaper fails
    NasdaqExtractor(),  # Fallback for Nasdaq if newspaper fails
    GenericExtractor(),  # Last resort - lxml heuristics
]


def get_extractor(url: str) -> BaseExtractor:
    """Get the appropriate extractor for a URL.

    Iterates through registered extractors and returns the first one
    that can handle the given URL. Falls back to GenericExtractor
    if no specific extractor matches.

    Args:
        url: The article URL.

    Returns:
        A BaseExtractor instance that can handle the URL.
    """
    for extractor in _EXTRACTORS:
        if extractor.can_handle(url):
            return extractor

    # Should never reach here since GenericExtractor always returns True
    return _EXTRACTORS[-1]
