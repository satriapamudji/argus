"""Database connection utilities for Argus."""

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as Connection


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
    return psycopg2.connect(get_database_url())


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
