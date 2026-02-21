import responses

from metadata_grabber.fetchers.ena import ENAFetcher

PORTAL_URL = "https://www.ebi.ac.uk/ena/portal/api/search"
XREF_URL = "https://www.ebi.ac.uk/ena/xref/rest/json/search"
PUBMED_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


@responses.activate
def test_ena_fetch_success(
    session, fast_limiter, pubmed_resolver,
    ena_study_payload, ena_run_payload, ena_xref_payload, pubmed_esummary_payload,
):
    # Portal API: study-level
    responses.add(responses.GET, PORTAL_URL, json=ena_study_payload, status=200)
    # Portal API: run-level
    responses.add(responses.GET, PORTAL_URL, json=ena_run_payload, status=200)
    # Xref service
    responses.add(responses.GET, XREF_URL, json=ena_xref_payload, status=200)
    # PubMed eSummary for resolving PMID from xref
    responses.add(responses.GET, PUBMED_URL, json=pubmed_esummary_payload, status=200)

    fetcher = ENAFetcher(session, fast_limiter, pubmed_resolver)
    record = fetcher.fetch("ERP119049")

    assert record.accession == "ERP119049"
    assert record.species == "Staphylococcus aureus"
    assert record.data_type == "WGS"
    assert record.platform == "ILLUMINA"
    assert record.date_deposited == "2019-12-24"
    assert "Genomic surveillance" in record.experimental_details
    assert "Sanger Institute" in record.experimental_details
    assert "BioProject:PRJEB35921" in record.database_references
    assert record.fetch_status == "success"


@responses.activate
def test_ena_fetch_no_study(session, fast_limiter, pubmed_resolver):
    responses.add(responses.GET, PORTAL_URL, json=[], status=200)

    fetcher = ENAFetcher(session, fast_limiter, pubmed_resolver)
    record = fetcher.fetch("ERP000000")

    assert record.fetch_status == "error"
    assert "no study data" in record.error_message
