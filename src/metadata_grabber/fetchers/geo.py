"""Fetch metadata for GSE accessions from NCBI GEO via E-utilities."""

import logging
from typing import List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from metadata_grabber.fetchers.base import BaseFetcher
from metadata_grabber.models import MetadataRecord
from metadata_grabber.pubmed import PubMedResolver
from metadata_grabber.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
GEO_UID_OFFSET = 200_000_000


class GEOFetcher(BaseFetcher):
    def __init__(
        self,
        session: requests.Session,
        rate_limiter: RateLimiter,
        pubmed_resolver: PubMedResolver,
        api_key: Optional[str] = None,
    ):
        self._session = session
        self._limiter = rate_limiter
        self._pubmed = pubmed_resolver
        self._api_key = api_key

    def prefixes(self) -> List[str]:
        return ["GSE"]

    def fetch(self, accession: str) -> MetadataRecord:
        record = MetadataRecord(accession=accession)
        try:
            uid = self._accession_to_uid(accession)
        except ValueError as exc:
            record.fetch_status = "error"
            record.error_message = str(exc)
            return record

        # 1. Fetch eSummary
        doc = self._fetch_esummary(uid)
        if doc is None:
            record.fetch_status = "error"
            record.error_message = "eSummary returned no data"
            return record

        # 2. Map fields
        record.species = doc.get("taxon", "")
        record.data_type = doc.get("gdstype", "")

        gpl = doc.get("gpl", "")
        record.platform = f"GPL{gpl}" if gpl else ""

        pdat = doc.get("pdat", "")
        record.date_deposited = pdat.replace("/", "-") if pdat else ""

        title = doc.get("title", "")
        summary = doc.get("summary", "")
        n_samples = doc.get("n_samples", "")
        details = title
        if summary:
            details += f". {summary}"
        if n_samples:
            details += f" (n={n_samples} samples)"
        record.experimental_details = details

        # 3. Collect database references
        db_refs = []
        bioproject = doc.get("bioproject", "")
        if bioproject:
            db_refs.append(f"BioProject:{bioproject}")

        ext_relations = doc.get("extrelations", [])
        for rel in ext_relations:
            rel_type = rel.get("relationtype", "")
            target = rel.get("targetobject", "")
            if rel_type and target:
                db_refs.append(f"{rel_type}:{target}")

        if gpl:
            db_refs.append(f"GEO_Platform:GPL{gpl}")
        record.database_references = "; ".join(db_refs)

        # 4. Resolve publications
        pmids = [str(p) for p in doc.get("pubmedids", []) if p]
        elink_pmids = self._fetch_elink_pubmed(uid)
        all_pmids = list(dict.fromkeys(pmids + elink_pmids))

        if all_pmids:
            citations = self._pubmed.resolve(all_pmids)
            record.published_works = "; ".join(citations)

        return record

    @staticmethod
    def _accession_to_uid(accession: str) -> int:
        prefix = ""
        num_str = ""
        for ch in accession:
            if ch.isalpha():
                prefix += ch
            else:
                num_str += ch
        if prefix.upper() != "GSE" or not num_str:
            raise ValueError(f"Invalid GSE accession: {accession}")
        return GEO_UID_OFFSET + int(num_str)

    def _http_get(self, url: str, params: dict) -> Optional[requests.Response]:
        try:
            return self._http_get_with_retry(url, params)
        except Exception:
            logger.warning("HTTP GET failed: %s", url, exc_info=True)
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _http_get_with_retry(self, url: str, params: dict) -> requests.Response:
        self._limiter.acquire()
        if self._api_key:
            params["api_key"] = self._api_key
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            raise requests.ConnectionError("Rate limited (429)")
        resp.raise_for_status()
        return resp

    def _fetch_esummary(self, uid: int) -> Optional[dict]:
        params = {"db": "gds", "id": str(uid), "retmode": "json", "version": "2.0"}
        resp = self._http_get(ESUMMARY_URL, params)
        if resp is None:
            return None
        data = resp.json()
        result = data.get("result", {})
        return result.get(str(uid))

    def _fetch_elink_pubmed(self, uid: int) -> List[str]:
        params = {
            "dbfrom": "gds",
            "db": "pubmed",
            "id": str(uid),
            "retmode": "json",
        }
        resp = self._http_get(ELINK_URL, params)
        if resp is None:
            return []
        data = resp.json()
        pmids = []
        for linkset in data.get("linksets", []):
            for linksetdb in linkset.get("linksetdbs", []):
                if linksetdb.get("linkname") == "gds_pubmed":
                    pmids.extend(str(lid) for lid in linksetdb.get("links", []))
        return pmids
