"""Normalized metadata record — the single contract between fetchers and output."""

from dataclasses import dataclass

OUTPUT_COLUMNS = [
    "accession",
    "species",
    "tissue",
    "age",
    "sequencing_type",
    "data_type",
    "platform",
    "date_deposited",
    "experimental_details",
    "published_works",
    "database_references",
]


@dataclass
class MetadataRecord:
    accession: str
    species: str = ""
    tissue: str = ""
    age: str = ""
    sequencing_type: str = ""  # bulk, single cell, single nuclei, or other
    data_type: str = ""
    platform: str = ""
    date_deposited: str = ""
    experimental_details: str = ""
    published_works: str = ""
    database_references: str = ""
    fetch_status: str = "success"
    error_message: str = ""

    def to_dict(self) -> dict:
        """Return ordered dict of only the output columns (excludes internal fields)."""
        return {col: getattr(self, col) for col in OUTPUT_COLUMNS}
