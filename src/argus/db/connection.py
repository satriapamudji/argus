"""Database connection utilities for Argus."""

import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.pool import ThreadedConnectionPool

_pool: Optional[ThreadedConnectionPool] = None


def _parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    return default


def _get_pool_limits() -> tuple[int, int]:
    min_size = int(os.getenv("DB_POOL_MIN", "1"))
    max_size = int(os.getenv("DB_POOL_MAX", "5"))

    if min_size < 1:
        min_size = 1
    if max_size < min_size:
        max_size = min_size

    return min_size, max_size


class PooledConnection:
    """Connection wrapper that returns connections to the pool on close()."""

    def __init__(self, conn: Connection, pool: ThreadedConnectionPool) -> None:
        self._conn = conn
        self._pool = pool
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Connection already returned to pool")

    def close(self) -> None:
        if self._closed:
            return
        self._pool.putconn(self._conn)
        self._closed = True

    @property
    def closed(self) -> int:
        if self._closed:
            return 1
        return self._conn.closed

    def __enter__(self) -> "PooledConnection":
        self._ensure_open()
        return self

    def __exit__(
        self, exc_type: Optional[type[BaseException]], exc: Optional[BaseException], tb: Any
    ) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        self._ensure_open()
        return getattr(self._conn, name)


def get_database_url() -> str:
    """Get database URL from environment.

    Returns:
        Database URL string.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")
    return url


def get_connection() -> Connection:
    """Create a new database connection.

    Returns:
        psycopg2 connection object.
    """
    if not _parse_bool_env("DB_POOL_ENABLED", True):
        return psycopg2.connect(get_database_url())

    global _pool
    if _pool is None:
        min_size, max_size = _get_pool_limits()
        _pool = ThreadedConnectionPool(
            minconn=min_size,
            maxconn=max_size,
            dsn=get_database_url(),
        )

    conn = _pool.getconn()
    return PooledConnection(conn, _pool)


@contextmanager
def get_connection_context() -> Generator[Connection, None, None]:
    """Context manager for database connections.

    Yields:
        psycopg2 connection object.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
