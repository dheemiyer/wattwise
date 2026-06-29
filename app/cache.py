"""Tiny SQLite TTL cache for upstream API responses.

We never store user data here -- only public grid data keyed by region/date,
so repeated lookups don't hammer EIA. Values are JSON strings.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "wattwise_cache.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
        """
    )
    return conn


def get(key: str):
    """Return cached value (parsed JSON) or None if missing/expired."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    value, expires_at = row
    if expires_at < time.time():
        return None
    return json.loads(value)


def set(key: str, value, ttl_seconds: int) -> None:
    """Cache a JSON-serializable value for `ttl_seconds`."""
    expires_at = time.time() + ttl_seconds
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), expires_at),
        )
        conn.commit()
