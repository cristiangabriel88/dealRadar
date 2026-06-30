"""Marketplace sources. Implement MarketplaceSource to add a new site."""

from olx_finder.sources.base import MarketplaceSource, matches_city
from olx_finder.sources.olx import OlxSource
from olx_finder.sources.publi24 import Publi24Source
from olx_finder.sources.lajumate import LajumateSource
from olx_finder.sources.anuntul import AnuntulSource
from olx_finder.sources.biklo import BikloSource
from olx_finder.sources.facebook import FacebookSource

__all__ = [
    "MarketplaceSource",
    "matches_city",
    "OlxSource",
    "Publi24Source",
    "LajumateSource",
    "AnuntulSource",
    "BikloSource",
    "FacebookSource",
]
