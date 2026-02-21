import responses

from metadata_grabber.fetchers.geo import GEOFetcher


ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
PUBMED_ESUMMARY_URL = ESUMMARY_URL  # same base URL, different db param


@responses.activate
def test_geo_fetch_success(
    session, fast_limiter, pubmed_resolver,
    geo_esummary_payload, geo_elink_payload, pubmed_esummary_payload,
):
    responses.add(responses.GET, ESUMMARY_URL, json=geo_esummary_payload, status=200)
    responses.add(responses.GET, ELINK_URL, json=geo_elink_payload, status=200)
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
