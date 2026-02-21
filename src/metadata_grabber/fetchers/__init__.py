"""Fetcher registry — add new fetcher classes here."""

from metadata_grabber.fetchers.geo import GEOFetcher
from metadata_grabber.fetchers.ena import ENAFetcher

FETCHER_CLASSES = [
    GEOFetcher,
    ENAFetcher,
]
