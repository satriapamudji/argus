"""CLI entrypoint for Argus."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from . import __version__
from .config import ArgusConfig, UnknownStreamError


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
@click.option(
    "--stream", default=None, help="Stream name (required when using multi-stream config)"
)
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
@click.option(
    "--skip-publish",
    is_flag=True,
    default=False,
    help="Run pipeline but don't send to Telegram",
)
@click.option(
    "--print-message",
    is_flag=True,
    default=False,
    help="Print the final generated message to stdout at the end of the run",
)
@click.option(
    "--save-message",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the final generated message to a file",
)
@click.option(
    "--skip-scoring",
    is_flag=True,
    default=False,
    help="Assume items are already scored",
)
@click.option(
    "--skip-enrichment",
    is_flag=True,
    default=False,
    help="Assume items are already enriched",
)
@click.option(
    "--include-ingest",
    is_flag=True,
    default=False,
    help="Trigger ingestion before pipeline",
)
@click.option(
    "--conditional",
    is_flag=True,
    default=False,
    help="For monday_preview: check risk_score threshold",
)
@click.option(
    "--force-publish",
    is_flag=True,
    default=False,
    help="Override conditional check (always publish)",
)
@click.option(
    "--force-skip",
    is_flag=True,
    default=False,
    help="Override conditional check (never publish)",
)
@click.pass_context
def run(
    ctx: click.Context,
    stream: Optional[str],
    mode: str,
    dry_run: bool,
    skip_publish: bool,
    print_message: bool,
    save_message: Optional[Path],
    skip_scoring: bool,
    skip_enrichment: bool,
    include_ingest: bool,
    conditional: bool,
    force_publish: bool,
    force_skip: bool,
) -> None:
    """Execute a run for the specified stream and mode.

    Examples:

        # Basic dry run to see configuration
        argus run --stream us_markets --mode us_close --dry-run

        # Full execution
        argus run --stream us_markets --mode us_close

        # Skip publishing (generate message but don't send)
        argus run --stream us_markets --mode us_close --skip-publish

        # Monday preview with conditional gate
        argus run --stream us_markets --mode monday_preview --conditional

        # Force publish monday preview regardless of risk score
        argus run --stream us_markets --mode monday_preview --force-publish
    """
    from argus.orchestrator import OrchestratorOptions, RunOrchestrator, RunMode, RunStatus

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if stream is None:
        if len(config.streams) > 1:
            click.echo(
                "Error: --stream is required when config.yaml defines multiple streams. "
                f"Available: {', '.join(config.list_streams())}",
                err=True,
            )
            raise SystemExit(2)

        # Single-stream backward compatibility
        stream = config.stream.name

    try:
        config.select_stream(stream)
    except UnknownStreamError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(2)

    # Build orchestrator options
    options = OrchestratorOptions(
        dry_run=dry_run,
        skip_publish=skip_publish,
        skip_scoring=skip_scoring,
        skip_enrichment=skip_enrichment,
        include_ingest=include_ingest,
        conditional=conditional or config.stream.monday_preview.conditional,
        force_publish=force_publish or config.stream.monday_preview.force_publish,
        force_skip=force_skip or config.stream.monday_preview.force_skip,
        risk_threshold=config.stream.monday_preview.risk_threshold,
    )

    if save_message is not None:
        save_message.parent.mkdir(parents=True, exist_ok=True)

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
        click.echo("Options:")
        click.echo(f"  skip_publish: {options.skip_publish}")
        click.echo(f"  skip_scoring: {options.skip_scoring}")
        click.echo(f"  skip_enrichment: {options.skip_enrichment}")
        click.echo(f"  include_ingest: {options.include_ingest}")
        click.echo(f"  conditional: {options.conditional}")
        click.echo(f"  force_publish: {options.force_publish}")
        click.echo(f"  force_skip: {options.force_skip}")
        click.echo()
        click.echo("=== Dry run complete ===")
        return

    # Execute the orchestrator
    click.echo(f"Running stream '{stream}' in mode '{mode}'...")

    run_mode = RunMode.from_string(mode)
    orchestrator = RunOrchestrator(
        config=config,
        mode=run_mode,
        options=options,
    )

    result = orchestrator.run()

    # Report results
    click.echo()
    if result.status == RunStatus.COMPLETED:
        click.echo(click.style("[OK] Run completed successfully", fg="green"))
        click.echo(f"  Run ID: {result.run_id}")
        click.echo(f"  Message ID: {result.message_id}")
        if result.telegram_message_id:
            click.echo(f"  Telegram Message ID: {result.telegram_message_id}")
        if result.timings:
            click.echo(f"  Total time: {result.timings.total_ms}ms")
    elif result.status == RunStatus.SKIPPED:
        click.echo(click.style("[SKIP] Run skipped", fg="yellow"))
        if result.holiday_info and result.holiday_info.should_skip:
            click.echo(f"  Reason: {result.holiday_info.behavior_applied}")
        elif result.was_conditional_skip:
            click.echo("  Reason: Risk score below threshold")
            if result.risk_score:
                click.echo(f"  Risk score: {result.risk_score.total}")
    elif result.status == RunStatus.FAILED:
        click.echo(click.style("[FAIL] Run failed", fg="red"))
        click.echo(f"  Error: {result.error}")
        if result.run_id:
            click.echo(f"  Run ID: {result.run_id}")

    # Show risk score breakdown for monday_preview
    if result.risk_score:
        click.echo()
        click.echo("Risk Score Breakdown:")
        click.echo(f"  Calendar: {result.risk_score.calendar_score}/60")
        click.echo(f"  Market: {result.risk_score.market_score}/30")
        click.echo(f"  Headline: {result.risk_score.headline_score}/30")
        click.echo(f"  Total: {result.risk_score.total}/100")

    if print_message or save_message is not None:
        if not result.message_content:
            click.echo()
            click.echo(
                click.style("[WARN] No message content available to print/save", fg="yellow")
            )
        else:
            if print_message:
                click.echo()
                click.echo("--- FINAL GENERATED MESSAGE ---")
                click.echo(result.message_content)
                click.echo("--- END MESSAGE ---")

            if save_message is not None:
                save_message.write_text(result.message_content)
                click.echo()
                click.echo(f"Message written to: {save_message}")


@cli.group()
def db() -> None:
    """Database management commands."""
    from dotenv import load_dotenv

    load_dotenv()


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
        click.echo(f"  [OK] {version}")


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
            click.echo(f"  [OK] {version}")
    else:
        click.echo("  (none)")

    click.echo("\nPending migrations:")
    if pending:
        for version, _ in pending:
            click.echo(f"  [*] {version}")
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
    run_record = create_run(conn, stream_name="us_markets", run_mode="us_close")
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
    click.echo("\nTest data inserted successfully.")


def main() -> None:
    """Entry point."""
    cli()


@cli.command()
@click.option(
    "--stream", default=None, help="Stream name (required when using multi-stream config)"
)
@click.option("--dry-run", is_flag=True, help="Parse feeds but don't insert into DB")
@click.pass_context
def ingest(ctx: click.Context, stream: Optional[str], dry_run: bool) -> None:
    """Run news ingestion using configured provider.

    Uses the ingestion provider configured in stream.providers.ingestion:
    - 'rss': Poll RSS feeds from allowlist files
    - 'api_newsapi': Fetch from TheNewsAPI.com

    Designed to be run via cron at regular intervals (e.g., every 10 minutes).
    """
    from argus.db.connection import get_connection
    from argus.pipeline.registry import get_ingestion_provider

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if stream is None:
        if len(config.streams) > 1:
            click.echo(
                "Error: --stream is required when config.yaml defines multiple streams. "
                f"Available: {', '.join(config.list_streams())}",
                err=True,
            )
            raise SystemExit(2)

        # Single-stream backward compatibility
        stream = config.stream.name

    try:
        config.select_stream(stream)
    except UnknownStreamError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(2)

    provider_key = config.stream.providers.ingestion
    click.echo(f"Ingestion provider: {provider_key}")

    # Dry run for RSS only (API dry-run not implemented)
    if dry_run and provider_key == "rss":
        from argus.ingestion.rss_parser import parse_feed

        feed_urls = config.get_rss_feeds()

        if not feed_urls:
            click.echo("No RSS feeds configured. Add feeds to rss/*.txt files.")
            return

        click.echo(f"Dry run: parsing {len(feed_urls)} feed(s)...")
        click.echo()

        total_entries = 0
        for url in feed_urls:
            entries, error = parse_feed(url)
            if error:
                click.echo(f"  ERROR {url}")
                click.echo(f"    Error: {error}")
            else:
                click.echo(f"  OK {url}: {len(entries)} entries")
                total_entries += len(entries)

        click.echo()
        click.echo(f"Total entries found: {total_entries}")
        click.echo("Dry run complete. No items inserted.")
        return

    if dry_run and provider_key != "rss":
        click.echo(f"Dry run not supported for provider '{provider_key}'. Running normally...")

    # Get the provider and run ingestion
    try:
        provider = get_ingestion_provider(config.stream)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    try:
        stats = provider.run(config=config, conn=conn)
    finally:
        conn.close()

    click.echo()
    click.echo("=== Ingestion Complete ===")
    click.echo(f"Feeds/pages processed: {stats.feeds_processed}")
    click.echo(f"Feeds/pages failed: {stats.feeds_failed}")
    click.echo(f"Entries found: {stats.entries_found}")
    click.echo(f"New entries: {stats.entries_new}")
    click.echo(f"Duplicates skipped: {stats.entries_duplicate}")

    if stats.errors:
        click.echo()
        click.echo("Errors:")
        for err in stats.errors:
            click.echo(f"  - {err}")


@cli.group()
def newsapi() -> None:
    """TheNewsAPI utilities."""
    pass


@newsapi.command()
@click.option("--language", default="en", help="Filter by language code (default: en)")
@click.option("--locale", default="us", help="Filter by locale (default: us)")
@click.option("--categories", default=None, help="Comma-separated categories to filter")
@click.option("--limit", default=50, help="Maximum sources to display (default: 50)")
def sources(language: str, locale: str, categories: Optional[str], limit: int) -> None:
    """List available news sources from TheNewsAPI.

    Fetches and displays available source domains that can be used
    in the 'domains' setting in apis/newsapi_{stream}.txt.

    Examples:

        # List all US English business sources
        argus newsapi sources --categories business

        # List UK sources
        argus newsapi sources --locale gb

        # List all available sources
        argus newsapi sources --limit 100
    """
    from argus.config import NewsApiConfig
    from argus.pipeline.providers.news_api_client import NewsApiClient, NewsApiError

    # Create minimal config for sources lookup
    config = NewsApiConfig()

    if not config.api_keys:
        click.echo(
            "Error: No API keys configured. Set NEWS_API_KEYS environment variable.",
            err=True,
        )
        raise SystemExit(1)

    # Parse categories if provided
    cats = None
    if categories:
        cats = [c.strip() for c in categories.split(",") if c.strip()]

    click.echo(f"Fetching sources (locale={locale}, language={language})...")

    try:
        with NewsApiClient(config) as client:
            result = client.get_sources(
                locale=locale,
                language=language,
                categories=cats,
            )
    except NewsApiError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        raise SystemExit(1)

    sources_data = result.get("data", [])

    if not sources_data:
        click.echo("No sources found matching the criteria.")
        return

    click.echo()
    click.echo(f"Found {len(sources_data)} source(s):")
    click.echo()

    # Display sources in a table format
    displayed = 0
    for source in sources_data:
        if displayed >= limit:
            click.echo(f"\n... and {len(sources_data) - limit} more (use --limit to show more)")
            break

        domain = source.get("domain_url", "unknown")
        name = source.get("source_id", "unknown")
        src_locale = source.get("locale", "?")
        src_cats = source.get("categories", [])

        click.echo(f"  {domain}")
        click.echo(f"    Name: {name}, Locale: {src_locale}")
        if src_cats:
            click.echo(f"    Categories: {', '.join(src_cats)}")
        click.echo()
        displayed += 1

    click.echo()
    click.echo("To use these sources, add domains to apis/newsapi_{stream}.txt:")
    click.echo("  domains=reuters.com,bloomberg.com,wsj.com")


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

    Scores unscored news items from the window using the configured
    scoring provider (heuristic_v1 or heuristic_v2).

    Run this after ingestion to prepare items for enrichment.
    """
    from argus.db.connection import get_connection
    from argus.pipeline.registry import get_scoring_provider

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if not config.stream.scoring.enabled:
        click.echo("Scoring is disabled in configuration.")
        return

    provider_key = config.stream.providers.scoring
    click.echo(f"Scoring provider: {provider_key}")

    if dry_run:
        click.echo(f"Dry run: scoring candidates (window: {window_hours} hours)...")
        click.echo()

        # Show config
        click.echo("Scoring configuration:")
        click.echo(f"  Max items per run: {config.stream.scoring.max_items_per_run}")
        click.echo(f"  Provider: {provider_key}")
        click.echo(f"  LLM triage enabled: {config.stream.scoring.llm_triage_enabled}")
        if config.stream.scoring.llm_triage_enabled:
            click.echo(f"  LLM model: {config.stream.scoring.llm_model}")
            click.echo(f"  LLM max items: {config.stream.scoring.llm_max_items}")
        click.echo()

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    try:
        provider = get_scoring_provider(config.stream)
        stats = provider.run(
            config=config,
            conn=conn,
            window_hours=window_hours,
            dry_run=dry_run,
        )
    finally:
        conn.close()

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
@click.option("--days", default=1.0, type=float, help="Lookback window in days (default 1.0)")
@click.option("--limit", default=800, type=int, help="Max items to load from DB (default 800)")
@click.option(
    "--movers", default=25, type=int, help="How many biggest movers to print (default 25)"
)
@click.option("--topk", default=12, type=int, help="How many top items in JSON output (default 12)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON instead of text")
@click.pass_context
def evaluate(
    ctx: click.Context,
    days: float,
    limit: int,
    movers: int,
    topk: int,
    as_json: bool,
) -> None:
    """Compare old vs new scoring rankings and evaluate quality.

    Runs deterministic evaluation on scored news items:
    - Loads items with existing scores from DB (old)
    - Re-scores with in-memory heuristic_v2 (new)
    - Classifies items as A/B/C/D based on macro-heavy rubric
    - Reports TopK composition, inversions, spam counts
    - Shows biggest rank movers between old and new

    Requires DATABASE_URL in environment.

    Examples:
        argus evaluate --days 1
        argus evaluate --days 7 --limit 500
        argus evaluate --topk 20 --movers 50
        argus evaluate --json
    """
    import json as json_module
    import os

    from dotenv import load_dotenv
    import psycopg2

    from argus.config import ArgusConfig
    from argus.scoring.heuristics_v2 import score_candidates_v2
    from argus.scoring.types import ScoringCandidate

    load_dotenv()

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    # Load items from DB
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        click.echo("Error: DATABASE_URL not set in environment", err=True)
        raise SystemExit(1)

    click.echo(f"Loading scored items (days={days}, limit={limit})...")

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        query = """
        SELECT
            ni.id,
            ni.fingerprint_id,
            ni.source_name,
            ni.source_url,
            ni.title,
            COALESCE(ni.snippet, '') AS snippet,
            ni.raw_metadata->>'feed_url' AS feed_url,
            ni.ingested_at,
            ni.published_at,
            nf.simhash,
            ns.impact_score,
            ns.scorer_version
        FROM news_items ni
        JOIN news_fingerprints nf ON ni.fingerprint_id = nf.id
        JOIN news_scores ns ON ni.id = ns.news_item_id
        WHERE ni.ingested_at >= NOW() - INTERVAL %s
        ORDER BY ns.impact_score DESC
        LIMIT %s
        """
        cur.execute(query, (f"{days} days", limit))
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        click.echo(f"Error: Database query failed: {e}", err=True)
        raise SystemExit(1)

    if not rows:
        click.echo("No scored items found in window.")
        return

    click.echo(f"Loaded {len(rows)} items.")
    click.echo()

    # Build data structures
    class DbRow:
        def __init__(self, row: tuple) -> None:
            self.id = row[0]
            self.fingerprint_id = row[1]
            self.source_name = row[2]
            self.source_url = row[3]
            self.title = row[4]
            self.snippet = row[5]
            self.feed_url = row[6]
            self.ingested_at = row[7]
            self.published_at = row[8]
            self.simhash = row[9]
            self.old_impact_score = int(row[10])
            self.old_scorer_version = row[11]

    db_rows = [DbRow(r) for r in rows]

    # OLD ranking (as loaded from DB)
    def to_eval_item(row: DbRow, impact_score: int) -> dict:
        return {
            "id": row.id,
            "source_name": row.source_name,
            "source_url": row.source_url,
            "title": row.title,
            "snippet": row.snippet,
            "feed_url": row.feed_url,
            "impact_score": int(impact_score),
        }

    old_ranked = [to_eval_item(r, r.old_impact_score) for r in db_rows]

    # NEW ranking (in-memory v2 scores)
    candidates = [
        ScoringCandidate(
            news_item_id=r.id,
            fingerprint_id=r.fingerprint_id,
            source_name=r.source_name,
            source_url=r.source_url,
            title=r.title,
            snippet=r.snippet,
            published_at=r.published_at,
            ingested_at=r.ingested_at,
            simhash=r.simhash,
        )
        for r in db_rows
    ]

    recent_simhashes = [r.simhash for r in db_rows if r.simhash is not None]
    v2_results = score_candidates_v2(
        candidates, config.stream.scoring, recent_simhashes=recent_simhashes
    )

    v2_score_by_id = {res.news_item_id: res.impact_score for res in v2_results}
    new_ranked = [to_eval_item(r, v2_score_by_id.get(r.id, 0)) for r in db_rows]
    new_ranked.sort(key=lambda it: it["impact_score"], reverse=True)

    # Import eval framework functions (inline to avoid dependency at module load)
    import re

    def _text(item: dict) -> str:
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        return f"{title} {snippet}".strip().lower()

    def _has_keyword(text: str, kw: str) -> bool:
        kw = kw.strip().lower()
        if not kw:
            return False
        if any(ch.isspace() for ch in kw):
            return kw in text
        if len(kw) <= 4:
            return re.search(rf"\\b{re.escape(kw)}\\b", text) is not None
        return kw in text

    # Classification patterns
    D_PATTERNS = [
        (
            "pundit_content",
            r"\b(jim\s+cramer|cramer\s+says|motley\s+fool|seeking\s+alpha|mad\s+money)\b",
        ),
        (
            "stock_picks",
            r"\b(stocks?\s+to\s+buy|top\s+\d+\s+stocks?|best\s+(dividend\s+)?stocks?|should\s+you\s+buy|hot\s+stocks?)\b",
        ),
        (
            "fomo_bait",
            r"\b(if\s+you('d|\s+had)\s+invested|millionaire[\s-]maker|could\s+(double|triple|10x)|get\s+rich|next\s+(amazon|apple|nvidia|tesla))\b",
        ),
        (
            "why_stock_moved",
            r"\bwhy\s+\w+\s+(stock\s+)?(crashed|soared|plunged|skyrocketed|fell|jumped)\b",
        ),
        (
            "listicle",
            r"\b(\d+\s+reasons?\s+why|\d+\s+best|\d+\s+worst|\d+\s+things?\s+to|top\s+\d+\s+reasons?)\b",
        ),
    ]
    D_REGEX = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in D_PATTERNS]

    EARNINGS_ROUTINE = re.compile(
        r"\b(beats?\s+estimates?|misses?\s+estimates?|tops?\s+expectations?|falls?\s+short|q\d\s+profit|q\d\s+earnings)\b",
        re.IGNORECASE,
    )
    EARNINGS_SYSTEMIC = re.compile(
        r"\b(profit\s+warning|guidance\s+cut|guidance\s+lower|sector[-\s]wide|industry[-\s]wide|bellwether|mass\s+layoffs|restructuring|large\s+layoffs)\b",
        re.IGNORECASE,
    )

    A_KEYWORDS = {
        "central_bank": [
            "fed",
            "federal reserve",
            "fomc",
            "powell",
            "ecb",
            "boe",
            "boj",
            "rate cut",
            "rate hike",
            "interest rate",
            "qt",
            "qe",
        ],
        "macro_data": [
            "cpi",
            "pce",
            "inflation",
            "deflation",
            "gdp",
            "nfp",
            "nonfarm",
            "payrolls",
            "jobs report",
            "jobless claims",
            "ism",
            "pmi",
        ],
        "geopolitics_policy": [
            "tariff",
            "tariffs",
            "sanctions",
            "embargo",
            "trade war",
            "war",
            "conflict",
            "invasion",
        ],
        "energy_shock": ["opec", "opec+", "supply disruption", "pipeline", "shipping", "hormuz"],
        "credit_systemic": [
            "credit spread",
            "high yield",
            "default",
            "bank stress",
            "liquidity",
            "sovereign",
            "sovereign debt",
        ],
    }

    B_KEYWORDS = {
        "market_wrap": [
            "stock market today",
            "markets",
            "shares",
            "stocks",
            "s&p",
            "dow",
            "nasdaq",
            "close",
            "rally",
            "selloff",
        ],
        "rates_fx": ["yield", "yields", "treasury", "treasuries", "dollar", "dxy", "fx", "forex"],
        "commodities": ["oil", "crude", "wti", "brent", "gold", "silver", "copper", "natural gas"],
    }

    TEMPLATE_MARKET_TODAY = re.compile(r"\bstock\s+market\s+today\b", re.IGNORECASE)

    def classify(item: dict) -> tuple[str, list[str]]:
        t = _text(item)
        reasons: list[str] = []

        # D overrides
        for name, rx in D_REGEX:
            if rx.search(t):
                reasons.append(f"D:{name}")
        if reasons:
            return "D", reasons

        # Earnings handling
        if EARNINGS_SYSTEMIC.search(t):
            return "B", ["B:systemic_earnings"]
        if EARNINGS_ROUTINE.search(t):
            return "C", ["C:routine_earnings"]

        # A detection
        a_reasons = []
        for group, kws in A_KEYWORDS.items():
            if any(_has_keyword(t, kw) for kw in kws):
                a_reasons.append(f"A:{group}")
        if a_reasons:
            return "A", a_reasons

        # B detection
        b_reasons = []
        for group, kws in B_KEYWORDS.items():
            if any(_has_keyword(t, kw) for kw in kws):
                b_reasons.append(f"B:{group}")
        if b_reasons:
            return "B", b_reasons

        return "C", ["C:default"]

    def annotate(items: list[dict]) -> list[dict]:
        out = []
        for it in items:
            label, reasons = classify(it)
            it2 = dict(it)
            it2["_class"] = {"label": label, "reasons": reasons}
            out.append(it2)
        return out

    # Annotate both rankings
    old_annotated = annotate(old_ranked)
    new_annotated = annotate(new_ranked)

    # Compute metrics
    def topk_counts(items: list[dict], k: int) -> dict[str, int]:
        counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for item in items[:k]:
            label = item["_class"]["label"]
            counts[label] += 1
        return counts

    def spam_count(items: list[dict], k: int) -> int:
        return sum(1 for it in items[:k] if TEMPLATE_MARKET_TODAY.search(_text(it)))

    def inversions(items: list[dict], k: int) -> int:
        top = items[:k]
        hard = 0
        for i, it in enumerate(top):
            if it["_class"]["label"] == "D":
                if any(it2["_class"]["label"] in ("A", "B") for it2 in top[i + 1 :]):
                    hard += 1
        return hard

    # Print results
    def print_eval(name: str, items: list[dict]) -> dict:
        c12 = topk_counts(items, 12)
        c20 = topk_counts(items, 20)
        c50 = topk_counts(items, 50)
        spam12 = spam_count(items, 12)
        inv50 = inversions(items, 50)

        summary = {
            "name": name,
            "top12": c12,
            "top20": c20,
            "top50": c50,
            "spam12": spam12,
            "inversions50_hard": inv50,
        }

        if not as_json:
            click.echo("=" * 70)
            click.echo(name)
            click.echo("=" * 70)
            click.echo(
                f"Top12: A={c12['A']} B={c12['B']} C={c12['C']} D={c12['D']} | spam={spam12}"
            )
            click.echo(f"Top20: A={c20['A']} B={c20['B']} C={c20['C']} D={c20['D']}")
            click.echo(
                f"Top50: A={c50['A']} B={c50['B']} C={c50['C']} D={c50['D']} | inv_hard={inv50}"
            )

            # Contract check
            violations = []
            if not (c12["A"] >= 6 and c12["B"] >= 4 and c12["C"] <= 2 and c12["D"] == 0):
                violations.append("Top12 composition")
            if not (c20["A"] >= 8 and c20["C"] <= 5 and c20["D"] <= 1):
                violations.append("Top20 composition")
            d_rate = c50["D"] / 50.0
            if d_rate > 0.05:
                violations.append(f"Top50 D-rate ({d_rate:.1%})")
            if inv50 > 0:
                violations.append("Hard inversions")
            if spam12 > 1:
                violations.append("Spam")

            if violations:
                click.echo(click.style(f"Contract: FAIL ({', '.join(violations)})", fg="red"))
            else:
                click.echo(click.style("Contract: PASS", fg="green"))

        # Top-k items
        top_items = []
        for i, it in enumerate(items[:topk], 1):
            top_items.append(
                {
                    "rank": i,
                    "id": it.get("id"),
                    "impact_score": it.get("impact_score"),
                    "class": it["_class"]["label"],
                    "title": (it.get("title") or "")[:100],
                    "reasons": it["_class"]["reasons"],
                }
            )

        if not as_json:
            click.echo(f"\nTop{topk}:")
            for item in top_items:
                click.echo(
                    f"  [{item['rank']:2}] {item['class']} {item['impact_score']:3} | {item['title'][:60]}..."
                )

        summary["top_items"] = top_items
        return summary

    old_summary = print_eval("OLD (DB scores)", old_annotated)
    if not as_json:
        click.echo()
    new_summary = print_eval("NEW (heuristic_v2)", new_annotated)

    # Biggest movers
    old_rank = {it["id"]: i for i, it in enumerate(old_annotated, 1)}
    new_rank = {it["id"]: i for i, it in enumerate(new_annotated, 1)}

    movers_list = []
    for r in db_rows:
        if r.id in old_rank and r.id in new_rank:
            delta = old_rank[r.id] - new_rank[r.id]
            movers_list.append(
                {
                    "id": r.id,
                    "delta": delta,
                    "old_rank": old_rank[r.id],
                    "new_rank": new_rank[r.id],
                    "old_score": r.old_impact_score,
                    "new_score": v2_score_by_id.get(r.id, 0),
                    "title": r.title,
                }
            )

    movers_list.sort(key=lambda m: abs(m["delta"]), reverse=True)
    top_movers = movers_list[:movers]

    if not as_json:
        click.echo()
        click.echo("=" * 70)
        click.echo(f"Biggest rank movers (top {movers})")
        click.echo("=" * 70)
        for m in top_movers:
            sign = "+" if m["delta"] >= 0 else ""
            click.echo(
                f"{sign}{m['delta']:4} | {m['old_rank']:4} -> {m['new_rank']:4} | "
                f"{m['old_score']:3} -> {m['new_score']:3} | {m['title'][:60]}..."
            )

    if as_json:
        report = {
            "meta": {
                "days": days,
                "limit": limit,
                "items_loaded": len(db_rows),
            },
            "old": old_summary,
            "new": new_summary,
            "movers": top_movers,
        }
        click.echo(json_module.dumps(report, indent=2, ensure_ascii=False))


@cli.command()
@click.option(
    "--bundle-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to facts bundle JSON file",
)
@click.option(
    "--mode",
    type=click.Choice(["us_close", "weekend_wrap", "monday_preview"]),
    default=None,
    help="Override generation mode (defaults to bundle's run_mode)",
)
@click.option("--dry-run", is_flag=True, help="Show prompts but don't call LLM")
@click.option("--output", type=click.Path(path_type=Path), help="Write generated message to file")
@click.pass_context
def generate(
    ctx: click.Context,
    bundle_file: Path,
    mode: Optional[str],
    dry_run: bool,
    output: Optional[Path],
) -> None:
    """Generate a Telegram message from a facts bundle.

    Uses LLM (GPT-4.1 via OpenRouter) to transform a facts bundle into
    a formatted market update message ready for Telegram.

    The bundle must be created first using `argus bundle --output bundle.json`.
    """
    import json

    from argus.facts_bundle.types import FactsBundle
    from argus.generator import (
        GenerationError,
        GenerationMode,
        MessageGenerator,
        build_news_contexts,
        build_user_prompt,
        get_system_prompt,
    )
    from argus.generator.types import GeneratorConfig as GenConfig

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    # Load bundle from file
    click.echo(f"Loading bundle from: {bundle_file}")
    try:
        with open(bundle_file, "r") as f:
            bundle_data = json.load(f)
        bundle = FactsBundle.from_dict(bundle_data)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in bundle file: {e}", err=True)
        raise SystemExit(1)
    except (KeyError, ValueError) as e:
        click.echo(f"Error: Invalid bundle format: {e}", err=True)
        raise SystemExit(1)

    # Determine generation mode
    if mode is not None:
        gen_mode = GenerationMode.from_string(mode)
    else:
        gen_mode = GenerationMode.from_string(bundle.run_mode)

    click.echo(f"Generation mode: {gen_mode.value}")
    click.echo(f"News items in bundle: {len(bundle.news_items)}")
    click.echo(f"Calendar events: {len(bundle.calendar_events)}")
    click.echo(f"Has spotlight: {bundle.spotlight is not None}")
    click.echo()

    # Build generator config from app config
    generator_config = GenConfig(
        enabled=config.stream.generator.enabled,
        model=config.stream.generator.model,
        temperature=config.stream.generator.temperature,
        max_retries=config.stream.generator.max_retries,
        timeout_seconds=config.stream.generator.timeout_seconds,
    )

    if not generator_config.enabled:
        click.echo("Error: Generator is disabled in configuration", err=True)
        raise SystemExit(1)

    if dry_run:
        click.echo("=== Dry Run: Showing prompts ===")
        click.echo()

        # Build prompts
        news_contexts = build_news_contexts(bundle)
        system_prompt = get_system_prompt(gen_mode)

        # Get max words from constraints
        word_limits = {
            GenerationMode.US_CLOSE: config.stream.constraints.max_words_daily,
            GenerationMode.WEEKEND_WRAP: config.stream.constraints.max_words_weekend,
            GenerationMode.MONDAY_PREVIEW: config.stream.constraints.max_words_preview,
        }
        max_words = word_limits[gen_mode]

        user_prompt = build_user_prompt(bundle, news_contexts, gen_mode, max_words)

        click.echo("--- SYSTEM PROMPT ---")
        click.echo(system_prompt)
        click.echo()
        click.echo("--- USER PROMPT ---")
        click.echo(user_prompt)
        click.echo()
        click.echo("--- NEWS CONTEXTS ---")
        for nc in news_contexts:
            click.echo(f"  [{nc.ref_number}] (ID={nc.news_item_id}) {nc.title[:50]}...")
        click.echo()
        click.echo("Dry run complete. No LLM call made.")
        return

    click.echo(f"Calling OpenRouter ({generator_config.model})...")
    click.echo()

    try:
        with MessageGenerator(
            config=generator_config,
            constraints=config.stream.constraints,
        ) as generator:
            result, validation = generator.generate(bundle, gen_mode)
    except GenerationError as e:
        click.echo(f"Error: Generation failed: {e}", err=True)
        raise SystemExit(1)

    click.echo("=== Generation Complete ===")
    click.echo(f"Word count: {result.word_count}")
    click.echo(f"Sources referenced: {result.sources_count}")
    click.echo(f"LLM duration: {result.llm_duration_seconds:.2f}s")
    click.echo(f"Retries: {result.retry_count}")
    click.echo(f"Validation: {'valid' if validation.is_valid else 'fallback'}")
    if validation.errors:
        click.echo(f"Validation errors: {', '.join(validation.errors)}")
    if result.error:
        click.echo(f"Warning (recovered): {result.error}")
    click.echo()
    click.echo("--- GENERATED MESSAGE (Escaped) ---")
    click.echo(result.message)
    click.echo()

    # Output to file if requested
    if output:
        output.write_text(result.message)
        click.echo(f"Message written to: {output}")

        # Also write raw version
        raw_path = output.with_suffix(".raw.md")
        raw_path.write_text(result.message_raw)
        click.echo(f"Raw message written to: {raw_path}")


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
        economic_calendar=builder_config.economic_calendar,
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


@cli.group()
def calendar() -> None:
    """Economic calendar management commands."""
    from dotenv import load_dotenv

    load_dotenv()


@calendar.command()
@click.pass_context
def refresh(ctx: click.Context) -> None:
    """Refresh economic calendar data from ForexFactory.

    Fetches the latest high-impact USD economic events and stores
    them in the database for use in the "Key Dates (UTC)" section.
    """
    from argus.adapters.economic_calendar import EconomicCalendarAdapter
    from argus.db.connection import get_connection

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if not config.stream.economic_calendar.enabled:
        click.echo("Economic calendar is disabled in configuration.")
        click.echo("Set economic_calendar.enabled = true to enable.")
        return

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo("Refreshing economic calendar from ForexFactory...")
    click.echo(f"  Feed URL: {config.stream.economic_calendar.feed_url}")
    click.echo(f"  Countries: {', '.join(config.stream.economic_calendar.countries)}")
    click.echo(f"  Impact filter: {', '.join(config.stream.economic_calendar.impact_filter)}")
    click.echo()

    adapter = EconomicCalendarAdapter(conn, config.stream.economic_calendar)
    result = adapter.force_refresh()
    conn.close()

    if result.success:
        click.echo("=== Refresh Complete ===")
        click.echo(f"Events fetched: {result.events_fetched}")
        click.echo(f"Events inserted: {result.events_inserted}")
        click.echo(f"Events updated: {result.events_updated}")
        click.echo(f"Duration: {result.duration_seconds:.2f}s")
    else:
        click.echo("=== Refresh Failed ===", err=True)
        for error in result.errors:
            click.echo(f"  Error: {error}", err=True)
        raise SystemExit(1)


@calendar.command()
@click.option("--days", default=7, help="Number of days ahead to show (default 7)")
@click.pass_context
def show(ctx: click.Context, days: int) -> None:
    """Show upcoming economic calendar events.

    Displays high-impact USD events for the next N days.
    """

    from argus.adapters.economic_calendar import EconomicCalendarAdapter
    from argus.config import EconomicCalendarConfig
    from argus.db.connection import get_connection

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    # Override lookahead_days for this display
    calendar_config = EconomicCalendarConfig(
        enabled=True,
        feed_url=config.stream.economic_calendar.feed_url,
        countries=config.stream.economic_calendar.countries,
        impact_filter=config.stream.economic_calendar.impact_filter,
        lookahead_days=days,
        stale_hours=config.stream.economic_calendar.stale_hours,
    )

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    adapter = EconomicCalendarAdapter(conn, calendar_config)

    # Check if data is stale
    if adapter.is_stale():
        click.echo("Warning: Economic calendar data is stale.")
        click.echo("Run 'argus calendar refresh' to update.")
        click.echo()

    events = adapter.get_upcoming_events(auto_refresh=False)
    conn.close()

    if not events:
        click.echo(f"No upcoming events in the next {days} days.")
        click.echo()
        click.echo("This could mean:")
        click.echo("  - No high-impact USD events scheduled")
        click.echo("  - Data hasn't been fetched yet (run 'argus calendar refresh')")
        return

    click.echo(f"=== Upcoming Economic Events (next {days} days) ===")
    click.echo()

    current_date = None
    for event in events:
        event_date = event.timestamp_utc.date()
        if event_date != current_date:
            current_date = event_date
            click.echo(f"--- {event_date.strftime('%A, %b %d')} ---")

        time_str = event.timestamp_utc.strftime("%H:%M UTC")
        click.echo(f"  {time_str} - {event.name}")

    click.echo()
    click.echo(f"Total: {len(events)} event(s)")


@calendar.command(name="status")
@click.pass_context
def calendar_status(ctx: click.Context) -> None:
    """Show economic calendar status and configuration."""
    from argus.adapters.economic_calendar import EconomicCalendarAdapter
    from argus.db.connection import get_connection

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    adapter = EconomicCalendarAdapter(conn, config.stream.economic_calendar)
    status_info = adapter.get_status()
    conn.close()

    # Cast to expected types for type checker
    countries = status_info["countries"]
    impact_filter = status_info["impact_filter"]

    click.echo("=== Economic Calendar Status ===")
    click.echo()
    click.echo("Configuration:")
    click.echo(f"  Enabled: {status_info['enabled']}")
    click.echo(f"  Feed URL: {status_info['feed_url']}")
    if isinstance(countries, list):
        click.echo(f"  Countries: {', '.join(countries)}")
    if isinstance(impact_filter, list):
        click.echo(f"  Impact filter: {', '.join(impact_filter)}")
    click.echo(f"  Lookahead days: {status_info['lookahead_days']}")
    click.echo(f"  Stale hours: {status_info['stale_hours']}")
    click.echo()
    click.echo("Data Status:")
    click.echo(f"  Events in DB: {status_info['event_count']}")
    click.echo(f"  Last fetch: {status_info['last_fetch'] or 'Never'}")
    click.echo(f"  Data stale: {'Yes' if status_info['stale'] else 'No'}")


@cli.command(name="show")
@click.option("--message-id", type=int, help="Message ID to display")
@click.option("--run-id", type=int, help="Run ID to display the most recent message for")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["raw", "escaped", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Which message variant to print",
)
@click.pass_context
def show_message(
    ctx: click.Context,
    message_id: Optional[int],
    run_id: Optional[int],
    output_format: str,
) -> None:
    """Show a generated message from the database.

    Useful to verify the exact Telegram payload after an online run.

    Examples:
        argus show --message-id 15
        argus show --run-id 15
        argus show --run-id 15 --format raw
    """

    from dotenv import load_dotenv

    from argus.db.connection import get_connection
    from argus.db.repository import get_message_by_id, get_messages_by_run_id
    from argus.generator.renderer import escape_markdown_v2

    load_dotenv()

    if (message_id is None and run_id is None) or (message_id is not None and run_id is not None):
        click.echo("Error: Must specify exactly one of --message-id or --run-id", err=True)
        raise SystemExit(1)

    try:
        conn = get_connection()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    try:
        if message_id is not None:
            message = get_message_by_id(conn, message_id)
            if message is None:
                click.echo(f"Error: Message not found: {message_id}", err=True)
                raise SystemExit(1)
        else:
            assert run_id is not None
            messages = get_messages_by_run_id(conn, run_id)
            if not messages:
                click.echo(f"Error: No messages found for run_id={run_id}", err=True)
                raise SystemExit(1)
            message = messages[-1]

        raw = message.content
        escaped = escape_markdown_v2(raw)

        click.echo(f"Message ID: {message.id}")
        click.echo(f"Run ID: {message.run_id}")
        click.echo(f"Validation: {message.validation_status}")
        click.echo(f"Publish: {message.publish_status}")
        if message.telegram_message_id is not None:
            click.echo(f"Telegram Message ID: {message.telegram_message_id}")
        click.echo(f"Created at: {message.created_at}")
        if message.published_at is not None:
            click.echo(f"Published at: {message.published_at}")
        click.echo()

        if output_format.lower() in ("raw", "both"):
            click.echo("--- MESSAGE (Raw) ---")
            click.echo(raw)
            click.echo()

        if output_format.lower() in ("escaped", "both"):
            click.echo("--- MESSAGE (Escaped / MarkdownV2) ---")
            click.echo(escaped)
            click.echo()
    finally:
        conn.close()


@cli.command()
@click.option("--message-id", type=int, help="ID of message to publish from database")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to file containing message content (for testing)",
)
@click.option("--dry-run", is_flag=True, help="Show payload without sending to Telegram")
@click.option("--silent", is_flag=True, help="Send without notification sound")
@click.pass_context
def publish(
    ctx: click.Context,
    message_id: Optional[int],
    file_path: Optional[Path],
    dry_run: bool,
    silent: bool,
) -> None:
    """Publish a message to Telegram.

    Publish a message from the database by ID, or from a file for testing.
    Use --dry-run to see the exact payload without sending.

    Examples:
        argus publish --message-id 123
        argus publish --message-id 123 --dry-run
        argus publish --file message.txt --dry-run
        argus publish --file message.txt --silent
    """
    """Publish a message to Telegram.

    Publish a message from the database by ID, or from a file for testing.
    Use --dry-run to see the exact payload without sending.

    Examples:
        argus publish --message-id 123
        argus publish --message-id 123 --dry-run
        argus publish --file message.txt --dry-run
        argus publish --file message.txt --silent
    """
    import json

    from argus.publisher import publish_content, run_publish

    config_path = ctx.obj.get("config_path")
    config = ArgusConfig.load(config_path)

    if message_id is None and file_path is None:
        click.echo("Error: Must specify either --message-id or --file", err=True)
        raise SystemExit(1)

    if message_id is not None and file_path is not None:
        click.echo("Error: Cannot specify both --message-id and --file", err=True)
        raise SystemExit(1)

    telegram_config = config.stream.telegram

    if file_path is not None:
        # Publish from file (for testing)
        content = file_path.read_text()
        click.echo(f"Publishing from file: {file_path}")
        click.echo(f"Content length: {len(content)} chars")
        click.echo()

        result = publish_content(
            content=content,
            config=telegram_config,
            dry_run=dry_run,
            silent=silent,
        )
    else:
        # Publish from database
        from argus.db.connection import get_connection

        try:
            conn = get_connection()
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)

        click.echo(f"Publishing message ID: {message_id}")

        try:
            result = run_publish(
                conn=conn,
                message_id=message_id,  # type: ignore[arg-type]
                config=telegram_config,
                dry_run=dry_run,
                silent=silent,
            )
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            conn.close()
            raise SystemExit(1)

        conn.close()

    # Display results
    click.echo()
    if dry_run:
        click.echo("=== Dry Run Result ===")
    else:
        click.echo("=== Publish Result ===")

    click.echo(f"Success: {result.success}")

    if result.telegram_message_id:
        click.echo(f"Telegram Message ID: {result.telegram_message_id}")

    if result.published_at:
        click.echo(f"Published at: {result.published_at.isoformat()}")

    if result.was_truncated:
        click.echo(f"Warning: Message was truncated from {result.original_length} chars")

    if result.retries > 0:
        click.echo(f"Retries: {result.retries}")

    if result.error:
        click.echo(f"Error: {result.error}", err=True)

    click.echo()
    click.echo("--- Payload ---")
    # Pretty print payload (but truncate text for readability)
    payload_display = result.payload.copy()
    if "text" in payload_display and len(payload_display["text"]) > 500:
        payload_display["text"] = payload_display["text"][:500] + "... [truncated for display]"
    click.echo(json.dumps(payload_display, indent=2, ensure_ascii=False))

    if not result.success:
        raise SystemExit(1)


@cli.command()
@click.option(
    "--fixtures-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to fixtures directory (default: tests/fixtures)",
)
@click.option("--verbose", is_flag=True, help="Show detailed validation output")
@click.option(
    "--test-invalid",
    is_flag=True,
    help="Also validate invalid fixture (expect failure)",
)
def smoke(fixtures_dir: Optional[Path], verbose: bool, test_invalid: bool) -> None:
    """Run offline smoke test using fixture data.

    Validates the full generation+validation pipeline without network access.
    No database or LLM API calls are made - uses pre-built fixture files.

    This command:
    1. Loads a sample facts bundle from fixtures
    2. Loads a pre-generated message (simulating LLM output)
    3. Runs the validator to ensure the message is valid
    4. Reports success/failure

    Examples:
        argus smoke
        argus smoke --verbose
        argus smoke --test-invalid
        argus smoke --fixtures-dir path/to/fixtures
    """
    import json
    import re

    from argus.config import ConstraintsConfig
    from argus.facts_bundle.types import FactsBundle
    from argus.generator import build_news_contexts
    from argus.generator.renderer import extract_referenced_ids, render_message
    from argus.generator.types import GenerationMode, GeneratorResult, LLMGeneratedContent
    from argus.validator.validator import MessageValidator

    click.echo("=== Argus Smoke Test ===")
    click.echo()

    # Determine fixtures directory
    if fixtures_dir is None:
        # Default to tests/fixtures relative to current working directory
        fixtures_dir = Path("tests/fixtures")
        if not fixtures_dir.exists():
            # Try relative to the package
            import argus

            package_dir = Path(argus.__file__).parent.parent.parent
            fixtures_dir = package_dir / "tests" / "fixtures"

    if not fixtures_dir.exists():
        click.echo(f"Error: Fixtures directory not found: {fixtures_dir}", err=True)
        click.echo("Run this command from the project root, or specify --fixtures-dir")
        raise SystemExit(1)

    click.echo(f"Loading fixtures from: {fixtures_dir}")
    click.echo()

    # 1. Load facts bundle
    bundle_path = fixtures_dir / "facts_bundle.json"
    if not bundle_path.exists():
        click.echo(f"Error: facts_bundle.json not found in {fixtures_dir}", err=True)
        raise SystemExit(1)

    try:
        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle_data = json.load(f)
        bundle = FactsBundle.from_dict(bundle_data)
        click.echo(click.style("[OK] Loaded facts_bundle.json", fg="green"))
        click.echo(f"  - Trading date: {bundle.trading_date.isoformat()}")
        click.echo(f"  - News items: {len(bundle.news_items)}")
        click.echo(f"  - Calendar events: {len(bundle.calendar_events)}")
        click.echo(f"  - Spotlight: {'Yes' if bundle.spotlight else 'No'}")
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in facts_bundle.json: {e}", err=True)
        raise SystemExit(1)
    except (KeyError, ValueError, TypeError) as e:
        click.echo(f"Error: Invalid bundle format: {e}", err=True)
        raise SystemExit(1)

    click.echo()

    # 2. Build news contexts
    news_contexts = build_news_contexts(bundle)
    click.echo(click.style(f"[OK] Built news contexts ({len(news_contexts)} items)", fg="green"))

    click.echo()

    # 3. Render a deterministic “LLM output” fixture through the renderer.
    # The fixture is treated as LLM-generated narrative content and may contain cite keys
    # like [#A1B2C3D4]. The renderer will renumber these to [1]..[k] and filter Sources.
    valid_message_path = fixtures_dir / "generated_message_valid.md"
    if not valid_message_path.exists():
        click.echo(f"Error: generated_message_valid.md not found in {fixtures_dir}", err=True)
        raise SystemExit(1)

    fixture_text = valid_message_path.read_text(encoding="utf-8")
    click.echo(click.style("[OK] Loaded generated_message_valid.md", fg="green"))
    click.echo(f"  - Length: {len(fixture_text)} chars, ~{len(fixture_text.split())} words")

    click.echo()

    # Parse referenced IDs from cite keys (strict) and render full final message.
    referenced_ids = extract_referenced_ids(fixture_text, news_contexts)

    # The smoke test validator expects a full message shape (incl. 3-5 takeaways, 2-3 watch items).
    # We keep these deterministic and fixture-driven to remain offline.
    llm_content = LLMGeneratedContent(
        narrative=fixture_text,
        takeaways=[
            "Leadership is broadening—rotate exposure toward earnings quality and avoid single-theme concentration.",
            'Cross-asset hedges still matter: the gold bid alongside equity strength points to "risk-on with protection."',
            "Treat headline spikes as catalysts for positioning review, not automatic trend breaks, unless confirmed by follow-through in rates/FX.",
        ],
        watch_next=[
            "Whether yields confirm the risk rally (further declines in real yields would support equities).",
            "Follow-through in cyclicals vs. a quick reversal back to defensives.",
        ],
        referenced_item_ids=referenced_ids,
        raw_response="smoke-test-fixture",
    )

    escaped_message, raw_message = render_message(bundle, news_contexts, llm_content, True)

    word_count = len(raw_message.split())
    result = GeneratorResult(
        message=escaped_message,
        message_raw=raw_message,
        word_count=word_count,
        sources_count=len(referenced_ids),
        has_spotlight=bundle.spotlight is not None,
        model="smoke-test-fixture",
        generation_mode=GenerationMode.from_string(bundle.run_mode),
        generated_at=bundle.generated_at,
        retry_count=0,
        llm_duration_seconds=0.0,
    )

    click.echo(
        click.style(
            f"[OK] Created GeneratorResult ({len(referenced_ids)} cited sources)", fg="green"
        )
    )

    click.echo()

    # 5. Run validation
    click.echo("Running validation...")
    constraints = ConstraintsConfig()
    validator = MessageValidator(constraints)
    validation = validator.validate(result, bundle)

    if validation.is_valid:
        click.echo(click.style("[OK] Validation PASSED", fg="green", bold=True))
    else:
        click.echo(click.style("[FAIL] Validation FAILED", fg="red", bold=True))

    if verbose or not validation.is_valid:
        click.echo(f"  - Sections valid: {'[OK]' if validation.sections_valid else '[FAIL]'}")
        click.echo(
            f"  - Bullet counts valid: {'[OK]' if validation.bullet_counts_valid else '[FAIL]'}"
        )
        click.echo(f"  - No hallucinations: {'[OK]' if validation.no_hallucinations else '[FAIL]'}")
        click.echo(f"  - Formatting valid: {'[OK]' if validation.formatting_valid else '[FAIL]'}")
        if validation.errors:
            click.echo("  Errors:")
            for error in validation.errors:
                click.echo(f"    - {error}")

    click.echo()

    # 6. Optionally test invalid fixture
    if test_invalid:
        click.echo("--- Testing invalid fixture ---")
        click.echo()

        invalid_message_path = fixtures_dir / "generated_message_invalid.md"
        if not invalid_message_path.exists():
            click.echo(f"Warning: generated_message_invalid.md not found in {fixtures_dir}")
            click.echo("Skipping invalid fixture test.")
        else:
            invalid_message = invalid_message_path.read_text(encoding="utf-8")
            click.echo(click.style("[OK] Loaded generated_message_invalid.md", fg="green"))

            invalid_result = GeneratorResult(
                message=invalid_message,
                message_raw=invalid_message,
                word_count=len(invalid_message.split()),
                sources_count=0,
                has_spotlight=False,
                model="smoke-test-fixture-invalid",
                generation_mode=GenerationMode.from_string(bundle.run_mode),
                generated_at=bundle.generated_at,
                retry_count=0,
                llm_duration_seconds=0.0,
            )

            invalid_validation = validator.validate(invalid_result, bundle)

            if not invalid_validation.is_valid:
                click.echo(
                    click.style("[OK] Invalid fixture correctly rejected", fg="green", bold=True)
                )
                click.echo(f"  Detected {len(invalid_validation.errors)} error(s):")
                for error in invalid_validation.errors[:5]:  # Show first 5
                    click.echo(f"    - {error}")
                if len(invalid_validation.errors) > 5:
                    click.echo(f"    ... and {len(invalid_validation.errors) - 5} more")
            else:
                click.echo(
                    click.style(
                        "[FAIL] Invalid fixture was NOT rejected (validator issue)",
                        fg="red",
                        bold=True,
                    )
                )
                validation = invalid_validation  # Mark overall test as failed

        click.echo()

    # Final summary
    if validation.is_valid:
        click.echo(click.style("=== Smoke test PASSED ===", fg="green", bold=True))
    else:
        click.echo(click.style("=== Smoke test FAILED ===", fg="red", bold=True))
        raise SystemExit(1)


# =============================================================================
# Daemon Commands
# =============================================================================


@cli.group()
def daemon() -> None:
    """Daemon scheduler commands.

    The daemon runs as a long-lived process with internal scheduling,
    eliminating the need for external cron. Suitable for VPS deployment.
    """
    pass


@daemon.command("start")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config.yaml",
)
def daemon_start(config_path: Optional[Path]) -> None:
    """Start the daemon scheduler (foreground).

    Runs until interrupted with SIGTERM/SIGINT (Ctrl+C).

    Example:
        argus daemon start
        argus daemon start --config /path/to/config.yaml
    """
    import asyncio

    from .config import ArgusConfig
    from .daemon import ArgusDaemon

    # Load config
    config = ArgusConfig.load(config_path)

    click.echo(f"Starting Argus daemon v{__version__}...")
    click.echo(
        f"Health endpoint: http://{config.daemon.health_bind}:{config.daemon.health_port}/health"
    )
    click.echo("Press Ctrl+C to stop")
    click.echo()

    # Run daemon
    daemon_instance = ArgusDaemon(config)
    asyncio.run(daemon_instance.start())

    click.echo("Daemon stopped.")


@daemon.command("status")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config.yaml",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def daemon_status(config_path: Optional[Path], as_json: bool) -> None:
    """Show daemon and job status.

    Queries the daemon's health endpoint to get current status.
    The daemon must be running for this command to work.

    Example:
        argus daemon status
        argus daemon status --json
    """
    import json
    import urllib.request
    import urllib.error

    from .config import ArgusConfig

    # Load config to get health endpoint
    config = ArgusConfig.load(config_path)
    url = f"http://{config.daemon.health_bind}:{config.daemon.health_port}/health"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
    except urllib.error.URLError as e:
        click.echo(click.style(f"Error: Cannot connect to daemon at {url}", fg="red"))
        click.echo(f"  {e.reason}")
        click.echo()
        click.echo("Is the daemon running? Start it with: argus daemon start")
        raise SystemExit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return

    # Pretty print status
    status = data.get("status", "unknown")
    status_color = {"healthy": "green", "degraded": "yellow", "unhealthy": "red"}.get(
        status, "white"
    )

    click.echo(click.style(f"Daemon Status: {status.upper()}", fg=status_color, bold=True))
    click.echo(f"Version: {data.get('version', 'unknown')}")
    click.echo(f"Uptime: {_format_uptime(data.get('uptime_seconds', 0))}")
    click.echo()

    # Jobs table
    jobs = data.get("jobs", {})
    if jobs:
        click.echo("Jobs:")
        click.echo("-" * 72)
        click.echo(f"{'Job':<18} {'Enabled':<8} {'Status':<10} {'Last Run':<20} {'Next Run':<14}")
        click.echo("-" * 72)

        for job_id, job_info in jobs.items():
            enabled = "Yes" if job_info.get("enabled") else "No"
            last_status = job_info.get("last_status") or "-"
            last_run = _format_timestamp(job_info.get("last_run"))
            next_run = _format_timestamp(job_info.get("next_run"))
            running = " (running)" if job_info.get("is_running") else ""

            status_color = {"success": "green", "failed": "red", "running": "yellow"}.get(
                last_status, "white"
            )
            status_str = click.style(f"{last_status}{running}", fg=status_color)

            click.echo(f"{job_id:<18} {enabled:<8} {status_str:<19} {last_run:<20} {next_run:<14}")
    else:
        click.echo("No jobs configured.")


@daemon.command("trigger")
@click.argument(
    "job_id",
    type=click.Choice(["ingest", "us_close", "weekend_wrap", "monday_preview", "retention"]),
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config.yaml",
)
def daemon_trigger(job_id: str, config_path: Optional[Path]) -> None:
    """Manually trigger a scheduled job.

    Sends a request to the running daemon to trigger the specified job.
    The daemon must be running for this command to work.

    Example:
        argus daemon trigger ingest
        argus daemon trigger us_close
    """
    import json
    import urllib.request
    import urllib.error

    from .config import ArgusConfig

    # Load config to get health endpoint
    config = ArgusConfig.load(config_path)
    url = f"http://{config.daemon.health_bind}:{config.daemon.health_port}/trigger/{job_id}"

    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        # HTTPError must be caught before URLError (it's a subclass)
        click.echo(click.style(f"Error: {e.code} {e.reason}", fg="red"))
        raise SystemExit(1)
    except urllib.error.URLError as e:
        click.echo(click.style("Error: Cannot connect to daemon", fg="red"))
        click.echo(f"  {e.reason}")
        click.echo()
        click.echo("Is the daemon running? Start it with: argus daemon start")
        raise SystemExit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        raise SystemExit(1)

    if data.get("status") == "triggered":
        click.echo(click.style(f"Job '{job_id}' triggered successfully", fg="green"))
    elif data.get("status") == "already_running":
        click.echo(click.style(f"Job '{job_id}' is already running", fg="yellow"))
    elif data.get("status") == "disabled":
        click.echo(click.style(f"Job '{job_id}' is disabled in config", fg="yellow"))
    else:
        click.echo(f"Response: {data}")


@daemon.command("history")
@click.argument(
    "job_id",
    type=click.Choice(["ingest", "us_close", "weekend_wrap", "monday_preview", "retention"]),
)
@click.option("--limit", default=10, help="Number of records to show")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config.yaml",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def daemon_history(job_id: str, limit: int, config_path: Optional[Path], as_json: bool) -> None:
    """Show recent run history for a job.

    Queries the daemon's health endpoint to get job run history.
    The daemon must be running for this command to work.

    Example:
        argus daemon history ingest
        argus daemon history us_close --limit 20
    """
    import json
    import urllib.request
    import urllib.error

    from .config import ArgusConfig

    # Load config to get health endpoint
    config = ArgusConfig.load(config_path)
    url = f"http://{config.daemon.health_bind}:{config.daemon.health_port}/health/jobs/{job_id}/history?limit={limit}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
    except urllib.error.URLError as e:
        click.echo(click.style(f"Error: Cannot connect to daemon", fg="red"))
        click.echo(f"  {e.reason}")
        raise SystemExit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        raise SystemExit(1)

    records = data.get("history", [])

    if as_json:
        click.echo(json.dumps(records, indent=2, default=str))
        return

    if not records:
        click.echo(f"No history for job '{job_id}'")
        return

    click.echo(f"History for '{job_id}' (last {len(records)} runs):")
    click.echo("-" * 80)
    click.echo(f"{'ID':<6} {'Status':<10} {'Trigger':<10} {'Started':<20} {'Duration':<12}")
    click.echo("-" * 80)

    for record in records:
        rec_id = record.get("id", "-")
        status = record.get("status", "-")
        trigger = record.get("trigger_type", "-")
        started = _format_timestamp(record.get("started_at"))
        duration_ms = record.get("duration_ms")
        duration = f"{duration_ms}ms" if duration_ms else "-"

        status_color = {"success": "green", "failed": "red", "running": "yellow"}.get(
            status, "white"
        )
        status_str = click.style(status, fg=status_color)

        click.echo(f"{rec_id:<6} {status_str:<19} {trigger:<10} {started:<20} {duration:<12}")

        # Show error message if failed
        if status == "failed" and record.get("error_message"):
            click.echo(f"       Error: {record['error_message'][:60]}...")


def _format_uptime(seconds: int) -> str:
    """Format uptime in human-readable form."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def _format_timestamp(ts: Optional[str]) -> str:
    """Format ISO timestamp for display."""
    if not ts:
        return "-"
    try:
        # Parse ISO format
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts[:16] if len(ts) > 16 else ts
