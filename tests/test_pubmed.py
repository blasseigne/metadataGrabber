import responses

from metadata_grabber.pubmed import PubMedResolver

ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


@responses.activate
def test_resolve_single_pmid(session, fast_limiter, pubmed_esummary_payload):
    responses.add(responses.GET, ESUMMARY_URL, json=pubmed_esummary_payload, status=200)

    resolver = PubMedResolver(session, fast_limiter)
    citations = resolver.resolve(["33046531"])

    assert len(citations) == 1
    assert "Smith J et al." in citations[0]
    assert "(2020" in citations[0]
    assert "Nat Neurosci" in citations[0]
    assert "DOI:10.1038/nn.1234" in citations[0]


def test_resolve_empty():
    import requests
    resolver = PubMedResolver(requests.Session(), RateLimiter(10_000))
    assert resolver.resolve([]) == []


@responses.activate
def test_resolve_deduplicates(session, fast_limiter, pubmed_esummary_payload):
    responses.add(responses.GET, ESUMMARY_URL, json=pubmed_esummary_payload, status=200)

    resolver = PubMedResolver(session, fast_limiter)
    citations = resolver.resolve(["33046531", "33046531"])

    assert len(citations) == 1


from metadata_grabber.rate_limiter import RateLimiter
