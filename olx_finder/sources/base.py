"""The marketplace abstraction.

Adding another site (Publi24, etc.) is just a new subclass implementing
``search`` and returning normalized ``Listing`` objects — nothing downstream
(parsing, stats, UI) needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from olx_finder.models import Listing
from olx_finder.parsing import normalize


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


class MarketplaceSource(ABC):
    """A source of listings for a given query + city."""

    #: Short, human-readable identifier (e.g. "OLX"). Used in the UI and cache key.
    name: str = "base"

    @abstractmethod
    def search(self, query: str, city: str) -> list[Listing]:
        """Return current listings matching ``query`` in ``city``.

        Implementations should be polite (rate-limit, cap pages, back off on
        429/403) and return already-normalized :class:`Listing` objects.
        """
        raise NotImplementedError

    @abstractmethod
    def supported_cities(self) -> list[str]:
        """City names this source can search, for populating the UI dropdown."""
        raise NotImplementedError
