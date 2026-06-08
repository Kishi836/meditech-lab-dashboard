"""
Meditech Lab 2.0 — Postgres connection helper
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thin wrapper around psycopg2 that the rest of the app uses instead of
talking to the driver directly. Keeps a single cached connection (and
reconnects if it has gone stale/closed), and returns plain dicts so
templates/JSON responses don't need to know about cursor objects.

`ping()` is the one function the health endpoint depends on — it must
never raise, even when Postgres is completely unreachable.
"""

import psycopg2
import psycopg2.extras

from config import Config

_conn = None


def get_conn():
    """Return a live psycopg2 connection, (re)connecting if needed."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(Config.DB_DSN)
        _conn.autocommit = True
    return _conn


def query(sql, params=()):
    """Run a parameterized SELECT and return rows as a list[dict]."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def execute(sql, params=()):
    """
    Run a parameterized INSERT/UPDATE/DELETE.

    If the statement has a RETURNING clause, the returned row is given
    back as a dict; otherwise None is returned.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        if cur.description:  # statement returned rows (e.g. RETURNING ...)
            row = cur.fetchone()
            return dict(row) if row is not None else None
        return None


def ping():
    """True if Postgres is reachable; never raises."""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        global _conn
        _conn = None
        return False
