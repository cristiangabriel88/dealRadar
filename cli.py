"""CLI verification harness for the OLX integration and the model parser.

Run a live search and print: a sample of parsed Listings, the grouped breakdown
(brand+model, count, median, range) and the flagged deals with explanations.

    python cli.py --city "Bucuresti"
    python cli.py --city "Cluj-Napoca" --no-cache --sample 15
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import config
from olx_finder.products import PRODUCTS, get_product
from olx_finder.sources import OlxSource
from olx_finder.stats import (
    DEFAULT_MATCH_LEVEL,
    GROUPING_MODES,
    MATCH_LEVELS,
    build_groups,
    build_model_groups,
    flag_deals,
    get_mode,
    to_ron,
)

# Make stdout UTF-8 on Windows consoles (diacritics in titles/cities).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="OLX Deal Finder — CLI verification")
    parser.add_argument("--city", default="Bucuresti", help="City to search (see config.CITIES)")
    parser.add_argument(
        "--product",
        default="Bikes",
        choices=list(PRODUCTS),
        help="Product type to hunt (default: %(default)s)",
    )
    parser.add_argument("--query", default=None, help="Override the product's search query")
    parser.add_argument("--sample", type=int, default=10, help="How many parsed listings to print")
    parser.add_argument("--no-cache", action="store_true", help="Bypass the SQLite cache")
    parser.add_argument(
        "--mode",
        default=config.DEFAULT_GROUPING_MODE,
        choices=list(GROUPING_MODES),
        help="Grouping strategy (default: %(default)s)",
    )
    parser.add_argument(
        "--match",
        default=DEFAULT_MATCH_LEVEL,
        choices=list(MATCH_LEVELS),
        help="Value deals against the whole brand (brand) or only same brand+model "
        "comparables (brand_model). Default: %(default)s",
    )
    args = parser.parse_args()

    mode = get_mode(args.mode)
    product = get_product(args.product)
    if args.query:
        product = replace(product, query=args.query)
    source = OlxSource(use_cache=not args.no_cache)
    print(f"Fetching '{product.query}' ({product.key}) in {args.city} from {source.name} ...")
    listings = to_ron(source.search(product, args.city))
    print(
        f"Fetched {len(listings)} listings.  Mode: {mode.key} — {mode.label}  "
        f"Match: {args.match} — {MATCH_LEVELS[args.match]}\n"
    )

    groups = build_groups(listings, mode, product)
    deals = flag_deals(groups, mode, args.match)

    _print_sample(listings, args.sample)
    _print_groups(groups)
    if args.match == "brand_model":
        # Same-model comparables actually used to value deals in this mode.
        model_groups = build_model_groups([lst for g in groups for lst in g.listings])
        _print_model_groups(model_groups)
    _print_deals(deals)


def _print_sample(listings: list, n: int) -> None:
    print("=" * 78)
    print(f"SAMPLE OF PARSED LISTINGS (first {n})")
    print("=" * 78)
    for lst in listings[:n]:
        brand = lst.brand or "-"
        model = lst.model or "-"
        posted = lst.posted_at.date().isoformat() if lst.posted_at else "?"
        print(f"  {int(lst.price):>6} {lst.currency}  [{brand} / {model}]  {posted}")
        print(f"         {lst.title[:70]}")
    print()


def _print_groups(groups: list) -> None:
    print("=" * 78)
    print("GROUPED BREAKDOWN (current grouping mode — context only)")
    print("=" * 78)
    print(f"  {'group':<34} {'count':>5} {'median':>9} {'range':>17}")
    print("  " + "-" * 70)
    for g in groups:
        if g.median is not None:
            rng = f"{int(g.low)}-{int(g.high)}"
            print(f"  {g.key[:34]:<34} {g.count:>5} {int(g.median):>9} {rng:>17}  *")
        else:
            print(f"  {g.key[:34]:<34} {g.count:>5} {'-':>9} {'(below MIN_SAMPLES)':>17}")
    print("\n  (context for the chosen mode; deals are flagged from the "
          "model breakdown below)\n")


def _print_model_groups(groups: list) -> None:
    print("=" * 78)
    print("MODEL BREAKDOWN (brand + model — deals are flagged from these)")
    print("=" * 78)
    print(f"  {'brand+model':<34} {'count':>5} {'median':>9} {'range':>17}")
    print("  " + "-" * 70)
    for g in groups:
        if g.median is not None:
            rng = f"{int(g.low)}-{int(g.high)}"
            print(f"  {g.key[:34]:<34} {g.count:>5} {int(g.median):>9} {rng:>17}  *")
        else:
            print(f"  {g.key[:34]:<34} {g.count:>5} {'-':>9} {'(too few comparables)':>17}")
    print(f"\n  ('*' rows have {config.MIN_MODEL_COMPARABLES}+ same-model "
          "comparables; only those can back a deal)\n")


def _print_deals(deals: list) -> None:
    print("=" * 78)
    print(f"FLAGGED DEALS ({len(deals)}) — biggest discount first")
    print("=" * 78)
    if not deals:
        print("  No deals flagged with the current thresholds "
              f"(mod_z <= {config.MOD_Z_THRESHOLD}, >= {int(config.MIN_PERCENT_BELOW*100)}% below).")
        return
    for d in deals:
        print(f"\n  [{round(d.percent_below*100)}% below] {d.listing.title[:64]}")
        print(f"      {d.explanation}")
        print(f"      mod_z={d.mod_z:.2f}  {d.listing.url}")
    print()


if __name__ == "__main__":
    main()
