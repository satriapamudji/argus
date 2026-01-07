"""Validator for generated messages.

Enforces formatting, section presence, bullet counts, and hallucination guards.
"""

import re
import logging
from decimal import Decimal
from typing import Optional, Any
from argus.facts_bundle.types import FactsBundle
from argus.generator.types import GeneratorResult
from argus.validator.types import ValidationResult

logger = logging.getLogger(__name__)

# Regex patterns for hallucination detection
# Match percentages like +1.5%, -0.3%, 2.75%
PERCENT_PATTERN = re.compile(r"[+-]?\d+(?:\.\d+)?%")
# Match bps like 10 bps, +5 bp, -2.5bps
BPS_PATTERN = re.compile(r"[+-]?\d+(?:\.\d+)?\s*(?:bps?|basis\s+points?)", re.IGNORECASE)
# Match dollar amounts like $1,000, $50.00
DOLLAR_PATTERN = re.compile(r"\$\d{1,3}(?:,\d{3})*(?:\.\d+)?")
# Match URLs
URL_PATTERN = re.compile(r"https?://[^\s\)\]]+")
# Match large numbers with decimals (e.g., 5000.00, 38000.00) - NOT plain integers which could be years
# This pattern requires either:
# - A decimal point (5000.00) OR
# - Commas as thousands separators (38,000)
LARGE_NUMBER_WITH_DECIMAL_PATTERN = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{4,}\.\d+\b")


class MessageValidator:
    """Validates generated messages against facts bundle and formatting rules."""

    def __init__(self, constraints: Optional[Any] = None) -> None:
        """Initialize the validator.

        Args:
            constraints: ConstraintsConfig object for word/bullet limits.
        """
        self.constraints = constraints

    def validate(self, result: GeneratorResult, bundle: FactsBundle) -> ValidationResult:
        """Validate a generator result against a facts bundle.

        Args:
            result: The generator result to validate.
            bundle: The source facts bundle.

        Returns:
            ValidationResult containing status and any errors.
        """
        errors = []

        # 1. Section Presence
        sections_valid = self._check_sections(result.message_raw, errors)

        # 2. Bullet Counts
        bullet_counts_valid = self._check_bullet_counts(result.message_raw, errors)

        # 3. Hallucination Guard
        no_hallucinations = self._check_hallucinations(result.message_raw, bundle, errors)

        # 4. Formatting (MarkdownV2)
        formatting_valid = self._check_formatting(result.message, errors)

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            sections_valid=sections_valid,
            bullet_counts_valid=bullet_counts_valid,
            no_hallucinations=no_hallucinations,
            formatting_valid=formatting_valid,
        )

    def _check_sections(self, text: str, errors: list[str]) -> bool:
        """Verify all required sections are present.

        Supports both bold (*text*) and underline (__text__) formatting.
        """
        # Section headers - check for either bold or underline format
        required_sections = [
            ("Market Update", ["*Market Update*"]),  # Header stays bold
            ("Investor Key Takeaways", ["*Investor Key Takeaways*", "__Investor Key Takeaways__"]),
            ("Key Dates (UTC)", ["*Key Dates (UTC)*", "__Key Dates (UTC)__"]),
            ("What to Watch Next", ["*What to Watch Next*", "__What to Watch Next__"]),
            ("Sources", ["*Sources*", "__Sources__"]),
        ]
        valid = True
        for name, patterns in required_sections:
            found = any(pattern in text for pattern in patterns)
            if not found:
                errors.append(f"Missing required section: {name}")
                valid = False
        return valid

    def _check_bullet_counts(self, text: str, errors: list[str]) -> bool:
        """Verify bullet counts for takeaways and watch next.

        Supports both bold (*text*) and underline (__text__) section headers.
        """
        valid = True

        # Takeaways: 3-5 bullets (support both formats)
        takeaways_match = re.search(
            r"(?:\*|__)Investor Key Takeaways(?:\*|__)(.*?)(?:(?:\*|__)Key Dates|\Z)",
            text,
            re.DOTALL,
        )
        if takeaways_match:
            bullets = re.findall(r"^•", takeaways_match.group(1), re.MULTILINE)
            if not (3 <= len(bullets) <= 5):
                errors.append(f"Invalid takeaway bullet count: {len(bullets)} (expected 3-5)")
                valid = False

        # Watch Next: max 3 bullets (support both formats)
        watch_match = re.search(
            r"(?:\*|__)What to Watch Next(?:\*|__)(.*?)(?:(?:\*|__)Sources|\Z)", text, re.DOTALL
        )
        if watch_match:
            bullets = re.findall(r"^•", watch_match.group(1), re.MULTILINE)
            if len(bullets) > 3:
                errors.append(f"Invalid watch next bullet count: {len(bullets)} (expected max 3)")
                valid = False

        return valid

    def _check_hallucinations(self, text: str, bundle: FactsBundle, errors: list[str]) -> bool:
        """Hallucination check: citations, links, and numbers.

        High-confidence checks:
        1. Citation references [n] must be within news_items range
        2. URLs in message must exist in bundle's news item source_urls
        3. Percentages and large numbers must exist in bundle (market data or news text)
        """
        valid = True

        # 1. Check citation references [n]
        max_ref = len(bundle.news_items)
        refs = re.findall(r"\[(\d+)\]", text)
        for ref in refs:
            ref_int = int(ref)
            if ref_int > max_ref or ref_int < 1:
                errors.append(f"Invalid reference number: [{ref}] (max is {max_ref})")
                valid = False

        # 2. Check URLs - extract allowed URLs from bundle
        allowed_urls = {item.source_url for item in bundle.news_items}
        message_urls = URL_PATTERN.findall(text)
        for url in message_urls:
            # Clean trailing punctuation that might have been captured
            clean_url = url.rstrip(".,;:!?")
            # Check if URL is in allowed set (exact match or starts with)
            is_allowed = any(
                clean_url == allowed or clean_url.startswith(allowed.rstrip("/"))
                for allowed in allowed_urls
            )
            if not is_allowed:
                errors.append(f"Hallucinated URL not in bundle: {clean_url}")
                valid = False

        # 3. Build allowed numbers set from bundle
        allowed_numbers = self._extract_allowed_numbers(bundle)

        # Extract numbers from narrative/takeaways/watch sections (not sources)
        # Split text to exclude sources section (support both formats)
        sources_idx = text.find("__Sources__")
        if sources_idx == -1:
            sources_idx = text.find("*Sources*")
        check_text = text[:sources_idx] if sources_idx != -1 else text

        # Check percentages
        for match in PERCENT_PATTERN.findall(check_text):
            normalized = self._normalize_number(match.rstrip("%"))
            if normalized not in allowed_numbers:
                errors.append(f"Hallucinated percentage not in bundle: {match}")
                valid = False

        # Check bps values
        for match in BPS_PATTERN.findall(check_text):
            # Extract just the numeric part
            num_match = re.search(r"[+-]?\d+(?:\.\d+)?", match)
            if num_match:
                normalized = self._normalize_number(num_match.group())
                if normalized not in allowed_numbers:
                    errors.append(f"Hallucinated bps value not in bundle: {match}")
                    valid = False

        # Check large numbers (market levels like 5000.00, 38000.00)
        for match in LARGE_NUMBER_WITH_DECIMAL_PATTERN.findall(check_text):
            normalized = self._normalize_number(match)
            if normalized not in allowed_numbers:
                errors.append(f"Hallucinated number not in bundle: {match}")
                valid = False

        return valid

    def _extract_allowed_numbers(self, bundle: FactsBundle) -> set[str]:
        """Extract all allowed numbers from the facts bundle.

        Returns:
            Set of normalized number strings that are allowed in the message.
        """
        allowed: set[str] = set()

        # Market snapshot numbers
        snapshot = bundle.market_snapshot
        for index_data in [snapshot.sp500, snapshot.dow, snapshot.nasdaq]:
            allowed.add(self._normalize_number(str(index_data.level)))
            allowed.add(self._normalize_number(str(index_data.change_1d_pct)))
            allowed.add(self._normalize_number(str(index_data.change_1d_pts)))

        # Cross-asset data if present
        if snapshot.cross_assets:
            ca = snapshot.cross_assets
            for val in [
                ca.vix_level,
                ca.vix_change_pct,
                ca.us10y_yield,
                ca.us10y_change_bps,
                ca.dxy_level,
                ca.dxy_change_pct,
                ca.wti_level,
                ca.wti_change_pct,
                ca.gold_level,
                ca.gold_change_pct,
            ]:
                if val is not None:
                    allowed.add(self._normalize_number(str(val)))

        # Extract numbers from news item titles and snippets
        for item in bundle.news_items:
            for field in [item.title, item.snippet, item.content_excerpt]:
                if field:
                    # Extract all numbers from these fields
                    for pattern in [
                        PERCENT_PATTERN,
                        BPS_PATTERN,
                        DOLLAR_PATTERN,
                        LARGE_NUMBER_WITH_DECIMAL_PATTERN,
                    ]:
                        for match in pattern.findall(field):
                            num_only = re.search(r"[+-]?\d+(?:,\d+)*(?:\.\d+)?", match)
                            if num_only:
                                allowed.add(self._normalize_number(num_only.group()))

        # Also add some common formatting variations
        # For each decimal, add integer version if it's .00
        extras: set[str] = set()
        for num in allowed:
            if num.endswith(".00"):
                extras.add(num[:-3])
            # Also add with + prefix for positive percentages
            try:
                if float(num) > 0:
                    extras.add(f"+{num}")
            except ValueError:
                pass
        allowed.update(extras)

        return allowed

    def _normalize_number(self, num_str: str) -> str:
        """Normalize a number string for comparison.

        Removes commas and normalizes decimal places.
        """
        # Remove commas
        normalized = num_str.replace(",", "")
        # Remove leading + for comparison (we'll check both)
        normalized = normalized.lstrip("+")
        # Try to normalize decimal representation
        try:
            dec = Decimal(normalized)
            # Keep 2 decimal places for consistency
            normalized = f"{dec:.2f}"
        except Exception:
            pass
        return normalized

    def _check_formatting(self, escaped_text: str, errors: list[str]) -> bool:
        """Verify MarkdownV2 formatting is valid."""
        # Common MarkdownV2 issues: unescaped characters
        # Reserved: _ * [ ] ( ) ~ ` > # + - = | { } . !

        # A simple check for unescaped reserved characters that aren't part of our format
        # This is hard to do perfectly without a full parser.
        # Let's check for basic unbalanced markers.

        valid = True
        if escaped_text.count("*") % 2 != 0:
            errors.append("Unbalanced bold markers (*)")
            valid = False

        return valid
