"""Fetch metadata for ERP accessions from EBI ENA."""

import logging
from collections import Counter
from typing import List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from metadata_grabber.fetchers.base import BaseFetcher
from metadata_grabber.models import MetadataRecord
from metadata_grabber.pubmed import PubMedResolver
from metadata_grabber.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

PORTAL_API_URL = "https://www.ebi.ac.uk/ena/portal/api/search"
XREF_URL = "https://www.ebi.ac.uk/ena/xref/rest/json/search"
EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class ENAFetcher(BaseFetcher):
    def __init__(
        self,
        session: requests.Session,
        rate_limiter: RateLimiter,
        pubmed_resolver: PubMedResolver,
    ):
        self._session = session
        self._limiter = rate_limiter
        self._pubmed = pubmed_resolver

    def prefixes(self) -> List[str]:
        return ["ERP"]

    def fetch(self, accession: str) -> MetadataRecord:
        record = MetadataRecord(accession=accession)

        # 1. Study-level metadata
        study = self._fetch_study_metadata(accession)
        if study is None:
            record.fetch_status = "error"
            record.error_message = "ENA Portal API returned no study data"
            return record

        record.date_deposited = study.get("first_public", "")
        title = study.get("study_title", "")
        description = study.get("study_description", "") or study.get("description", "")
        center = study.get("center_name", "")
        details = title
        if description:
            details += f". {description}"
        if center:
            details += f" (Center: {center})"
        record.experimental_details = details

        # Study-level species (often blank — will override from run level)
        record.species = study.get("scientific_name", "")

        # 2. Run-level metadata (species, platform, library strategy, tissue, age)
        run = self._fetch_run_metadata(accession)
        if run:
            if run.get("scientific_name"):
                record.species = run["scientific_name"]
            record.platform = run.get("instrument_platform", "")
            record.data_type = run.get("library_strategy", "")
            record.tissue = run.get("tissue_type", "")
            record.age = run.get("age", "")
            record.sequencing_type = _classify_library_source(
                run.get("library_source", "")
            )

        # 3. Database references
        db_refs = []
        primary_acc = study.get("study_accession", "")
        if primary_acc:
            db_refs.append(f"BioProject:{primary_acc}")
        geo_acc = study.get("geo_accession", "")
        if geo_acc:
            db_refs.append(f"GEO:{geo_acc}")

        # 4. Cross-references + publications
        xrefs = self._fetch_xrefs(accession)
        pmids = []
        for xref in xrefs:
            source = xref.get("Source", "")
            primary = xref.get("Source Primary Accession", "")
            secondary = xref.get("Source Secondary Accession", "")

            if source and primary:
                db_refs.append(f"{source}:{primary}")

            # EuropePMC xrefs have PMCID as primary, PMID as secondary
            if source == "EuropePMC" and secondary:
                pmids.append(secondary)

        record.database_references = "; ".join(db_refs)

        # 5. Resolve publications from xref PMIDs
        if pmids:
            citations = self._pubmed.resolve(pmids)
            record.published_works = "; ".join(citations)
        else:
            # Fallback: search Europe PMC by accession and alias
            aliases = [accession, study.get("study_alias", "")]
            citations = self._search_europepmc_publications(aliases)
            if citations:
                record.published_works = "; ".join(citations)

        return record

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
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            raise requests.ConnectionError("Rate limited (429)")
        resp.raise_for_status()
        return resp

    def _fetch_study_metadata(self, accession: str) -> Optional[dict]:
        params = {
            "result": "study",
            "query": f'secondary_study_accession="{accession}"',
            "format": "json",
            "fields": "all",
        }
        resp = self._http_get(PORTAL_API_URL, params)
        if resp is None:
            return None
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
        return None

    def _fetch_run_metadata(self, accession: str) -> Optional[dict]:
        """Query read_study for species/platform/tissue/age (study-level often lacks these)."""
        params = {
            "result": "read_study",
            "query": f'secondary_study_accession="{accession}"',
            "format": "json",
            "fields": (
                "scientific_name,tax_id,instrument_platform,library_strategy,"
                "library_source,tissue_type,age,cell_type"
            ),
            "limit": "5",
        }
        resp = self._http_get(PORTAL_API_URL, params)
        if resp is None:
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None

        # Take most common value for each field across runs
        result = {}
        for field in (
            "scientific_name", "instrument_platform", "library_strategy",
            "library_source", "tissue_type", "age", "cell_type",
        ):
            values = [row.get(field, "") for row in data if row.get(field)]
            if values:
                result[field] = Counter(values).most_common(1)[0][0]
        return result if result else None

    def _fetch_xrefs(self, accession: str) -> List[dict]:
        params = {"accession": accession}
        resp = self._http_get(XREF_URL, params)
        if resp is None:
            return []
        try:
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _search_europepmc_publications(self, queries: List[str]) -> List[str]:
        """Fallback: search Europe PMC full text for accession mentions."""
        citations = []
        seen_pmids = set()
        for q in queries:
            if not q:
                continue
            params = {
                "query": q,
                "format": "json",
                "resultType": "lite",
                "pageSize": "5",
            }
            resp = self._http_get(EUROPEPMC_URL, params)
            if resp is None:
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            for item in data.get("resultList", {}).get("result", []):
                pmid = item.get("pmid", "")
                if pmid and pmid not in seen_pmids:
                    seen_pmids.add(pmid)
                    # Format inline from Europe PMC data
                    author = item.get("authorString", "Unknown")
                    year = str(item.get("pubYear", ""))
                    title = item.get("title", "").rstrip(".")
                    journal = item.get("journalTitle", "")
                    doi = item.get("doi", "")
                    parts = [f"{author} ({year})", title, journal]
                    if doi:
                        parts.append(f"DOI:{doi}")
                    else:
                        parts.append(f"PMID:{pmid}")
                    citations.append(". ".join(p for p in parts if p))
        return citations


def _classify_library_source(library_source: str) -> str:
    """Classify sequencing type from ENA library_source field."""
    if not library_source:
        return ""
    src = library_source.lower()
    if "single cell" in src:
        return "single cell"
    if "transcriptomic" in src or "genomic" in src:
        return "bulk"
    return "other"
