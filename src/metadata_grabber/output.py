"""Write MetadataRecords to TSV/CSV files."""

import csv
import io
from typing import List

from metadata_grabber.models import MetadataRecord, OUTPUT_COLUMNS


def write_tsv(records: List[MetadataRecord], filepath: str) -> None:
    _write(records, filepath, delimiter="\t")


def write_csv(records: List[MetadataRecord], filepath: str) -> None:
    _write(records, filepath, delimiter=",")


def _write(records: List[MetadataRecord], filepath: str, delimiter: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=OUTPUT_COLUMNS, delimiter=delimiter, extrasaction="ignore"
        )
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.to_dict())


def records_to_bytes(records: List[MetadataRecord], fmt: str = "tsv") -> bytes:
    """Serialize records to bytes (for Streamlit download button)."""
    buf = io.StringIO()
    delimiter = "\t" if fmt == "tsv" else ","
    writer = csv.DictWriter(
        buf, fieldnames=OUTPUT_COLUMNS, delimiter=delimiter, extrasaction="ignore"
    )
    writer.writeheader()
    for rec in records:
        writer.writerow(rec.to_dict())
    return buf.getvalue().encode("utf-8")
