"""Shared fixtures for metadata-grabber tests."""

import pytest
import requests

from metadata_grabber.pubmed import PubMedResolver
from metadata_grabber.rate_limiter import RateLimiter


@pytest.fixture
def fast_limiter():
    """Rate limiter that never blocks (high rate)."""
    return RateLimiter(10_000)


@pytest.fixture
def session():
    return requests.Session()


@pytest.fixture
def pubmed_resolver(session, fast_limiter):
    return PubMedResolver(session, fast_limiter)


# --- Mock API response payloads ---

@pytest.fixture
def geo_esummary_payload():
    """Realistic GEO eSummary response for GSE149739."""
    return {
        "result": {
            "uids": ["200149739"],
            "200149739": {
                "accession": "GSE149739",
                "taxon": "Mus musculus",
                "gdstype": "Expression profiling by high throughput sequencing",
                "gpl": "17021",
                "pdat": "2020/12/31",
                "title": "RNA-seq of mouse cortex samples",
                "summary": "We profiled gene expression in mouse cortex.",
                "n_samples": 9,
                "pubmedids": [33046531],
                "bioproject": "PRJNA629819",
                "extrelations": [
                    {"relationtype": "SRA", "targetobject": "SRP259944"}
                ],
            },
        }
    }


@pytest.fixture
def geo_elink_payload():
    return {
        "linksets": [
            {
                "linksetdbs": [
                    {"linkname": "gds_pubmed", "links": ["33046531"]}
                ]
            }
        ]
    }


@pytest.fixture
def pubmed_esummary_payload():
    return {
        "result": {
            "uids": ["33046531"],
            "33046531": {
                "authors": [
                    {"name": "Smith J", "authtype": "Author"},
                    {"name": "Doe A", "authtype": "Author"},
                ],
                "pubdate": "2020 Oct",
                "title": "Cortical gene expression in mice.",
                "source": "Nat Neurosci",
                "articleids": [
                    {"idtype": "doi", "value": "10.1038/nn.1234"},
                    {"idtype": "pubmed", "value": "33046531"},
                ],
            },
        }
    }


@pytest.fixture
def ena_study_payload():
    return [
        {
            "study_accession": "PRJEB35921",
            "secondary_study_accession": "ERP119049",
            "study_title": "Genomic surveillance study",
            "study_description": "A study on genomic surveillance.",
            "scientific_name": "",
            "center_name": "Sanger Institute",
            "first_public": "2019-12-24",
            "geo_accession": "",
            "study_alias": "E-MTAB-8086",
            "description": "Genomic surveillance.",
        }
    ]


@pytest.fixture
def ena_run_payload():
    return [
        {
            "scientific_name": "Staphylococcus aureus",
            "tax_id": "1280",
            "instrument_platform": "ILLUMINA",
            "library_strategy": "WGS",
        }
    ]


@pytest.fixture
def ena_xref_payload():
    return [
        {
            "Source": "EuropePMC",
            "Source Primary Accession": "PMC6497808",
            "Source Secondary Accession": "31080781",
        }
    ]
