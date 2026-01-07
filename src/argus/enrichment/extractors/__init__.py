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

__all__ = [
    "BaseExtractor",
    "ExtractedArticle",
    "CNBCExtractor",
    "NasdaqExtractor",
    "GenericExtractor",
    "get_extractor",
]

# Extractor registry - order matters!
# First match wins, Generic is the fallback (always returns True for can_handle)
_EXTRACTORS: list[BaseExtractor] = [
    CNBCExtractor(),
    NasdaqExtractor(),
    GenericExtractor(),  # Must be last - handles everything
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
