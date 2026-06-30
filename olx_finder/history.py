"""Durable price history — the per-brand+model price stack the daily job builds.

Unlike :mod:`olx_finder.cache` (a 5-minute TTL cache that is overwritten on each
refresh and keeps only the latest snapshot), this is a *time series*: every daily
run appends the listings it observed, stamped with the date, and they are never
overwritten across days. With a stack of recent prices per brand+model, a new
listing can be valued against the *average of recent prices* rather than only the
current snapshot the live app compares against.

One table, ``price_history``, with the primary key ``(observed_on, listing_id,
source)`` so a same-day re-run upserts rather than duplicating. The ``hist_*``
columns hold the comparison computed at write time against the *prior* days'
observations (see :func:`record_observations`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean as _mean, median as _median
from typing import Any

import config


@dataclass(slots=True)
class Observation:
    """One listing seen on a given day, ready to be stored in the price stack."""

    listing_id: str
    source: str
    brand: str | None
    model: str | None
    title: str
    price: float          # normalized RON
    currency: str
    city: str | None
    url: str | None
    condition: str | None


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            observed_on   TEXT NOT NULL,
            listing_id    TEXT NOT NULL,
            source        TEXT NOT NULL,
            brand         TEXT,
            model         TEXT,
            title         TEXT NOT NULL,
            price         REAL NOT NULL,
            currency      TEXT NOT NULL,
            city          TEXT,
            url           TEXT,
            condition     TEXT,
            hist_mean     REAL,
            hist_median   REAL,
            hist_n        INTEGER,
            pct_below     REAL,
            is_deal       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (observed_on, listing_id, source)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_hist_brand_model "
        "ON price_history (brand, model, observed_on)"
    )
    return conn


def trailing_stats(
    conn: sqlite3.Connection,
    brand: str,
    model: str,
    before_on: str,
    days: int = config.HISTORY_WINDOW_DAYS,
) -> tuple[float | None, float | None, int]:
    """Mean, median and count of recent prices for one brand+model.

    Considers observations of this exact ``brand``+``model`` in the window
    ``[before_on - days, before_on)`` — strictly *before* ``before_on``, so a
    listing is always valued against history, never against itself. Returns
    ``(None, None, n)`` when fewer than :data:`config.HISTORY_MIN_OBSERVATIONS`
    comparables exist (no trustworthy average yet).
    """
    start = (date.fromisoformat(before_on) - timedelta(days=days)).isoformat()
    prices = [
        row[0]
        for row in conn.execute(
            """
            SELECT price FROM price_history
            WHERE brand = ? AND model = ?
              AND observed_on >= ? AND observed_on < ?
            """,
            (brand, model, start, before_on),
        )
    ]
    n = len(prices)
    if n < config.HISTORY_MIN_OBSERVATIONS:
        return None, None, n
    return _mean(prices), _median(prices), n


def record_observations(
    observations: list[Observation],
    observed_on: str,
    db_path: str = config.HISTORY_DB_PATH,
) -> int:
    """Append a day's observations to the stack, computing the deal flags.

    For every observation we look up the trailing-window average/median of its
    brand+model (prior days only) and store it alongside the row. A row is
    flagged ``is_deal`` when there is enough history *and* its price is at least
    :data:`config.MIN_PERCENT_BELOW` under the historical median (median, not
    mean, to stay robust to the odd extreme repost — same reasoning as the
    snapshot deal engine). Observations without a parsed model can't be valued
    against same-model history, so they are stored with empty stats and never
    flagged. Idempotent for a given day via the primary-key upsert.

    Returns the number of rows written.
    """
    conn = _connect(db_path)
    try:
        written = 0
        for obs in observations:
            hist_mean = hist_median = pct_below = None
            hist_n = 0
            is_deal = 0
            if obs.brand and obs.model:
                hist_mean, hist_median, hist_n = trailing_stats(
                    conn, obs.brand, obs.model, observed_on
                )
                if hist_median is not None and hist_median > 0:
                    pct_below = (hist_median - obs.price) / hist_median
                    if pct_below >= config.MIN_PERCENT_BELOW:
                        is_deal = 1
                    else:
                        pct_below = None  # only record the margin when it's a deal
            conn.execute(
                """
                INSERT INTO price_history (
                    observed_on, listing_id, source, brand, model, title,
                    price, currency, city, url, condition,
                    hist_mean, hist_median, hist_n, pct_below, is_deal
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observed_on, listing_id, source) DO UPDATE SET
                    brand=excluded.brand, model=excluded.model, title=excluded.title,
                    price=excluded.price, currency=excluded.currency, city=excluded.city,
                    url=excluded.url, condition=excluded.condition,
                    hist_mean=excluded.hist_mean, hist_median=excluded.hist_median,
                    hist_n=excluded.hist_n, pct_below=excluded.pct_below,
                    is_deal=excluded.is_deal
                """,
                (
                    observed_on, obs.listing_id, obs.source, obs.brand, obs.model,
                    obs.title, obs.price, obs.currency, obs.city, obs.url, obs.condition,
                    hist_mean, hist_median, hist_n, pct_below, is_deal,
                ),
            )
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()


def todays_deals(
    observed_on: str, db_path: str = config.HISTORY_DB_PATH
) -> list[dict[str, Any]]:
    """Rows flagged ``is_deal`` for ``observed_on``, biggest discount first.

    A convenience read over the stored flags (no UI consumes it yet); handy for
    the daily run's stdout summary and for any future view over the history.
    """
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM price_history
            WHERE observed_on = ? AND is_deal = 1
            ORDER BY pct_below DESC
            """,
            (observed_on,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
