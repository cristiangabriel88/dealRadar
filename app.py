"""Flask UI for OLX Deal Finder.

Run locally with:  python app.py   -> http://127.0.0.1:5000
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request

import config
from olx_finder.models import Listing, _fmt
from olx_finder.parsing import normalize
from olx_finder.products import PRODUCTS, Product, get_product
from olx_finder.products import DEFAULT_PRODUCT
from olx_finder.defects import find_defects
from olx_finder.sleepers import find_sleepers
from olx_finder.sources import (
    AnuntulSource,
    BikloSource,
    FacebookSource,
    LajumateSource,
    OlxSource,
    Publi24Source,
)
from olx_finder.stats import (
    GROUPING_MODES,
    build_groups,
    build_model_groups,
    cheapest_by_brand,
    cheapest_by_model,
    dedupe_cross_source,
    flag_deals,
    get_mode,
    to_ron,
)

app = Flask(
    __name__,
    template_folder="olx_finder/templates",
    static_folder="olx_finder/static",
)


@app.context_processor
def _inject_config() -> dict:
    """Expose the config module to templates (for displaying thresholds)."""
    return {"config": config}


# Selectable marketplaces. Order here is the order shown in the UI and the
# tie-break order used when deduping the same item across sites.
SOURCES = {
    "OLX": OlxSource,
    "Publi24": Publi24Source,
    "Lajumate": LajumateSource,
    "Anuntul": AnuntulSource,
    "Facebook Marketplace": FacebookSource,
}
DEFAULT_SOURCES = ["OLX"]

# Sources shown in the UI but not yet implemented (rendered as disabled boxes).
DISABLED_SOURCES: dict[str, str] = {}

# Product-specific marketplaces, keyed by source name. A source listed here is
# only shown (and only fetched) for the products whose ``extra_sources`` name it:
# biklo.ro is a bike-only marketplace, so its checkbox appears only when "Bikes"
# is selected. The general SOURCES above apply to every product.
PRODUCT_SOURCE_CLASSES = {"biklo.ro": BikloSource}

# Flat name -> class registry spanning general + product-specific sources, used
# to resolve whatever the user selected when fetching.
ALL_SOURCES = {**SOURCES, **PRODUCT_SOURCE_CLASSES}

# UI mapping product -> its extra source names (only products that have any).
PRODUCT_SOURCES = {
    p.key: list(p.extra_sources) for p in PRODUCTS.values() if p.extra_sources
}


def aggregate(
    selected_sources: list[str], product: Product, city: str, distance: int = 0
) -> tuple[list[Listing], list[str]]:
    """Fetch every selected source, pool + dedup their listings.

    Sources are fetched concurrently (each paginates with its own polite delay).
    A source that fails contributes an error message rather than aborting the
    whole search, so deals from the sites that succeeded are still shown. Each
    listing is stamped with its source name before pooling. ``distance`` is the
    search radius in km around ``city`` (0 = that city only).
    """
    names = [s for s in selected_sources if s in ALL_SOURCES] or DEFAULT_SOURCES

    def fetch(name: str) -> tuple[str, list[Listing] | None, str | None]:
        try:
            listings = ALL_SOURCES[name]().search(product, city, distance)
            for lst in listings:
                lst.source = name
            return name, listings, None
        except Exception as exc:  # one bad source must not sink the rest
            return name, None, f"{name}: {exc}"

    pooled: list[Listing] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        for name, listings, error in pool.map(fetch, names):
            if error is not None:
                errors.append(error)
            else:
                pooled.extend(listings)

    # Hard title exclusion: drop listings whose title contains an excluded whole
    # word (e.g. "copii") before any view sees them.
    if config.EXCLUDE_TITLE_WORDS:
        pooled = [lst for lst in pooled if not _is_excluded(lst.title)]

    # Normalize every price to RON before dedup/stats so the whole pipeline and
    # the UI work in a single currency (and EUR/RON reposts of one item dedup).
    return dedupe_cross_source(to_ron(pooled)), errors


def _is_excluded(title: str) -> bool:
    """True when a listing title contains one of EXCLUDE_TITLE_WORDS as a word."""
    tokens = set(normalize(title).split())
    return bool(tokens & config.EXCLUDE_TITLE_WORDS)


@app.template_filter("lei")
def _lei(value: float) -> str:
    """Jinja filter to format a price like '2 000'."""
    return _fmt(value)


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    cities = sorted(config.MAIN_CITIES)
    modes = list(GROUPING_MODES.values())

    # Form state (defaults on first load; Bucharest is preselected).
    default_city = config.DEFAULT_CITY if config.DEFAULT_CITY in config.MAIN_CITIES else cities[0]
    selected_city = request.form.get("city", default_city)
    # Search radius (km) around the selected city; validated against the allowed
    # options so a hand-edited value can't slip through.
    try:
        selected_distance = int(request.form.get("distance", config.DEFAULT_DISTANCE))
    except (TypeError, ValueError):
        selected_distance = config.DEFAULT_DISTANCE
    if selected_distance not in config.DISTANCE_OPTIONS:
        selected_distance = config.DEFAULT_DISTANCE
    # Source is a multi-select checkbox group. First load starts with a clean
    # slate (nothing checked, no search run); the user picks sources or "Select
    # all". On POST an empty selection still falls back to DEFAULT_SOURCES.
    if request.method == "POST":
        selected_sources = request.form.getlist("source") or DEFAULT_SOURCES
    else:
        selected_sources = []
    selected_product = request.form.get("product", DEFAULT_PRODUCT)
    selected_mode = request.form.get("mode", config.DEFAULT_GROUPING_MODE)
    # Checkbox: checked => match by brand+model. On POST its absence means the
    # user unchecked it (= brand only); on first load it defaults unchecked
    # (brand only, no model filtering — the loosest, maximum-recall view).
    if request.method == "POST":
        match_model = request.form.get("match_model") is not None
    else:
        match_model = False
    match_level = "brand_model" if match_model else "brand"

    context: dict = {
        "cities": cities,
        "all_cities": config.ALL_CITIES,
        "distances": config.DISTANCE_OPTIONS,
        "selected_distance": selected_distance,
        "modes": modes,
        "sources": list(SOURCES),
        "disabled_sources": DISABLED_SOURCES,
        "product_sources": PRODUCT_SOURCES,
        "product_types": list(PRODUCTS),
        "selected_city": selected_city,
        "selected_sources": selected_sources,
        "selected_product": selected_product,
        "selected_mode": selected_mode,
        "match_model": match_model,
        "searched": False,
        "deals": [],
        "groups": [],
        "model_groups": [],
        "cheapest": [],
        "cheapest_brand": [],
        "sleepers": [],
        "defects": [],
        "listing_count": 0,
        "error": None,
        "source_errors": [],
        "mode_obj": get_mode(selected_mode),
    }

    if request.method == "POST":
        context["searched"] = True
        product = get_product(selected_product)
        mode = get_mode(selected_mode)
        try:
            listings, source_errors = aggregate(
                selected_sources, product, selected_city, selected_distance
            )
            groups = build_groups(listings, mode, product)
            deals = flag_deals(groups, mode, match_level)
            # Listings that survived noise filtering, pooled across every source.
            pooled = [lst for g in groups for lst in g.listings]
            # Same-model comparables that actually back the deals (mode-independent).
            model_groups = build_model_groups(pooled)
            # Cross-platform "cheapest exemplar per brand+model" view.
            cheapest = cheapest_by_model(pooled)
            # Cross-platform "cheapest listings per brand" view (any model).
            cheapest_brand = cheapest_by_brand(pooled)
            # Sleepers: scored over the FULL deduped listings (NOT `pooled`,
            # which excludes the unbranded listings that are the whole point).
            sleepers = find_sleepers(listings, product)
            # Defects: every listing that admits a fault, over the FULL deduped
            # set (like sleepers), brand/model-agnostic.
            defects = find_defects(listings, product)
            context.update(
                listing_count=len(listings),
                groups=groups,
                model_groups=model_groups,
                cheapest=cheapest,
                cheapest_brand=cheapest_brand,
                sleepers=sleepers,
                defects=defects,
                deals=deals,
                # Partial failures: show deals from the sources that worked.
                source_errors=source_errors,
            )
        except Exception as exc:  # surface unexpected pipeline errors in the UI
            context["error"] = str(exc)

    return render_template("index.html", **context)


@app.route("/listing/<listing_id>")
def listing_detail(listing_id: str) -> str:
    """Show a single listing on top, with the comparables that backed its deal below.

    The app keeps no server-side result state, so this re-runs the exact same
    pipeline as the search (served from the SQLite cache within its TTL) using the
    search parameters carried in the query string, then locates the matching deal.
    """
    city = request.args.get("city", "")
    try:
        distance = int(request.args.get("distance", config.DEFAULT_DISTANCE))
    except (TypeError, ValueError):
        distance = config.DEFAULT_DISTANCE
    selected_sources = request.args.getlist("source") or DEFAULT_SOURCES
    product = get_product(request.args.get("product", DEFAULT_PRODUCT))
    mode_key = request.args.get("mode", config.DEFAULT_GROUPING_MODE)
    match_model = request.args.get("match_model") == "1"
    match_level = "brand_model" if match_model else "brand"
    mode = get_mode(mode_key)

    deal = None
    error = None
    try:
        # Re-run the same multi-source pipeline so the deal's comparison group is
        # reproduced from the identical pool (the app keeps no server-side state).
        listings, _ = aggregate(selected_sources, product, city, distance)
        groups = build_groups(listings, mode, product)
        deals = flag_deals(groups, mode, match_level)
        deal = next((d for d in deals if d.listing.id == listing_id), None)
    except Exception as exc:  # surface fetch/parsing errors in the UI
        error = str(exc)

    # Comparables = the group behind the deal, cheapest first, the selected one excluded.
    comparables = []
    if deal is not None:
        comparables = sorted(
            (lst for lst in deal.group.listings if lst.id != deal.listing.id),
            key=lambda lst: lst.price,
        )

    return render_template(
        "listing.html",
        deal=deal,
        comparables=comparables,
        error=error,
        city=city,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
