"""Defect tab — surfacing the listings that admit a fault.

The Deals and Cheapest views reason about *comparable* items: they need a
recognised brand (and, for deals, enough same-model comparables) before they can
say anything. This module is the opposite lens — it ignores brand and model
entirely and pools every listing whose own text owns up to a problem ("defect",
"nu merge", "ruginit", …). For a flipper those are the cheap fix-up candidates
the seller has already discounted in their own head.

A listing qualifies on a single fault signal found in its title OR description
(the body is where the honest caveat usually hides). Listings are still
noise-filtered (sub-floor prices and standalone parts dropped) so the tab stays
whole-items only, then ranked cheapest first.
"""

from __future__ import annotations

import config
from olx_finder.models import Defect, Listing
from olx_finder.parsing import _alias_in_title, normalize
from olx_finder.products import BIKES, Product
from olx_finder.stats import annotate_listings, _passes_noise_filter, get_mode


def _build_signals() -> list[str]:
    """Normalized fault signals (tokens + phrases), longest first.

    Longest-first so a card naming both a phrase and a word it contains reports
    the most specific match; the membership test itself is order-independent.
    """
    signals = {normalize(s) for s in (config.DEFECT_TOKENS | config.DEFECT_PHRASES)}
    return sorted((s for s in signals if s), key=len, reverse=True)


# The signal vocabulary is built from stable module-level config constants, so
# compute it once at import time.
_SIGNALS = _build_signals()


def find_defect_signals(title: str, description: str | None = None) -> list[str]:
    """Fault wording found in a listing's title/description, or [].

    Scans both fields (like :func:`olx_finder.parsing.find_premium_components`):
    the title is terse, but the description is where a seller buries "merge dar
    are o problema la frana". Each signal is reported at most once, longest match
    first.
    """
    text = normalize(f"{title} {description or ''}")
    if not text:
        return []
    return [sig for sig in _SIGNALS if _alias_in_title(text, sig)]


def find_defects(
    listings: list[Listing],
    product: Product = BIKES,
    *,
    limit: int = config.DEFECT_MAX_RESULTS,
) -> list[Defect]:
    """Listings that admit a fault, brand/model-agnostic, cheapest first.

    ``listings`` is the FULL deduped pool (as for :func:`find_sleepers`), so the
    unbranded items the deal engine never groups are considered too. Listings are
    noise-filtered with the unguarded ``brand_raw`` mode — this keeps the parts
    filter (a bag of parts isn't a flip) and the price floor, but allows
    brand-less and kids items — then any listing carrying a fault signal in its
    title or description is kept, ordered cheapest first (the best fix-up buys).
    """
    annotate_listings(listings, product)  # idempotent; safe if already annotated
    mode = get_mode("brand_raw")

    defects: list[Defect] = []
    for listing in listings:
        if not _passes_noise_filter(listing, mode, product):
            continue
        signals = find_defect_signals(listing.title, listing.description)
        if signals:
            defects.append(Defect(listing=listing, signals=signals))

    defects.sort(key=lambda d: d.listing.price)
    return defects[:limit]
