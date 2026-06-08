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


def _run(sql, params, fetch):
    """
    Shared core for query()/execute(): run `sql` and hand the cursor to
    `fetch` to extract the result.

    If a connection/operational error occurs (e.g. the DB container
    restarted mid-session and the cached connection has gone stale),
    drop the cached connection and retry exactly once with a fresh one.
    Genuine SQL errors (bad query, constraint violation, etc.) are not
    connection problems — they propagate immediately without retrying.
    """
    global _conn
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return fetch(cur)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        _conn = None
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return fetch(cur)


def query(sql, params=()):
    """Run a parameterized SELECT and return rows as a list[dict]."""
    return _run(sql, params, lambda cur: [dict(row) for row in cur.fetchall()])


def execute(sql, params=()):
    """
    Run a parameterized INSERT/UPDATE/DELETE.

    If the statement has a RETURNING clause, the returned row is given
    back as a dict; otherwise None is returned.
    """
    def _fetch(cur):
        if cur.description:  # statement returned rows (e.g. RETURNING ...)
            row = cur.fetchone()
            return dict(row) if row is not None else None
        return None

    return _run(sql, params, _fetch)


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
