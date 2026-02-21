import gzip

import responses

from metadata_grabber.fetchers.geo import GEOFetcher, _classify_sequencing_type


ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
GEO_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/geo/series"
PUBMED_ESUMMARY_URL = ESUMMARY_URL  # same base URL, different db param


@responses.activate
def test_geo_fetch_success(
    session, fast_limiter, pubmed_resolver,
    geo_esummary_payload, geo_elink_payload, pubmed_esummary_payload,
    geo_soft_single_nuclei,
):
    responses.add(responses.GET, ESUMMARY_URL, json=geo_esummary_payload, status=200)
    responses.add(responses.GET, ELINK_URL, json=geo_elink_payload, status=200)
    # SOFT FTP response (gzip-compressed)
    soft_gz = gzip.compress(geo_soft_single_nuclei.encode("utf-8"))
    ftp_url = f"{GEO_FTP_BASE}/GSE149nnn/GSE149739/soft/GSE149739_family.soft.gz"
    responses.add(responses.GET, ftp_url, body=soft_gz, status=200)
    responses.add(responses.GET, PUBMED_ESUMMARY_URL, json=pubmed_esummary_payload, status=200)

    fetcher = GEOFetcher(session, fast_limiter, pubmed_resolver)
    record = fetcher.fetch("GSE149739")

    assert record.accession == "GSE149739"
    assert record.species == "Mus musculus"
    assert record.data_type == "Expression profiling by high throughput sequencing"
    assert record.platform == "GPL17021"
    assert record.date_deposited == "2020-12-31"
    assert "RNA-seq of mouse cortex" in record.experimental_details
    assert "n=9 samples" in record.experimental_details
    assert "BioProject:PRJNA629819" in record.database_references
    assert "SRA:SRP259944" in record.database_references
    assert record.fetch_status == "success"
    # New fields
    assert record.tissue == "left hippocampus"
    assert "12 months" in record.age
    assert "6 months" in record.age
    assert record.sequencing_type == "single nuclei"


@responses.activate
def test_geo_fetch_bad_accession(session, fast_limiter, pubmed_resolver):
    fetcher = GEOFetcher(session, fast_limiter, pubmed_resolver)
    record = fetcher.fetch("XYZ999")
    assert record.fetch_status == "error"
    assert "Invalid GSE accession" in record.error_message


@responses.activate
def test_geo_fetch_esummary_failure(session, fast_limiter, pubmed_resolver):
    responses.add(responses.GET, ESUMMARY_URL, status=500)

    fetcher = GEOFetcher(session, fast_limiter, pubmed_resolver)
    record = fetcher.fetch("GSE149739")
    assert record.fetch_status == "error"


def test_uid_calculation():
    assert GEOFetcher._accession_to_uid("GSE149739") == 200149739
    assert GEOFetcher._accession_to_uid("GSE1") == 200000001


def test_build_ftp_url():
    url = GEOFetcher._build_ftp_url("GSE261596")
    assert url == "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE261nnn/GSE261596/soft/GSE261596_family.soft.gz"

    url2 = GEOFetcher._build_ftp_url("GSE149739")
    assert url2 == "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE149nnn/GSE149739/soft/GSE149739_family.soft.gz"

    # Small accession number (e.g. GSE100)
    url3 = GEOFetcher._build_ftp_url("GSE100")
    assert url3 == "https://ftp.ncbi.nlm.nih.gov/geo/series/GSEnnn/GSE100/soft/GSE100_family.soft.gz"


# --- SOFT parsing unit tests ---


def test_parse_soft_single_nuclei(geo_soft_single_nuclei):
    result = GEOFetcher._parse_sample_soft(geo_soft_single_nuclei)
    assert result["tissue"] == "left hippocampus"
    assert "12 months" in result["age"]
    assert "6 months" in result["age"]
    assert result["sequencing_type"] == "single nuclei"


def test_parse_soft_bulk(geo_soft_bulk):
    result = GEOFetcher._parse_sample_soft(geo_soft_bulk)
    assert result["tissue"] == "kidney"
    assert result["age"] == "8 weeks"
    assert result["sequencing_type"] == "bulk"


def test_classify_sequencing_type():
    # Single cell
    assert _classify_sequencing_type(
        ["transcriptomic single cell"], ["polya rna"]
    ) == "single cell"

    # Single nuclei
    assert _classify_sequencing_type(
        ["transcriptomic single cell"], ["nuclear rna"]
    ) == "single nuclei"

    # Bulk transcriptomic
    assert _classify_sequencing_type(
        ["transcriptomic"], ["polya rna"]
    ) == "bulk"

    # Bulk genomic
    assert _classify_sequencing_type(
        ["genomic"], []
    ) == "bulk"

    # Empty
    assert _classify_sequencing_type([], []) == ""
