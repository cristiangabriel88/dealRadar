"""Unit tests for the daily job's assembly (no network)."""

from __future__ import annotations

import config
from olx_finder import daily
from olx_finder.daily import _is_excluded, _to_observations
from olx_finder.models import Listing
from olx_finder.sources import FacebookSource


def make(id_: str, title: str, price: float, *, brand: str | None = None,
         model: str | None = None) -> Listing:
    lst = Listing(
        id=id_,
        title=title,
        price=price,
        currency="RON",
        url=f"http://example/{id_}",
        city="Bucuresti",
        posted_at=None,
        thumbnail=None,
        raw_title=title,
    )
    lst.brand = brand
    lst.model = model
    lst.source = "OLX"
    return lst


def test_facebook_is_excluded_from_bike_sources() -> None:
    assert FacebookSource not in daily.BIKE_SOURCES.values()
    assert "Facebook Marketplace" not in daily.BIKE_SOURCES
    # The other five live-app bike sources are all present.
    assert set(daily.BIKE_SOURCES) == {"OLX", "Publi24", "Lajumate", "Anuntul", "biklo.ro"}


def test_to_observations_keeps_clean_branded_whole_bikes() -> None:
    listings = [
        make("keep", "Trek Marlin 7", 2000, brand="Trek", model="Marlin 7"),
        make("nobrand", "bicicleta oarecare", 1500, brand=None),
        make("cheap", "Trek", config.MIN_PLAUSIBLE_PRICE - 1, brand="Trek"),
    ]
    obs = _to_observations(listings)
    ids = {o.listing_id for o in obs}
    assert "keep" in ids
    assert "nobrand" not in ids   # no recognised brand
    assert "cheap" not in ids     # below MIN_PLAUSIBLE_PRICE


def test_to_observations_drops_parts() -> None:
    # A clearly parts-only listing (strong part-noise token "cadru") must not
    # pollute the whole-bike price stack, even with a brand attached.
    part = make("part", "Cadru carbon Trek", 2000, brand="Trek")
    kept = make("bike", "Cube Aim 27.5", 2000, brand="Cube", model="Aim")
    obs = _to_observations([part, kept])
    ids = {o.listing_id for o in obs}
    assert "bike" in ids
    assert "part" not in ids


def test_is_excluded_matches_config_words() -> None:
    if not config.EXCLUDE_TITLE_WORDS:
        return
    word = next(iter(config.EXCLUDE_TITLE_WORDS))
    assert _is_excluded(f"bicicleta {word} buna")
    assert not _is_excluded("Trek Marlin 7 stare buna")
