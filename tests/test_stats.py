"""Unit tests for grouping and modified-z-score outlier detection (no network)."""

from __future__ import annotations

from olx_finder.models import Listing
from olx_finder.stats import build_groups, dedupe_cross_source, flag_deals, get_mode


def make(
    id_: str,
    title: str,
    price: float,
    *,
    wheel: float | None = None,
    brand_hint: str | None = None,
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
        brand_hint=brand_hint,
        wheel_inches=wheel,
    )


def test_flags_clear_low_outlier() -> None:
    # Five comparable Trek Marlins clustered ~2000, one obvious outlier at 1000.
    prices = [1900, 2000, 2100, 2000, 2050, 1000]
    listings = [make(str(i), f"Trek Marlin 7 nr {i}", p) for i, p in enumerate(prices)]
    mode = get_mode("brand_guarded")
    groups = build_groups(listings, mode)
    deals = flag_deals(groups, mode)

    assert len(deals) == 1
    deal = deals[0]
    assert deal.listing.price == 1000
    assert deal.is_cheapest_in_group is True
    assert deal.percent_below > 0.4  # ~50% below median of 2000
    assert deal.mod_z <= -1.5
    # Profit framing: resale spread = typical (median) − asking.
    assert deal.estimated_margin == deal.median - deal.listing.price
    assert deal.estimated_margin == 1000  # median 2000 − asking 1000


def test_below_min_samples_not_flagged() -> None:
    # Only 4 samples (< MIN_SAMPLES=5) -> no deals, no stats.
    listings = [make(str(i), f"Giant Talon {i}", p) for i, p in enumerate([2000, 2000, 2000, 800])]
    mode = get_mode("brand_guarded")
    groups = build_groups(listings, mode)
    assert all(g.median is None for g in groups)
    assert flag_deals(groups, mode) == []


def test_mad_zero_treats_cheaper_as_outlier() -> None:
    # All identical except one much cheaper: MAD becomes 0 for the cluster.
    prices = [2000, 2000, 2000, 2000, 2000, 900]
    listings = [make(str(i), "Cube Aim 240", p) for i, p in enumerate(prices)]
    mode = get_mode("brand_guarded")
    groups = build_groups(listings, mode)
    deals = flag_deals(groups, mode)
    assert len(deals) == 1
    assert deals[0].listing.price == 900
    assert deals[0].mod_z == float("-inf")


def test_noise_filters_low_price_and_parts() -> None:
    listings = [
        make("a", "Trek Marlin 7", 2000),
        make("b", "Trek Marlin 7", 2100),
        make("c", "Trek Marlin 7", 1950),
        make("d", "Trek Marlin 7", 2050),
        make("e", "Trek Marlin 7", 2000),
        make("f", "Trek Marlin 7", 50),       # implausibly low -> dropped
        make("g", "Cadru Trek Marlin", 1000),  # part -> dropped
    ]
    mode = get_mode("brand_guarded")
    groups = build_groups(listings, mode)
    trek = next(g for g in groups if g.brand == "Trek")
    assert trek.count == 5  # the 50-lei and the frame are excluded


def test_guarded_mode_excludes_kids() -> None:
    # A set of comparable 14" kids Btwins of the same model, one a cheap outlier.
    prices = [600, 620, 610, 600, 300]
    listings = [
        make(str(i), "Btwin 500 copii 14 inch", p, wheel=14.0)
        for i, p in enumerate(prices)
    ]

    guarded = get_mode("brand_guarded")
    deals_guarded = flag_deals(build_groups(listings, guarded), guarded)
    # Kids bikes excluded entirely from the pool -> nothing to flag.
    assert deals_guarded == []

    raw = get_mode("brand_raw")
    deals_raw = flag_deals(build_groups(listings, raw), raw)
    # Without the guard the kids form their own model group and the outlier flags.
    assert any(d.listing.price == 300 for d in deals_raw)


def test_lone_model_not_flagged_against_brand_pool() -> None:
    # A pool of Cube bikes of assorted models plus a single very cheap Cube of a
    # one-off model. Even though it is far below the overall Cube median, it has
    # no same-model comparables, so its market value cannot be estimated and it
    # must NOT be flagged (the regression this change fixes).
    listings = [
        make("a", "Cube Aim 29", 2000),
        make("b", "Cube Aim 29", 2100),
        make("c", "Cube Aim 29", 1950),
        make("d", "Cube Reaction 29", 3000),
        make("e", "Cube Attention 27", 2500),
        make("f", "Cube Touring SL 28", 900),  # lone one-off model, very cheap
    ]
    mode = get_mode("brand_guarded")
    deals = flag_deals(build_groups(listings, mode), mode)
    assert all(d.listing.id != "f" for d in deals)


def test_brand_match_flags_lone_model() -> None:
    # Same lone-one-off scenario, but matching by brand only: the listing is now
    # valued against the whole Cube pool, so it IS flagged ("work like before").
    listings = [
        make("a", "Cube Aim 29", 2000),
        make("b", "Cube Aim 29", 2100),
        make("c", "Cube Aim 29", 1950),
        make("d", "Cube Reaction 29", 3000),
        make("e", "Cube Attention 27", 2500),
        make("f", "Cube Touring SL 28", 900),  # lone one-off, very cheap
    ]
    mode = get_mode("brand_guarded")
    groups = build_groups(listings, mode)

    brand_deals = flag_deals(groups, mode, match_level="brand")
    assert any(d.listing.id == "f" for d in brand_deals)

    # ...whereas the default brand+model matching does NOT flag it.
    model_deals = flag_deals(groups, mode, match_level="brand_model")
    assert all(d.listing.id != "f" for d in model_deals)


def test_model_flagged_when_comparables_exist() -> None:
    # Same shape as above, but now there ARE comparable Touring SLs establishing
    # the model's ~2600 market, and one is far below it -> that one is flagged,
    # valued against its same-model peers (not the broader Cube pool).
    listings = [
        make("a", "Cube Aim 29", 2000),
        make("b", "Cube Aim 29", 2100),
        make("c", "Cube Touring SL 28", 2600),
        make("d", "Cube Touring SL 28", 2700),
        make("e", "Cube Touring SL 28", 2550),
        make("f", "Cube Touring SL 28", 1200),
    ]
    mode = get_mode("brand_guarded")
    deals = flag_deals(build_groups(listings, mode), mode)
    assert len(deals) == 1
    assert deals[0].listing.id == "f"
    assert deals[0].group.model == "touring sl"
    assert deals[0].sample_size == 4


def test_strict_mode_requires_model() -> None:
    # Brand present, but no parseable model for any listing.
    listings = [make(str(i), "Bicicleta Nakamura", p) for i, p in enumerate([1900, 2000, 2100, 800])]
    strict = get_mode("strict")
    groups = build_groups(listings, strict)
    # Group exists with >= STRICT_MIN_SAMPLES(3) but model is unknown -> no deals.
    assert flag_deals(groups, strict) == []


def test_strict_mode_flags_within_model() -> None:
    prices = [800, 850, 900, 400]
    listings = [make(str(i), "Rockrider ST120", p) for i, p in enumerate(prices)]
    strict = get_mode("strict")
    groups = build_groups(listings, strict)
    deals = flag_deals(groups, strict)
    assert len(deals) == 1
    assert deals[0].listing.price == 400
    assert deals[0].group.model == "st120"


def _sourced(id_: str, title: str, price: float, source: str) -> Listing:
    lst = make(id_, title, price)
    lst.source = source
    return lst


def test_dedupe_collapses_cross_source_repost() -> None:
    listings = [
        _sourced("1", "Trek Marlin 7 stare buna", 2000, "Publi24"),
        _sourced("2", "Trek Marlin 7  stare bună!", 2000, "OLX"),  # same item, OLX wins
        _sourced("3", "Cube Aim 2021", 1500, "Lajumate"),          # distinct, kept
    ]
    out = dedupe_cross_source(listings)
    assert len(out) == 2
    trek = next(l for l in out if l.price == 2000)
    assert trek.source == "OLX"  # higher-priority source kept on a tie
    assert {l.price for l in out} == {2000, 1500}


def test_dedupe_keeps_distinct_titles_and_prices() -> None:
    listings = [
        _sourced("1", "Trek Marlin 7", 2000, "OLX"),
        _sourced("2", "Trek Marlin 7", 1800, "Publi24"),  # same title, diff price
    ]
    out = dedupe_cross_source(listings)
    assert len(out) == 2


def test_dedupe_preserves_order_and_first_seen() -> None:
    listings = [
        _sourced("1", "Giant Talon", 2500, "Anuntul"),
        _sourced("2", "Specialized Rockhopper", 3000, "OLX"),
        _sourced("3", "Giant Talon", 2500, "Lajumate"),  # dup of #1; Lajumate < Anuntul
    ]
    out = dedupe_cross_source(listings)
    assert [l.title for l in out] == ["Giant Talon", "Specialized Rockhopper"]
    assert out[0].source == "Lajumate"  # higher priority than Anuntul
