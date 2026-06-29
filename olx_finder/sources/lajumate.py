"""Lajumate.ro source.

Lajumate is a Next.js app: its bikes-category page ships the listing objects as
JSON inside the ``__NEXT_DATA__`` script tag (``props.pageProps.adsServer`` and
``premiumAdsServer``), which is far more robust than scraping the Tailwind
markup. We page through the category (``?page=N``) and filter to the selected
city client-side. Each ad already carries a structured ``city`` object.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

import config
from olx_finder import cache
from olx_finder.models import Listing
from olx_finder.sources import _http
from olx_finder.sources.base import MarketplaceSource, matches_city


class LajumateSource(MarketplaceSource):
    """Fetch bicycle listings from Lajumate.ro via its embedded Next.js data."""

    name = "Lajumate"

    def __init__(self, use_cache: bool = True) -> None:
        self.use_cache = use_cache

    def supported_cities(self) -> list[str]:
        return sorted(config.CITIES)

    def search(self, query: str, city: str) -> list[Listing]:
        if city not in config.CITIES:
            raise ValueError(
                f"Unknown city {city!r}. Known cities: {', '.join(sorted(config.CITIES))}"
            )

        if self.use_cache:
            cached = cache.get(self.name, query, city)
            if cached is not None:
                return self._build(cached, city)

        raw = self._fetch_all()

        if self.use_cache:
            cache.put(self.name, query, city, raw)

        return self._build(raw, city)

    # ------------------------------------------------------------------ #

    def _build(self, raw: list[dict[str, Any]], city: str) -> list[Listing]:
        out = []
        for ad in raw:
            lst = self._to_listing(ad)
            if lst is not None and matches_city(city, lst.city):
                out.append(lst)
        return out

    def _fetch_all(self) -> list[dict[str, Any]]:
        """Page through the bikes category, politely, up to MAX_PAGES."""
        results: list[dict[str, Any]] = []
        seen: set[Any] = set()
        with _http.make_client() as client:
            for page in range(config.MAX_PAGES):
                params = {"page": page + 1} if page else None
                html = _http.get_html(client, config.LAJUMATE_BICYCLES_URL, params)
                if not html:
                    break
                ads, total_pages = self._parse_page(html)
                new = 0
                for ad in ads:
                    if ad.get("id") not in seen:
                        seen.add(ad.get("id"))
                        results.append(ad)
                        new += 1
                if new == 0:
                    break
                if total_pages and page + 1 >= total_pages:
                    break
                time.sleep(config.REQUEST_DELAY)
        return results

    @staticmethod
    def _parse_page(html: str) -> tuple[list[dict[str, Any]], int | None]:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("script", id="__NEXT_DATA__")
        if tag is None or not tag.string:
            return [], None
        try:
            pp = json.loads(tag.string)["props"]["pageProps"]
        except (ValueError, KeyError):
            return [], None
        ads = list(pp.get("premiumAdsServer") or []) + list(pp.get("adsServer") or [])
        total_pages = (pp.get("paginationServer") or {}).get("totalPages")
        return ads, total_pages

    def _to_listing(self, ad: dict[str, Any]) -> Listing | None:
        try:
            price = float(ad.get("price"))
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        slug = ad.get("slug") or ""
        currency = (ad.get("currency") or "RON").strip()
        if currency.lower() == "lei":
            currency = "RON"
        city = (ad.get("city") or {}).get("name") or ""
        image = (ad.get("mainImage") or {}).get("path")
        return Listing(
            id=f"lajumate:{ad.get('id')}",
            title=(ad.get("title") or "").strip(),
            price=price,
            currency=currency,
            url=f"{config.LAJUMATE_BASE}/ad/{slug}-{ad.get('id')}",
            city=city,
            posted_at=_parse_time(ad.get("listed_at")),
            thumbnail=f"{config.LAJUMATE_BASE}/{image}" if image else None,
            raw_title=ad.get("title") or "",
        )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
