"""Migration runner for Argus database migrations."""

from pathlib import Path
from typing import Optional

from psycopg2.extensions import connection as Connection


MIGRATIONS_DIR = Path(__file__).parent


def get_applied_migrations(conn: Connection) -> list[str]:
    """Get list of already applied migrations.

    Args:
        conn: Database connection.

    Returns:
        List of applied migration versions.
    """
    with conn.cursor() as cur:
        # Check if schema_migrations table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'schema_migrations'
            )
        """)
        result = cur.fetchone()
        exists = result[0] if result else False

        if not exists:
            return []

        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [row[0] for row in cur.fetchall()]


def get_available_migrations() -> list[tuple[str, Path]]:
    """Get list of available migration files.

    Returns:
        List of (version, path) tuples sorted by version.
    """
    migrations = []
    for filepath in MIGRATIONS_DIR.glob("*.sql"):
        # Extract version from filename (e.g., "001_initial_schema.sql" -> "001_initial_schema")
        version = filepath.stem
        migrations.append((version, filepath))

    return sorted(migrations, key=lambda x: x[0])


def get_pending_migrations(conn: Connection) -> list[tuple[str, Path]]:
    """Get list of migrations that haven't been applied yet.

    Args:
        conn: Database connection.

    Returns:
        List of (version, path) tuples for pending migrations.
    """
    applied = set(get_applied_migrations(conn))
    available = get_available_migrations()

    return [(version, path) for version, path in available if version not in applied]


def apply_migration(conn: Connection, version: str, path: Path) -> None:
    """Apply a single migration.

    Args:
        conn: Database connection.
        version: Migration version string.
        path: Path to migration SQL file.
    """
    with open(path, "r") as f:
        sql = f.read()

    with conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()


def apply_migrations(
    conn: Connection, target_version: Optional[str] = None, dry_run: bool = False
) -> list[str]:
    """Apply pending migrations up to target version.

    Args:
        conn: Database connection.
        target_version: Optional version to migrate to. If None, applies all pending.
        dry_run: If True, don't actually apply migrations.

    Returns:
        List of applied migration versions.
    """
    pending = get_pending_migrations(conn)
    applied = []

    for version, path in pending:
        if target_version and version > target_version:
            break

        if dry_run:
            applied.append(version)
            continue

        apply_migration(conn, version, path)
        applied.append(version)

    return applied
