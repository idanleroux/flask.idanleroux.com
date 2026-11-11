"""Check read-only database connection using DATABASE_URL.

Connects to Supabase via the tracker_ro read-only role and prints
connection status, current role, and row counts for the main tables.
Never prints the connection string or password.
"""
from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("FAIL: DATABASE_URL environment variable is not set")
        return 1

    print("Connecting using DATABASE_URL (read-only role)...")
    try:
        conn = psycopg.connect(dsn, connect_timeout=10, sslmode="require")
    except Exception as exc:
        print(f"FAIL: could not connect: {exc}")
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database()")
            role, database = cur.fetchone()
            print(f"OK: connected as role '{role}' to database '{database}'")

            tables = [
                "political_tracker.members",
                "political_tracker.votes",
                "political_tracker.member_votes",
                "political_tracker.member_stats",
                "political_tracker.similarity",
                "political_tracker.finance_us",
                "political_tracker.meta",
            ]
            for table in tables:
                try:
                    cur.execute(f"SELECT count(*) FROM {table}")
                    count = cur.fetchone()[0]
                    print(f"  {table}: {count:,} rows")
                except Exception as exc:
                    print(f"  {table}: ERROR — {exc}")

            # Show US/UK breakdown
            try:
                with conn.cursor() as cur2:
                    cur2.execute(
                        """
                        SELECT country,
                               COUNT(*) FILTER (WHERE is_current) AS current_members,
                               COUNT(*) AS total_members
                        FROM political_tracker.members
                        GROUP BY country
                        ORDER BY country
                        """
                    )
                    print("Members by country:")
                    for country, current, total in cur2.fetchall():
                        print(f"  {country}: {current:,} current / {total:,} total")
            except Exception as exc:
                print(f"Members breakdown ERROR — {exc}")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
