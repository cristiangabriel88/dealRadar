"""Sleepers — surfacing the listings the deal engine throws away.

:mod:`olx_finder.stats` finds deals by valuing a listing against same brand+model
comparables. That structurally requires a *recognised brand* (no brand -> the
listing is never grouped -> never judged) and *enough comparables* (a one-off
model is never flagged). The most profitable flips are the opposite case: a
neglected, mislabelled listing from a seller who doesn't know what they have.

This module scores every (noise-filtered) listing — brand or not, comparables or
not — by neglect/mislabel signals and ranks the strongest. Each signal adds its
weight ONLY when its data is available, so a missing description or photo count
never penalises a listing; it simply can't fire that one signal. This keeps the
view useful for the HTML/Facebook sources (which expose neither) while letting
the richer OLX/biklo data lift the listings that have it.
"""

from __future__ import annotations

from statistics import median as _median

import config
from olx_finder.models import Listing, Sleeper
from olx_finder.parsing import find_premium_components, normalize
from olx_finder.products import BIKES, Product
from olx_finder.stats import annotate_listings, _passes_noise_filter, get_mode


def _category_median(pool: list[Listing]) -> float | None:
    """Median price of the whole (noise-filtered) product pool, or None.

    This is brand-independent: a single "typical price for this kind of item"
    that anchors the cheap-vs-category signal even for listings with no brand
    and no comparables of their own.
    """
    prices = [lst.price for lst in pool]
    return _median(prices) if prices else None


def _photo_phrase(count: int) -> str:
    if count <= 0:
        return "no photos"
    return "only 1 photo" if count == 1 else f"only {count} photos"


def _score(
    listing: Listing, category_median: float | None, product: Product
) -> tuple[float, list[str], list[str]]:
    """Sleeper score, the human-readable reasons, and any premium parts found.

    Pure sum of independently-fired signals. Every branch that reads optional
    data (``description``, ``photo_count``, the category median) is guarded, so a
    ``None`` contributes nothing rather than raising or penalising.
    """
    tokens = set(normalize(listing.title).split())

    # Scrap / for-parts listings are never a flip — drop them outright.
    if tokens & config.SLEEPER_JUNK_TOKENS:
        return 0.0, [], []

    score = 0.0
    reasons: list[str] = []

    if listing.brand is None:
        score += config.SLEEPER_WEIGHT_NO_BRAND
        reasons.append("no brand named")

    word_count = len(tokens)
    if word_count and word_count <= config.SLEEPER_SHORT_TITLE_MAX_WORDS:
        score += config.SLEEPER_WEIGHT_SHORT_TITLE
        reasons.append(f"terse title ({word_count} words)")

    # Only a *known* description can fire this; None means "not available".
    if listing.description is not None and len(listing.description) <= config.SLEEPER_MIN_DESC_CHARS:
        score += config.SLEEPER_WEIGHT_MIN_DESC
        reasons.append("minimal description")

    if listing.photo_count is not None and listing.photo_count <= config.SLEEPER_FEW_PHOTOS_MAX:
        score += config.SLEEPER_WEIGHT_FEW_PHOTOS
        reasons.append(_photo_phrase(listing.photo_count))

    if category_median and listing.price < category_median:
        pct = (category_median - listing.price) / category_median
        if pct >= config.SLEEPER_MIN_CATEGORY_BELOW:
            cap = config.SLEEPER_CATEGORY_BELOW_CAP
            graded = config.SLEEPER_WEIGHT_CHEAP_CATEGORY * min(pct, cap) / cap
            score += graded
            reasons.append(f"{round(pct * 100)}% below the typical price")

    motivated = tokens & config.MOTIVATED_SELLER_TOKENS
    if motivated:
        score += config.SLEEPER_WEIGHT_MOTIVATED
        reasons.append(f"motivated seller ({', '.join(sorted(motivated))})")

    # A cheap listing that names premium parts is the strongest "doesn't know
    # what they have" tell — scan the description too, where it's often buried.
    components = find_premium_components(listing.title, listing.description, product)
    if components:
        score += config.SLEEPER_WEIGHT_PREMIUM_COMPONENT
        reasons.append("premium parts: " + ", ".join(components[:3]))

    return score, reasons, components


def find_sleepers(
    listings: list[Listing],
    product: Product = BIKES,
    *,
    min_score: float = config.SLEEPER_MIN_SCORE,
    limit: int = config.SLEEPER_MAX_RESULTS,
) -> list[Sleeper]:
    """Rank the listings most likely to be a "seller doesn't know what they have".

    ``listings`` must be the FULL pooled set (e.g. the deduped output of
    ``aggregate()``), NOT the brand-grouped ``pooled`` list — the unbranded
    listings that are the whole point never enter a group. Listings are
    noise-filtered with the unguarded ``brand_raw`` mode (keeps the parts filter,
    but allows kids/small bikes and, crucially, brand-less items), scored, and
    returned strongest first (cheapest first within a score tie).
    """
    annotate_listings(listings, product)  # idempotent; safe if already annotated
    mode = get_mode("brand_raw")
    pool = [lst for lst in listings if _passes_noise_filter(lst, mode, product)]

    category_median = _category_median(pool)

    sleepers: list[Sleeper] = []
    for listing in pool:
        score, reasons, components = _score(listing, category_median, product)
        if score >= min_score:
            sleepers.append(
                Sleeper(
                    listing=listing,
                    score=score,
                    reasons=reasons,
                    category_median=category_median,
                    components=components,
                )
            )

    sleepers.sort(key=lambda s: (-s.score, s.listing.price))
    return sleepers[:limit]
