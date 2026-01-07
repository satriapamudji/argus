"""Facts bundle module - creates the sole source of truth for the LLM.

This module provides:
- Type definitions for the facts bundle structure
- JSON Schema validation
- Selection with topic/source diversity constraints
- Bundle building orchestration
"""

from argus.facts_bundle.builder import (
    BundleBuilderConfig,
    FactsBundleBuilder,
    run_bundle,
)
from argus.facts_bundle.schema import (
    BUNDLE_SCHEMA_VERSION,
    BundleValidationError,
    get_schema,
    get_schema_json,
    validate_bundle,
    validate_bundle_json,
)
from argus.facts_bundle.selector import (
    BundleSelector,
    select_bundle_items,
)
from argus.facts_bundle.types import (
    BundleCandidate,
    BundleStats,
    CalendarEventBundle,
    CrossAssetsData,
    FactsBundle,
    IndexData,
    MarketSnapshotBundle,
    NewsItemBundle,
    SpotlightBundle,
)

__all__ = [
    # Types
    "BundleCandidate",
    "BundleStats",
    "CalendarEventBundle",
    "CrossAssetsData",
    "FactsBundle",
    "IndexData",
    "MarketSnapshotBundle",
    "NewsItemBundle",
    "SpotlightBundle",
    # Schema
    "BUNDLE_SCHEMA_VERSION",
    "BundleValidationError",
    "get_schema",
    "get_schema_json",
    "validate_bundle",
    "validate_bundle_json",
    # Selector
    "BundleSelector",
    "select_bundle_items",
    # Builder
    "BundleBuilderConfig",
    "FactsBundleBuilder",
    "run_bundle",
]
