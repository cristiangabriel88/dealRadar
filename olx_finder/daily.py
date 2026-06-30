"""Once-a-day background scrape that builds the durable bike price history.

Run on the Raspberry Pi by cron (see the project README), e.g.::

    0 3 * * * cd /home/pi/dealRadar && /usr/bin/python3 -m olx_finder.daily \
        >> /home/pi/dealRadar/daily.log 2>&1

It scrapes *bikes only*, from every bike source **except Facebook Marketplace**
(that one needs a logged-in Playwright browser and is too fragile for an
unattended job), for Bucharest plus a radius, then appends what it saw to the
price stack in :mod:`olx_finder.history`. It is deliberately Flask-free so the Pi
never loads the web stack, and it leaves the live app (``app.py``) and its
5-minute cache untouched — this only ever writes ``history.db``.

The aggregation here mirrors ``app.py``'s ``aggregate`` (concurrent fetch, source
stamping, title exclusion, RON normalization, cross-source dedup) but is kept
separate so importing this module doesn't pull in Flask.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config
from olx_finder import history
from olx_finder.history import Observation
from olx_finder.models import Listing
from olx_finder.parsing import is_part_listing, normalize
from olx_finder.products import BIKES
from olx_finder.sources import (
    AnuntulSource,
    BikloSource,
    LajumateSource,
    OlxSource,
    Publi24Source,
)
from olx_finder.stats import annotate_listings, dedupe_cross_source, to_ron

# Every bike source the live app offers EXCEPT Facebook Marketplace. The name is
# the one stamped on each listing (and used by dedupe's source priority).
BIKE_SOURCES: dict[str, type] = {
    "OLX": OlxSource,
    "Publi24": Publi24Source,
    "Lajumate": LajumateSource,
    "Anuntul": AnuntulSource,
    "biklo.ro": BikloSource,
}


def _is_excluded(title: str) -> bool:
    """True when a title contains one of ``config.EXCLUDE_TITLE_WORDS`` as a word.

    Same hard title filter the web app applies before any view sees a listing
    (see ``app.py:_is_excluded``).
    """
    tokens = set(normalize(title).split())
    return bool(tokens & config.EXCLUDE_TITLE_WORDS)


def collect_listings(city: str, distance: int) -> list[Listing]:
    """Fetch every bike source (no Facebook), pool, dedup — like ``aggregate``.

    Sources are fetched concurrently; one that fails is logged and skipped rather
    than sinking the whole run. Prices are normalized to RON and the same item
    reposted across sites is collapsed to one listing.
    """
    def fetch(item: tuple[str, type]) -> tuple[str, list[Listing] | None, str | None]:
        name, source_cls = item
        try:
            listings = source_cls().search(BIKES, city, distance)
            for lst in listings:
                lst.source = name
            return name, listings, None
        except Exception as exc:  # one bad source must not sink the rest
            return name, None, f"{name}: {exc}"

    pooled: list[Listing] = []
    with ThreadPoolExecutor(max_workers=len(BIKE_SOURCES)) as pool:
        for name, listings, error in pool.map(fetch, BIKE_SOURCES.items()):
            if error is not None:
                print(f"  ! source failed, skipped — {error}", file=sys.stderr)
            else:
                print(f"  - {name}: {len(listings)} listings")
                pooled.extend(listings)

    if config.EXCLUDE_TITLE_WORDS:
        pooled = [lst for lst in pooled if not _is_excluded(lst.title)]

    return dedupe_cross_source(to_ron(pooled))


def _to_observations(listings: list[Listing]) -> list[Observation]:
    """Keep clean, brand-known whole-bike listings and map them to observations.

    Applies the same noise gate the deal pipeline uses (``stats._passes_noise_filter``):
    implausibly cheap listings and parts/accessories are dropped, and a listing
    must have a recognised brand to land in a brand+model stack.
    """
    observations: list[Observation] = []
    for lst in listings:
        if lst.price < config.MIN_PLAUSIBLE_PRICE:
            continue
        if is_part_listing(lst.title, BIKES):
            continue
        if not lst.brand:
            continue
        observations.append(
            Observation(
                listing_id=lst.id,
                source=lst.source,
                brand=lst.brand,
                model=lst.model,
                title=lst.title,
                price=lst.price,
                currency=lst.currency,
                city=lst.city,
                url=lst.url,
                condition=lst.condition,
            )
        )
    return observations


def main() -> None:
    observed_on = datetime.now().date().isoformat()
    city, distance = config.HISTORY_CITY, config.HISTORY_DISTANCE_KM
    print(f"[{observed_on}] daily bike scrape — {city} +{distance}km "
          f"(sources: {', '.join(BIKE_SOURCES)})")

    listings = collect_listings(city, distance)
    annotate_listings(listings, BIKES)  # fills brand/model/condition in place
    observations = _to_observations(listings)
    written = history.record_observations(observations, observed_on)
    print(f"Stored {written} observations "
          f"({len(listings)} pooled, {len(observations)} kept after noise filter).")

    deals = history.todays_deals(observed_on)
    if deals:
        print(f"\nTop deals vs the {config.HISTORY_WINDOW_DAYS}-day average:")
        for d in deals[:10]:
            pct = round((d["pct_below"] or 0) * 100)
            print(f"  -{pct:>2}%  {d['price']:>7.0f} RON  "
                  f"[{d['brand']} {d['model']}]  {d['title'][:48]}")
            print(f"        avg ~{d['hist_mean']:.0f} / median ~{d['hist_median']:.0f} "
                  f"RON over {d['hist_n']} obs — {d['url']}")
    else:
        print("\nNo deals vs history yet (the stack needs a few days to build up).")


if __name__ == "__main__":
    # UTF-8 stdout on Windows consoles (diacritics in titles/cities), as cli.py does.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    main()
