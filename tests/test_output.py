import csv
import io
import tempfile

from metadata_grabber.models import MetadataRecord, OUTPUT_COLUMNS
from metadata_grabber.output import records_to_bytes, write_tsv, write_csv


def _sample_records():
    return [
        MetadataRecord(
            accession="GSE12345",
            species="Homo sapiens",
            data_type="RNA-Seq",
            platform="GPL20301",
            date_deposited="2021-06-29",
            experimental_details="A test study. Details here.",
            published_works="Smith J et al. (2021). Title. Journal.",
            database_references="BioProject:PRJNA123; SRA:SRP456",
        ),
        MetadataRecord(
            accession="ERP99999",
            species="Mus musculus",
            data_type="WGS",
        ),
    ]


def test_write_tsv():
    records = _sample_records()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
        path = f.name
    write_tsv(records, path)

    with open(path, newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["accession"] == "GSE12345"
    assert rows[0]["species"] == "Homo sapiens"
    assert rows[1]["accession"] == "ERP99999"


def test_write_csv():
    records = _sample_records()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name
    write_csv(records, path)

    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == 2
    assert list(rows[0].keys()) == OUTPUT_COLUMNS


def test_records_to_bytes_tsv():
    records = _sample_records()
    data = records_to_bytes(records, fmt="tsv")
    lines = data.decode("utf-8").strip().split("\n")
    assert len(lines) == 3  # header + 2 rows
    assert "accession" in lines[0]
