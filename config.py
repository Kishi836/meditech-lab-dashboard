"""
Meditech Lab 2.0 — configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Central place for environment-driven settings. Every key has a sane
local-dev default so the app runs out of the box against the lab's
docker-compose stack (Postgres on localhost:5432, ES optional).
"""

import os


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean-ish environment variable (e.g. '1', 'true', 'yes')."""
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    DB_DSN = os.environ.get(
        "DB_DSN", "postgresql://admin:adminpassword@localhost:5432/healthcare_db"
    )
    ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
    ES_ENABLED = _env_bool("ES_ENABLED", False)
    ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", "data/archive")
