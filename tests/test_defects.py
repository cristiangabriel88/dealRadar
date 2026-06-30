"""Unit tests for the Defect tab (no network).

The Defect view is brand/model-agnostic: a listing qualifies purely on fault
wording in its own title or description (``config.DEFECT_TOKENS`` /
``DEFECT_PHRASES``). The guarantees tested here: a fault word/phrase surfaces a
listing whatever its brand, a clean listing never does, standalone parts are
still filtered out, and results come back cheapest first.
"""

from __future__ import annotations

from olx_finder.defects import find_defect_signals, find_defects
from olx_finder.models import Listing
from olx_finder.products import BIKES


def make(
    id_: str,
    title: str,
    price: float = 1000,
    *,
    description: str | None = None,
) -> Listing:
    return Listing(
        id=id_,
        title=title,
        price=price,
        currency="RON",
        url=f"http://example/{id_}",
        city="Bucuresti",
        posted_at=None,
        thumbnail=None,
        raw_title=title,
        description=description,
    )


def test_token_in_title_surfaces() -> None:
    defects = find_defects([make("d", "Bicicleta MTB defecta")])
    assert [x.listing.id for x in defects] == ["d"]
    assert "defect" in defects[0].signals[0] or "defect" in " ".join(defects[0].signals)


def test_phrase_in_description_surfaces() -> None:
    # The fault is only in the body — non-title sources lean on the title, but
    # OLX/biklo expose the description where the honest caveat usually hides.
    lst = make("x", "Bicicleta de oras", description="frumoasa dar nu mai merge schimbatorul")
    defects = find_defects([lst])
    assert [d.listing.id for d in defects] == ["x"]
    assert "nu mai merge" in defects[0].signals


def test_clean_listing_does_not_surface() -> None:
    assert find_defects([make("c", "Trek Marlin 7 stare buna")]) == []


def test_brand_agnostic_unbranded_defect() -> None:
    # No recognised brand at all — the deal engine would never group it, but the
    # Defect tab judges it on its own wording.
    defects = find_defects([make("u", "vand ceva ruginit si stricat", 500)])
    assert [d.listing.id for d in defects] == ["u"]


def test_standalone_part_is_filtered_out() -> None:
    # "piese" is a strong part token: a bag of broken parts isn't a flip, so the
    # noise filter drops it before it can qualify as a defect.
    assert find_defects([make("p", "set piese bicicleta defecte")]) == []


def test_sub_floor_price_dropped() -> None:
    assert find_defects([make("lo", "bicicleta defecta", 50)]) == []


def test_sorted_cheapest_first() -> None:
    listings = [
        make("b", "bicicleta defecta", 1500),
        make("a", "bicicleta stricata", 600),
        make("c", "bicicleta nefunctionala", 900),
    ]
    order = [d.listing.id for d in find_defects(listings)]
    assert order == ["a", "c", "b"]


def test_signals_whole_word_only() -> None:
    # Whole-word matching: a fault token must stand alone, not be a substring.
    assert find_defect_signals("bicicleta indefecta") == []
    assert "defect" in find_defect_signals("bicicleta defect")


def test_multiple_signals_reported_longest_first() -> None:
    sigs = find_defect_signals("este defect, nu functioneaza deloc")
    assert "nu functioneaza" in sigs
    assert "defect" in sigs
    # Longest match first so the card badge shows the most specific wording.
    assert sigs.index("nu functioneaza") < sigs.index("defect")
