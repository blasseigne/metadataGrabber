"""Resolve PubMed IDs to formatted citation strings."""

import logging
from typing import List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from metadata_grabber.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
MAX_IDS_PER_REQUEST = 200


class PubMedResolver:
    def __init__(
        self,
        session: requests.Session,
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
    ):
        self._session = session
        self._limiter = rate_limiter
        self._api_key = api_key

    def resolve(self, pmids: List[str]) -> List[str]:
        """Take a list of PMIDs and return formatted citation strings."""
        if not pmids:
            return []

        unique = list(dict.fromkeys(pmids))  # deduplicate, preserve order
        citations = []

        for i in range(0, len(unique), MAX_IDS_PER_REQUEST):
            batch = unique[i : i + MAX_IDS_PER_REQUEST]
            try:
                data = self._fetch_esummary(batch)
                result = data.get("result", {})
                for pmid in batch:
                    doc = result.get(pmid)
                    if doc and "error" not in doc:
                        citations.append(self._format_citation(doc))
                    else:
                        citations.append(f"PMID:{pmid}")
            except Exception:
                logger.warning("Failed to resolve PMIDs: %s", batch, exc_info=True)
                citations.extend(f"PMID:{p}" for p in batch)

        return citations

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _fetch_esummary(self, pmids: List[str]) -> dict:
        self._limiter.acquire()
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
            "version": "2.0",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        resp = self._session.get(ESUMMARY_URL, params=params, timeout=30)
        if resp.status_code == 429:
            raise requests.ConnectionError("Rate limited (429)")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _format_citation(doc: dict) -> str:
        authors = doc.get("authors", [])
        if authors:
            first = authors[0].get("name", "Unknown")
            author_str = f"{first} et al." if len(authors) > 1 else first
        else:
            author_str = "Unknown"

        year = doc.get("pubdate", "")[:4]
        title = doc.get("title", "").rstrip(".")
        journal = doc.get("source", "")

        article_ids = doc.get("articleids", [])
        dois = [a["value"] for a in article_ids if a.get("idtype") == "doi"]
        doi_str = f"DOI:{dois[0]}" if dois else ""

        pmid_list = [a["value"] for a in article_ids if a.get("idtype") == "pubmed"]
        pmid_str = f"PMID:{pmid_list[0]}" if pmid_list else ""

        parts = [f"{author_str} ({year})", title, journal]
        if doi_str:
            parts.append(doi_str)
        elif pmid_str:
            parts.append(pmid_str)

        return ". ".join(p for p in parts if p)
