"""Offline parsing tests for the Facebook Marketplace source.

No browser, no network: feed a saved fixture page to the pure DOM parser and
check the produced ``Listing`` objects and the client-side city filter. The
browser-only ``_fetch_all`` is not exercised here.
"""

from __future__ import annotations

from pathlib import Path

import config
from olx_finder.sources.facebook import FacebookSource

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_facebook_parse_and_to_listing() -> None:
    src = FacebookSource(use_cache=False)
    raw = src._parse_page(_read("facebook_sample.html"))
    # Unique cards in order; the duplicate of card 1 (appended last) is dropped.
    # Card 6 uses the location-scoped "/marketplace/np/item/<id>/" link form.
    assert [r["id"] for r in raw] == [
        "1111111111", "2222222222", "3333333333", "4444444444", "5555555555",
        "6666666666",
    ]

    listings = [src._to_listing(r) for r in raw]
    trek = listings[0]
    assert trek.id == "fb:1111111111"
    assert trek.title == "Bicicleta Trek Marlin 7"
    assert trek.price == 2000.0          # "2.000 lei" -> 2000 (dot = thousands)
    assert trek.currency == "RON"
    assert trek.city == "Sector 3, Bucuresti"
    assert trek.url == "https://www.facebook.com/marketplace/item/1111111111/"
    assert trek.thumbnail == "https://scontent.xx.fbcdn.net/v/photo1.jpg"

    cube = listings[1]
    assert cube.id == "fb:2222222222"
    assert cube.price == 500.0
    assert cube.currency == "EUR"        # "€500" -> EUR
    assert cube.city == "Cluj-Napoca"
    assert cube.thumbnail is None        # data: lazy-load placeholder dropped

    # The "Gratuit" card has no comparable price, so it yields no Listing.
    assert listings[2] is None

    # Discounted card: the current (first) price wins over the struck-through one.
    discounted = listings[3]
    assert discounted.price == 1500.0
    assert discounted.currency == "RON"
    assert discounted.title == "Bicicleta GT Avalanche redusa"
    assert discounted.city == "Brasov"

    # Logged-out US default: "120 USD" parses with a USD currency.
    usd = listings[4]
    assert usd.price == 120.0
    assert usd.currency == "USD"

    # The "/np/item/" location-scoped link form is parsed like a plain item link.
    np_card = listings[5]
    assert np_card.id == "fb:6666666666"
    assert np_card.price == 800.0
    assert np_card.title == "Bicicleta Btwin Rockrider"
    assert np_card.city == "Pantelimon, Bucuresti"
    assert np_card.url == "https://www.facebook.com/marketplace/item/6666666666/"


def test_facebook_build_filters_to_selected_city() -> None:
    # FB pins the search to Bucharest but still returns out-of-area cards, so
    # _build client-filters to the selected city scope. With "Bucuresti" and
    # "this city only" (distance 0), only the Bucharest cards survive — the
    # Cluj-Napoca, Brasov and San Francisco cards are dropped (and the
    # free/unpriced one yields no Listing).
    src = FacebookSource(use_cache=False)
    raw = src._parse_page(_read("facebook_sample.html"))
    kept = src._build(raw, "Bucuresti", 0)
    assert [l.city for l in kept] == [
        "Sector 3, Bucuresti", "Pantelimon, Bucuresti",
    ]


def test_facebook_build_radius_widens_scope() -> None:
    # A radius pulls in nearby main cities: Brasov is ~143km from Bucharest, so
    # a +150km search keeps it alongside the Bucharest cards. Cluj (~330km) and
    # San Francisco stay out of scope.
    src = FacebookSource(use_cache=False)
    raw = src._parse_page(_read("facebook_sample.html"))
    kept = src._build(raw, "Bucuresti", 150)
    assert [l.city for l in kept] == [
        "Sector 3, Bucuresti", "Brasov", "Pantelimon, Bucuresti",
    ]


def test_facebook_build_national_keeps_all() -> None:
    # An ALL_CITIES (national) search applies no city filter.
    src = FacebookSource(use_cache=False)
    raw = src._parse_page(_read("facebook_sample.html"))
    kept = src._build(raw, config.ALL_CITIES, 0)
    assert [l.city for l in kept] == [
        "Sector 3, Bucuresti", "Cluj-Napoca", "Brasov",
        "San Francisco, CA", "Pantelimon, Bucuresti",
    ]
