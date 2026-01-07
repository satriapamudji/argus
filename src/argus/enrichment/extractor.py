"""HTML content extraction using lxml.

.. deprecated::
    This module is deprecated. Use ``argus.enrichment.extractors`` instead,
    which provides source-specific extractors for better content extraction.

    The ``truncate_to_excerpt`` function is still used by the worker and
    remains available here.

    For new code, use::

        from argus.enrichment.extractors import get_extractor

        extractor = get_extractor(url)
        result = extractor.extract(html, url)
"""

import re
from typing import Optional

from lxml import html
from lxml.html.clean import Cleaner


# Tags that typically contain article content
ARTICLE_TAGS = ["article", "main", "div.article", "div.post", "div.entry", "div.content"]

# Tags to remove from content
REMOVE_TAGS = [
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "iframe",
    "form",
    "button",
    "noscript",
    "svg",
    "figure",
    "figcaption",
]

# Cleaner configuration
_cleaner = Cleaner(
    scripts=True,
    javascript=True,
    comments=True,
    style=True,
    inline_style=True,
    links=False,
    meta=True,
    page_structure=False,
    processing_instructions=True,
    remove_unknown_tags=False,
    safe_attrs_only=True,
    add_nofollow=True,
    remove_tags=REMOVE_TAGS,
)


def extract_article_text(html_content: str) -> Optional[str]:
    """Extract clean article text from HTML.

    Uses heuristics to find the main article content and strips
    HTML tags, scripts, styles, and navigation elements.

    Args:
        html_content: Raw HTML string.

    Returns:
        Cleaned text content, or None if extraction failed.
    """
    if not html_content or not html_content.strip():
        return None

    try:
        # Parse HTML
        doc = html.fromstring(html_content)

        # Clean the document
        doc = _cleaner.clean_html(doc)

        # Try to find article content using common selectors
        content_element = None

        # Try semantic tags first
        for tag in ["article", "main"]:
            elements = doc.xpath(f"//{tag}")
            if elements:
                # Take the largest one by text length
                content_element = max(elements, key=lambda e: len(e.text_content()))
                break

        # Try common class/id patterns if no semantic tags found
        if content_element is None:
            for pattern in [
                "//*[contains(@class, 'article')]",
                "//*[contains(@class, 'post-content')]",
                "//*[contains(@class, 'entry-content')]",
                "//*[contains(@class, 'story-body')]",
                "//*[contains(@id, 'article')]",
                "//*[contains(@id, 'content')]",
            ]:
                elements = doc.xpath(pattern)
                if elements:
                    content_element = max(elements, key=lambda e: len(e.text_content()))
                    break

        # Fall back to body if no article container found
        if content_element is None:
            body = doc.xpath("//body")
            if body:
                content_element = body[0]
            else:
                content_element = doc

        # Extract text
        text = content_element.text_content()

        # Clean up whitespace
        text = _normalize_whitespace(text)

        return text if text else None

    except Exception:
        # If lxml parsing fails, fall back to simple regex stripping
        return _fallback_extract(html_content)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace in extracted text.

    - Collapses multiple spaces/tabs to single space
    - Collapses multiple newlines to double newline (paragraph break)
    - Strips leading/trailing whitespace
    """
    # Replace tabs with spaces
    text = text.replace("\t", " ")

    # Collapse multiple spaces to single space
    text = re.sub(r" +", " ", text)

    # Collapse multiple newlines to double (paragraph break)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # Strip each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def _fallback_extract(html_content: str) -> Optional[str]:
    """Fallback text extraction using regex.

    Used when lxml parsing fails.
    """
    # Remove script and style content
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    text = _normalize_whitespace(text)

    return text if text else None


def truncate_to_excerpt(text: str, max_chars: int = 1200) -> str:
    """Truncate text to a maximum character count at word boundary.

    Attempts to break at sentence end if possible, otherwise at word boundary.

    Args:
        text: Text to truncate.
        max_chars: Maximum characters (default 1200).

    Returns:
        Truncated text, potentially with "..." appended.
    """
    if len(text) <= max_chars:
        return text

    # Find a good breaking point
    truncated = text[:max_chars]

    # Try to break at sentence end
    sentence_ends = [
        truncated.rfind(". "),
        truncated.rfind("! "),
        truncated.rfind("? "),
        truncated.rfind(".\n"),
        truncated.rfind("!\n"),
        truncated.rfind("?\n"),
    ]
    best_sentence_end = max(sentence_ends)

    if best_sentence_end > max_chars * 0.5:  # At least 50% of content
        return truncated[: best_sentence_end + 1]

    # Fall back to word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:  # At least 80% of content
        return truncated[:last_space] + "..."

    # Just truncate and add ellipsis
    return truncated.rstrip() + "..."
