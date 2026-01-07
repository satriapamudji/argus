"""RSS ingestion module for Argus."""

from argus.ingestion.rss_parser import parse_feed, strip_html
from argus.ingestion.rss_worker import IngestionStats, RSSWorker, run_ingestion
from argus.ingestion.types import RSSEntry

__all__ = [
    "RSSEntry",
    "parse_feed",
    "strip_html",
    "RSSWorker",
    "IngestionStats",
    "run_ingestion",
]
