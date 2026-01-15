"""JSON Schema definition and validation for facts bundle.

Provides strict schema validation to ensure bundle integrity before
passing to the generator LLM.
"""

import json
import logging
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# Current schema version
BUNDLE_SCHEMA_VERSION = "1.2.0"

# JSON Schema for FactsBundle
FACTS_BUNDLE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://argus/facts-bundle/v1",
    "title": "FactsBundle",
    "description": "The complete facts bundle - sole source of truth for the LLM generator",
    "type": "object",
    "required": [
        "version",
        "stream_name",
        "run_mode",
        "generated_at",
        "trading_date",
        "market_snapshot",
        "news_items",
        "calendar_events",
    ],
    "properties": {
        "version": {
            "type": "string",
            "description": "Schema version",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
        },
        "stream_name": {
            "type": "string",
            "description": "Name of the stream",
            "minLength": 1,
        },
        "run_mode": {
            "type": "string",
            "description": "Run mode",
            "enum": ["us_close", "weekend_wrap", "monday_preview", "crypto_daily"],
        },
        "generated_at": {
            "type": "string",
            "description": "ISO 8601 timestamp when bundle was generated",
            "format": "date-time",
        },
        "trading_date": {
            "type": "string",
            "description": "Trading date in YYYY-MM-DD format",
            "format": "date",
        },
        "market_snapshot": {
            "oneOf": [
                {"$ref": "#/$defs/MarketSnapshotBundle"},
                {"$ref": "#/$defs/CryptoMarketSnapshotBundle"},
            ],
        },
        "news_items": {
            "type": "array",
            "description": "Selected news items for the bundle",
            "items": {"$ref": "#/$defs/NewsItemBundle"},
            "minItems": 2,
            "maxItems": 6,
        },
        "calendar_events": {
            "type": "array",
            "description": "Calendar events (may be empty)",
            "items": {"$ref": "#/$defs/CalendarEventBundle"},
        },
        "spotlight": {
            "oneOf": [{"$ref": "#/$defs/SpotlightBundle"}, {"type": "null"}],
            "description": "Optional spotlight content",
        },
        "weekly_stats": {
            "oneOf": [{"$ref": "#/$defs/WeeklyStatsBundle"}, {"type": "null"}],
            "description": "Optional weekly performance stats",
        },
    },
    "$defs": {
        "IndexData": {
            "type": "object",
            "required": ["name", "symbol", "level", "change_1d_pct", "change_1d_pts"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "symbol": {"type": "string", "minLength": 1},
                "level": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "change_1d_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "change_1d_pts": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
            },
            "additionalProperties": False,
        },
        "CrossAssetsData": {
            "type": "object",
            "properties": {
                "vix_level": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "vix_change_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "us10y_yield": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "us10y_change_bps": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "dxy_level": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "dxy_change_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "wti_level": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "wti_change_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "gold_level": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "gold_change_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
            },
            "additionalProperties": False,
        },
        "CryptoIndexData": {
            "type": "object",
            "required": ["symbol", "name", "price_usd", "change_1d_pct"],
            "properties": {
                "symbol": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
                "price_usd": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "change_1d_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "market_cap_usd": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "volume_24h_usd": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
            },
            "additionalProperties": False,
        },
        "CryptoMarketData": {
            "type": "object",
            "properties": {
                "btc_dominance": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "total_market_cap": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "fear_greed_index": {"type": "integer", "minimum": 0, "maximum": 100},
                "funding_rates": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                    },
                },
                "open_interest": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                    },
                },
            },
            "additionalProperties": False,
        },
        "DeFiTVLSnapshot": {
            "type": "object",
            "required": ["total_tvl_usd"],
            "properties": {
                "total_tvl_usd": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                "top_protocols": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
                "chain_breakdown": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
                    },
                },
            },
            "additionalProperties": False,
        },
        "MarketSnapshotBundle": {
            "type": "object",
            "required": ["trading_date", "sp500", "dow", "nasdaq"],
            "properties": {
                "trading_date": {"type": "string", "format": "date"},
                "sp500": {"$ref": "#/$defs/IndexData"},
                "dow": {"$ref": "#/$defs/IndexData"},
                "nasdaq": {"$ref": "#/$defs/IndexData"},
                "cross_assets": {"oneOf": [{"$ref": "#/$defs/CrossAssetsData"}, {"type": "null"}]},
            },
            "additionalProperties": False,
        },
        "CryptoMarketSnapshotBundle": {
            "type": "object",
            "required": ["trading_date", "btc", "eth", "major_alts"],
            "properties": {
                "trading_date": {"type": "string", "format": "date"},
                "btc": {"$ref": "#/$defs/CryptoIndexData"},
                "eth": {"$ref": "#/$defs/CryptoIndexData"},
                "major_alts": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/CryptoIndexData"},
                    "minItems": 1,
                },
                "crypto_metrics": {"oneOf": [{"$ref": "#/$defs/CryptoMarketData"}, {"type": "null"}]},
                "defi_tvl": {"oneOf": [{"$ref": "#/$defs/DeFiTVLSnapshot"}, {"type": "null"}]},
            },
            "additionalProperties": False,
        },
        "NewsItemBundle": {
            "type": "object",
            "required": ["id", "title", "source_name", "source_url", "impact_score"],
            "properties": {
                "id": {"type": "integer", "minimum": 1},
                "title": {"type": "string", "minLength": 1},
                "source_name": {"type": "string", "minLength": 1},
                "source_url": {"type": "string", "format": "uri"},
                "published_at": {
                    "oneOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]
                },
                "snippet": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                "content_excerpt": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                "topic": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                "impact_score": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "additionalProperties": False,
        },
        "CalendarEventBundle": {
            "type": "object",
            "required": ["name", "timestamp_utc", "event_type", "formatted_display"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "timestamp_utc": {"type": "string", "format": "date-time"},
                "event_type": {
                    "type": "string",
                    "enum": ["economic", "earnings", "fed", "other"],
                },
                "formatted_display": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "SpotlightBundle": {
            "type": "object",
            "required": ["title", "body", "disclaimer"],
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "body": {"type": "string", "minLength": 1},
                "disclaimer": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "WeeklyReturnBundle": {
            "type": "object",
            "required": ["label", "start_date", "end_date", "return_pct"],
            "properties": {
                "label": {"type": "string", "minLength": 1},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "return_pct": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
            },
            "additionalProperties": False,
        },
        "WeeklyStatsBundle": {
            "type": "object",
            "required": ["week_start", "week_end", "sp500_return", "dow_return", "nasdaq_return"],
            "properties": {
                "week_start": {"type": "string", "format": "date"},
                "week_end": {"type": "string", "format": "date"},
                "sp500_return": {
                    "oneOf": [{"$ref": "#/$defs/WeeklyReturnBundle"}, {"type": "null"}]
                },
                "dow_return": {"oneOf": [{"$ref": "#/$defs/WeeklyReturnBundle"}, {"type": "null"}]},
                "nasdaq_return": {
                    "oneOf": [{"$ref": "#/$defs/WeeklyReturnBundle"}, {"type": "null"}]
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


class BundleValidationError(Exception):
    """Raised when bundle validation fails."""

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


def validate_bundle(bundle_dict: dict[str, Any], raise_on_error: bool = True) -> list[str]:
    """Validate a bundle dictionary against the JSON schema.

    Args:
        bundle_dict: The bundle as a dictionary (from FactsBundle.to_dict()).
        raise_on_error: If True, raises BundleValidationError on failure.

    Returns:
        List of validation error messages (empty if valid).

    Raises:
        BundleValidationError: If validation fails and raise_on_error is True.
    """
    errors: list[str] = []

    try:
        jsonschema.validate(instance=bundle_dict, schema=FACTS_BUNDLE_SCHEMA)
    except jsonschema.ValidationError:
        # Collect all errors, not just the first one
        validator = jsonschema.Draft202012Validator(FACTS_BUNDLE_SCHEMA)
        for error in validator.iter_errors(bundle_dict):
            path = ".".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"{path}: {error.message}")

    if errors and raise_on_error:
        logger.error(f"Bundle validation failed with {len(errors)} error(s)")
        for error in errors:
            logger.error(f"  - {error}")
        raise BundleValidationError(f"Bundle validation failed with {len(errors)} error(s)", errors)

    return errors


def validate_bundle_json(bundle_json: str, raise_on_error: bool = True) -> list[str]:
    """Validate a bundle from its JSON string representation.

    Args:
        bundle_json: JSON string of the bundle.
        raise_on_error: If True, raises BundleValidationError on failure.

    Returns:
        List of validation error messages (empty if valid).

    Raises:
        BundleValidationError: If validation fails and raise_on_error is True.
        json.JSONDecodeError: If JSON parsing fails.
    """
    bundle_dict = json.loads(bundle_json)
    return validate_bundle(bundle_dict, raise_on_error=raise_on_error)


def get_schema() -> dict[str, Any]:
    """Return the JSON Schema for documentation or external validation.

    Returns:
        The complete JSON Schema as a dictionary.
    """
    return FACTS_BUNDLE_SCHEMA.copy()


def get_schema_json(indent: int = 2) -> str:
    """Return the JSON Schema as a formatted JSON string.

    Args:
        indent: Indentation level for pretty-printing.

    Returns:
        The JSON Schema as a formatted string.
    """
    return json.dumps(FACTS_BUNDLE_SCHEMA, indent=indent)
