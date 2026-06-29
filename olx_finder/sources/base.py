"""The marketplace abstraction.

Adding another site (Publi24, etc.) is just a new subclass implementing
``search`` and returning normalized ``Listing`` objects — nothing downstream
(parsing, stats, UI) needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from math import asin, cos, radians, sin, sqrt

import config
from olx_finder.models import Listing
from olx_finder.parsing import normalize
from olx_finder.products import Product


def matches_city(selected: str, listing_city: str | None) -> bool:
    """Whether a listing's location belongs to the selected city.

    OLX scopes by city server-side, but the other sources return national results
    that we filter here. We compare on normalized text and accept a substring
    match either way so "Bucuresti" matches "Sector 6, Bucuresti" and
    "Drobeta-Turnu Severin" matches "Drobeta Turnu Severin".
    """
    want = normalize(selected)
    have = normalize(listing_city or "")
    if not want or not have:
        return False
    return want in have or have in want


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    lat1, lon1 = a
    lat2, lon2 = b
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def cities_within(selected_city: str, distance_km: int) -> list[str]:
    """Main cities within ``distance_km`` of ``selected_city`` (including it).

    Falls back to just the selected city when no radius is requested or the city
    has no known coordinates (e.g. it isn't in MAIN_CITIES).
    """
    origin = config.MAIN_CITIES.get(selected_city)
    if origin is None or distance_km <= 0:
        return [selected_city]
    return [
        name
        for name, coord in config.MAIN_CITIES.items()
        if _haversine(origin, coord) <= distance_km
    ]


def city_in_scope(selected_city: str, distance_km: int, listing_city: str | None) -> bool:
    """Whether a client-filtered listing falls within the selected search scope.

    ``ALL_CITIES`` matches everything (national search). Otherwise a listing is
    in scope when its locality matches the selected city, or — when a radius is
    set — any main city within that radius of it.
    """
    if selected_city == config.ALL_CITIES:
        return True
    return any(
        matches_city(name, listing_city)
        for name in cities_within(selected_city, distance_km)
    )


class MarketplaceSource(ABC):
    """A source of listings for a given query + city."""

    #: Short, human-readable identifier (e.g. "OLX"). Used in the UI and cache key.
    name: str = "base"

    @abstractmethod
    def search(self, product: Product, city: str, distance: int = 0) -> list[Listing]:
        """Return current listings for ``product`` in ``city``.

        The ``product`` carries the search query and this source's category
        endpoint for that product (see :class:`~olx_finder.products.Product`).
        ``city`` may be :data:`config.ALL_CITIES` for a national search, and
        ``distance`` is the search radius in km around ``city`` (0 = that city
        only). Implementations should be polite (rate-limit, cap pages, back off
        on 429/403) and return already-normalized :class:`Listing` objects.
        """
        raise NotImplementedError

    @abstractmethod
    def supported_cities(self) -> list[str]:
        """City names this source can search, for populating the UI dropdown."""
        raise NotImplementedError
