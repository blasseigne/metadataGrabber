"""Orchestrator — routes accessions to fetchers and collects results."""

import logging
import re
from typing import Dict, List, Optional

import requests

from metadata_grabber.fetchers import FETCHER_CLASSES
from metadata_grabber.fetchers.base import BaseFetcher
from metadata_grabber.models import MetadataRecord
from metadata_grabber.pubmed import PubMedResolver
from metadata_grabber.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class MetadataGrabber:
    def __init__(self, ncbi_api_key: Optional[str] = None):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "metadataGrabber/0.1.0"})

        ncbi_rate = 10.0 if ncbi_api_key else 3.0
        self._ncbi_limiter = RateLimiter(ncbi_rate)
        self._ebi_limiter = RateLimiter(20.0)
        self._pubmed = PubMedResolver(self._session, self._ncbi_limiter, ncbi_api_key)

        # Build prefix -> fetcher routing map
        self._prefix_map: Dict[str, BaseFetcher] = {}
        for cls in FETCHER_CLASSES:
            fetcher = self._instantiate_fetcher(cls, ncbi_api_key)
            for prefix in fetcher.prefixes():
                self._prefix_map[prefix.upper()] = fetcher

    def _instantiate_fetcher(
        self, cls: type, ncbi_api_key: Optional[str]
    ) -> BaseFetcher:
        from metadata_grabber.fetchers.geo import GEOFetcher
        from metadata_grabber.fetchers.ena import ENAFetcher

        if cls is GEOFetcher:
            return GEOFetcher(
                self._session, self._ncbi_limiter, self._pubmed, ncbi_api_key
            )
        elif cls is ENAFetcher:
            return ENAFetcher(self._session, self._ebi_limiter, self._pubmed)
        else:
            # Generic fallback: try common constructor signatures
            return cls(self._session, self._ebi_limiter, self._pubmed)

    def fetch_one(self, accession: str) -> MetadataRecord:
        """Fetch metadata for a single accession."""
        accession = accession.strip()
        prefix = self._detect_prefix(accession)
        if prefix is None or prefix not in self._prefix_map:
            return MetadataRecord(
                accession=accession,
                fetch_status="error",
                error_message=f"Unsupported accession prefix: {prefix or accession}",
            )
        fetcher = self._prefix_map[prefix]
        logger.info("Fetching %s via %s", accession, type(fetcher).__name__)
        return fetcher.fetch(accession)

    def fetch_all(self, accessions: List[str]) -> List[MetadataRecord]:
        """Fetch metadata for a list of accessions, in order."""
        return [self.fetch_one(acc) for acc in accessions]

    @staticmethod
    def _detect_prefix(accession: str) -> Optional[str]:
        match = re.match(r"^([A-Za-z]+)", accession.strip())
        return match.group(1).upper() if match else None
