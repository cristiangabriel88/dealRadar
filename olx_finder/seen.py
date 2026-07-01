""""New since last scan" registry — what the web app has already laid eyes on.

Every search records the ``(listing_id, source)`` of the listings it pooled,
stamped with the first and last time they were seen. A listing is *new* when
this is the first time it has ever appeared in any prior scan — the signal a
flipper wants for reaching a fresh, mislabelled listing before other buyers.
``first_seen`` also gives a cross-source age ("seen 3 days ago") that works even
for the sources that carry no ``posted_at``.

One table, ``seen_listings``, keyed by ``(listing_id, source)`` so a repeated
scan upserts rather than duplicating — the same ``ON CONFLICT … DO UPDATE`` idiom
as :mod:`olx_finder.cache`. This is deliberately its own file (not the TTL cache,
not the daily history stack): clearing the cache must not forget what's new.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime

import config
from olx_finder.models import Listing


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_listings (
            listing_id TEXT NOT NULL,
            source     TEXT NOT NULL,
            first_seen REAL NOT NULL,
            last_seen  REAL NOT NULL,
            PRIMARY KEY (listing_id, source)
        )
        """
    )
    return conn


def mark_and_flag(listings: list[Listing], db_path: str = config.SEEN_DB_PATH) -> int:
    """Flag which listings are new, then record every one as seen.

    Annotates each :class:`~olx_finder.models.Listing` in place: ``is_new`` is
    True when its ``(id, source)`` has never been recorded before, and
    ``first_seen`` is set to the datetime it was first observed (now, for a new
    one). All rows are then upserted with ``last_seen = now``, leaving an
    existing ``first_seen`` untouched. Idempotent within a scan; an immediate
    re-run of the same search flags nothing new.

    Returns the number of listings that were new this call.
    """
    now = time.time()
    conn = _connect(db_path)
    try:
        # One read: the first_seen of every pair we already know about.
        known: dict[tuple[str, str], float] = {
            (row[0], row[1]): row[2]
            for row in conn.execute(
                "SELECT listing_id, source, first_seen FROM seen_listings"
            )
        }
        new_count = 0
        for lst in listings:
            key = (lst.id, lst.source)
            prior = known.get(key)
            if prior is None:
                lst.is_new = True
                lst.first_seen = datetime.fromtimestamp(now)
                new_count += 1
            else:
                lst.is_new = False
                lst.first_seen = datetime.fromtimestamp(prior)
            conn.execute(
                """
                INSERT INTO seen_listings (listing_id, source, first_seen, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(listing_id, source)
                DO UPDATE SET last_seen=excluded.last_seen
                """,
                (lst.id, lst.source, prior if prior is not None else now, now),
            )
        conn.commit()
        return new_count
    finally:
        conn.close()
