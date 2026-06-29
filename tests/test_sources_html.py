"""Offline parsing tests for the HTML/embedded-JSON marketplace sources.

No network: each test feeds a saved fixture page to the source's parser and
checks the produced ``Listing`` objects and the client-side city filter. Run the
sources with ``use_cache=False`` so the SQLite cache is never touched.
"""

from __future__ import annotations

from pathlib import Path

from olx_finder.sources.anuntul import AnuntulSource
from olx_finder.sources.lajumate import LajumateSource
from olx_finder.sources.publi24 import Publi24Source

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Publi24
# --------------------------------------------------------------------------- #

def test_publi24_parse_and_to_listing() -> None:
    src = Publi24Source(use_cache=False)
    raw = src._parse_page(_read("publi24_sample.html"))
    assert len(raw) == 2

    listings = [src._to_listing(r) for r in raw]
    trek = listings[0]
    assert trek.id == "publi24:ABC-123"
    assert trek.title == "Bicicleta Trek Marlin 7"
    assert trek.price == 2000.0
    assert trek.currency == "RON"
    assert trek.city == "Sector 3, Bucuresti"
    assert trek.thumbnail == "https://s3.publi24.ro/x/photo1.jpg"
    # The no_img.png placeholder is dropped to None.
    assert listings[1].thumbnail is None


def test_publi24_city_filter() -> None:
    src = Publi24Source(use_cache=False)
    raw = src._parse_page(_read("publi24_sample.html"))
    kept = src._build(raw, "Bucuresti")
    assert [l.city for l in kept] == ["Sector 3, Bucuresti"]


# --------------------------------------------------------------------------- #
# Lajumate
# --------------------------------------------------------------------------- #

def test_lajumate_parse_and_to_listing() -> None:
    src = LajumateSource(use_cache=False)
    ads, total_pages = src._parse_page(_read("lajumate_sample.html"))
    assert total_pages == 1
    # Premium ads come first, then regular ads.
    assert [a["id"] for a in ads] == [16789437, 16869877]

    trek = src._to_listing(ads[0])
    assert trek.id == "lajumate:16789437"
    assert trek.price == 1400.0
    assert trek.currency == "RON"  # "lei" normalized to RON
    assert trek.city == "Bucuresti"
    assert trek.url == "https://lajumate.ro/ad/bicicleta-trek-marlin-7-16789437"
    assert trek.thumbnail == "https://lajumate.ro/media/i/big/x/0.webp"
    assert trek.posted_at is not None

    cube = src._to_listing(ads[1])
    assert cube.thumbnail is None
    assert cube.posted_at is not None  # ISO-8601 with Z parses


def test_lajumate_city_filter() -> None:
    src = LajumateSource(use_cache=False)
    ads, _ = src._parse_page(_read("lajumate_sample.html"))
    kept = src._build(ads, "Cluj-Napoca")
    assert [l.city for l in kept] == ["Cluj-Napoca"]


# --------------------------------------------------------------------------- #
# Anuntul
# --------------------------------------------------------------------------- #

def test_anuntul_parse_and_to_listing() -> None:
    src = AnuntulSource(use_cache=False)
    raw = src._parse_page(_read("anuntul_sample.html"))
    assert len(raw) == 2

    bike = src._to_listing(raw[0])
    assert bike.id == "anuntul:67032701"
    assert bike.title == "Bicicleta Trek Marlin 7"
    assert bike.price == 1000.0          # "1.000 RON" -> 1000 (dot = thousands)
    assert bike.currency == "RON"
    assert bike.city == "Bucuresti"      # city part before the comma
    assert bike.url == "https://www.anuntul.ro/anunt-vand-bicicleta-trek-zMoGJ7"
    assert bike.thumbnail is None        # /build/no-photo placeholder dropped

    house = src._to_listing(raw[1])
    assert house.price == 108779.0
    assert house.currency == "EUR"


def test_anuntul_city_filter() -> None:
    src = AnuntulSource(use_cache=False)
    raw = src._parse_page(_read("anuntul_sample.html"))
    kept = src._build(raw, "Bucuresti")
    assert [l.city for l in kept] == ["Bucuresti"]
