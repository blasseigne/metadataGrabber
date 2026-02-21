"""Abstract base class for accession fetchers."""

from abc import ABC, abstractmethod
from typing import List

from metadata_grabber.models import MetadataRecord


class BaseFetcher(ABC):
    @abstractmethod
    def prefixes(self) -> List[str]:
        """Return accession prefixes this fetcher handles (e.g., ['GSE'])."""
        ...

    @abstractmethod
    def fetch(self, accession: str) -> MetadataRecord:
        """Fetch metadata for a single accession. Must not raise."""
        ...
