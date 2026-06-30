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
from olx_finder.parsing import normalize
from olx_finder.products import BIKES, Product
from olx_finder.stats import annotate_listings, _passes_noise_filter, get_mode


def _build_signals() -> list[tuple[str, list[str]]]:
    """Normalized fault signals as (phrase, words), longest first.

    Longest-first so a card naming both a phrase and a word it contains reports
    the most specific match; the membership test itself is order-independent.
    Pre-split into words so the per-listing scan compares word spans directly.
    """
    signals = {normalize(s) for s in (config.DEFECT_TOKENS | config.DEFECT_PHRASES)}
    return [(s, s.split()) for s in sorted(signals, key=len, reverse=True) if s]


# The signal vocabulary is built from stable module-level config constants, so
# compute it once at import time.
_SIGNALS = _build_signals()


def _is_negated(words: list[str], start: int) -> bool:
    """True if the fault span starting at word index ``start`` is denied.

    Looks at the few words immediately before the fault word (Romanian puts the
    negator first): if that trailing window ends with a ``config.NEGATION_CUES``
    phrase — "fara probleme", "nu are defecte", "niciun defect" — the seller is
    saying the part is *fine*, so the word must not flag the listing. Requiring
    the cue to END the window keeps real faults like "nu doar defect" (not only
    defective) intact.
    """
    window = words[max(0, start - config.NEGATION_LOOKBACK):start]
    for size in range(1, len(window) + 1):
        if " ".join(window[-size:]) in config.NEGATION_CUES:
            return True
    return False


def _has_unnegated_match(words: list[str], sig_words: list[str]) -> bool:
    """True if ``sig_words`` occurs as a whole-word span that isn't negated.

    A fault word may appear twice ("are probleme la frana, in rest fara
    probleme") — one admission is enough, so a single un-denied occurrence
    qualifies while an all-denied word ("fara probleme") is dropped.
    """
    n = len(sig_words)
    for i in range(len(words) - n + 1):
        if words[i:i + n] == sig_words and not _is_negated(words, i):
            return True
    return False


def find_defect_signals(title: str, description: str | None = None) -> list[str]:
    """Fault wording found in a listing's title/description, or [].

    Scans both fields (like :func:`olx_finder.parsing.find_premium_components`):
    the title is terse, but the description is where a seller buries "merge dar
    are o problema la frana". Each signal is reported at most once, longest match
    first. Romanian negation is honoured: a fault word the seller explicitly
    denies ("fara probleme", "nu are defecte") does NOT count (see
    :func:`_is_negated`).
    """
    text = normalize(f"{title} {description or ''}")
    if not text:
        return []
    words = text.split()
    return [sig for sig, sig_words in _SIGNALS if _has_unnegated_match(words, sig_words)]


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
