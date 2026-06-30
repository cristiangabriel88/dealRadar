"""Offline tests for the OLX source's radius/merge logic.

OLX scopes by city + radius server-side and returns only a capped, recency-sorted
window of offers. A wider radius has many more total offers, so the city's own
listings can fall out of that window — making a +Nkm result *smaller* than the
city-only one. ``search`` guards against that by merging the distance-0 page in,
so the radius result is always a superset of the city-only result. These tests
stub ``_fetch_all`` so no network or browser is involved.
"""

from __future__ import annotations

from typing import Any

from olx_finder.products import get_product
from olx_finder.sources.olx import OlxSource


def _offer(offer_id: int, price: float = 1000.0) -> dict[str, Any]:
    """A minimal raw OLX offer that ``_to_listing`` can map to a Listing."""
    return {
        "id": offer_id,
        "title": f"Bicicleta {offer_id}",
        "url": f"https://www.olx.ro/d/oferta/{offer_id}",
        "params": [{"key": "price", "value": {"value": price, "currency": "RON"}}],
    }


def test_merge_raw_keeps_city_listings_and_dedups() -> None:
    # primary (city) listings lead; secondary (radius) adds new ids and drops
    # ids already present in primary.
    primary = [_offer(1), _offer(2)]
    secondary = [_offer(2), _offer(3)]  # 2 overlaps, 3 is new
    merged = OlxSource._merge_raw(primary, secondary)
    assert [m["id"] for m in merged] == [1, 2, 3]


def test_radius_result_is_superset_of_city_only(monkeypatch) -> None:
    # Simulate OLX's capped window: the distance-0 fetch returns the city's
    # listings; the +100km fetch returns a *different* window (the city's older
    # offers pushed out by nearer-town ones). Without the merge, listing 1 and 2
    # would vanish at +100km.
    city_only = [_offer(1), _offer(2)]
    radius_only = [_offer(3), _offer(4), _offer(5)]  # note: 1 and 2 absent

    def fake_fetch(self, query, city_id, category_id, distance=0):
        return city_only if distance == 0 else radius_only

    monkeypatch.setattr(OlxSource, "_fetch_all", fake_fetch)

    src = OlxSource(use_cache=False)
    prod = get_product("bikes")

    base_ids = {l.id for l in src.search(prod, "Bucuresti", 0)}
    radius_ids = {l.id for l in src.search(prod, "Bucuresti", 100)}

    assert base_ids <= radius_ids  # every city listing survives the radius search
    assert base_ids == {"1", "2"}
    assert radius_ids == {"1", "2", "3", "4", "5"}


def test_distance_zero_does_not_double_fetch(monkeypatch) -> None:
    # A city-only search must not trigger the extra distance-0 merge fetch.
    calls: list[int] = []

    def fake_fetch(self, query, city_id, category_id, distance=0):
        calls.append(distance)
        return [_offer(1)]

    monkeypatch.setattr(OlxSource, "_fetch_all", fake_fetch)

    src = OlxSource(use_cache=False)
    src.search(get_product("bikes"), "Bucuresti", 0)
    assert calls == [0]  # exactly one fetch, no merge pass
