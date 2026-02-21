from metadata_grabber.models import MetadataRecord, OUTPUT_COLUMNS


def test_to_dict_has_correct_keys():
    rec = MetadataRecord(accession="GSE12345", species="Homo sapiens")
    d = rec.to_dict()
    assert list(d.keys()) == OUTPUT_COLUMNS


def test_to_dict_excludes_internal_fields():
    rec = MetadataRecord(accession="GSE12345", fetch_status="error", error_message="fail")
    d = rec.to_dict()
    assert "fetch_status" not in d
    assert "error_message" not in d


def test_default_values():
    rec = MetadataRecord(accession="X")
    assert rec.species == ""
    assert rec.fetch_status == "success"
