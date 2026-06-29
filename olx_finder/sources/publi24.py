"""Publi24.ro source.

Publi24 has no public JSON API, but its bicycles *category* page renders clean
server-side HTML: each listing is a ``div.article-item`` carrying the id, a
title link, price, and location. We page through that category (``?pag=N``) and
filter to the selected city client-side (Publi24 only scopes by county in its
URLs). The bicycle category already keeps us on-topic; the downstream brand /
parts filtering removes any stray accessories.
"""

from __future__ import annotations

import re
import time
from typing import Any

from bs4 import BeautifulSoup

import config
from olx_finder import cache
from olx_finder.models import Listing
from olx_finder.products import Product
from olx_finder.sources import _http
from olx_finder.sources.base import MarketplaceSource, city_in_scope

_DIGITS = re.compile(r"[\d.\s]+")


class Publi24Source(MarketplaceSource):
    """Fetch bicycle listings from Publi24.ro's bicycles category page."""

    name = "Publi24"

    def __init__(self, use_cache: bool = True) -> None:
        self.use_cache = use_cache

    def supported_cities(self) -> list[str]:
        return sorted(config.CITIES)

    def search(self, product: Product, city: str, distance: int = 0) -> list[Listing]:
        if city != config.ALL_CITIES and city not in config.CITIES:
            raise ValueError(
                f"Unknown city {city!r}. Known cities: {', '.join(sorted(config.CITIES))}"
            )
        if product.publi24_url is None:
            return []  # Publi24 has no category page for this product

        query = product.query
        # The fetched feed is national; the city/radius scope is applied in
        # _build, so the cache is keyed by city alone (raw is the same for any
        # radius) and re-filtered on read.
        if self.use_cache:
            cached = cache.get(self.name, query, city)
            if cached is not None:
                return self._build(cached, city, distance)

        raw = self._fetch_all(product.publi24_url)

        if self.use_cache:
            cache.put(self.name, query, city, raw)

        return self._build(raw, city, distance)

    # ------------------------------------------------------------------ #

    def _build(self, raw: list[dict[str, Any]], city: str, distance: int) -> list[Listing]:
        out = []
        for item in raw:
            lst = self._to_listing(item)
            if lst is not None and city_in_scope(city, distance, lst.city):
                out.append(lst)
        return out

    def _fetch_all(self, category_url: str) -> list[dict[str, Any]]:
        """Page through the product's category, politely, up to MAX_PAGES."""
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        with _http.make_client() as client:
            for page in range(config.MAX_PAGES):
                params = {"pag": page + 1} if page else None
                html = _http.get_html(client, category_url, params)
                if not html:
                    break
                items = self._parse_page(html)
                new = 0
                for item in items:
                    if item["id"] and item["id"] not in seen:
                        seen.add(item["id"])
                        results.append(item)
                        new += 1
                if new == 0:
                    break  # no more / repeated page
                time.sleep(config.REQUEST_DELAY)
        return results

    @staticmethod
    def _parse_page(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        items: list[dict[str, Any]] = []
        for art in soup.select(".article-item"):
            a = art.select_one("h2.article-title a")
            if a is None:
                continue
            img = art.select_one("img")
            src = (img.get("data-src") or img.get("src")) if img else None
            if src and "no_img" in src:
                src = None
            items.append(
                {
                    "id": art.get("data-articleid"),
                    "title": a.get_text(" ", strip=True),
                    "url": a.get("href"),
                    "price": _text(art.select_one(".article-price")),
                    "city": _text(art.select_one(".article-location")),
                    "thumbnail": src,
                }
            )
        return items

    def _to_listing(self, raw: dict[str, Any]) -> Listing | None:
        price, currency = _parse_price(raw.get("price"))
        if price is None:
            return None
        return Listing(
            id=f"publi24:{raw.get('id')}",
            title=(raw.get("title") or "").strip(),
            price=price,
            currency=currency,
            url=raw.get("url") or "",
            city=raw.get("city") or "",
            posted_at=None,  # Publi24 shows only relative dates ("ieri 22:58")
            thumbnail=raw.get("thumbnail"),
            raw_title=raw.get("title") or "",
        )


def _text(node: Any) -> str | None:
    return node.get_text(" ", strip=True) if node is not None else None


def _parse_price(text: str | None) -> tuple[float | None, str]:
    """Parse a Publi24 price like '1 000 RON' / '1.000 EUR'."""
    if not text:
        return None, "RON"
    currency = "EUR" if ("€" in text or "EUR" in text.upper()) else "RON"
    m = _DIGITS.search(text)
    if not m:
        return None, currency
    digits = re.sub(r"\D", "", m.group(0))  # drop thousands separators (space/.)
    if not digits:
        return None, currency
    try:
        return float(digits), currency
    except ValueError:
        return None, currency
