"""Fetch metadata for GSE accessions from NCBI GEO via E-utilities."""

import gzip
import io
import logging
import re
from collections import Counter
from typing import Dict, List, Optional, Set

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from metadata_grabber.fetchers.base import BaseFetcher
from metadata_grabber.models import MetadataRecord
from metadata_grabber.pubmed import PubMedResolver
from metadata_grabber.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
GEO_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/geo/series"
GEO_UID_OFFSET = 200_000_000

# Keywords for classifying sequencing type from library_source + molecule
_SINGLE_CELL_KEYWORDS = {"transcriptomic single cell", "single cell"}
_NUCLEAR_RNA_KEYWORDS = {"nuclear rna"}


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

        # 4. Fetch sample-level metadata from SOFT format
        #    (tissue, age, sequencing type)
        sample_meta = self._fetch_sample_soft(accession)
        if sample_meta:
            record.tissue = sample_meta.get("tissue", "")
            record.age = sample_meta.get("age", "")
            record.sequencing_type = sample_meta.get("sequencing_type", "")

        # 5. Resolve publications
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

    # --- Sample-level SOFT parsing for tissue, age, sequencing type ---

    @staticmethod
    def _build_ftp_url(accession: str) -> str:
        """Build the GEO FTP URL for the family SOFT file.

        URL pattern:
          https://ftp.ncbi.nlm.nih.gov/geo/series/GSE{prefix}nnn/GSE{num}/soft/GSE{num}_family.soft.gz

        where {prefix} is the accession number with the last 3 digits replaced by 'nnn'.
        E.g. GSE261596 → GSE261nnn/GSE261596
        """
        num_str = accession[3:]  # strip "GSE"
        if len(num_str) > 3:
            prefix = num_str[:-3] + "nnn"
        else:
            prefix = "nnn"
        return f"{GEO_FTP_BASE}/GSE{prefix}/{accession}/soft/{accession}_family.soft.gz"

    def _fetch_sample_soft(self, accession: str) -> Optional[Dict[str, str]]:
        """Download the compressed SOFT file from GEO FTP and extract
        tissue, age, and sequencing type (bulk/single cell/single nuclei).
        Returns aggregated values across samples."""
        url = self._build_ftp_url(accession)
        try:
            self._limiter.acquire()
            resp = self._session.get(url, timeout=90)
            resp.raise_for_status()
        except Exception:
            logger.warning("SOFT FTP fetch failed for %s", accession, exc_info=True)
            return None

        # Decompress gzip content
        try:
            soft_text = gzip.decompress(resp.content).decode("utf-8", errors="replace")
        except Exception:
            logger.warning("Failed to decompress SOFT for %s", accession, exc_info=True)
            return None

        return self._parse_sample_soft(soft_text)

    @staticmethod
    def _parse_sample_soft(soft_text: str) -> Dict[str, str]:
        """Parse SOFT text for all samples and return aggregated metadata."""
        tissues: List[str] = []
        ages: List[str] = []
        library_sources: List[str] = []
        molecules: List[str] = []
        source_names: List[str] = []

        for line in soft_text.split("\n"):
            line = line.strip()

            # Sample characteristics (key: value format)
            if line.startswith("!Sample_characteristics_ch1"):
                value = line.split("=", 1)[-1].strip()
                kv = value.split(":", 1)
                if len(kv) == 2:
                    key = kv[0].strip().lower()
                    val = kv[1].strip()
                    if key in ("tissue", "tissue type", "organ", "cell type"):
                        tissues.append(val)
                    elif key in ("age", "developmental stage", "dev stage"):
                        ages.append(val)

            elif line.startswith("!Sample_source_name_ch1"):
                val = line.split("=", 1)[-1].strip()
                if val:
                    source_names.append(val)

            elif line.startswith("!Sample_library_source"):
                val = line.split("=", 1)[-1].strip().lower()
                if val:
                    library_sources.append(val)

            elif line.startswith("!Sample_molecule_ch1"):
                val = line.split("=", 1)[-1].strip().lower()
                if val:
                    molecules.append(val)

        result: Dict[str, str] = {}

        # Tissue: use characteristics first, fall back to source_name
        if tissues:
            result["tissue"] = _most_common(tissues)
        elif source_names:
            result["tissue"] = _most_common(source_names)

        # Age: collect unique values
        if ages:
            unique_ages = sorted(set(ages))
            result["age"] = "; ".join(unique_ages)

        # Sequencing type: classify from library_source + molecule
        result["sequencing_type"] = _classify_sequencing_type(
            library_sources, molecules
        )

        return result


def _most_common(values: List[str]) -> str:
    """Return the most common value, or semicolon-separated unique values
    if there are multiple distinct values."""
    counts = Counter(values)
    unique = sorted(counts.keys())
    if len(unique) == 1:
        return unique[0]
    # Multiple distinct values: return all unique, sorted
    return "; ".join(unique)


def _classify_sequencing_type(
    library_sources: List[str], molecules: List[str]
) -> str:
    """Classify as bulk, single cell, single nuclei, or other
    based on GEO SOFT library_source and molecule fields."""
    if not library_sources:
        return ""

    source_set = set(library_sources)
    molecule_set = set(molecules)

    # Check for single-cell indicators in library_source
    is_single_cell = any(
        kw in src for src in source_set for kw in _SINGLE_CELL_KEYWORDS
    )

    if is_single_cell:
        # Distinguish single nuclei vs single cell via molecule
        is_nuclear = any(
            kw in mol for mol in molecule_set for kw in _NUCLEAR_RNA_KEYWORDS
        )
        if is_nuclear:
            return "single nuclei"
        return "single cell"

    # Check for standard transcriptomic/genomic (bulk)
    if any("transcriptomic" in src for src in source_set):
        return "bulk"
    if any("genomic" in src for src in source_set):
        return "bulk"

    return "other"
