"""Generator module for Argus.

Generates Telegram-ready messages from facts bundles using LLM.
"""

from argus.generator.generator import (
    GenerationError,
    MessageGenerator,
    generate_message,
)
from argus.generator.prompts import (
    build_news_contexts,
    build_user_prompt,
    get_system_prompt,
)
from argus.generator.renderer import (
    MessageRenderer,
    count_words,
    escape_markdown_v2,
    extract_referenced_ids,
    format_header_windows,
    format_index_snapshot,
    format_key_dates_raw,
    format_sources,
    render_message,
)
from argus.generator.types import (
    GenerationMode,
    GeneratorConfig,
    GeneratorResult,
    LLMGeneratedContent,
    NewsContext,
)
from argus.validator.types import ValidationResult

__all__ = [
    # Types
    "GenerationMode",
    "GeneratorConfig",
    "GeneratorResult",
    "LLMGeneratedContent",
    "NewsContext",
    "ValidationResult",
    # Generator
    "GenerationError",
    "MessageGenerator",
    "generate_message",
    # Prompts
    "build_news_contexts",
    "build_user_prompt",
    "get_system_prompt",
    # Renderer
    "MessageRenderer",
    "count_words",
    "escape_markdown_v2",
    "extract_referenced_ids",
    "format_header_windows",
    "format_index_snapshot",
    "format_key_dates_raw",
    "format_sources",
    "render_message",
]
