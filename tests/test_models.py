"""Unit tests for DealResult valuation properties (margin / ROI / fix-up)."""

from __future__ import annotations

import config
from olx_finder.models import DealResult, Group, Listing


def _deal(price: float, median: float, condition: str | None) -> DealResult:
    listing = Listing(
        id="1",
        title="Bicicleta test",
        price=price,
        currency="lei",
        url="http://example/1",
        city="Bucuresti",
        posted_at=None,
        thumbnail=None,
        raw_title="Bicicleta test",
        condition=condition,
    )
    group = Group(key="Trek|marlin", brand="Trek", model="marlin", listings=[listing])
    return DealResult(
        listing=listing,
        group=group,
        median=median,
        low=median,
        high=median,
        sample_size=5,
        mod_z=-2.0,
        percent_below=(median - price) / median,
        is_cheapest_in_group=True,
    )


def test_effective_touchup_by_condition() -> None:
    assert _deal(800, 1200, "like_new").effective_touchup == config.TOUCHUP_BUFFER_LIKE_NEW_LEI
    assert _deal(800, 1200, "needs_work").effective_touchup == config.TOUCHUP_BUFFER_NEEDS_WORK_LEI
    assert _deal(800, 1200, "refurbished").effective_touchup == config.TOUCHUP_BUFFER_LEI
    assert _deal(800, 1200, None).effective_touchup == config.TOUCHUP_BUFFER_LEI


def test_net_margin_subtracts_fixup() -> None:
    deal = _deal(800, 1200, "needs_work")
    # gross spread 400, minus the needs-work buffer.
    assert deal.estimated_margin == 400
    assert deal.net_margin == 400 - config.TOUCHUP_BUFFER_NEEDS_WORK_LEI


def test_roi_is_net_over_cost() -> None:
    deal = _deal(800, 1200, "like_new")  # buffer 0 -> net == gross == 400
    assert deal.roi == 400 / 800


def test_roi_rewards_cheap_flips() -> None:
    # A small cheap flip should out-ROI a big-ticket one with the same buffer.
    cheap = _deal(200, 500, "like_new")    # net 300 on 200 -> 150%
    pricey = _deal(3000, 3400, "like_new")  # net 400 on 3000 -> ~13%
    assert cheap.roi > pricey.roi
