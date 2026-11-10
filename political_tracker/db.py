"""Lazy, pooled Postgres connection helper for the web app.

Uses psycopg_pool with a read-only connection string from DATABASE_URL.
Pool is created on first use, not at import time.
"""

import os
from contextlib import contextmanager
from threading import Lock

import psycopg
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_pool_lock = Lock()


def _get_pool() -> ConnectionPool:
    """Get or create the connection pool (thread-safe, lazy)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                dsn = os.environ.get("DATABASE_URL")
                if not dsn:
                    raise RuntimeError("DATABASE_URL environment variable not set")
                # Use a small pool for Render free tier (max ~3 connections)
                # prepare_threshold=None disables prepared statements (needed for transaction pooler)
                _pool = ConnectionPool(
                    dsn,
                    min_size=1,
                    max_size=3,
                    kwargs={
                        "prepare_threshold": None,
                        "sslmode": "require",
                        "connect_timeout": 5,
                    },
                    open=False,  # don't open until first use
                )
                _pool.open()
    return _pool


@contextmanager
def get_db():
    """Get a database connection from the pool.

    Usage:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def close_pool():
    """Close the connection pool (for testing or shutdown)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None