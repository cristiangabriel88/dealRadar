"""Product types and everything that varies between them.

Deal Radar runs the *same mechanic* (pool listings across marketplaces, group
comparable ones, flag statistical low-side outliers) over different kinds of
second-hand goods. Everything that differs between, say, bikes and guitars —
the search query, each marketplace's category endpoint, the brand list, the
parts/stopword vocabularies and the comparison-pool guards — is bundled here in
a :class:`Product`. The parsing, stats and source layers take a ``Product`` and
read what they need from it, so adding a new product is a data change, not a
rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config


@dataclass(frozen=True, slots=True)
class Product:
    """A kind of item to hunt deals for, with all its product-specific knobs."""

    key: str                       # display label + form value, e.g. "Bikes"

    # Search scope. ``query`` is the keyword used by the keyword-based sources
    # (OLX, Anuntul). The category endpoints scope the category-page sources;
    # a ``None`` here means "this source can't be scoped for this product" and
    # the source yields nothing rather than fetching the wrong category.
    query: str
    olx_category_id: int | None    # OLX offers-API category (None => query only)
    publi24_url: str | None        # Publi24 category page
    lajumate_url: str | None       # Lajumate category page

    # Brand/model parsing vocabularies.
    brands: dict[str, list[str]]
    part_noise_tokens: frozenset[str]
    model_stopwords: frozenset[str]

    # Parts handling. ``part_noise_tokens`` (above) are "strong" — always a part.
    # ``part_component_tokens`` (component words whole-item listings also use, e.g.
    # "frane") and ``part_accessory_tokens`` (bonus add-ons a whole item throws in,
    # e.g. "pompa cadou") are ambiguous: they only mark a part when no
    # ``whole_item_tokens`` word and no known brand is present. Leave them empty to
    # keep the strict "any strong token => a part" behaviour.
    part_component_tokens: frozenset[str] = frozenset()
    part_accessory_tokens: frozenset[str] = frozenset()
    whole_item_tokens: frozenset[str] = frozenset()

    # Premium component vocabulary (canonical label -> aliases) the Sleepers
    # scorer rewards. Empty => no component signal for this product.
    premium_components: dict[str, list[str]] = field(default_factory=dict)

    # Condition vocabularies (drive the fix-up buffer in the margin/ROI math).
    # Generic Romanian wording, so every product shares the config defaults; a
    # product can override if its listings phrase condition differently.
    condition_like_new_tokens: frozenset[str] = config.CONDITION_LIKE_NEW_TOKENS
    condition_needs_work_tokens: frozenset[str] = config.CONDITION_NEEDS_WORK_TOKENS
    condition_refurbished_tokens: frozenset[str] = config.CONDITION_REFURBISHED_TOKENS

    # Comparison-pool guards (used by the "guarded" grouping mode). Kids/junior
    # items are dropped from the adult pool; ``small_wheel_max_inches`` is the
    # bike-only wheel-size guard (None => no size guard for this product).
    kids_title_tokens: frozenset[str] = frozenset()
    small_wheel_max_inches: float | None = None

    # Names of marketplaces that only make sense for this product (e.g. the
    # bike-only biklo.ro). Shown in the UI only when this product is selected.
    extra_sources: tuple[str, ...] = field(default=())


BIKES = Product(
    key="Bikes",
    query=config.DEFAULT_QUERY,
    olx_category_id=config.OLX_BICYCLES_CATEGORY_ID,
    publi24_url=config.PUBLI24_BICYCLES_URL,
    lajumate_url=config.LAJUMATE_BICYCLES_URL,
    brands=config.BRANDS,
    part_noise_tokens=config.PART_NOISE_TOKENS,
    model_stopwords=config.BIKE_MODEL_STOPWORDS,
    part_component_tokens=config.PART_COMPONENT_TOKENS,
    part_accessory_tokens=config.PART_ACCESSORY_TOKENS,
    whole_item_tokens=config.WHOLE_ITEM_TOKENS,
    premium_components=config.PREMIUM_BIKE_COMPONENTS,
    kids_title_tokens=config.KIDS_TITLE_TOKENS,
    small_wheel_max_inches=config.SMALL_WHEEL_MAX_INCHES,
    extra_sources=("biklo.ro",),
)

GUITARS = Product(
    key="Guitars",
    query=config.GUITAR_QUERY,
    olx_category_id=config.OLX_GUITARS_CATEGORY_ID,
    publi24_url=config.PUBLI24_GUITARS_URL,
    lajumate_url=config.LAJUMATE_GUITARS_URL,
    brands=config.GUITAR_BRANDS,
    part_noise_tokens=config.GUITAR_PART_NOISE_TOKENS,
    model_stopwords=config.GUITAR_MODEL_STOPWORDS,
    part_component_tokens=config.GUITAR_PART_COMPONENT_TOKENS,
    part_accessory_tokens=config.GUITAR_PART_ACCESSORY_TOKENS,
    whole_item_tokens=config.GUITAR_WHOLE_ITEM_TOKENS,
    premium_components=config.GUITAR_PREMIUM_COMPONENTS,
    kids_title_tokens=config.GUITAR_KIDS_TITLE_TOKENS,
    small_wheel_max_inches=None,  # guitars have no wheel-size guard
    extra_sources=(),
)

# Registry, in UI display order.
PRODUCTS: dict[str, Product] = {p.key: p for p in (BIKES, GUITARS)}
DEFAULT_PRODUCT: str = BIKES.key


def get_product(key: str | None) -> Product:
    """Resolve a product key to a :class:`Product`, falling back to the default."""
    return PRODUCTS.get(key or DEFAULT_PRODUCT, PRODUCTS[DEFAULT_PRODUCT])
