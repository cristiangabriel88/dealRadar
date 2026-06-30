"""Core data structures shared across the source, parsing and stats layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import config


@dataclass(slots=True)
class Listing:
    """A single marketplace listing, normalized across sources."""

    id: str
    title: str
    price: float
    currency: str
    url: str
    city: str
    posted_at: datetime | None
    thumbnail: str | None
    raw_title: str
    # Brand pre-tagged by the marketplace (e.g. OLX `brand` param), if any.
    brand_hint: str | None = None
    # Wheel size in inches from the OLX `dimensiune_roata` param (if present).
    wheel_inches: float | None = None

    # Filled in by the parsing layer.
    brand: str | None = None
    model: str | None = None
    # Best-effort condition read from the title/description ("like_new",
    # "refurbished", "needs_work", or None when no condition wording is found).
    # Sizes the fix-up buffer in the deal margin/ROI math.
    condition: str | None = None

    # Free-text body of the listing and how many photos it carries. Only the
    # richer sources expose these (OLX, biklo); the HTML/Facebook sources leave
    # them None, and the Sleepers scorer treats a None as "unknown" (no signal).
    description: str | None = None
    photo_count: int | None = None

    # Which marketplace this listing came from (e.g. "OLX", "Publi24"). Stamped
    # by the aggregation layer; used for the source badge and the "Open on …" link.
    source: str = ""


@dataclass(slots=True)
class Group:
    """A set of comparable listings (same brand+model) plus their statistics."""

    key: str
    brand: str
    model: str
    listings: list[Listing] = field(default_factory=list)

    # Computed statistics (None until there are enough samples).
    median: float | None = None
    mad: float | None = None       # median absolute deviation
    low: float | None = None       # typical-range lower bound (display)
    high: float | None = None      # typical-range upper bound (display)

    @property
    def count(self) -> int:
        return len(self.listings)


@dataclass(slots=True)
class DealResult:
    """A flagged underpriced listing together with the numbers behind it."""

    listing: Listing
    group: Group
    median: float
    low: float
    high: float
    sample_size: int
    mod_z: float
    percent_below: float           # 0.40 == 40% below median
    is_cheapest_in_group: bool

    @property
    def estimated_margin(self) -> float:
        """Rough resale spread in lei: the typical price minus the asking price.

        A flipper's gross headline number — buy at ``listing.price``, resell around
        the comparable median. It's *before* the fix-up buffer (see
        :attr:`net_margin`); negative only if the listing isn't actually a bargain.
        """
        return self.median - self.listing.price

    @property
    def effective_touchup(self) -> float:
        """Fix-up cost (lei) to subtract, sized by the listing's read condition.

        ``like_new`` needs almost nothing, ``needs_work`` needs real work; an
        unknown condition falls back to the default buffer.
        """
        condition = self.listing.condition
        if condition == "like_new":
            return config.TOUCHUP_BUFFER_LIKE_NEW_LEI
        if condition == "needs_work":
            return config.TOUCHUP_BUFFER_NEEDS_WORK_LEI
        # "refurbished" and unknown both use the default.
        return config.TOUCHUP_BUFFER_LEI

    @property
    def net_margin(self) -> float:
        """Resale spread after the condition-aware fix-up buffer (lei)."""
        return self.estimated_margin - self.effective_touchup

    @property
    def roi(self) -> float:
        """Return on the cash put in: net margin / (asking + fix-up).

        The flipper's real ranking metric — a small cheap flip can beat a big
        one in percentage terms. Guarded against a zero cost basis.
        """
        cost = self.listing.price + self.effective_touchup
        if cost <= 0:
            return 0.0
        return self.net_margin / cost

    @property
    def explanation(self) -> str:
        """Plain-language, numbers-only reason this is a good deal."""
        price = _fmt(self.listing.price)
        median = _fmt(self.median)
        low = _fmt(self.low)
        high = _fmt(self.high)
        pct = round(self.percent_below * 100)
        cheapest = (
            " — the cheapest of the group"
            if self.is_cheapest_in_group
            else ""
        )
        # For brand-only / unknown-model groups the model is a "(...)" marker;
        # drop it so the sentence reads naturally.
        descriptor = self.group.brand
        if self.group.model and not self.group.model.startswith("("):
            descriptor = f"{self.group.brand} {self.group.model}"
        condition_note = ""
        if self.listing.condition:
            label = self.listing.condition.replace("_", " ")
            condition_note = (
                f" Reads as {label}, so after a ~{_fmt(self.effective_touchup)} "
                f"{self.listing.currency} fix-up the net spread is ~"
                f"{_fmt(self.net_margin)} {self.listing.currency} "
                f"({round(self.roi * 100)}% ROI)."
            )
        return (
            f"Listed at {price} {self.listing.currency}. Based on {self.sample_size} "
            f"comparable {descriptor} listings in "
            f"{self.listing.city}, the typical price is ~{median} {self.listing.currency} "
            f"(range {low}–{high}). This one is {pct}% below the median{cheapest}."
            f"{condition_note}"
        )


@dataclass(slots=True)
class Sleeper:
    """A listing that looks like a "seller doesn't know what they have" find.

    Powers the Sleepers view: unlike :class:`DealResult` (which values a listing
    against same brand+model comparables and so can only judge *correctly labelled*
    items), a sleeper is scored by neglect/mislabel signals — no recognised brand,
    a terse title, a minimal description, one photo, motivated-seller wording, and
    a price well under the whole category's typical level. The signals each fire
    independently, so a listing with no brand and no description at all can still
    surface — which is exactly the opportunity the deal engine drops.
    """

    listing: Listing
    score: float
    reasons: list[str]             # human-readable, e.g. "only 1 photo"
    category_median: float | None  # typical price for the whole product pool
    components: list[str] = field(default_factory=list)  # premium parts found, if any

    @property
    def has_brand(self) -> bool:
        """Whether a known brand was recognised in the title/hint at all."""
        return self.listing.brand is not None

    @property
    def percent_below_category(self) -> float | None:
        """How far under the category's typical price this sits (None if n/a)."""
        if self.category_median is None or self.category_median <= 0:
            return None
        if self.listing.price >= self.category_median:
            return None
        return (self.category_median - self.listing.price) / self.category_median


@dataclass(slots=True)
class CheapestListing:
    """The single lowest-priced current listing for one brand+model.

    Powers the "Cheapest by model" view: for each brand+model that appears in the
    pooled results (across *every* selected marketplace), this is the cheapest
    exemplar out there, together with how many comparable listings back it and —
    when there are enough of them — the model's typical price for context.
    """

    brand: str
    model: str               # display label; "(model not detected)" when unknown
    listing: Listing         # the cheapest listing of this brand+model
    count: int               # how many listings of this brand+model were pooled
    median: float | None     # None until there are enough comparables to trust
    low: float | None
    high: float | None

    @property
    def has_model(self) -> bool:
        """Whether a real model (not the unknown-model marker) was identified."""
        return bool(self.model) and not self.model.startswith("(")

    @property
    def descriptor(self) -> str:
        """Human label for the group, e.g. 'GT Avalanche' or just 'GT'."""
        return f"{self.brand} {self.model}" if self.has_model else self.brand

    @property
    def percent_below(self) -> float | None:
        """How far the cheapest sits below the model median (None if no median)."""
        if self.median is None or self.median <= 0:
            return None
        return (self.median - self.listing.price) / self.median


@dataclass(slots=True)
class BrandCheapest:
    """The cheapest current listings for one brand, across all sources.

    Powers the "Cheapest by brand" view: for each major brand present in the
    pooled results, the lowest-priced listings regardless of model — a place to
    spot underpriced gems the model-level views split across tiny groups. No
    median is computed: a whole-brand pool mixes models, so an "average price"
    would be meaningless (the same reason :class:`CheapestListing` withholds a
    median from its mixed unknown-model bucket).
    """

    brand: str
    count: int                 # total listings of this brand in the pool
    listings: list[Listing]    # cheapest first, truncated to the requested limit


def _fmt(value: float) -> str:
    """Format a price like '2 000' (no decimals, space thousands separator)."""
    return f"{round(value):,}".replace(",", " ")
