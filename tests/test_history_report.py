"""Unit tests for the price-band-over-time / margin report (no network, temp DB)."""

from __future__ import annotations

from statistics import median as _median

import config
from olx_finder import history, history_report
from olx_finder.history import Observation


def o(i: str, price: float, *, condition: str | None = None,
      brand: str = "Trek", model: str | None = "Marlin 7") -> Observation:
    return Observation(i, "OLX", brand, model, f"{brand} {model} {i}", price,
                       "RON", "Bucuresti", f"http://x/{i}", condition)


def _seed_three_days(db: str) -> None:
    history.record_observations([o("a", 2000), o("b", 2100), o("c", 2200)], "2026-06-28", db_path=db)
    history.record_observations([o("d", 1900), o("e", 2000), o("f", 2100)], "2026-06-29", db_path=db)
    history.record_observations([o("g", 1500), o("h", 1850), o("i", 2000)], "2026-06-30", db_path=db)


def test_bands_are_chronological_with_correct_stats(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    _seed_three_days(db)
    [t] = history_report.build_trends(db_path=db, today="2026-06-30")
    assert [b.day for b in t.bands] == ["2026-06-28", "2026-06-29", "2026-06-30"]
    last = t.bands[-1]
    assert (last.low, last.median, last.high, last.count) == (1500, 1850, 2000, 3)
    assert t.obs == 9


def test_trend_pct_reflects_first_to_last_median(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    _seed_three_days(db)
    [t] = history_report.build_trends(db_path=db, today="2026-06-30")
    # First-day median 2100 -> last-day median 1850.
    assert round(t.trend_pct * 100) == round((1850 - 2100) / 2100 * 100)


def test_margin_uses_cheapest_latest_and_window_median(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    _seed_three_days(db)
    [t] = history_report.build_trends(db_path=db, today="2026-06-30")
    assert t.cheapest == 1500            # cheapest on the latest day
    assert t.typical == 2000             # median over all nine observations
    assert t.gross_margin == 500
    # Unknown condition -> default fix-up buffer.
    assert t.touchup == config.TOUCHUP_BUFFER_LEI
    assert t.net_margin == 500 - config.TOUCHUP_BUFFER_LEI


def test_condition_sizes_the_touchup_buffer(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    history.record_observations(
        [o("a", 2000), o("b", 2100), o("g", 1500, condition="like_new")],
        "2026-06-30", db_path=db,
    )
    [t] = history_report.build_trends(db_path=db, today="2026-06-30")
    assert t.cheapest_condition == "like_new"
    assert t.touchup == config.TOUCHUP_BUFFER_LIKE_NEW_LEI  # 0
    assert t.net_margin == t.gross_margin


def test_min_obs_and_filters(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    history.record_observations(
        [o("a", 2000, model="Marlin 7"), o("b", 2100, model="Marlin 7"),
         o("c", 2200, model="Marlin 7"), o("x", 900, brand="Cube", model="Aim")],
        "2026-06-30", db_path=db,
    )
    # Cube Aim has only 1 obs -> excluded by min_obs=3.
    keys = {(t.brand, t.model) for t in history_report.build_trends(db_path=db, today="2026-06-30")}
    assert keys == {("Trek", "Marlin 7")}
    # Brand filter narrows correctly (and case-insensitively).
    assert history_report.build_trends(db_path=db, today="2026-06-30", brand="trek")
    assert history_report.build_trends(db_path=db, today="2026-06-30", brand="Cube") == []


def test_off_band_submodels_are_trimmed(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    # An alloy cluster ~2800-3500 plus two carbon outliers that pollute the band.
    prices = [2800, 3000, 3200, 3300, 3500, 2900, 3100, 12000, 14500]
    history.record_observations(
        [o(str(i), p) for i, p in enumerate(prices)], "2026-06-30", db_path=db
    )
    [t] = history_report.build_trends(db_path=db, today="2026-06-30")
    assert t.trimmed == 2
    assert t.obs == 7
    assert t.bands[-1].high == 3500          # the 14500 no longer sets the top
    assert t.typical == _median([2800, 3000, 3200, 3300, 3500, 2900, 3100])


def test_small_sample_is_not_trimmed(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    # Three points (below HISTORY_TRIM_MIN_SAMPLE) — even a wild spread is kept,
    # because the spread can't be trusted on so little data.
    history.record_observations(
        [o("a", 2800), o("b", 4999), o("c", 14500)], "2026-06-30", db_path=db
    )
    [t] = history_report.build_trends(db_path=db, today="2026-06-30")
    assert t.trimmed == 0
    assert t.obs == 3


def test_unknown_model_rows_are_ignored(tmp_path) -> None:
    db = str(tmp_path / "h.db")
    history.record_observations(
        [o(str(i), 2000, model=None) for i in range(5)], "2026-06-30", db_path=db
    )
    assert history_report.build_trends(db_path=db, today="2026-06-30") == []
