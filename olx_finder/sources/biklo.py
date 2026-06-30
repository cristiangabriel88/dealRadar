"""Biklo.ro source.

Biklo is a bike-only marketplace: a Next.js front-end backed by a clean Laravel
JSON API. Its "bazar" classifieds expose a per-category, page-based endpoint
(``/api/bazar-ads-elastic/biciclete?page=N``) returning a Laravel paginator —
``posts.data`` is the listing array, ``posts.last_page`` the page count. We page
through the whole-bikes ("biciclete") category and filter to the selected city
client-side (the feed is national). Each ad carries a structured ``city`` object
and a ``brand`` tag we pass through as a brand hint. Prices are always RON.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import config
from olx_finder import cache
from olx_finder.models import Listing
from olx_finder.products import Product
from olx_finder.sources import _http
from olx_finder.sources._util import strip_html
from olx_finder.sources.base import MarketplaceSource, city_in_scope

# post_type_id of "Vând" (for sale). The bazar also carries wanted/exchange/
# donate posts (4/5/6) which are not deals, so we keep only sell listings.
_SELL_POST_TYPE = "3"


class BikloSource(MarketplaceSource):
    """Fetch bicycle listings from biklo.ro via its bazar JSON API."""

    name = "biklo.ro"

    def __init__(self, use_cache: bool = True) -> None:
        self.use_cache = use_cache

    def supported_cities(self) -> list[str]:
        return sorted(config.CITIES)

    def search(self, product: Product, city: str, distance: int = 0) -> list[Listing]:
        if city != config.ALL_CITIES and city not in config.CITIES:
            raise ValueError(
                f"Unknown city {city!r}. Known cities: {', '.join(sorted(config.CITIES))}"
            )

        query = product.query  # bike-only feed; query used only for the cache key
        # National feed; city/radius scope is applied in _build, so we cache by
        # city alone (raw is radius-independent) and re-filter on read.
        if self.use_cache:
            cached = cache.get(self.name, query, city)
            if cached is not None:
                return self._build(cached, city, distance)

        raw = self._fetch_all()

        if self.use_cache:
            cache.put(self.name, query, city, raw)

        return self._build(raw, city, distance)

    # ------------------------------------------------------------------ #

    def _build(self, raw: list[dict[str, Any]], city: str, distance: int = 0) -> list[Listing]:
        out = []
        for ad in raw:
            lst = self._to_listing(ad)
            if lst is not None and city_in_scope(city, distance, lst.city):
                out.append(lst)
        return out

    def _fetch_all(self) -> list[dict[str, Any]]:
        """Page through the bikes category, politely, up to MAX_PAGES."""
        results: list[dict[str, Any]] = []
        seen: set[Any] = set()
        with _http.make_client({"Accept": "application/json"}) as client:
            for page in range(config.MAX_PAGES):
                params = {"page": page + 1}
                data = _http.get_json(client, config.BIKLO_BICYCLES_URL, params)
                if not data:
                    break
                posts = data.get("posts") or {}
                ads = posts.get("data") or []
                new = 0
                for ad in ads:
                    if ad.get("id") not in seen:
                        seen.add(ad.get("id"))
                        results.append(ad)
                        new += 1
                if new == 0:
                    break
                last_page = posts.get("last_page")
                if last_page and page + 1 >= last_page:
                    break
                time.sleep(config.REQUEST_DELAY)
        return results

    def _to_listing(self, ad: dict[str, Any]) -> Listing | None:
        # Only listings being sold; drafts/sold ones are not buyable deals.
        if str(ad.get("post_type_id")) != _SELL_POST_TYPE:
            return None
        if str(ad.get("is_draft")) == "1" or str(ad.get("is_sold")) == "1":
            return None
        try:
            price = float(ad.get("price"))
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        slug = ad.get("slug") or ""
        city = (ad.get("city") or {}).get("name") or ""
        return Listing(
            id=f"biklo:{ad.get('id')}",
            title=(ad.get("title") or "").strip(),
            price=price,
            currency="RON",  # biklo prices are always in lei
            url=f"{config.BIKLO_BASE}/bazar/{slug}",
            city=city,
            posted_at=_parse_time(ad.get("created_at")),
            thumbnail=_first_image(ad.get("pictures")),
            raw_title=ad.get("title") or "",
            brand_hint=ad.get("brand") or None,
            description=strip_html(ad.get("description")),
            photo_count=len(ad.get("pictures") or []),
        )


def _first_image(pictures: Any) -> str | None:
    """Build the storage URL of a listing's first picture, if any."""
    if not isinstance(pictures, list) or not pictures:
        return None
    filename = (pictures[0] or {}).get("filename")
    return f"{config.BIKLO_IMAGE_BASE}{filename}" if filename else None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
