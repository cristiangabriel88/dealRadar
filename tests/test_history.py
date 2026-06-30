"""Unit tests for the durable price-history store (no network, temp DB)."""

from __future__ import annotations

from datetime import date, timedelta

import config
from olx_finder import history
from olx_finder.history import Observation


def obs(
    listing_id: str,
    price: float,
    *,
    brand: str = "Trek",
    model: str | None = "Marlin 7",
    source: str = "OLX",
) -> Observation:
    return Observation(
        listing_id=listing_id,
        source=source,
        brand=brand,
        model=model,
        title=f"{brand} {model} {listing_id}",
        price=price,
        currency="RON",
        city="Bucuresti",
        url=f"http://example/{listing_id}",
        condition=None,
    )


def _db(tmp_path) -> str:
    return str(tmp_path / "history.db")


def test_record_is_idempotent_same_day(tmp_path) -> None:
    db = _db(tmp_path)
    day = "2026-06-30"
    history.record_observations([obs("a", 2000), obs("b", 2100)], day, db_path=db)
    # Same day again (e.g. a re-run) must upsert, not duplicate.
    history.record_observations([obs("a", 1950), obs("b", 2100)], day, db_path=db)

    conn = history._connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        price_a = conn.execute(
            "SELECT price FROM price_history WHERE listing_id='a'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2
    assert price_a == 1950  # latest write wins


def test_trailing_stats_uses_prior_days_only(tmp_path) -> None:
    db = _db(tmp_path)
    d1, d2 = "2026-06-01", "2026-06-02"
    history.record_observations(
        [obs("a", 2000), obs("b", 2100), obs("c", 1900)], d1, db_path=db
    )
    # Today's listings should NOT count toward today's own average.
    history.record_observations([obs("x", 500), obs("y", 600)], d2, db_path=db)

    conn = history._connect(db)
    try:
        mean, median, n = history.trailing_stats(conn, "Trek", "Marlin 7", d2)
    finally:
        conn.close()
    assert n == 3  # only the three from d1, not the two cheap ones from d2
    assert median == 2000
    assert round(mean) == 2000


def test_trailing_stats_below_minimum_returns_none(tmp_path) -> None:
    db = _db(tmp_path)
    d1, d2 = "2026-06-01", "2026-06-02"
    # Only two prior observations — under HISTORY_MIN_OBSERVATIONS (3).
    history.record_observations([obs("a", 2000), obs("b", 2100)], d1, db_path=db)
    history.record_observations([obs("x", 1000)], d2, db_path=db)

    conn = history._connect(db)
    try:
        mean, median, n = history.trailing_stats(conn, "Trek", "Marlin 7", d2)
    finally:
        conn.close()
    assert (mean, median) == (None, None)
    assert n == 2


def test_window_excludes_old_observations(tmp_path) -> None:
    db = _db(tmp_path)
    today = date(2026, 6, 30)
    old = (today - timedelta(days=config.HISTORY_WINDOW_DAYS + 5)).isoformat()
    recent = (today - timedelta(days=2)).isoformat()
    history.record_observations(
        [obs("o1", 9000), obs("o2", 9000), obs("o3", 9000)], old, db_path=db
    )
    history.record_observations(
        [obs("r1", 2000), obs("r2", 2000), obs("r3", 2000)], recent, db_path=db
    )

    conn = history._connect(db)
    try:
        mean, median, n = history.trailing_stats(
            conn, "Trek", "Marlin 7", today.isoformat()
        )
    finally:
        conn.close()
    assert n == 3  # the old batch fell outside the trailing window
    assert median == 2000


def test_deal_flagged_only_when_below_median_threshold(tmp_path) -> None:
    db = _db(tmp_path)
    d1, d2 = "2026-06-01", "2026-06-02"
    # A solid market history clustered around 2000.
    history.record_observations(
        [obs("a", 1950), obs("b", 2000), obs("c", 2050), obs("d", 2000)], d1, db_path=db
    )
    # Day 2: one clear bargain, one priced at the median (not a deal).
    cheap = round(2000 * (1 - config.MIN_PERCENT_BELOW) - 1)
    history.record_observations(
        [obs("deal", cheap), obs("fair", 2000)], d2, db_path=db
    )

    deals = history.todays_deals(d2, db_path=db)
    assert [d["listing_id"] for d in deals] == ["deal"]
    d = deals[0]
    assert d["hist_n"] == 4
    assert d["hist_median"] == 2000
    assert d["pct_below"] >= config.MIN_PERCENT_BELOW


def test_unknown_model_is_stored_but_never_flagged(tmp_path) -> None:
    db = _db(tmp_path)
    d1, d2 = "2026-06-01", "2026-06-02"
    history.record_observations(
        [obs(f"h{i}", 2000, model=None) for i in range(5)], d1, db_path=db
    )
    history.record_observations([obs("x", 100, model=None)], d2, db_path=db)

    # Stored (the row exists) ...
    conn = history._connect(db)
    try:
        row = conn.execute(
            "SELECT is_deal, hist_n FROM price_history WHERE listing_id='x'"
        ).fetchone()
    finally:
        conn.close()
    assert row == (0, 0)  # ... but no model => no same-model history => no flag
    assert history.todays_deals(d2, db_path=db) == []
