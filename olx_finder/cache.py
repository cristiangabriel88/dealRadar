"""SQLite-backed cache so repeated searches don't hammer the marketplace.

A whole result set (the list of raw listing dicts) is stored under a
(source, query, city) key with a timestamp. Reads within ``CACHE_TTL_MINUTES``
are served from SQLite. Listings are deduplicated by id on write.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

import config


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_cache (
            source     TEXT NOT NULL,
            query      TEXT NOT NULL,
            city       TEXT NOT NULL,
            fetched_at REAL NOT NULL,
            payload    TEXT NOT NULL,
            PRIMARY KEY (source, query, city)
        )
        """
    )
    return conn


def get(source: str, query: str, city: str, db_path: str = config.CACHE_DB_PATH) -> list[dict[str, Any]] | None:
    """Return cached raw listings if a fresh entry exists, else None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT fetched_at, payload FROM search_cache WHERE source=? AND query=? AND city=?",
            (source, query, city),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    fetched_at, payload = row
    if (time.time() - fetched_at) > config.CACHE_TTL_MINUTES * 60:
        return None
    return json.loads(payload)


def put(
    source: str,
    query: str,
    city: str,
    raw_listings: list[dict[str, Any]],
    db_path: str = config.CACHE_DB_PATH,
) -> None:
    """Store raw listings (deduplicated by id) for a search."""
    deduped: dict[str, dict[str, Any]] = {}
    for raw in raw_listings:
        deduped[str(raw.get("id"))] = raw
    payload = json.dumps(list(deduped.values()))
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO search_cache (source, query, city, fetched_at, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, query, city)
            DO UPDATE SET fetched_at=excluded.fetched_at, payload=excluded.payload
            """,
            (source, query, city, time.time(), payload),
        )
        conn.commit()
    finally:
        conn.close()
