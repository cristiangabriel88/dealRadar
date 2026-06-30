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


def test_negated_probleme_not_a_signal() -> None:
    # "fara probleme" = WITHOUT problems. The word is present but denied, so it
    # must not be reported and a clean listing must not surface.
    assert find_defect_signals("bicicleta merge fara probleme") == []
    assert find_defects([make("c", "bicicleta in stare buna, fara probleme")]) == []


def test_negation_cues_across_tokens() -> None:
    # Each negator that cancels a fault word, in its common Romanian forms.
    for clean in (
        "fara defecte",
        "fara niciun defect",
        "nu are defecte",
        "nu are nicio problema",
        "nu prezinta defecte",
        "niciun defect",
        "nicio problema",
        "nu este defecta",
        "nu a avut probleme",
        "zero probleme",
    ):
        assert find_defect_signals(f"bicicleta {clean}") == [], clean


def test_real_fault_kept_when_only_other_word_is_negated() -> None:
    # The reported listing: a genuine fault ("defect schimbator") AND a denial
    # ("fara probleme") in one description. The fault must surface; "probleme"
    # (denied) must not be among the reported signals.
    desc = "viteze 1/6 defect schimbator, dar se poate merge pe ea fara probleme"
    sigs = find_defect_signals("Bicicleta 28", desc)
    assert "defect" in sigs
    assert "probleme" not in sigs
    assert find_defects([make("r", "Bicicleta 28", description=desc)])[0].listing.id == "r"


def test_unnegated_occurrence_still_counts() -> None:
    # "nu doar defect" = NOT ONLY defective: the cue must end the lookback
    # window, so a "nu" further back does not cancel a real fault.
    assert "defect" in find_defect_signals("bicicleta nu doar defect ci si spart")
    # A second, denied occurrence does not erase a first, admitted one.
    assert "probleme" in find_defect_signals("are probleme la frana, in rest fara probleme")
