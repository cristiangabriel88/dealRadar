"""Facebook Marketplace source (browser-driven).

Marketplace is login-gated and rendered client-side with JavaScript, so — unlike
every other source, which fetches over ``httpx`` — it needs a real, logged-in
browser. We drive a headless Chromium (Playwright) with a dedicated, persistent
profile: log in once via ``python -m olx_finder.fb_login`` and the saved session
is reused on every search. Marketplace is keyword-based, so we search by
``product.query``.

Unlike the other national sources, Facebook is **always searched in Bucharest**:
Marketplace pins results to the account's saved location (ours defaults to Paris)
and that location can't be set via query params, so we force it through the
``/marketplace/np/<location_id>/search`` path and honour the UI's km selector via
the ``radius`` query param. If the saved profile location ever isn't Bucharest,
``_fetch_all`` sets it once (via the location picker) and retries. FB still
returns the occasional out-of-area card, so results are client-filtered to the
selected city scope (``city_in_scope``) like the other national sources; when a
city far from Bucharest is selected, the browser launch is skipped entirely.

The browser only appears in ``_fetch_all``; everything else is pure so the DOM
parsing can be tested offline (see ``tests/test_facebook.py``). Marketplace's
markup is obfuscated and shifts over time, so we key off the one stable thing —
the ``/marketplace/item/<id>/`` listing link (which may carry an extra path
segment, e.g. ``/marketplace/np/item/<id>/``) — and read the card's visible text
by position rather than by (randomized) class names.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

import config
from olx_finder import cache
from olx_finder.models import Listing
from olx_finder.products import Product
from olx_finder.sources.base import MarketplaceSource, city_in_scope, within_reach

# A persistent profile dir can only be opened by one Chromium process at a time,
# and aggregate() (used by both "/" and "/listing/<id>") can run searches that
# overlap. This lock serializes all browser access to the FB profile.
_FB_LOCK = threading.Lock()

# Listing-card link. The id always sits under ``/marketplace/.../item/<id>``; the
# optional middle segment (e.g. ``np/``) appears when results are scoped to a
# location, so we allow one between ``marketplace`` and ``item``.
_ITEM_HREF = re.compile(r"/marketplace/(?:[a-z]+/)?item/(\d+)")
# Broad CSS prefilter for card links; each match is validated by _ITEM_HREF.
_ITEM_LINK_CSS = 'a[href*="/item/"]'
# A card text counts as the price line if it carries a currency token (or marks
# the item free). Romanian Marketplace shows prices like "1.234 lei", "1234 RON"
# or "€500"; logged out (US default) they read "20 USD". "Gratuit"/"Free" items
# have no usable number and are dropped later.
_PRICE_TOKEN = re.compile(r"(lei|ron|eur|usd|€|\$|gratuit|free)", re.IGNORECASE)
_DIGITS = re.compile(r"\d[\d.\s,]*")


class FacebookSource(MarketplaceSource):
    """Fetch Marketplace listings via a logged-in headless browser session."""

    name = "Facebook Marketplace"

    def __init__(self, use_cache: bool = True) -> None:
        self.use_cache = use_cache

    def supported_cities(self) -> list[str]:
        return sorted(config.MAIN_CITIES)

    def search(self, product: Product, city: str, distance: int = 0) -> list[Listing]:
        query = product.query
        # Facebook always searches Bucharest with the selected radius, so the
        # fetched set depends on (query, radius) only — not the chosen city. We
        # cache by radius so each radius is stored separately and the chosen city
        # doesn't fragment the cache; the city filter is applied after, on read.
        radius = self._radius(distance)
        # FB only ever searches Bucharest. When another city is selected, FB's
        # Bucharest-area results are relevant only if Bucharest can fall within
        # the chosen scope — i.e. the two radii overlap (centres within
        # distance + radius). Otherwise skip the expensive browser launch.
        if city != config.ALL_CITIES and not within_reach(
            city, config.FB_SEARCH_CITY, distance + radius
        ):
            return []

        cache_city = f"BUC:{radius}"
        if self.use_cache:
            cached = cache.get(self.name, query, cache_city)
            if cached is not None:
                return self._build(cached, city, distance)

        raw = self._fetch_all(query, radius)

        if self.use_cache:
            cache.put(self.name, query, cache_city, raw)

        return self._build(raw, city, distance)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _radius(distance: int) -> int:
        """Map the UI's km selector to a Facebook search radius (km).

        "This city only" (0) has no FB equivalent, so it becomes a modest radius
        covering Bucharest; any explicit distance is passed through.
        """
        return distance if distance and distance > 0 else config.FB_DEFAULT_RADIUS_KM

    def _build(
        self, raw: list[dict[str, Any]], city: str, distance: int = 0
    ) -> list[Listing]:
        # FB pins the search to Bucharest but still returns the odd out-of-area
        # card, so client-filter to the selected city scope — exactly like the
        # other national sources. ``city_in_scope`` keeps everything for an
        # ALL_CITIES (national) search.
        out = []
        for item in raw:
            lst = self._to_listing(item)
            if lst is not None and city_in_scope(city, distance, lst.city):
                out.append(lst)
        return out

    def _fetch_all(self, query: str, radius: int) -> list[dict[str, Any]]:
        """Open Marketplace in a headless browser (in Bucharest), scroll, parse.

        Serialized by ``_FB_LOCK``. Raises a clear error if the saved session is
        no longer logged in, or if the Marketplace location can't be set to
        Bucharest — which ``aggregate`` turns into a per-source message without
        sinking the other sources.
        """
        from playwright.sync_api import sync_playwright

        url = self._search_url(query, radius)
        with _FB_LOCK, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                config.FB_PROFILE_DIR,
                headless=True,
                user_agent=config.USER_AGENT,
                locale="ro-RO",
                viewport={"width": 1280, "height": 1800},
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded")
                self._require_logged_in(page)
                # The location lives in the profile, not the URL. Usually the
                # saved profile is already on Bucharest and the /np/<id>/ path
                # just works; if not, set it once via the picker and reload.
                if not self._on_bucharest(page):
                    self._set_location_bucharest(page)
                    page.goto(url, wait_until="domcontentloaded")
                    self._require_logged_in(page)
                    if not self._on_bucharest(page):
                        raise RuntimeError(
                            "could not set Marketplace location to Bucharest"
                        )
                self._scroll_for_cards(page)
                html = page.content()
            finally:
                context.close()
        return self._parse_page(html)

    @staticmethod
    def _search_url(query: str, radius: int) -> str:
        # The /np/<id>/ ("neighbourhood page") prefix is what makes the path-based
        # location actually take; a bare /marketplace/<id>/ is ignored.
        base = config.FB_MARKETPLACE_BASE
        loc = config.FB_LOCATION_ID
        return f"{base}/np/{loc}/search/?query={quote(query)}&radius={radius}"

    @staticmethod
    def _require_logged_in(page: Any) -> None:
        if "login" in page.url or page.query_selector('input[name="email"]'):
            raise RuntimeError(
                "Facebook session expired — run python -m olx_finder.fb_login"
            )

    @staticmethod
    def _on_bucharest(page: Any) -> bool:
        """Whether Marketplace's location filter is currently set to Bucharest.

        The left-hand "Filters" label reads e.g. "Pantelimon, Bucuresti, Romania
        · Within 60 kilometres" (or "Paris · Within 60 kilometres" when not set).
        """
        try:
            page.wait_for_timeout(1500)
            label = page.get_by_text(re.compile(r"kilomet", re.I))
            if label.count() == 0:
                return False
            return "bucur" in label.first.inner_text().lower()
        except Exception:
            return False

    @classmethod
    def _set_location_bucharest(cls, page: Any) -> None:
        """Set the Marketplace location to Bucharest via the location picker.

        Run only when the saved profile isn't already on Bucharest; the choice
        persists in the profile, so later searches skip this. Best-effort: any
        failure here surfaces as the "could not set location" error upstream.
        """
        # Open the location dialog from the "Within N kilometres" filter link.
        page.get_by_text(re.compile(r"Within .* kilomet", re.I)).first.click(force=True)
        inp = cls._poll(lambda: cls._dialog_text_input(page))
        if inp is None:
            return
        inp.click(force=True)
        inp.fill("Bucuresti")
        page.wait_for_timeout(2500)
        opt = cls._poll(lambda: (page.query_selector_all('[role="option"]') or [None])[0])
        if opt is None:
            return
        opt.click(force=True)
        page.wait_for_timeout(1500)
        # Click the dialog's "Apply" button.
        dlg = page.query_selector('[role="dialog"]')
        if dlg is not None:
            for b in dlg.query_selector_all('[role="button"]'):
                if (b.inner_text() or "").strip().lower().startswith("appl"):
                    b.click(force=True)
                    break
        page.wait_for_timeout(4000)

    @staticmethod
    def _dialog_text_input(page: Any) -> Any:
        """The free-text ('Postal code or city') input inside the location dialog."""
        dlg = page.query_selector('[role="dialog"]')
        if dlg is None:
            return None
        for inp in dlg.query_selector_all("input"):
            if (inp.get_attribute("type") or "text") != "checkbox":
                return inp
        return None

    @staticmethod
    def _poll(fn: Any, tries: int = 30, pause: float = 0.5) -> Any:
        """Poll ``fn`` until it returns something truthy, or give up."""
        for _ in range(tries):
            value = fn()
            if value:
                return value
            time.sleep(pause)
        return None

    @staticmethod
    def _scroll_for_cards(page: Any) -> None:
        """Scroll up to FB_MAX_SCROLLS times, stopping when no new cards load."""
        try:
            page.wait_for_selector(
                _ITEM_LINK_CSS, timeout=int(config.REQUEST_TIMEOUT * 1000)
            )
        except Exception:
            return  # no results at all (e.g. an empty query)
        prev = 0
        for _ in range(config.FB_MAX_SCROLLS):
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(config.FB_SCROLL_PAUSE_MS)
            count = len(page.query_selector_all(_ITEM_LINK_CSS))
            if count <= prev:
                break  # nothing new loaded; stop early
            prev = count

    @staticmethod
    def _parse_page(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.select(_ITEM_LINK_CSS):
            m = _ITEM_HREF.search(a.get("href") or "")
            if m is None:
                continue
            item_id = m.group(1)
            if item_id in seen:
                continue  # the same card can appear more than once after scrolling
            seen.add(item_id)

            texts = [t for t in a.stripped_strings]
            price, title, city = _card_fields(texts)
            img = a.select_one("img")
            src = img.get("src") if img else None
            if src and src.startswith("data:"):
                src = None  # lazy-load placeholder, not a real image yet
            items.append(
                {
                    "id": item_id,
                    "title": title,
                    "url": f"https://www.facebook.com/marketplace/item/{item_id}/",
                    "price": price,
                    "city": city,
                    "thumbnail": src,
                }
            )
        return items

    def _to_listing(self, raw: dict[str, Any]) -> Listing | None:
        price, currency = _parse_price(raw.get("price"))
        if price is None:
            return None  # free / unpriced cards carry no comparable value
        return Listing(
            id=f"fb:{raw.get('id')}",
            title=(raw.get("title") or "").strip(),
            price=price,
            currency=currency,
            url=raw.get("url") or "",
            city=raw.get("city") or "",
            posted_at=None,  # Marketplace cards show no reliable post date
            thumbnail=raw.get("thumbnail"),
            raw_title=raw.get("title") or "",
        )


def _card_fields(texts: list[str]) -> tuple[str | None, str, str]:
    """Split a card's visible text lines into (price, title, location).

    Marketplace renders each card as price, then title, then location, e.g.
    ``["20 USD", "Bicicleta", "Oakland, CA"]``. When an item is discounted the
    current price comes first and the struck-through original second
    (``["1.500 lei", "2.000 lei", ...]``), so we take the *first* price line. The
    location is the last non-price line and the title is what's left in between.
    """
    price = next((t for t in texts if _PRICE_TOKEN.search(t)), None)
    rest = [t for t in texts if not _PRICE_TOKEN.search(t)]
    if not rest:
        return price, "", ""
    city = rest[-1]
    title = " ".join(rest[:-1]) if len(rest) > 1 else rest[0]
    return price, title, city


def _parse_price(text: str | None) -> tuple[float | None, str]:
    """Parse a Marketplace price like '1.234 lei' / '€500'. Free => None."""
    if not text:
        return None, "RON"
    low = text.lower()
    if "€" in text or "eur" in low:
        currency = "EUR"
    elif "$" in text or "usd" in low:
        currency = "USD"  # only seen logged out (US default location)
    else:
        currency = "RON"
    if "gratuit" in low or "free" in low:
        return None, currency  # free items have no comparable price
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
