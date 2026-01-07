"""Tests for database migrations module."""

from argus.db.migrations.runner import (
    MIGRATIONS_DIR,
    get_available_migrations,
)


class TestMigrationsAvailable:
    """Tests for get_available_migrations function."""

    def test_migrations_dir_exists(self) -> None:
        """Test that migrations directory exists."""
        assert MIGRATIONS_DIR.exists()
        assert MIGRATIONS_DIR.is_dir()

    def test_initial_schema_migration_exists(self) -> None:
        """Test that initial schema migration exists."""
        migrations = get_available_migrations()
        versions = [v for v, _ in migrations]
        assert "001_initial_schema" in versions

    def test_migrations_sorted_by_version(self) -> None:
        """Test that migrations are sorted."""
        migrations = get_available_migrations()
        versions = [v for v, _ in migrations]
        assert versions == sorted(versions)

    def test_all_migrations_are_sql_files(self) -> None:
        """Test that all migrations are .sql files."""
        migrations = get_available_migrations()
        for _, path in migrations:
            assert path.suffix == ".sql"
            assert path.exists()


class TestMigrationSqlContent:
    """Tests for migration SQL file content."""

    def test_initial_schema_contains_required_tables(self) -> None:
        """Test that initial schema creates all required tables."""
        migration_path = MIGRATIONS_DIR / "001_initial_schema.sql"
        content = migration_path.read_text()

        # Check for required tables
        assert "CREATE TABLE news_fingerprints" in content
        assert "CREATE TABLE news_items" in content
        assert "CREATE TABLE news_content" in content
        assert "CREATE TABLE news_scores" in content
        assert "CREATE TABLE runs" in content
        assert "CREATE TABLE messages" in content
        assert "CREATE TABLE IF NOT EXISTS schema_migrations" in content

    def test_initial_schema_has_partitioning(self) -> None:
        """Test that news_items table is partitioned."""
        migration_path = MIGRATIONS_DIR / "001_initial_schema.sql"
        content = migration_path.read_text()

        assert "PARTITION BY RANGE (ingested_at)" in content
        assert "create_news_items_partition" in content

    def test_initial_schema_has_pg_trgm(self) -> None:
        """Test that pg_trgm extension is enabled."""
        migration_path = MIGRATIONS_DIR / "001_initial_schema.sql"
        content = migration_path.read_text()

        assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in content
        assert "gin_trgm_ops" in content

    def test_initial_schema_has_unique_hash_url(self) -> None:
        """Test that hash_url has unique index."""
        migration_path = MIGRATIONS_DIR / "001_initial_schema.sql"
        content = migration_path.read_text()

        assert "CREATE UNIQUE INDEX idx_fingerprints_hash_url" in content

    def test_initial_schema_has_retention_function(self) -> None:
        """Test that retention cleanup function exists."""
        migration_path = MIGRATIONS_DIR / "001_initial_schema.sql"
        content = migration_path.read_text()

        assert "drop_old_news_items_partitions" in content

    def test_initial_schema_has_risk_score_fields(self) -> None:
        """Test that runs table has monday_preview risk breakdown."""
        migration_path = MIGRATIONS_DIR / "001_initial_schema.sql"
        content = migration_path.read_text()

        assert "risk_score" in content
        assert "calendar_score" in content
        assert "market_score" in content
        assert "headline_score" in content
