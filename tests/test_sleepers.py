"""Unit tests for the Sleepers scorer (no network).

Sleepers deliberately invert the deal engine: they surface listings with no
recognised brand and no comparables — the ones ``build_groups`` drops — and
score them by neglect/mislabel signals. The key guarantees tested here are that
(1) an unbranded listing the deal engine discards still surfaces, and (2) a
missing optional signal (description, photo count) is neutral, never a penalty.
"""

from __future__ import annotations

from olx_finder.models import Listing
from olx_finder.products import BIKES
from olx_finder.sleepers import _score, find_sleepers
from olx_finder.stats import annotate_listings, build_groups, get_mode


def scored(title: str, price: float, median: float | None) -> tuple[float, list[str], list[str]]:
    """Brand-annotate a single listing (as find_sleepers does) then score it."""
    lst = make("t", title, price)
    annotate_listings([lst], BIKES)
    return _score(lst, median, BIKES)


def make(
    id_: str,
    title: str,
    price: float,
    *,
    description: str | None = None,
    photo_count: int | None = None,
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
        photo_count=photo_count,
    )


def test_unbranded_listing_surfaces_as_sleeper() -> None:
    # Five branded comparables plus one unbranded mystery the deal engine drops.
    pool = [make(str(i), f"Trek Marlin {i}", 2000) for i in range(5)]
    mystery = make("x", "bicicleta de vanzare", 900)
    listings = pool + [mystery]

    sleepers = find_sleepers(listings)
    surfaced = {s.listing.id for s in sleepers}
    assert "x" in surfaced
    sleeper = next(s for s in sleepers if s.listing.id == "x")
    assert "no brand named" in sleeper.reasons

    # Contrast: the deal engine never even groups the unbranded listing.
    groups = build_groups(listings, get_mode("brand_guarded"))
    grouped_ids = {lst.id for g in groups for lst in g.listings}
    assert "x" not in grouped_ids


def test_missing_description_is_neutral() -> None:
    # description=None and a long description score identically (signal not fired);
    # a genuinely short description fires the signal and scores strictly higher.
    none_desc = find_sleepers([make("a", "bicicleta oras", 5000, description=None)])
    long_desc = find_sleepers([make("b", "bicicleta oras", 5000, description="x" * 200)])
    short_desc = find_sleepers([make("c", "bicicleta oras", 5000, description="vand")])

    assert none_desc and long_desc and short_desc
    assert none_desc[0].score == long_desc[0].score
    assert short_desc[0].score > none_desc[0].score
    assert "minimal description" in short_desc[0].reasons


def test_missing_photo_count_is_neutral() -> None:
    none_pc = find_sleepers([make("a", "bicicleta oras", 5000, photo_count=None)])
    many_pc = find_sleepers([make("b", "bicicleta oras", 5000, photo_count=5)])
    one_pc = find_sleepers([make("c", "bicicleta oras", 5000, photo_count=1)])

    assert none_pc[0].score == many_pc[0].score   # None and 5 both fire nothing
    assert one_pc[0].score > none_pc[0].score      # 1 photo fires the signal
    assert "only 1 photo" in one_pc[0].reasons


def test_short_title_signal() -> None:
    # Branded (so "no brand" can't fire) — isolates the terse-title signal.
    short, reasons, _ = scored("Trek Marlin", 5000, None)
    long, _, _ = scored("Trek Marlin 7 mountain bike usoara", 5000, None)
    assert "terse title (2 words)" in reasons
    assert short > long


def test_motivated_keywords() -> None:
    score, reasons, _ = scored("bicicleta urgent mutare", 5000, None)
    assert any("motivated seller" in r for r in reasons)
    plain, _, _ = scored("bicicleta oras buna", 5000, None)
    assert score > plain


def test_cheap_vs_category_graded() -> None:
    # Branded, long title isolates the cheap-vs-category signal. Median = 2000.
    def cheap_score(price: float) -> float:
        return scored("Trek Marlin 7 mountain bike", price, 2000)[0]

    assert cheap_score(1000) > cheap_score(1360) > 0   # 50% > 32% below
    assert cheap_score(1800) == 0                       # 10% below: under threshold


def test_category_median_excludes_parts_and_low_price() -> None:
    listings = [
        make("1", "Trek Marlin", 2000),
        make("2", "Trek Marlin", 2000),
        make("3", "Trek Marlin", 2000),
        make("p", "cadru aluminiu 26", 1500),  # a (strong) part -> excluded from the pool
        make("lo", "bicicleta veche", 50),     # below the price floor -> excluded
        make("x", "bicicleta dama", 800),      # the unbranded sleeper
    ]
    sleepers = find_sleepers(listings)
    surfaced = {s.listing.id for s in sleepers}
    assert "p" not in surfaced and "lo" not in surfaced
    sleeper = next(s for s in sleepers if s.listing.id == "x")
    # Median over {2000,2000,2000,800} only — parts and sub-floor prices excluded.
    assert sleeper.category_median == 2000


def test_sort_score_then_cheapest() -> None:
    # Expensive fillers push the median high so both mysteries hit the cheap cap
    # (equal cheap contribution) -> equal score -> the cheaper one ranks first.
    fillers = [make(f"f{i}", "Trek Marlin", 10000) for i in range(5)]
    a = make("a", "bicicleta dama oras", 1000)
    b = make("b", "bicicleta dama oras", 2000)

    res = find_sleepers([b, a, *fillers])  # input order b-before-a
    order = [s.listing.id for s in res if s.listing.id in ("a", "b")]
    assert order == ["a", "b"]  # cheaper first despite equal score


def test_min_score_filters_weak() -> None:
    fillers = [make(f"f{i}", "Trek Marlin", 2000) for i in range(3)]
    weak = make("w", "Trek Marlin 7 mountain bike aluminiu", 2000)  # branded, priced normally
    strong = make("s", "bicicleta", 900)                            # unbranded, cheap
    surfaced = {x.listing.id for x in find_sleepers([weak, strong, *fillers])}
    assert "w" not in surfaced
    assert "s" in surfaced


def test_premium_component_signal() -> None:
    # Same length (so the short-title signal can't differ) isolates the parts
    # signal: naming a premium component scores higher and is reported.
    high, reasons, comps = scored("bicicleta mtb cu deore xt", 5000, None)
    low, _, comps2 = scored("bicicleta mtb cu cadru", 5000, None)
    assert "XT" in comps
    assert comps2 == []
    assert any("premium parts" in r for r in reasons)
    assert high > low


def test_premium_component_found_in_description() -> None:
    lst = make("d", "bicicleta de vanzare", 800, description="furca RockShox, frane hidraulice")
    annotate_listings([lst], BIKES)
    _, _, comps = _score(lst, None, BIKES)
    assert "RockShox" in comps
    assert "Hydraulic disc" in comps


def test_junk_tokens_dropped() -> None:
    fillers = [make(f"f{i}", "Trek Marlin", 2000) for i in range(3)]
    junk = make("j", "bicicleta fier dezmembrez", 300)
    surfaced = {x.listing.id for x in find_sleepers([junk, *fillers])}
    assert "j" not in surfaced
