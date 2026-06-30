"""Read the price stack and show, per brand+model, how the price band moved over
time and the current flip margin.

Where :mod:`olx_finder.daily` *writes* the history and flags individual deals,
this *reads* it for analysis: for each model it prints a day-by-day price band
(count / min / median / max) so you can watch the range drift, plus the margin of
buying the current cheapest and reselling at the recent typical price — gross,
net after the condition-based fix-up buffer, and ROI (the same flipper math the
live app's :class:`~olx_finder.models.DealResult` uses).

    python -m olx_finder.history_report                 # top models by gross margin
    python -m olx_finder.history_report --brand Trek     # drill into one brand
    python -m olx_finder.history_report --model marlin --days 60
    python -m olx_finder.history_report --top 30 --min-obs 4
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median as _median

import config
from olx_finder.models import _fmt


# --------------------------------------------------------------------------- #
# Margin math — mirrors DealResult.effective_touchup / net_margin / roi so the
# numbers here match the live app. Kept as a tiny standalone helper because those
# live as properties on the DealResult dataclass.
# --------------------------------------------------------------------------- #
def _effective_touchup(condition: str | None) -> float:
    if condition == "like_new":
        return config.TOUCHUP_BUFFER_LIKE_NEW_LEI
    if condition == "needs_work":
        return config.TOUCHUP_BUFFER_NEEDS_WORK_LEI
    return config.TOUCHUP_BUFFER_LEI  # "refurbished" and unknown use the default


# Constant from the modified z-score definition (see olx_finder/stats.py).
_MOD_Z_CONST = 0.6745


def _trim_off_band(records: list[tuple]) -> tuple[list[tuple], int]:
    """Drop off-band prices from a model's pool; return (kept, trimmed_count).

    Brand+model grouping is loose, so a pool can mix sub-models with very
    different values. Using the median + MAD (the robust spread the deal engine
    already relies on), a record whose modified z-score
    ``0.6745*(price-median)/MAD`` exceeds ``config.HISTORY_TRIM_MOD_Z`` is treated
    as off-band and removed, so the typical price and margins reflect comparable
    units. A small sample (below ``config.HISTORY_TRIM_MIN_SAMPLE``) or a
    zero-spread pool is left untouched — too little to trust a trim — and if a
    trim would collapse the pool below two prices it is abandoned rather than
    mislead. ``records`` are ``(day, price, condition, source, url)`` tuples.
    """
    if len(records) < config.HISTORY_TRIM_MIN_SAMPLE:
        return records, 0
    prices = [r[1] for r in records]
    med = _median(prices)
    mad = _median([abs(p - med) for p in prices])
    if mad == 0:
        return records, 0
    kept = [
        r for r in records
        if abs(_MOD_Z_CONST * (r[1] - med) / mad) <= config.HISTORY_TRIM_MOD_Z
    ]
    if len(kept) < 2:
        return records, 0
    return kept, len(records) - len(kept)


@dataclass(slots=True)
class DayBand:
    """One day's price band for a brand+model."""

    day: str
    count: int
    low: float
    median: float
    high: float


@dataclass(slots=True)
class ModelTrend:
    """A brand+model's price band over time plus its current flip margin."""

    brand: str
    model: str
    bands: list[DayBand]            # chronological
    obs: int                        # in-band observations across the window
    trimmed: int                    # off-band prices removed by the within-band guard
    typical: float                  # recent typical price (median over the in-band window)
    cheapest: float                 # cheapest listing on the latest day seen
    cheapest_condition: str | None
    cheapest_source: str
    cheapest_url: str | None

    @property
    def touchup(self) -> float:
        return _effective_touchup(self.cheapest_condition)

    @property
    def gross_margin(self) -> float:
        return self.typical - self.cheapest

    @property
    def net_margin(self) -> float:
        return self.gross_margin - self.touchup

    @property
    def roi(self) -> float:
        cost = self.cheapest + self.touchup
        return self.net_margin / cost if cost > 0 else 0.0

    @property
    def trend_pct(self) -> float | None:
        """Median change from the first to the last day with data (None if one day)."""
        if len(self.bands) < 2 or self.bands[0].median <= 0:
            return None
        return (self.bands[-1].median - self.bands[0].median) / self.bands[0].median


def _fetch_rows(
    conn: sqlite3.Connection, since: str, brand: str | None, model: str | None
) -> list[tuple]:
    sql = [
        "SELECT brand, model, observed_on, price, condition, source, url "
        "FROM price_history WHERE model IS NOT NULL AND observed_on >= ?"
    ]
    params: list = [since]
    if brand:
        sql.append("AND lower(brand) = lower(?)")
        params.append(brand)
    if model:
        sql.append("AND lower(model) LIKE lower(?)")
        params.append(f"%{model}%")
    sql.append("ORDER BY brand, model, observed_on")
    return conn.execute(" ".join(sql), params).fetchall()


def build_trends(
    db_path: str = config.HISTORY_DB_PATH,
    days: int = config.HISTORY_WINDOW_DAYS,
    min_obs: int = config.HISTORY_MIN_OBSERVATIONS,
    brand: str | None = None,
    model: str | None = None,
    today: str | None = None,
) -> list[ModelTrend]:
    """Assemble per brand+model price bands and margins over the trailing window."""
    today = today or date.today().isoformat()
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        rows = _fetch_rows(conn, since, brand, model)
    finally:
        conn.close()

    # Group rows by (brand, model) -> flat list of (day, price, condition, source, url).
    grouped: dict[tuple[str, str], list[tuple]] = {}
    for b, m, day, price, cond, source, url in rows:
        grouped.setdefault((b, m), []).append((day, price, cond, source, url))

    trends: list[ModelTrend] = []
    for (b, m), records in grouped.items():
        # Trim off-band sub-models before any statistic, so the typical price and
        # margins reflect comparable units (see _trim_off_band).
        kept, trimmed = _trim_off_band(records)
        if len(kept) < min_obs:
            continue

        by_day: dict[str, list[tuple]] = {}
        for day, price, cond, source, url in kept:
            by_day.setdefault(day, []).append((price, cond, source, url))
        bands = [
            DayBand(
                day=day,
                count=len(items),
                low=min(p for p, _, _, _ in items),
                median=_median([p for p, _, _, _ in items]),
                high=max(p for p, _, _, _ in items),
            )
            for day, items in sorted(by_day.items())
        ]
        # "Buy now" candidate: cheapest in-band listing on the most recent day.
        latest_items = by_day[bands[-1].day]
        cheapest = min(latest_items, key=lambda it: it[0])
        trends.append(
            ModelTrend(
                brand=b,
                model=m,
                bands=bands,
                obs=len(kept),
                trimmed=trimmed,
                typical=_median([p for _, p, _, _, _ in kept]),
                cheapest=cheapest[0],
                cheapest_condition=cheapest[1],
                cheapest_source=cheapest[2],
                cheapest_url=cheapest[3],
            )
        )

    trends.sort(key=lambda t: t.gross_margin, reverse=True)
    return trends


def _print_trend(t: ModelTrend) -> None:
    span = f"{t.obs} obs over {len(t.bands)} day(s)"
    if t.trimmed:
        span += f", {t.trimmed} off-band filtered"
    trend = ""
    if t.trend_pct is not None:
        arrow = "↑" if t.trend_pct > 0 else "↓" if t.trend_pct < 0 else "→"
        trend = f"  median {arrow}{abs(round(t.trend_pct * 100))}% over window"
    print(f"\n{t.brand} {t.model}  ({span}){trend}")
    print(f"  {'date':<12}{'n':>4}{'min':>9}{'median':>9}{'max':>9}")
    print("  " + "-" * 41)
    for b in t.bands:
        marker = "  <- latest" if b is t.bands[-1] else ""
        print(f"  {b.day:<12}{b.count:>4}{int(b.low):>9}{int(b.median):>9}{int(b.high):>9}{marker}")
    cond = t.cheapest_condition or "condition unknown"
    print(f"  Cheapest now: {_fmt(t.cheapest)} RON ({cond}, {t.cheapest_source})"
          + (f"  {t.cheapest_url}" if t.cheapest_url else ""))
    print(f"  Typical (≤{config.HISTORY_WINDOW_DAYS}d median): {_fmt(t.typical)} RON")
    print(f"  Margin: gross {_fmt(t.gross_margin)}  |  net ~{_fmt(t.net_margin)} "
          f"(after ~{_fmt(t.touchup)} fix-up)  |  ROI {round(t.roi * 100)}%")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Price band over time + flip margins from the daily history store."
    )
    parser.add_argument("--days", type=int, default=config.HISTORY_WINDOW_DAYS,
                        help="Trailing window in days (default: %(default)s)")
    parser.add_argument("--min-obs", type=int, default=config.HISTORY_MIN_OBSERVATIONS,
                        help="Skip models with fewer observations (default: %(default)s)")
    parser.add_argument("--top", type=int, default=20,
                        help="How many models to show, by gross margin (default: %(default)s)")
    parser.add_argument("--brand", default=None, help="Filter to one brand")
    parser.add_argument("--model", default=None, help="Filter to models matching this text")
    parser.add_argument("--db", default=config.HISTORY_DB_PATH, help="History DB path")
    args = parser.parse_args()

    trends = build_trends(
        db_path=args.db, days=args.days, min_obs=args.min_obs,
        brand=args.brand, model=args.model,
    )
    if not trends:
        print("No models with enough history yet. Run `python -m olx_finder.daily` "
              "for a few days first (or lower --min-obs).")
        return

    shown = trends[: args.top]
    print(f"Price band over time + flip margins — {len(shown)} of {len(trends)} models "
          f"(≥{args.min_obs} obs, last {args.days} days), biggest gross margin first.")
    for t in shown:
        _print_trend(t)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    main()
