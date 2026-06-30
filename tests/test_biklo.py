"""Offline tests for biklo/Publi24 description + photo-count extraction.

Confirms the richer JSON source (biklo) populates ``description``/``photo_count``
from its ad payload, while an HTML source (Publi24) that has neither leaves both
None — which the Sleepers scorer treats as "no signal" rather than a penalty.
"""

from __future__ import annotations

from typing import Any

from olx_finder.sources.biklo import BikloSource
from olx_finder.sources.publi24 import Publi24Source


def _ad(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 1,
        "post_type_id": "3",  # "Vând" (for sale)
        "price": 1000,
        "title": "Trek Marlin",
        "slug": "trek-marlin",
        "city": {"name": "Bucuresti"},
        "pictures": [{"filename": "a.jpg"}, {"filename": "b.jpg"}],
        "description": "<p>stare buna</p>",
    }
    base.update(overrides)
    return base


def test_biklo_extracts_photos_and_description() -> None:
    lst = BikloSource(use_cache=False)._to_listing(_ad())
    assert lst is not None
    assert lst.photo_count == 2
    assert lst.description == "stare buna"


def test_biklo_without_pictures_or_description() -> None:
    lst = BikloSource(use_cache=False)._to_listing(_ad(pictures=None, description=None))
    assert lst is not None
    assert lst.photo_count == 0
    assert lst.description is None


def test_publi24_leaves_description_and_photos_none() -> None:
    raw = {
        "id": "1",
        "title": "Bicicleta de vanzare",
        "url": "https://www.publi24.ro/anunt/1",
        "price": "1000 RON",
        "city": "Bucuresti",
        "thumbnail": None,
    }
    lst = Publi24Source()._to_listing(raw)
    assert lst is not None
    assert lst.description is None
    assert lst.photo_count is None
