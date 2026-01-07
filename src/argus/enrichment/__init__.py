"""Content enrichment module for Argus.

Fetches full article content for top-scored news items to provide
richer context for LLM triage.
"""

from argus.enrichment.worker import EnrichmentWorker, run_enrichment

__all__ = ["EnrichmentWorker", "run_enrichment"]
