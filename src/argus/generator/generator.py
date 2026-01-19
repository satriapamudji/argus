"""Message generator using LLM via OpenRouter."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional
import httpx
from argus.config import ConstraintsConfig
from argus.facts_bundle.types import (
    CryptoFactsBundle,
    FactsBundle,
)
from argus.generator.prompts import (
    build_news_contexts,
    build_user_prompt,
    get_system_prompt,
)
from argus.generator.renderer import (
    count_words,
    escape_message_v2,
    extract_referenced_ids,
    format_cross_assets_section,
    format_header_windows,
    format_index_snapshot,
    format_key_dates_raw,
    format_weekly_stats_plain,
    format_weekly_stats_section,
    render_message,
)
from argus.generator.types import (
    GenerationMode,
    GeneratorConfig,
    GeneratorResult,
    LLMGeneratedContent,
    NewsContext,
)
from argus.validator.validator import MessageValidator
from argus.validator.types import ValidationResult

logger = logging.getLogger(__name__)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class GenerationError(Exception):
    pass


class MessageGenerator:
    def __init__(self, config, constraints=None, http_client=None):
        self.config = config
        self.constraints = constraints or ConstraintsConfig()
        self._client = http_client
        self._owns_client = False
        self.validator = MessageValidator(self.constraints)

    def _get_api_key(self):
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise GenerationError("OPENROUTER_API_KEY environment variable not set")
        return api_key

    def _get_client(self):
        if self._client is None:
            self._client = httpx.Client(timeout=float(self.config.timeout_seconds))
            self._owns_client = True
        return self._client

    def close(self):
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _get_max_words(self, mode):
        limits = {
            GenerationMode.US_CLOSE: self.constraints.max_words_daily,
            GenerationMode.WEEKEND_WRAP: self.constraints.max_words_weekend,
            GenerationMode.MONDAY_PREVIEW: self.constraints.max_words_preview,
            GenerationMode.CRYPTO_DAILY: self.constraints.max_words_daily,
        }
        return limits[mode]

    def _call_openrouter(self, system_prompt, user_prompt):
        client = self._get_client()
        headers = {
            "Authorization": f"Bearer {self._get_api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/argus-news",
            "X-Title": "Argus Market Update Generator",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": 2000,
        }
        try:
            response = client.post(OPENROUTER_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except Exception as e:
            raise GenerationError(str(e))

    def _parse_llm_response(self, response, news_contexts):
        try:
            cleaned = response
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]
            data = json.loads(cleaned.strip())
            narrative = str(data.get("narrative", ""))
            takeaways = list(data.get("takeaways", []))
            watch_next = list(data.get("watch_next", []))
            # Extract optional mode-specific fields
            opening_line = data.get("opening_line")
            sign_off = data.get("sign_off")
            # Extract refs from all text sections (narrative + takeaways + watch_next)
            all_text = narrative + " " + " ".join(takeaways) + " " + " ".join(watch_next)
            referenced_ids = extract_referenced_ids(all_text, news_contexts)
            return LLMGeneratedContent(
                narrative=narrative,
                takeaways=takeaways[: self.constraints.max_takeaway_bullets],
                watch_next=watch_next[: self.constraints.max_watch_bullets],
                referenced_item_ids=referenced_ids,
                raw_response=response,
                opening_line=opening_line if isinstance(opening_line, str) else None,
                sign_off=sign_off if isinstance(sign_off, str) else None,
            )
        except Exception as e:
            raise GenerationError(str(e))

    def _build_fallback_message(
        self, bundle: FactsBundle | CryptoFactsBundle, news_contexts: list[NewsContext], mode: GenerationMode
    ) -> GeneratorResult:
        """Build a minimal safe fallback message from bundle data only (no LLM).

        This is used when LLM generation fails validation after retry.
        The fallback contains only verified data from the facts bundle.
        Mode-aware: builds appropriate structure for us_close, weekend_wrap, monday_preview, or crypto_daily.
        """
        # For crypto bundles, use the crypto renderer
        if isinstance(bundle, CryptoFactsBundle):
            # Build a simple LLM content for rendering
            llm_content = LLMGeneratedContent(
                narrative="Market data is summarized above. See sources for details.",
                takeaways=[
                    "Review crypto market performance above",
                    "Monitor derivatives data for positioning signals",
                    "Check sources for detailed analysis",
                ],
                watch_next=[
                    "Upcoming economic events may impact crypto markets",
                    "Monitor regulatory developments",
                ],
            )
            # Use crypto renderer to build the message
            from argus.generator.renderer_crypto import CryptoMessageRenderer
            renderer = CryptoMessageRenderer(news_contexts)
            message_text, message_type = renderer.render(bundle, llm_content)
            return GeneratorResult(
                message=escape_message_v2(message_text),
                message_raw=message_text,
                word_count=0,
                sources_count=0,
                has_spotlight=False,
                model="fallback",
                generation_mode=GenerationMode.CRYPTO_DAILY,
                generated_at=datetime.now(timezone.utc),
                error="LLM generation failed, using fallback",
            )

        sections = []
        run_mode = bundle.run_mode

        # 1. Header (title + date) - mode-aware
        sections.append(format_header_windows(bundle.trading_date, run_mode))

        if run_mode == "weekend_wrap":
            # Weekend wrap format: scorecard, cross-assets, narrative, takeaways, sources
            if bundle.weekly_stats is not None:
                sections.append("")
                sections.append(format_weekly_stats_plain(bundle.weekly_stats, run_mode))

            cross_assets = format_cross_assets_section(bundle.market_snapshot)
            if cross_assets:
                sections.append("")
                sections.append(cross_assets)

            sections.append("")
            sections.append("Market data as of close. See sources for details.")

            sections.append("")
            sections.append("—————")
            sections.append("")

            sections.append("__*Key Takeaways for the Week*__")
            sections.append("**>• Review the weekly scorecard for index performance")
            sections.append(">• Monitor cross-asset signals for portfolio positioning")
            sections.append(">• Check sources for detailed analysis||")

            sections.append("")
            sections.append("__*Sources*__")
            sections.append("**>• No cited sources.||")

            sections.append("")
            sections.append("—————")
            sections.append("")
            sections.append("Have a good weekend.")

        elif run_mode == "monday_preview":
            # Monday preview format: prior week, opening, narrative, key things, key dates
            if bundle.weekly_stats is not None:
                sections.append("")
                sections.append(format_weekly_stats_plain(bundle.weekly_stats, run_mode))

            sections.append("")
            sections.append("Hope you had a restful weekend. Here's what to watch this week.")

            sections.append("")
            sections.append(
                "Key events are scheduled for the week ahead. See Key Dates for details."
            )

            sections.append("")
            sections.append("—————")
            sections.append("")

            sections.append("__*Key Things to Look Out For*__")
            sections.append("**>• Monitor scheduled events in Key Dates section")
            sections.append(">• Review prior week performance for context")
            sections.append(">• Check economic calendar for data releases||")

            sections.append("")
            sections.append(format_key_dates_raw(bundle.calendar_events))

        else:
            # us_close format (default): index snapshot, narrative, takeaways, key dates, watch next, sources
            sections.append("")
            sections.append(format_index_snapshot(bundle.market_snapshot))

            if bundle.weekly_stats is not None:
                sections.append("")
                sections.append(format_weekly_stats_section(bundle.weekly_stats, run_mode))

            sections.append("")
            sections.append("Market data as of close. See sources for details.")

            sections.append("")
            sections.append("—————")
            sections.append("")

            sections.append("__*Investor Key Takeaways*__")
            sections.append("**>• Market closed; review sources for key developments")
            sections.append(">• Monitor scheduled events in Key Dates section")
            sections.append(">• Check sources for detailed analysis||")

            sections.append("")
            sections.append(format_key_dates_raw(bundle.calendar_events))

            sections.append("")
            sections.append("__*What to Watch Next*__")
            sections.append("**>• Upcoming scheduled events (see Key Dates)||")

            sections.append("")
            sections.append("__*Sources*__")
            sections.append("**>• No cited sources.||")

        raw_message = "\n".join(sections)

        # Apply full MarkdownV2 escaping (preserves formatting markers)
        escaped_message = escape_message_v2(raw_message)

        return GeneratorResult(
            message=escaped_message,
            message_raw=raw_message,
            word_count=count_words(raw_message),
            sources_count=len(news_contexts),
            has_spotlight=False,  # Fallback never includes spotlight
            model="fallback",
            generation_mode=mode,
            generated_at=datetime.now(timezone.utc),
            retry_count=2,  # Indicates we tried twice before fallback
            llm_duration_seconds=0.0,
            error="Validation failed after retry; using fallback message",
        )

    def generate(
        self, bundle: FactsBundle, mode: Optional[GenerationMode] = None
    ) -> tuple[GeneratorResult, ValidationResult]:
        """Generate a message from a facts bundle.

        Args:
            bundle: The facts bundle to generate from.
            mode: Generation mode (defaults to bundle's run_mode).

        Returns:
            Tuple of (GeneratorResult, ValidationResult).
            - GeneratorResult contains the message (LLM-generated or fallback).
            - ValidationResult contains validation details for persistence.
        """
        if not self.config.enabled:
            raise GenerationError("Generator is disabled in configuration")
        if mode is None:
            mode = GenerationMode.from_string(bundle.run_mode)

        news_contexts = build_news_contexts(bundle)
        system_prompt = get_system_prompt(mode)
        user_prompt = build_user_prompt(bundle, news_contexts, mode, self._get_max_words(mode))

        llm_content: Optional[LLMGeneratedContent] = None
        retry_count = 0
        total_duration = 0.0
        final_result = None
        final_validation = None

        # Validation retry attempts (configurable, default 5)
        max_val_attempts = 5

        for val_attempt in range(max_val_attempts):
            for api_attempt in range(self.config.max_retries + 1):
                try:
                    start = time.time()
                    raw_response = self._call_openrouter(system_prompt, user_prompt)
                    total_duration += time.time() - start
                    llm_content = self._parse_llm_response(raw_response, news_contexts)

                    # Strict citations: require at least 1 cite key
                    if not llm_content.referenced_item_ids:
                        raise GenerationError(
                            "LLM output contained no valid cite keys; expected at least one [#A1B2C3D4] citation"
                        )

                    break
                except Exception as e:
                    retry_count += 1
                    if api_attempt == self.config.max_retries:
                        # LLM call failed completely - raise error (no fallback)
                        raise GenerationError(f"LLM generation failed after {self.config.max_retries + 1} attempts: {e}")

            if llm_content is None:
                raise GenerationError("LLM content missing after generation")

            escaped, raw = render_message(bundle, news_contexts, llm_content, True)
            candidate = GeneratorResult(
                message=escaped,
                message_raw=raw,
                word_count=count_words(llm_content.narrative),
                sources_count=len(llm_content.referenced_item_ids),
                has_spotlight=bundle.spotlight is not None,
                model=self.config.model,
                generation_mode=mode,
                generated_at=datetime.now(timezone.utc),
                retry_count=retry_count,
                llm_duration_seconds=total_duration,
            )

            val = self.validator.validate(candidate, bundle)
            if val.is_valid:
                final_result = candidate
                final_validation = val
                break
            else:
                # Save last validation for error reporting
                final_validation = val
                # Retry with corrective prompt
                user_prompt += f"\n\nValidation errors to fix: {', '.join(val.errors)}"
                user_prompt += (
                    "\nPlease regenerate the content fixing these issues. Do not add any facts not in the provided data."
                    "\nRemember: cite news ONLY using the provided cite keys in the exact format [#A1B2C3D4]."
                )
                retry_count += 1
                logger.warning(f"Validation failed (attempt {val_attempt + 1}/{max_val_attempts}): {val.errors}")

        # If all validation attempts failed, raise error
        if final_result is None:
            last_errors = final_validation.errors if final_validation else "unknown"
            raise GenerationError(f"LLM validation failed after {max_val_attempts} attempts. Last errors: {last_errors}")

        return final_result, final_validation


def generate_message(
    bundle: FactsBundle,
    config: Optional[GeneratorConfig] = None,
    constraints: Optional[ConstraintsConfig] = None,
    mode: Optional[GenerationMode] = None,
) -> tuple[GeneratorResult, ValidationResult]:
    """Convenience function to generate a message.

    Returns:
        Tuple of (GeneratorResult, ValidationResult).
    """
    if config is None:
        config = GeneratorConfig()
    with MessageGenerator(config, constraints) as gen:
        return gen.generate(bundle, mode)
