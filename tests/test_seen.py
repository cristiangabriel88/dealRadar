"""Unit tests for the "new since last scan" registry (no network, temp DB)."""

from __future__ import annotations

from olx_finder import seen
from olx_finder.models import Listing


def listing(listing_id: str, *, source: str = "OLX", price: float = 2000) -> Listing:
    return Listing(
        id=listing_id,
        title=f"Bicicleta {listing_id}",
        price=price,
        currency="RON",
        url=f"http://example/{listing_id}",
        city="Bucuresti",
        posted_at=None,
        thumbnail=None,
        raw_title=f"Bicicleta {listing_id}",
        source=source,
    )


def _db(tmp_path) -> str:
    return str(tmp_path / "seen.db")


def test_first_scan_flags_everything_new(tmp_path) -> None:
    db = _db(tmp_path)
    listings = [listing("a"), listing("b")]
    new_count = seen.mark_and_flag(listings, db_path=db)
    assert new_count == 2
    assert all(lst.is_new for lst in listings)
    assert all(lst.first_seen is not None for lst in listings)


def test_second_scan_flags_nothing_new_and_keeps_first_seen(tmp_path) -> None:
    db = _db(tmp_path)
    first = [listing("a"), listing("b")]
    seen.mark_and_flag(first, db_path=db)
    original_first_seen = first[0].first_seen

    # Re-scan the same ids: none should be new, and first_seen must be preserved.
    again = [listing("a"), listing("b")]
    new_count = seen.mark_and_flag(again, db_path=db)
    assert new_count == 0
    assert not any(lst.is_new for lst in again)
    assert again[0].first_seen == original_first_seen


def test_only_unseen_ids_are_new_on_a_later_scan(tmp_path) -> None:
    db = _db(tmp_path)
    seen.mark_and_flag([listing("a")], db_path=db)

    batch = [listing("a"), listing("c")]  # "a" seen before, "c" brand new
    new_count = seen.mark_and_flag(batch, db_path=db)
    assert new_count == 1
    flags = {lst.id: lst.is_new for lst in batch}
    assert flags == {"a": False, "c": True}


def test_same_id_different_source_is_a_distinct_listing(tmp_path) -> None:
    db = _db(tmp_path)
    seen.mark_and_flag([listing("a", source="OLX")], db_path=db)

    # The same id on another marketplace is a different (id, source) pair — new.
    other = [listing("a", source="Publi24")]
    new_count = seen.mark_and_flag(other, db_path=db)
    assert new_count == 1
    assert other[0].is_new
