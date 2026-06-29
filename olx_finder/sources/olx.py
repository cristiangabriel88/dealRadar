"""OLX.ro source backed by the site's internal JSON offers API.

This uses the same endpoint OLX's own search calls
(``https://www.olx.ro/api/v1/offers/``), which returns clean JSON — no HTML
scraping. The bicycles category id (987) and the ``city_id`` filter were
confirmed from live network traffic. A minimal HTML fallback is provided only
for the case where the JSON endpoint is unavailable.
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
from olx_finder.sources.base import MarketplaceSource


class OlxSource(MarketplaceSource):
    """Fetch bicycle listings from OLX.ro via its internal offers API."""

    name = "OLX"

    def __init__(self, use_cache: bool = True) -> None:
        self.use_cache = use_cache

    # --------------------------------------------------------------------- #
    # MarketplaceSource interface
    # --------------------------------------------------------------------- #

    def supported_cities(self) -> list[str]:
        return sorted(config.CITIES)

    def search(self, product: Product, city: str, distance: int = 0) -> list[Listing]:
        if city == config.ALL_CITIES:
            city_id = None  # national search: omit the city_id filter
        else:
            city_id = config.CITIES.get(city)
            if city_id is None:
                raise ValueError(
                    f"Unknown city {city!r}. Known cities: {', '.join(sorted(config.CITIES))}"
                )

        query = product.query
        # OLX scopes by city + radius server-side, so the cache key must capture
        # both — otherwise a wider-radius search would reuse a narrower result.
        cache_key = f"{city}|{distance}"
        if self.use_cache:
            cached = cache.get(self.name, query, cache_key)
            if cached is not None:
                return [self._to_listing(raw) for raw in cached if self._to_listing(raw)]

        raw_listings = self._fetch_all(query, city_id, product.olx_category_id, distance)

        if self.use_cache:
            cache.put(self.name, query, cache_key, raw_listings)

        listings = [self._to_listing(raw) for raw in raw_listings]
        return [lst for lst in listings if lst is not None]

    # --------------------------------------------------------------------- #
    # Fetching
    # --------------------------------------------------------------------- #

    def _fetch_all(
        self, query: str, city_id: int | None, category_id: int | None, distance: int = 0
    ) -> list[dict[str, Any]]:
        """Page through the offers API, politely, up to MAX_PAGES.

        ``category_id`` scopes the search to a single OLX category when known; if
        it is ``None`` the search is by ``query`` keyword alone (across categories).
        ``city_id`` of ``None`` searches nationally. ``distance`` (km) expands the
        search to a radius around the city — OLX's own ``distance`` filter — and is
        ignored without a city to anchor it.
        """
        results: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()
        with _http.make_client({"Accept": "application/json"}) as client:
            for page in range(config.MAX_PAGES):
                offset = page * config.PAGE_LIMIT
                params: dict[str, Any] = {
                    "offset": offset,
                    "limit": config.PAGE_LIMIT,
                    "query": query,
                }
                if city_id is not None:
                    params["city_id"] = city_id
                    if distance and distance > 0:
                        params["distance"] = distance
                if category_id is not None:
                    params["category_id"] = category_id
                data = _http.get_json(client, config.OLX_OFFERS_ENDPOINT, params)
                items = data.get("data", []) if data else []
                if not items:
                    break

                new_items = 0
                for item in items:
                    if item.get("id") not in seen_ids:
                        seen_ids.add(item.get("id"))
                        results.append(item)
                        new_items += 1

                total = data.get("metadata", {}).get("total_elements")
                if new_items == 0:
                    break
                if total is not None and len(results) >= total:
                    break
                if len(items) < config.PAGE_LIMIT:
                    break  # last page

                time.sleep(config.REQUEST_DELAY)  # be polite between pages
        return results

    # --------------------------------------------------------------------- #
    # JSON -> Listing
    # --------------------------------------------------------------------- #

    def _to_listing(self, raw: dict[str, Any]) -> Listing | None:
        """Map one offers-API item to a normalized Listing (None if unusable)."""
        price, currency = self._extract_price(raw)
        if price is None:
            return None  # listings without a price can't be compared

        return Listing(
            id=str(raw.get("id")),
            title=raw.get("title", "").strip(),
            price=price,
            currency=currency or "RON",
            url=raw.get("url", ""),
            city=self._extract_city(raw),
            posted_at=self._parse_time(raw.get("created_time")),
            thumbnail=self._extract_thumbnail(raw),
            raw_title=raw.get("title", ""),
            brand_hint=self._extract_brand_hint(raw),
            wheel_inches=self._extract_wheel_inches(raw),
        )

    @staticmethod
    def _extract_price(raw: dict[str, Any]) -> tuple[float | None, str | None]:
        for param in raw.get("params", []):
            if param.get("key") == "price":
                value = param.get("value", {})
                raw_value = value.get("value")
                if raw_value is None:
                    return None, value.get("currency")
                try:
                    return float(raw_value), value.get("currency")
                except (TypeError, ValueError):
                    return None, value.get("currency")
        return None, None

    @staticmethod
    def _extract_brand_hint(raw: dict[str, Any]) -> str | None:
        for param in raw.get("params", []):
            if param.get("key") == "brand":
                value = param.get("value", {})
                return value.get("label") or value.get("key")
        return None

    @staticmethod
    def _extract_wheel_inches(raw: dict[str, Any]) -> float | None:
        for param in raw.get("params", []):
            if param.get("key") == "dimensiune_roata":
                label = (param.get("value", {}) or {}).get("label", "")
                # Labels look like '26"', '27.5"'.
                cleaned = label.replace('"', "").replace(",", ".").strip()
                try:
                    return float(cleaned)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _extract_city(raw: dict[str, Any]) -> str:
        location = raw.get("location") or {}
        city = location.get("city") or {}
        return city.get("name", "")

    @staticmethod
    def _extract_thumbnail(raw: dict[str, Any]) -> str | None:
        photos = raw.get("photos") or []
        if not photos:
            return None
        link = photos[0].get("link")
        if not link:
            return None
        # The link is a template with {width}x{height} placeholders.
        return link.replace("{width}", "640").replace("{height}", "480")

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
