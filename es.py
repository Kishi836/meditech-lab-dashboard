"""
Meditech Lab 2.0 — Elasticsearch client (optional, feature-flagged)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ES is off by default (`Config.ES_ENABLED = False`). When disabled,
every function is a no-op that returns a "skipped" sentinel — nothing
ever raises and `requests` is never called. This lets the rest of the
app treat ES as best-effort without sprinkling feature-flag checks
everywhere.

Flip ES_ENABLED on (env var `ES_ENABLED=true`) once a real ES instance
is available at `Config.ES_URL`.
"""

import requests

from config import Config

SKIPPED = "skipped"


def es_enabled():
    """True if the ES feature flag is on."""
    return Config.ES_ENABLED


def ping():
    """True/False if enabled and reachable; 'disabled' sentinel if not."""
    if not es_enabled():
        return "disabled"
    try:
        resp = requests.get(Config.ES_URL, timeout=2)
        return resp.ok
    except Exception:
        return False


def index(doc):
    """Index a document. No-op (returns SKIPPED) when ES is disabled."""
    if not es_enabled():
        return SKIPPED
    try:
        resp = requests.post(f"{Config.ES_URL}/_doc", json=doc, timeout=5)
        return resp.ok
    except Exception:
        return False


def search(q):
    """Search for `q`. No-op (returns SKIPPED) when ES is disabled."""
    if not es_enabled():
        return SKIPPED
    try:
        resp = requests.get(
            f"{Config.ES_URL}/_search",
            params={"q": q},
            timeout=5,
        )
        if not resp.ok:
            return []
        return resp.json().get("hits", {}).get("hits", [])
    except Exception:
        return []
