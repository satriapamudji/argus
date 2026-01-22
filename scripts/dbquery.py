#!/usr/bin/env python3
"""Simple database query helper for Argus.

Usage:
    python scripts/dbquery.py "SELECT * FROM runs LIMIT 5"
    python scripts/dbquery.py --partitions
    python scripts/dbquery.py --stats
"""

import argparse
import os
import re

import psycopg2

def get_db_config():
    """Get database config from environment or .env file."""
    # Try DATABASE_URL from environment first
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        # Try to read from .env file
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip().replace('\r', '')
                    if line.startswith("DATABASE_URL="):
                        db_url = line.split("=", 1)[1]
                        break

    if not db_url:
        raise RuntimeError("DATABASE_URL not found in environment or .env file")

    # Parse the URL - handle Neon format
    # postgresql://user:pass@host/db?params
    match = re.match(r'postgresql://([^:]+):([^@]+)@([^/]+)/([^?]+)', db_url)
    if not match:
        raise RuntimeError(f"Could not parse DATABASE_URL: {db_url[:50]}...")

    return {
        "user": match.group(1),
        "password": match.group(2),
        "host": match.group(3),
        "database": match.group(4),
        "sslmode": "require",
    }


def get_connection():
    return psycopg2.connect(**get_db_config())


def run_query(sql: str):
    """Run a SQL query and print results."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description:
                headers = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                # Simple table formatting
                col_widths = [len(h) for h in headers]
                for row in rows:
                    for i, val in enumerate(row):
                        col_widths[i] = max(col_widths[i], len(str(val) if val else ""))
                # Print header
                header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
                print(header_line)
                print("-" * len(header_line))
                # Print rows
                for row in rows:
                    print("  ".join(str(v if v is not None else "").ljust(col_widths[i]) for i, v in enumerate(row)))
                print(f"\n({len(rows)} rows)")
            else:
                print(f"Query executed. Rows affected: {cur.rowcount}")
    finally:
        conn.close()


def show_partitions():
    """Show all news_items partitions."""
    sql = """
        SELECT tablename
        FROM pg_tables
        WHERE tablename LIKE 'news_items%'
        ORDER BY tablename
    """
    run_query(sql)


def show_stats():
    """Show news stats for all streams."""
    sql = """
        SELECT
            'us_markets' as stream,
            MIN(ingested_at)::date as earliest,
            MAX(ingested_at)::date as latest,
            COUNT(*) as total
        FROM news_items_us_markets
        UNION ALL
        SELECT
            'crypto' as stream,
            MIN(ingested_at)::date as earliest,
            MAX(ingested_at)::date as latest,
            COUNT(*) as total
        FROM news_items_crypto
    """
    run_query(sql)


def show_runs(limit: int = 10):
    """Show recent runs."""
    sql = f"""
        SELECT id, stream_name, run_mode, status,
               started_at::timestamp(0),
               COALESCE(error_message, '')::varchar(50) as error
        FROM runs
        ORDER BY id DESC
        LIMIT {limit}
    """
    run_query(sql)


def show_fingerprints():
    """Show fingerprint stats."""
    sql = """
        SELECT
            COUNT(*) as total,
            MIN(last_seen_at)::date as earliest,
            MAX(last_seen_at)::date as latest
        FROM news_fingerprints
    """
    run_query(sql)


def main():
    parser = argparse.ArgumentParser(description="Argus database query helper")
    parser.add_argument("sql", nargs="?", help="SQL query to execute")
    parser.add_argument("--partitions", action="store_true", help="Show all partitions")
    parser.add_argument("--stats", action="store_true", help="Show news stats")
    parser.add_argument("--runs", type=int, nargs="?", const=10, help="Show recent runs")
    parser.add_argument("--fingerprints", action="store_true", help="Show fingerprint stats")

    args = parser.parse_args()

    if args.partitions:
        show_partitions()
    elif args.stats:
        show_stats()
    elif args.runs is not None:
        show_runs(args.runs)
    elif args.fingerprints:
        show_fingerprints()
    elif args.sql:
        run_query(args.sql)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
