"""Lazy, pooled Postgres connection helper for the web app.

Uses psycopg_pool with a read-only connection string from DATABASE_URL.
Pool is created on first use, not at import time.

If the database is unreachable, routes catch the exception and degrade
gracefully (empty states). The pool is reset so the next call retries.
"""

import os
from contextlib import contextmanager
from threading import Lock

import psycopg
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_pool_lock = Lock()


def _get_pool() -> ConnectionPool:
    """Get or create the connection pool (thread-safe, lazy).

    The pool is created with open=False so no connections are established
    until getconn() is called. If the database is unreachable, _pool is
    reset to None so the next call retries.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                dsn = os.environ.get("DATABASE_URL")
                if not dsn:
                    raise RuntimeError("DATABASE_URL environment variable not set")
                _pool = ConnectionPool(
                    dsn,
                    min_size=0,
                    max_size=3,
                    kwargs={
                        "prepare_threshold": None,
                        "sslmode": "require",
                        "connect_timeout": 5,
                    },
                    open=False,
                )
    return _pool


@contextmanager
def get_db():
    """Get a database connection from the pool.

    Usage:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(...)

    If the database is unreachable, the pool is reset and the exception
    propagates to the caller, which should catch it and degrade gracefully.
    """
    global _pool
    pool = _get_pool()
    try:
        pool.open()
    except Exception:
        with _pool_lock:
            if _pool is pool:
                try:
                    pool.close()
                except Exception:
                    pass
                _pool = None
        raise

    try:
        conn = pool.getconn()
    except Exception:
        with _pool_lock:
            if _pool is pool:
                try:
                    pool.close()
                except Exception:
                    pass
                _pool = None
        raise

    try:
        yield conn
    finally:
        try:
            pool.putconn(conn)
        except Exception:
            pass


def close_pool():
    """Close the connection pool (for testing or shutdown)."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None
