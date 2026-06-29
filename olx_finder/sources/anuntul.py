"""Anuntul.ro source.

Anuntul has no bike-only category, so we keyword-search for "bicicleta"
(``?search[query]=...&page=N``). The results are mixed-category and noisy, but
the downstream brand/parts filtering keeps only real bikes (anything without a
known bike brand is dropped during grouping). Listings are clean Bootstrap
cards (``div.card.impression``); we city-filter client-side like the others.
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


class AnuntulSource(MarketplaceSource):
    """Fetch bicycle listings from Anuntul.ro's keyword search."""

    name = "Anuntul"

    def __init__(self, use_cache: bool = True) -> None:
        self.use_cache = use_cache

    def supported_cities(self) -> list[str]:
        return sorted(config.CITIES)

    def search(self, product: Product, city: str, distance: int = 0) -> list[Listing]:
        if city != config.ALL_CITIES and city not in config.CITIES:
            raise ValueError(
                f"Unknown city {city!r}. Known cities: {', '.join(sorted(config.CITIES))}"
            )

        query = product.query
        # National keyword feed; city/radius scope is applied in _build, so we
        # cache by city alone (raw is radius-independent) and re-filter on read.
        if self.use_cache:
            cached = cache.get(self.name, query, city)
            if cached is not None:
                return self._build(cached, city, distance)

        raw = self._fetch_all(query)

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

    def _fetch_all(self, query: str) -> list[dict[str, Any]]:
        """Page through the keyword search, politely, up to MAX_PAGES."""
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        with _http.make_client() as client:
            for page in range(config.MAX_PAGES):
                params: dict[str, Any] = {"search[query]": query}
                if page:
                    params["page"] = page + 1
                html = _http.get_html(client, config.ANUNTUL_SEARCH_URL, params)
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
                    break
                time.sleep(config.REQUEST_DELAY)
        return results

    @staticmethod
    def _parse_page(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        items: list[dict[str, Any]] = []
        for card in soup.select("div.card.impression"):
            a = card.select_one(".card-title a[href]")
            if a is None:
                continue
            href = (a.get("href") or "").split("#")[0].strip()
            card_id = (card.get("id") or "").replace("aid-", "") or card.get("data-hash")
            loc = card.select_one("span.float-end")
            img = card.select_one("img")
            src = (img.get("data-src") or img.get("src")) if img else None
            if src and ("no-photo" in src or "/build/" in src):
                src = None
            elif src and src.startswith("//"):
                src = "https:" + src
            items.append(
                {
                    "id": card_id,
                    "title": a.get_text(" ", strip=True),
                    "url": href,
                    "price": _text(card.select_one(".card-text.fw-bold")),
                    "city": _text(loc),
                    "thumbnail": src,
                }
            )
        return items

    def _to_listing(self, raw: dict[str, Any]) -> Listing | None:
        price, currency = _parse_price(raw.get("price"))
        if price is None:
            return None
        url = raw.get("url") or ""
        if url.startswith("/"):
            url = config.ANUNTUL_BASE + url
        # Location text looks like "Bucuresti, azi; 13:21" — keep the city part.
        city = (raw.get("city") or "").split(",")[0].strip()
        return Listing(
            id=f"anuntul:{raw.get('id')}",
            title=(raw.get("title") or "").strip(),
            price=price,
            currency=currency,
            url=url,
            city=city,
            posted_at=None,
            thumbnail=raw.get("thumbnail"),
            raw_title=raw.get("title") or "",
        )


def _text(node: Any) -> str | None:
    return node.get_text(" ", strip=True) if node is not None else None


def _parse_price(text: str | None) -> tuple[float | None, str]:
    """Parse an Anuntul price like '1.000 RON' / '108.779 €' (dot = thousands)."""
    if not text:
        return None, "RON"
    currency = "EUR" if ("€" in text or "EUR" in text.upper()) else "RON"
    m = _DIGITS.search(text)
    if not m:
        return None, currency
    digits = re.sub(r"\D", "", m.group(0))
    if not digits:
        return None, currency
    try:
        return float(digits), currency
    except ValueError:
        return None, currency
