"""Flask UI for OLX Deal Finder.

Run locally with:  python app.py   -> http://127.0.0.1:5000
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request

import config
from olx_finder.models import Listing, _fmt
from olx_finder.sources import (
    AnuntulSource,
    LajumateSource,
    OlxSource,
    Publi24Source,
)
from olx_finder.stats import (
    DEFAULT_MATCH_LEVEL,
    GROUPING_MODES,
    build_groups,
    build_model_groups,
    dedupe_cross_source,
    flag_deals,
    get_mode,
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
}
DEFAULT_SOURCES = ["OLX"]

# Sources shown in the UI but not yet implemented (rendered as disabled boxes).
# Facebook Marketplace needs a logged-in browser session (Playwright); deferred.
DISABLED_SOURCES = {"Facebook Marketplace": "coming soon"}

# Product types are fixed to bikes for now; the query is derived from this.
PRODUCT_TYPES = {"Bikes": config.DEFAULT_QUERY}


def aggregate(
    selected_sources: list[str], query: str, city: str
) -> tuple[list[Listing], list[str]]:
    """Fetch every selected source, pool + dedup their listings.

    Sources are fetched concurrently (each paginates with its own polite delay).
    A source that fails contributes an error message rather than aborting the
    whole search, so deals from the sites that succeeded are still shown. Each
    listing is stamped with its source name before pooling.
    """
    names = [s for s in selected_sources if s in SOURCES] or DEFAULT_SOURCES

    def fetch(name: str) -> tuple[str, list[Listing] | None, str | None]:
        try:
            listings = SOURCES[name]().search(query, city)
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

    return dedupe_cross_source(pooled), errors


@app.template_filter("lei")
def _lei(value: float) -> str:
    """Jinja filter to format a price like '2 000'."""
    return _fmt(value)


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    cities = sorted(config.CITIES)
    modes = list(GROUPING_MODES.values())

    # Form state (defaults on first load; Bucharest is preselected).
    default_city = config.DEFAULT_CITY if config.DEFAULT_CITY in config.CITIES else cities[0]
    selected_city = request.form.get("city", default_city)
    # Source is now a multi-select checkbox group; default to OLX on first load.
    if request.method == "POST":
        selected_sources = request.form.getlist("source") or DEFAULT_SOURCES
    else:
        selected_sources = list(DEFAULT_SOURCES)
    selected_product = request.form.get("product", "Bikes")
    selected_mode = request.form.get("mode", config.DEFAULT_GROUPING_MODE)
    # Checkbox: checked => match by brand+model (default). On POST its absence
    # means the user unchecked it (= brand only); on first load it defaults checked.
    if request.method == "POST":
        match_model = request.form.get("match_model") is not None
    else:
        match_model = DEFAULT_MATCH_LEVEL == "brand_model"
    match_level = "brand_model" if match_model else "brand"

    context: dict = {
        "cities": cities,
        "modes": modes,
        "sources": list(SOURCES),
        "disabled_sources": DISABLED_SOURCES,
        "product_types": list(PRODUCT_TYPES),
        "selected_city": selected_city,
        "selected_sources": selected_sources,
        "selected_product": selected_product,
        "selected_mode": selected_mode,
        "match_model": match_model,
        "searched": False,
        "deals": [],
        "groups": [],
        "model_groups": [],
        "listing_count": 0,
        "error": None,
        "source_errors": [],
        "mode_obj": get_mode(selected_mode),
    }

    if request.method == "POST":
        context["searched"] = True
        query = PRODUCT_TYPES.get(selected_product, config.DEFAULT_QUERY)
        mode = get_mode(selected_mode)
        try:
            listings, source_errors = aggregate(selected_sources, query, selected_city)
            groups = build_groups(listings, mode)
            deals = flag_deals(groups, mode, match_level)
            # Same-model comparables that actually back the deals (mode-independent).
            model_groups = build_model_groups(
                [lst for g in groups for lst in g.listings]
            )
            context.update(
                listing_count=len(listings),
                groups=groups,
                model_groups=model_groups,
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
    selected_sources = request.args.getlist("source") or DEFAULT_SOURCES
    product = request.args.get("product", "Bikes")
    mode_key = request.args.get("mode", config.DEFAULT_GROUPING_MODE)
    match_model = request.args.get("match_model") == "1"
    match_level = "brand_model" if match_model else "brand"
    query = PRODUCT_TYPES.get(product, config.DEFAULT_QUERY)
    mode = get_mode(mode_key)

    deal = None
    error = None
    try:
        # Re-run the same multi-source pipeline so the deal's comparison group is
        # reproduced from the identical pool (the app keeps no server-side state).
        listings, _ = aggregate(selected_sources, query, city)
        groups = build_groups(listings, mode)
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
