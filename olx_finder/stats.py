"""Grouping and robust outlier detection.

Samples are small and noisy, so we use the median and the Median Absolute
Deviation (MAD) rather than mean/stddev. A listing's *modified z-score* is

    mod_z = 0.6745 * (price - median) / MAD

and it is flagged as a deal when it is both a statistical low-side outlier and a
meaningful percentage below the group median (see config thresholds).

Single-city listings are sparse at the brand+model level, so grouping is
*mode-selectable* (see GROUPING_MODES). The same listings can be analysed under:

  * brand_guarded — brand-level groups, kids/small-wheel bikes excluded (default)
  * strict        — true brand+model groups, smaller min-sample requirement
  * brand_raw     — brand-level groups, no guards (maximum recall, more noise)
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median as _median

import config
from olx_finder.models import CheapestListing, DealResult, Group, Listing
from olx_finder.parsing import (
    extract_brand_model,
    is_kids_listing,
    is_part_listing,
    normalize,
)
from olx_finder.products import BIKES, Product

# Preferred order when the same item is reposted across sites: keep the first.
_SOURCE_PRIORITY = ["OLX", "Publi24", "Lajumate", "Anuntul", "biklo.ro"]

# Constant from the modified z-score definition (0.6745 ≈ 1 / Φ⁻¹(0.75)),
# which scales MAD to be consistent with the standard deviation for normal data.
_MOD_Z_CONST = 0.6745

_ALL_MODELS = "(all models)"
_UNKNOWN_MODEL = "(unknown model)"
# Label for the per-brand bucket of listings whose exact model could not be
# parsed (used by the "Cheapest by model" view, kept separate from real models).
_NO_MODEL = "(model not detected)"

# How a deal's "usual price" is established (selectable per search in the UI):
#   * brand       — value a listing against its whole brand pool (looser, more
#                   candidates, but a one-off model can look cheap vs the brand)
#   * brand_model — value a listing only against same brand+model comparables
#                   (default; a lone one-off model is never flagged)
MATCH_LEVELS: dict[str, str] = {
    "brand": "Brand only",
    "brand_model": "Brand + model",
}
DEFAULT_MATCH_LEVEL = "brand_model"


def get_match_level(value: str | None) -> str:
    """Resolve a match-level key, falling back to the default."""
    return value if value in MATCH_LEVELS else DEFAULT_MATCH_LEVEL


@dataclass(frozen=True, slots=True)
class GroupingMode:
    """A selectable strategy for grouping comparable listings."""

    key: str
    label: str
    description: str
    group_by: str          # "brand" or "brand_model"
    min_samples: int
    exclude_kids: bool
    require_model: bool     # if True, only flag deals in groups with a real model


GROUPING_MODES: dict[str, GroupingMode] = {
    "brand_guarded": GroupingMode(
        key="brand_guarded",
        label="Brand-only, kids/small-wheel excluded",
        description="Brand-level groups for sample size; drops kids and ≤20\" bikes "
        "from the comparison pool. Balanced recall and precision.",
        group_by="brand",
        min_samples=config.MIN_SAMPLES,
        exclude_kids=True,
        require_model=False,
    ),
    "strict": GroupingMode(
        key="strict",
        label="Strict brand + model",
        description="Only compares within true brand+model groups (e.g. 'Rockrider "
        "ST120'), with a smaller min-sample requirement. Purest, fewest deals.",
        group_by="brand_model",
        min_samples=config.STRICT_MIN_SAMPLES,
        exclude_kids=False,
        require_model=True,
    ),
    "brand_raw": GroupingMode(
        key="brand_raw",
        label="Brand-only, no filtering",
        description="Brand-level groups with no guards. Maximum deal volume, expect "
        "size-mismatch noise (kids bikes, mixed wheel sizes).",
        group_by="brand",
        min_samples=config.MIN_SAMPLES,
        exclude_kids=False,
        require_model=False,
    ),
}


def get_mode(mode_key: str | None) -> GroupingMode:
    """Resolve a mode key to a GroupingMode, falling back to the default."""
    return GROUPING_MODES.get(mode_key or config.DEFAULT_GROUPING_MODE,
                              GROUPING_MODES[config.DEFAULT_GROUPING_MODE])


def _mad(values: list[float], med: float) -> float:
    """Median absolute deviation about the median."""
    return _median([abs(v - med) for v in values])


def _compute_stats(group: Group) -> None:
    """Fill in median/MAD and the display range on a group from its prices."""
    prices = [lst.price for lst in group.listings]
    med = _median(prices)
    mad = _mad(prices, med)
    group.median = med
    group.mad = mad
    # Display "typical range": median ± MAD, clamped at the observed min.
    spread = mad if mad > 0 else 0.0
    group.low = max(min(prices), med - spread)
    group.high = med + spread


def dedupe_cross_source(listings: list[Listing]) -> list[Listing]:
    """Collapse the same item reposted on several sites into one listing.

    Two listings are treated as the same item when their normalized titles and
    (rounded) prices match. When that happens we keep the one from the
    highest-priority source (see ``_SOURCE_PRIORITY``) so a listing always links
    back to the most reliable site. Order is otherwise preserved.
    """
    def rank(lst: Listing) -> int:
        return _SOURCE_PRIORITY.index(lst.source) if lst.source in _SOURCE_PRIORITY else len(_SOURCE_PRIORITY)

    best: dict[tuple[str, int], int] = {}  # key -> index into result
    result: list[Listing] = []
    for lst in listings:
        key = (normalize(lst.title), round(lst.price))
        if not key[0]:
            result.append(lst)  # no title to compare on; never dedup blindly
            continue
        existing = best.get(key)
        if existing is None:
            best[key] = len(result)
            result.append(lst)
        elif rank(lst) < rank(result[existing]):
            result[existing] = lst  # prefer the higher-priority source
    return result


def annotate_listings(listings: list[Listing], product: Product = BIKES) -> list[Listing]:
    """Fill in brand/model on each listing (in place) and return the list."""
    for listing in listings:
        brand, model = extract_brand_model(listing.title, listing.brand_hint, product)
        listing.brand = brand
        listing.model = model
    return listings


def _passes_noise_filter(
    listing: Listing, mode: GroupingMode, product: Product
) -> bool:
    if listing.price <= 0 or listing.price < config.MIN_PLAUSIBLE_PRICE:
        return False
    if is_part_listing(listing.title, product):
        return False
    if mode.exclude_kids and is_kids_listing(listing.title, listing.wheel_inches, product):
        return False
    return True


def _group_key(listing: Listing, mode: GroupingMode) -> tuple[str, str, str] | None:
    """Return (key, brand, model_label) for a listing under the given mode."""
    if not listing.brand:
        return None
    if mode.group_by == "brand":
        return f"{listing.brand}", listing.brand, _ALL_MODELS
    model = listing.model or _UNKNOWN_MODEL
    return f"{listing.brand}|{model}", listing.brand, model


def build_groups(
    listings: list[Listing],
    mode: GroupingMode | str | None = None,
    product: Product = BIKES,
) -> list[Group]:
    """Filter noise, group by the mode's strategy, and compute robust statistics.

    Groups with at least ``mode.min_samples`` listings get median/MAD/range filled
    in; smaller groups are still returned (for the breakdown view) but left without
    statistics so they are never used to flag deals. ``product`` selects the brand
    list, parts/stopword vocabularies and comparison-pool guards to apply.
    """
    if not isinstance(mode, GroupingMode):
        mode = get_mode(mode)

    annotate_listings(listings, product)

    groups: dict[str, Group] = {}
    for listing in listings:
        if not _passes_noise_filter(listing, mode, product):
            continue
        keyed = _group_key(listing, mode)
        if keyed is None:
            continue
        key, brand, model_label = keyed
        group = groups.get(key)
        if group is None:
            group = Group(key=key, brand=brand, model=model_label)
            groups[key] = group
        group.listings.append(listing)

    for group in groups.values():
        if group.count >= mode.min_samples:
            _compute_stats(group)

    # Sort: largest, statistically usable groups first (most trustworthy).
    return sorted(
        groups.values(),
        key=lambda g: (g.median is not None, g.count),
        reverse=True,
    )


def build_model_groups(listings: list[Listing]) -> list[Group]:
    """Group listings by their exact brand+model and compute robust statistics.

    Only listings with a *known* model are included. A model group needs at least
    ``config.MIN_MODEL_COMPARABLES`` listings before its median/MAD are filled in;
    smaller groups are returned without statistics so they are never used to flag
    deals (a one-off model has no trustworthy second-hand market value).

    The input is expected to be already noise-filtered and brand/model-annotated
    (e.g. the listings collected from :func:`build_groups`' groups).
    """
    groups: dict[str, Group] = {}
    for listing in listings:
        if not listing.brand or not listing.model:
            continue
        key = f"{listing.brand}|{listing.model}"
        group = groups.get(key)
        if group is None:
            group = Group(key=key, brand=listing.brand, model=listing.model)
            groups[key] = group
        group.listings.append(listing)

    for group in groups.values():
        if group.count >= config.MIN_MODEL_COMPARABLES:
            _compute_stats(group)

    return sorted(
        groups.values(),
        key=lambda g: (g.median is not None, g.count),
        reverse=True,
    )


def cheapest_by_model(listings: list[Listing]) -> list[CheapestListing]:
    """One entry per brand+model: the single cheapest listing across all sources.

    Unlike :func:`flag_deals`, this is not statistical — it answers "where is the
    cheapest <brand model> right now, on any platform?". Every brand+model with at
    least one listing is represented (even a one-off), so nothing is hidden just
    because a model is rare. The cheapest pick links back to whichever marketplace
    actually hosts it (its ``source`` is already stamped on the listing).

    A model's median/range is filled in only when it has at least
    ``config.MIN_MODEL_COMPARABLES`` *same-model* listings, so the "% below" hint
    is shown only when there is a trustworthy market price to compare against.
    Listings whose exact model could not be parsed are pooled per brand under a
    clearly-labelled marker and never get a (meaningless, mixed) median.

    The input is expected to be already noise-filtered and brand/model-annotated
    (e.g. the listings collected from :func:`build_groups`' groups).
    """
    groups: dict[str, Group] = {}
    for listing in listings:
        if not listing.brand:
            continue
        model = listing.model or _NO_MODEL
        key = f"{listing.brand}|{model}"
        group = groups.get(key)
        if group is None:
            group = Group(key=key, brand=listing.brand, model=model)
            groups[key] = group
        group.listings.append(listing)

    picks: list[CheapestListing] = []
    for group in groups.values():
        # Only real models get a median; a per-brand unknown-model bucket mixes
        # different bikes, so an "average price" for it would be meaningless.
        if group.model != _NO_MODEL and group.count >= config.MIN_MODEL_COMPARABLES:
            _compute_stats(group)
        cheapest = min(group.listings, key=lambda lst: lst.price)
        picks.append(
            CheapestListing(
                brand=group.brand,
                model=group.model,
                listing=cheapest,
                count=group.count,
                median=group.median,
                low=group.low,
                high=group.high,
            )
        )

    # Surface the genuine bargains first: models whose cheapest sits well below a
    # trustworthy median float to the top, then the better-sampled models; lone
    # one-offs (no median) fall to the end but stay browseable via the filter.
    picks.sort(
        key=lambda p: (p.median is not None, p.percent_below or 0.0, p.count),
        reverse=True,
    )
    return picks


def _modified_z(price: float, median: float, mad: float) -> float:
    """Modified z-score, with a fallback when MAD == 0 (all prices identical)."""
    if mad == 0:
        # No spread: anything not equal to the median is treated as an extreme
        # outlier in the appropriate direction; equal prices score 0.
        if price < median:
            return float("-inf")
        if price > median:
            return float("inf")
        return 0.0
    return _MOD_Z_CONST * (price - median) / mad


def _deals_from_groups(groups: list[Group]) -> list[DealResult]:
    """Flag low-side outliers within each group that has usable statistics."""
    deals: list[DealResult] = []
    for group in groups:
        if group.median is None or group.mad is None:
            continue  # not enough samples to judge
        cheapest_price = min(lst.price for lst in group.listings)
        for listing in group.listings:
            mod_z = _modified_z(listing.price, group.median, group.mad)
            percent_below = (group.median - listing.price) / group.median
            if mod_z <= config.MOD_Z_THRESHOLD and percent_below >= config.MIN_PERCENT_BELOW:
                deals.append(
                    DealResult(
                        listing=listing,
                        group=group,
                        median=group.median,
                        low=group.low if group.low is not None else group.median,
                        high=group.high if group.high is not None else group.median,
                        sample_size=group.count,
                        mod_z=mod_z,
                        percent_below=percent_below,
                        is_cheapest_in_group=listing.price == cheapest_price,
                    )
                )

    deals.sort(key=lambda d: d.percent_below, reverse=True)
    return deals


def flag_deals(
    groups: list[Group],
    mode: GroupingMode | str | None = None,
    match_level: str = DEFAULT_MATCH_LEVEL,
) -> list[DealResult]:
    """Return deals across all groups, sorted by biggest discount first.

    ``match_level`` chooses how a listing's "usual price" is established:

    * ``"brand_model"`` (default) — listings are regrouped by their exact
      brand+model and a listing is only flagged when its model has at least
      ``config.MIN_MODEL_COMPARABLES`` listings (a real second-hand market) and
      it is a low-side outlier *within that model group*. A lone cheap listing of
      a one-off model is never flagged.
    * ``"brand"`` — listings are valued against the ``groups`` produced by the
      grouping ``mode`` (brand-level pools in the brand modes). Looser: surfaces
      more candidates, but a one-off model can look cheap against its brand.
    """
    if not isinstance(mode, GroupingMode):
        mode = get_mode(mode)

    if get_match_level(match_level) == "brand":
        # Value against the mode's groups as-is. In strict mode those are already
        # brand+model groups; honour its unknown-model guard.
        usable = [
            g for g in groups
            if not (mode.require_model and g.model.startswith("("))
        ]
        return _deals_from_groups(usable)

    # brand_model: regroup strictly by brand+model so deals are valued against
    # true comparables (and one-off models are never flagged).
    listings = [lst for group in groups for lst in group.listings]
    return _deals_from_groups(build_model_groups(listings))
