"""CLI entrypoint for Argus."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from . import __version__
from .config import ArgusConfig


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config.yaml",
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path]) -> None:
    """Argus - US Close Market Update Bot.

    Ingest news, score and curate items, generate market updates.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.option("--stream", default="us_close_basic", help="Stream name")
@click.option(
    "--mode",
    type=click.Choice(["us_close", "weekend_wrap", "monday_preview"]),
    required=True,
    help="Run mode",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Load config and print resolved settings without executing",
)
@click.pass_context
def run(ctx: click.Context, stream: str, mode: str, dry_run: bool) -> None:
    """Execute a run for the specified stream and mode."""
    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if dry_run:
        click.echo("=== Argus Dry Run ===")
        click.echo(f"Stream: {stream}")
        click.echo(f"Mode: {mode}")
        click.echo()
        click.echo("Configuration loaded:")
        click.echo(f"  Stream name: {config.stream.name}")
        click.echo(f"  Stream enabled: {config.stream.enabled}")
        click.echo()
        click.echo("Schedule:")
        click.echo(f"  Daily US Close (SGT): {config.stream.schedule.daily_us_close_sgt}")
        click.echo(f"  Weekend Wrap (SGT): {config.stream.schedule.weekend_wrap_sgt}")
        click.echo(f"  Monday Preview (NY): {config.stream.schedule.monday_preview_ny}")
        click.echo()
        click.echo("Monday Preview:")
        click.echo(f"  Conditional: {config.stream.monday_preview.conditional}")
        click.echo(f"  Risk threshold: {config.stream.monday_preview.risk_threshold}")
        click.echo(f"  Force publish: {config.stream.monday_preview.force_publish}")
        click.echo(f"  Force skip: {config.stream.monday_preview.force_skip}")
        click.echo()
        click.echo("Telegram:")
        click.echo(f"  Bot token env: {config.stream.telegram.bot_token_env}")
        click.echo(f"  Chat ID env: {config.stream.telegram.chat_id_env}")
        click.echo(f"  Parse mode env: {config.stream.telegram.parse_mode_env}")
        click.echo()
        click.echo("RSS Feeds:")
        feeds = config.get_rss_feeds()
        if feeds:
            for feed in feeds:
                click.echo(f"  - {feed}")
        else:
            click.echo("  (none configured)")
        click.echo()
        click.echo("Retention:")
        click.echo(f"  News items days: {config.stream.retention.news_items_days}")
        click.echo(f"  Fingerprints days: {config.stream.retention.fingerprints_days}")
        click.echo(f"  Runs days: {config.stream.retention.runs_days}")
        click.echo()
        click.echo("Enrichment:")
        click.echo(f"  Enabled: {config.stream.enrichment.enabled}")
        click.echo(f"  Max enrich per run: {config.stream.enrichment.max_enrich_per_run}")
        click.echo(f"  Allow full text storage: {config.stream.enrichment.allow_full_text_storage}")
        click.echo()
        click.echo("Constraints:")
        click.echo(f"  Max words (daily): {config.stream.constraints.max_words_daily}")
        click.echo(f"  Max words (weekend): {config.stream.constraints.max_words_weekend}")
        click.echo(f"  Max words (preview): {config.stream.constraints.max_words_preview}")
        click.echo()
        click.echo(f"Log level: {config.log_level}")
        click.echo()
        click.echo("=== Dry run complete ===")
        return

    click.echo(f"Running stream '{stream}' in mode '{mode}'...")
    click.echo("(Full execution not yet implemented)")


@cli.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command()
@click.option("--dry-run", is_flag=True, help="Show pending migrations without applying")
def migrate(dry_run: bool) -> None:
    """Apply pending database migrations."""
    from argus.db.connection import get_connection
    from argus.db.migrations import apply_migrations, get_pending_migrations

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    pending = get_pending_migrations(conn)

    if not pending:
        click.echo("No pending migrations.")
        conn.close()
        return

    click.echo(f"Found {len(pending)} pending migration(s):")
    for version, path in pending:
        click.echo(f"  - {version}")

    if dry_run:
        click.echo("\nDry run complete. No migrations applied.")
        conn.close()
        return

    click.echo("\nApplying migrations...")
    applied = apply_migrations(conn)
    conn.close()

    click.echo(f"Applied {len(applied)} migration(s):")
    for version in applied:
        click.echo(f"  ✓ {version}")


@db.command()
def status() -> None:
    """Show migration status."""
    from argus.db.connection import get_connection
    from argus.db.migrations import get_applied_migrations, get_pending_migrations

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    applied = get_applied_migrations(conn)
    pending = get_pending_migrations(conn)
    conn.close()

    click.echo("Applied migrations:")
    if applied:
        for version in applied:
            click.echo(f"  ✓ {version}")
    else:
        click.echo("  (none)")

    click.echo("\nPending migrations:")
    if pending:
        for version, _ in pending:
            click.echo(f"  • {version}")
    else:
        click.echo("  (none)")


@db.command()
@click.pass_context
def cleanup(ctx: click.Context) -> None:
    """Run retention cleanup (drop old partitions)."""
    from argus.db.connection import get_connection
    from argus.db.partitions import run_retention_cleanup

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    news_items_days = config.stream.retention.news_items_days
    fingerprints_days = config.stream.retention.fingerprints_days

    click.echo("Running retention cleanup...")
    click.echo(f"  News items retention: {news_items_days} days")
    click.echo(f"  Fingerprints retention: {fingerprints_days} days")

    result = run_retention_cleanup(
        conn,
        news_items_days=news_items_days,
        fingerprints_days=fingerprints_days if fingerprints_days < 3650 else None,
    )
    conn.close()

    if result["dropped_partitions"]:
        click.echo(f"\nDropped {len(result['dropped_partitions'])} partition(s):")
        for partition in result["dropped_partitions"]:
            click.echo(f"  - {partition}")
    else:
        click.echo("\nNo partitions needed cleanup.")

    if result["deleted_fingerprints"]:
        click.echo(f"\nDeleted {len(result['deleted_fingerprints'])} old fingerprint(s).")


@db.command()
@click.option("--days", default=7, help="Number of days ahead to create partitions for")
def create_partitions(days: int) -> None:
    """Create partitions for upcoming days."""
    from datetime import date, timedelta

    from argus.db.connection import get_connection
    from argus.db.partitions import create_partitions_for_range

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    start = date.today()
    end = start + timedelta(days=days - 1)

    click.echo(f"Creating partitions from {start} to {end}...")
    created = create_partitions_for_range(conn, start, end)
    conn.close()

    click.echo(f"Created/verified {len(created)} partition(s):")
    for partition in created:
        click.echo(f"  - {partition}")


@db.command()
@click.option("--url", required=True, help="News URL")
@click.option("--title", required=True, help="News title")
@click.option("--source", default="test", help="Source name")
@click.option("--snippet", default=None, help="News snippet")
def insert_test(url: str, title: str, source: str, snippet: Optional[str]) -> None:
    """Insert a test news item and create a run + message."""
    from argus.db.connection import get_connection
    from argus.db.repository import (
        create_message,
        create_run,
        get_or_create_fingerprint,
        insert_news_item,
        update_message,
        update_run,
    )

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo("Inserting test data...")

    # Create fingerprint
    fingerprint, was_created = get_or_create_fingerprint(
        conn,
        url=url,
        source_name=source,
        title=title,
        snippet=snippet,
    )
    click.echo(
        f"  Fingerprint: id={fingerprint.id}, "
        f"hash_url={fingerprint.hash_url[:16]}... "
        f"({'created' if was_created else 'existing'})"
    )

    # Create news item
    news_item = insert_news_item(
        conn,
        fingerprint_id=fingerprint.id,
        source_name=source,
        source_url=url,
        title=title,
        snippet=snippet,
    )
    click.echo(f"  News item: id={news_item.id}")

    # Create run
    run_record = create_run(conn, stream_name="us_close_basic", run_mode="us_close")
    click.echo(f"  Run: id={run_record.id}, status={run_record.status}")

    # Create message
    message = create_message(
        conn,
        run_id=run_record.id,
        content=f"Test message for: {title}",
    )
    click.echo(f"  Message: id={message.id}")

    # Update run to completed
    update_run(
        conn,
        run_id=run_record.id,
        status="completed",
        completed_at=datetime.utcnow(),
        facts_bundle_json={"test": True, "news_item_id": news_item.id},
    )
    click.echo("  Run updated to completed")

    # Update message to published
    update_message(
        conn,
        message_id=message.id,
        validation_status="valid",
        publish_status="published",
        published_at=datetime.utcnow(),
    )
    click.echo("  Message updated to published")

    conn.close()
    click.echo("\n✓ Test data inserted successfully!")


def main() -> None:
    """Entry point."""
    cli()


@cli.command()
@click.option("--dry-run", is_flag=True, help="Parse feeds but don't insert into DB")
@click.pass_context
def ingest(ctx: click.Context, dry_run: bool) -> None:
    """Run RSS feed ingestion.

    Polls all configured RSS feeds and ingests new items into the database.
    Designed to be run via cron at regular intervals (e.g., every 10 minutes).
    """
    from argus.ingestion import run_ingestion
    from argus.ingestion.rss_parser import parse_feed

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    feed_urls = config.get_rss_feeds()

    if not feed_urls:
        click.echo("No RSS feeds configured. Add feeds to rss/*.txt files.")
        return

    if dry_run:
        click.echo(f"Dry run: parsing {len(feed_urls)} feed(s)...")
        click.echo()

        total_entries = 0
        for url in feed_urls:
            entries, error = parse_feed(url)
            if error:
                click.echo(f"  ✗ {url}")
                click.echo(f"    Error: {error}")
            else:
                click.echo(f"  ✓ {url}: {len(entries)} entries")
                total_entries += len(entries)

        click.echo()
        click.echo(f"Total entries found: {total_entries}")
        click.echo("Dry run complete. No items inserted.")
        return

    click.echo(f"Ingesting from {len(feed_urls)} feed(s)...")
    stats = run_ingestion(config)

    click.echo()
    click.echo("=== Ingestion Complete ===")
    click.echo(f"Feeds processed: {stats.feeds_processed}")
    click.echo(f"Feeds failed: {stats.feeds_failed}")
    click.echo(f"Entries found: {stats.entries_found}")
    click.echo(f"New entries: {stats.entries_new}")
    click.echo(f"Duplicates skipped: {stats.entries_duplicate}")

    if stats.errors:
        click.echo()
        click.echo("Errors:")
        for err in stats.errors:
            click.echo(f"  - {err}")


@cli.command()
@click.option("--window-hours", default=24, help="Look back window in hours (default 24)")
@click.option("--dry-run", is_flag=True, help="Show candidates but don't fetch content")
@click.pass_context
def enrich(ctx: click.Context, window_hours: int, dry_run: bool) -> None:
    """Enrich top-scored news items with full article content.

    Fetches content for the top-scored news items that haven't been
    enriched yet. Run this after ingestion and scoring, before LLM triage.
    """
    from argus.enrichment import run_enrichment

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if not config.stream.enrichment.enabled:
        click.echo("Enrichment is disabled in configuration.")
        return

    if dry_run:
        click.echo(f"Dry run: checking candidates (window: {window_hours} hours)...")
        click.echo()

        # Show config
        click.echo("Enrichment configuration:")
        click.echo(f"  Max items per run: {config.stream.enrichment.max_enrich_per_run}")
        click.echo(f"  Allow full text: {config.stream.enrichment.allow_full_text_storage}")
        click.echo(f"  Snippet chars: {config.stream.enrichment.snippet_chars}")
        click.echo()

        # Get candidates without fetching
        from argus.db.connection import get_connection
        from argus.db.repository import get_news_items_for_enrichment

        try:
            conn = get_connection()
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)

        candidates = get_news_items_for_enrichment(
            conn,
            window_hours=window_hours,
            limit=config.stream.enrichment.max_enrich_per_run,
        )
        conn.close()

        if not candidates:
            click.echo("No candidates found for enrichment.")
            click.echo("(Items need to be scored before they can be enriched)")
            return

        click.echo(f"Found {len(candidates)} candidate(s) for enrichment:")
        for item_id, url, title, _, score in candidates:
            click.echo(f"  [{score:3d}] {title[:60]}...")
            click.echo(f"        {url}")

        click.echo()
        click.echo("Dry run complete. No content fetched.")
        return

    click.echo(f"Enriching top-scored items (window: {window_hours} hours)...")
    stats = run_enrichment(config, window_hours=window_hours)

    click.echo()
    click.echo("=== Enrichment Complete ===")
    click.echo(f"Candidates found: {stats.candidates_found}")
    click.echo(f"Items enriched: {stats.items_enriched}")
    click.echo(f"Items failed: {stats.items_failed}")
    click.echo(f"Items skipped: {stats.items_skipped}")
    click.echo(f"Total content: {stats.total_content_chars:,} chars")

    if stats.errors:
        click.echo()
        click.echo("Errors:")
        for err in stats.errors:
            click.echo(f"  - {err}")


@cli.command()
@click.option("--window-hours", default=24, help="Look back window in hours (default 24)")
@click.option("--dry-run", is_flag=True, help="Score items but don't write to database")
@click.pass_context
def score(ctx: click.Context, window_hours: int, dry_run: bool) -> None:
    """Score news items using heuristics and optional LLM triage.

    Scores unscored news items from the window using:
    - Recency (0-25 pts)
    - Source tier (0-20 pts)
    - Keyword relevance (0-30 pts)
    - Uniqueness via SimHash (0-15 pts)
    - Breaking/urgency indicators (0-10 pts)

    Optionally applies LLM triage via OpenRouter for top candidates.
    Run this after ingestion to prepare items for enrichment.
    """
    from argus.scoring import run_scoring

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if not config.stream.scoring.enabled:
        click.echo("Scoring is disabled in configuration.")
        return

    if dry_run:
        click.echo(f"Dry run: scoring candidates (window: {window_hours} hours)...")
        click.echo()

        # Show config
        click.echo("Scoring configuration:")
        click.echo(f"  Max items per run: {config.stream.scoring.max_items_per_run}")
        click.echo(f"  Scorer version: {config.stream.scoring.scorer_version}")
        click.echo(f"  LLM triage enabled: {config.stream.scoring.llm_triage_enabled}")
        if config.stream.scoring.llm_triage_enabled:
            click.echo(f"  LLM model: {config.stream.scoring.llm_model}")
            click.echo(f"  LLM max items: {config.stream.scoring.llm_max_items}")
        click.echo()

        # Show source tiers
        click.echo("Source tiers:")
        click.echo(f"  Tier 1 (20 pts): {', '.join(config.stream.scoring.source_tiers.tier_1)}")
        click.echo(f"  Tier 2 (15 pts): {', '.join(config.stream.scoring.source_tiers.tier_2)}")
        click.echo(f"  Tier 3 (10 pts): {', '.join(config.stream.scoring.source_tiers.tier_3)}")
        click.echo("  Unlisted:  5 pts")
        click.echo()

    click.echo(f"Scoring items (window: {window_hours} hours)...")
    stats = run_scoring(config, window_hours=window_hours, dry_run=dry_run)

    click.echo()
    click.echo("=== Scoring Complete ===")
    click.echo(f"Candidates found: {stats.total_candidates}")
    click.echo(f"Items scored: {stats.scored}")
    click.echo(f"Already scored (skipped): {stats.skipped_already_scored}")
    click.echo(f"Errors: {stats.errors}")
    if stats.llm_triaged > 0:
        click.echo(f"LLM triaged: {stats.llm_triaged}")
    click.echo(f"Duration: {stats.duration_seconds:.1f}s")

    if stats.scored > 0:
        click.echo()
        click.echo(f"Success rate: {stats.success_rate:.1f}%")


@cli.command()
@click.option("--window-hours", default=24, help="Look back window in hours (default 24)")
@click.option(
    "--mode",
    type=click.Choice(["us_close", "weekend_wrap", "monday_preview"]),
    default="us_close",
    help="Run mode (default us_close)",
)
@click.option("--dry-run", is_flag=True, help="Build bundle but don't save to database")
@click.option("--output", type=click.Path(path_type=Path), help="Write bundle JSON to file")
@click.pass_context
def bundle(
    ctx: click.Context,
    window_hours: int,
    mode: str,
    dry_run: bool,
    output: Optional[Path],
) -> None:
    """Build a facts bundle for LLM generation.

    Creates a deterministic facts bundle containing:
    - Market snapshot (indices + optional cross-assets)
    - Selected news items (with diversity constraints)
    - Calendar events (placeholder)
    - Optional spotlight content

    The bundle is the sole source of truth for the generator LLM.
    Run this after ingestion, scoring, and enrichment.
    """
    import json

    from argus.facts_bundle import BundleBuilderConfig, FactsBundleBuilder

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    # Build config from main config
    builder_config = BundleBuilderConfig.from_argus_config(config, run_mode=mode)
    builder_config = BundleBuilderConfig(
        stream_name=builder_config.stream_name,
        run_mode=mode,
        window_hours=window_hours,
        min_items=builder_config.min_items,
        max_items=builder_config.max_items,
        max_per_topic=builder_config.max_per_topic,
        max_per_source=builder_config.max_per_source,
        enriched_bonus=builder_config.enriched_bonus,
        include_cross_assets=builder_config.include_cross_assets,
        spotlight=builder_config.spotlight,
    )

    if dry_run:
        click.echo(f"Dry run: building bundle (window: {window_hours} hours, mode: {mode})...")
        click.echo()
        click.echo("Bundle configuration:")
        click.echo(f"  Stream: {builder_config.stream_name}")
        click.echo(f"  Mode: {mode}")
        click.echo(f"  Window: {window_hours} hours")
        click.echo(f"  Min/Max items: {builder_config.min_items}/{builder_config.max_items}")
        click.echo(f"  Max per topic: {builder_config.max_per_topic}")
        click.echo(f"  Max per source: {builder_config.max_per_source}")
        click.echo(f"  Enriched bonus: {builder_config.enriched_bonus}")
        click.echo()

    click.echo(f"Building facts bundle (window: {window_hours} hours, mode: {mode})...")

    try:
        builder = FactsBundleBuilder(config=builder_config)
        facts_bundle, stats = builder.build()
    except ValueError as e:
        click.echo(f"Error building bundle: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        raise SystemExit(1)

    click.echo()
    click.echo("=== Bundle Built ===")
    click.echo(f"Version: {facts_bundle.version}")
    click.echo(f"Generated at: {facts_bundle.generated_at.isoformat()}")
    click.echo(f"Trading date: {facts_bundle.trading_date.isoformat()}")
    click.echo()
    click.echo("Market Snapshot:")
    click.echo(
        f"  S&P 500: {facts_bundle.market_snapshot.sp500.level} ({facts_bundle.market_snapshot.sp500.change_1d_pct:+}%)"
    )
    click.echo(
        f"  Dow: {facts_bundle.market_snapshot.dow.level} ({facts_bundle.market_snapshot.dow.change_1d_pct:+}%)"
    )
    click.echo(
        f"  Nasdaq: {facts_bundle.market_snapshot.nasdaq.level} ({facts_bundle.market_snapshot.nasdaq.change_1d_pct:+}%)"
    )
    click.echo()
    click.echo("News Items:")
    for item in facts_bundle.news_items:
        topic_str = f"[{item.topic}]" if item.topic else "[other]"
        click.echo(f"  [{item.impact_score:3d}] {topic_str} {item.title[:50]}...")
        click.echo(f"        Source: {item.source_name}")
    click.echo()
    click.echo("Statistics:")
    click.echo(f"  Candidates: {stats.total_candidates}")
    click.echo(f"  Selected: {stats.selected_items}")
    click.echo(f"  Enriched: {stats.enriched_items}")
    click.echo(f"  Skipped (topic): {stats.skipped_by_topic}")
    click.echo(f"  Skipped (source): {stats.skipped_by_source}")
    click.echo(f"  Calendar events: {stats.calendar_events}")
    click.echo(f"  Has spotlight: {stats.has_spotlight}")
    click.echo(f"  Duration: {stats.duration_seconds:.2f}s")

    # Output to file if requested
    if output:
        bundle_json = json.dumps(facts_bundle.to_dict(), indent=2)
        output.write_text(bundle_json)
        click.echo()
        click.echo(f"Bundle written to: {output}")

    if dry_run:
        click.echo()
        click.echo("Dry run complete. Bundle not saved to database.")
