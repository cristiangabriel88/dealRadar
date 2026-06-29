"""Core data structures shared across the source, parsing and stats layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
        return (
            f"Listed at {price} {self.listing.currency}. Based on {self.sample_size} "
            f"comparable {descriptor} listings in "
            f"{self.listing.city}, the typical price is ~{median} {self.listing.currency} "
            f"(range {low}–{high}). This one is {pct}% below the median{cheapest}."
        )


def _fmt(value: float) -> str:
    """Format a price like '2 000' (no decimals, space thousands separator)."""
    return f"{round(value):,}".replace(",", " ")
