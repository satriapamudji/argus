# Task 02: Postgres Schema + Migrations Documentation

## Summary
Implemented the complete Postgres data model and migrations for Argus, supporting ingestion, scoring, runs, and publishing.

## Before
- No database module existed
- No migrations or schema defined
- No database connection utilities

## What Was Changed

### New Files Created

#### 1. Database Module (`src/argus/db/`)

**`__init__.py`**
- Central export hub for all database functionality
- Exports connection utilities, models, partitions, and repository functions

**`connection.py`**
- `get_database_url()`: Retrieves DATABASE_URL from environment
- `get_connection()`: Creates psycopg2 connection
- `get_connection_context()`: Context manager for auto-close connections

**`models.py`**
- Typed dataclass row types for all database tables:
  - `NewsFingerprintRow`: Long-lived dedupe hashes (URL hash, text hash, SimHash)
  - `NewsItemRow`: News metadata (partitioned table)
  - `NewsContentRow`: Optional full text / excerpt storage
  - `NewsScoreRow`: Scoring results from heuristics/LLM
  - `RunRow`: Run artifacts with facts bundle, timings, monday_preview risk breakdown
  - `MessageRow`: Generated messages with validation/publish status

**`partitions.py`**
- `create_partition_for_date()`: Creates daily partition for news_items
- `create_partitions_for_range()`: Bulk partition creation
- `ensure_partition_exists()`: Idempotent partition creation
- `drop_old_partitions()`: Retention cleanup (drops old partitions)
- `get_existing_partitions()`: Lists current partitions
- `run_retention_cleanup()`: Full retention cleanup for news_items and fingerprints

**`repository.py`**
- URL normalization and hashing for dedupe
- `normalize_url()`: Normalizes URLs (removes protocol, www, trailing slash)
- `hash_url()`: SHA256 hash of normalized URL
- `hash_text()`: SHA256 hash of normalized title + snippet
- CRUD operations:
  - `get_or_create_fingerprint()`: Upsert fingerprint
  - `insert_news_item()`: Insert with auto-partition creation
  - `create_run()`, `update_run()`: Run management
  - `create_message()`, `update_message()`: Message management
  - `check_duplicate_by_url()`, `check_duplicate_by_text()`: Dedupe checks

#### 2. Migrations (`src/argus/db/migrations/`)

**`__init__.py`**
- Exports migration runner functions

**`runner.py`**
- `get_applied_migrations()`: Checks schema_migrations table
- `get_available_migrations()`: Scans .sql files
- `get_pending_migrations()`: Returns unapplied migrations
- `apply_migrations()`: Applies pending migrations with optional dry-run

**`001_initial_schema.sql`**
- Creates `pg_trgm` extension for similarity search
- Creates `schema_migrations` table for tracking
- Creates all required tables with proper constraints:
  - `news_fingerprints`: Unique index on hash_url, indexes on hash_text, simhash
  - `news_items`: Partitioned by day on ingested_at, pg_trgm index on title
  - `news_content`: Content storage with status tracking
  - `news_scores`: Score values with constraints (0-100)
  - `runs`: Facts bundle JSON, timings, monday_preview risk breakdown fields
  - `messages`: Validation/publish status tracking
- Partition management functions:
  - `create_news_items_partition()`: Creates daily partition
  - `drop_old_news_items_partitions()`: Drops partitions older than retention days

#### 3. CLI Commands (`src/argus/cli.py`)

Added `db` command group with subcommands:
- `argus db migrate`: Apply pending migrations
- `argus db migrate --dry-run`: Show pending without applying
- `argus db status`: Show applied/pending migrations
- `argus db cleanup`: Run retention cleanup
- `argus db create-partitions --days N`: Create partitions for upcoming days
- `argus db insert-test`: Insert test data (news_item + run + message)

#### 4. Tests (`tests/`)

**`test_db_models.py`** (6 tests)
- Tests for all model `from_row()` methods

**`test_db_repository.py`** (13 tests)
- URL normalization tests (7 tests)
- Hash function tests (6 tests)

**`test_db_migrations.py`** (10 tests)
- Migration file existence and structure
- SQL content validation (tables, indexes, partitioning, pg_trgm)

### Dependencies Added

**`pyproject.toml`**
- Added `psycopg2-binary>=2.9` for Postgres connectivity

## Schema Design Decisions

### Partitioning Strategy
- `news_items` partitioned by day on `ingested_at`
- Partitions named `news_items_YYYY_MM_DD`
- Retention via partition drop (efficient bulk delete)

### Deduplication Layers
1. **Exact URL hash**: Unique index on `hash_url` (sha256 of normalized URL)
2. **Exact text hash**: Index on `hash_text` (sha256 of title + snippet)
3. **Near-duplicate SimHash**: 64-bit signature with Hamming distance check
4. **Title similarity**: pg_trgm GIN index for trigram similarity

### Retention Policy
- `news_items`: 60 days (partitioned, easy cleanup)
- `news_fingerprints`: 1-10 years (survives content deletion, blocks repeats)
- `runs` + `messages`: 1-2+ years (audit/replay)

### Monday Preview Risk Breakdown
- `runs` table stores individual scores: `risk_score`, `calendar_score`, `market_score`, `headline_score`
- All nullable with CHECK constraints (0-100)

## Reasoning

1. **Raw SQL migrations over Alembic**: Simple project, fewer dependencies, full control over Postgres-specific features (partitioning, extensions)

2. **Partition by day**: Matches 60-day retention, enables efficient bulk cleanup via `DROP TABLE`

3. **Separate fingerprints table**: Survives partition drops, enables long-term dedupe without storing content

4. **pg_trgm for title similarity**: Native Postgres, no external dependencies, fast similarity searches

5. **Repository pattern**: Clean separation between SQL and business logic, testable without database

6. **Context managers for connections**: Ensures proper resource cleanup

## Verification

- Type-check (mypy): Passes on all db module files
- Linting (ruff): All checks pass
- Tests: 33 tests pass, no warnings
- Pre-existing test failures (5) in calendar.py and market_data.py are unrelated to this task
