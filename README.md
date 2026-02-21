# metadataGrabber

A Python tool that takes genomic dataset accession numbers and automatically queries public databases to compile a standardized metadata report. Supports both a command-line interface and a Streamlit web UI.

## Features

- **GEO support** (GSE accessions) &mdash; fetches metadata from NCBI GEO via E-utilities and sample-level SOFT files from the GEO FTP server
- **ENA support** (ERP accessions) &mdash; fetches metadata from EBI ENA Portal API, Xref service, and Europe PMC
- **Publication resolution** &mdash; automatically links PubMed IDs to formatted citations via NCBI eSummary
- **Sample-level extraction** &mdash; parses tissue, age, and sequencing type (bulk / single cell / single nuclei) from sample characteristics
- **Rate limiting** &mdash; built-in token-bucket rate limiter respects NCBI and EBI request limits
- **Extensible** &mdash; add new databases by implementing the `BaseFetcher` interface and registering it

## Output columns

| Column | Description |
|---|---|
| `accession` | Dataset accession number |
| `species` | Organism (e.g., *Mus musculus*) |
| `tissue` | Tissue or cell type |
| `age` | Sample age or developmental stage |
| `sequencing_type` | `bulk`, `single cell`, `single nuclei`, or `other` |
| `data_type` | Experiment type (e.g., RNA-Seq, WGS) |
| `platform` | Sequencing platform |
| `date_deposited` | Date the dataset was made public |
| `experimental_details` | Title, summary, and sample count |
| `published_works` | Formatted citations with DOIs |
| `database_references` | Cross-references (BioProject, SRA, etc.) |

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/blasseigne/metadataGrabber.git
cd metadataGrabber
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

## Usage

### Command line

```bash
# Fetch metadata for one or more accessions
metadata-grabber GSE261596 ERP119049 -o results.tsv

# Read accessions from a file (one per line)
metadata-grabber -f accessions.txt -o results.tsv

# CSV output with verbose logging
metadata-grabber GSE261596 --format csv -v

# Use an NCBI API key for higher rate limits (10 req/s instead of 3)
metadata-grabber GSE261596 --ncbi-api-key YOUR_KEY
# Or set the environment variable:
export NCBI_API_KEY=YOUR_KEY
metadata-grabber GSE261596
```

**CLI options:**

```
positional arguments:
  accessions                 One or more accession numbers

optional arguments:
  -f, --file FILE            File containing accession numbers, one per line
  -o, --output OUTPUT        Output file path (default: metadata_report.tsv)
  --format {tsv,csv}         Output format (default: tsv)
  --ncbi-api-key KEY         NCBI API key (or set NCBI_API_KEY env var)
  -v, --verbose              Enable debug logging
```

### Streamlit web app

```bash
streamlit run src/metadata_grabber/streamlit_app.py
```

The web UI provides:
- Text area and file upload for entering accessions
- Optional NCBI API key and output format settings in the sidebar
- Progress bar during fetching
- Interactive results table
- Download button for TSV/CSV export

A hosted version is available on [Streamlit Community Cloud](https://metagrabber.streamlit.app) (if deployed).

### As a Python library

```python
from metadata_grabber.core import MetadataGrabber
from metadata_grabber.output import write_tsv

grabber = MetadataGrabber()
records = grabber.fetch_all(["GSE261596", "ERP119049"])
write_tsv(records, "output.tsv")
```

## Project structure

```
metadataGrabber/
├── pyproject.toml
├── requirements.txt
├── src/metadata_grabber/
│   ├── cli.py                  # Command-line interface
│   ├── core.py                 # Orchestrator: prefix routing, shared resources
│   ├── models.py               # MetadataRecord dataclass and output columns
│   ├── output.py               # TSV/CSV writer
│   ├── pubmed.py               # PubMed citation resolver
│   ├── rate_limiter.py         # Token-bucket rate limiter
│   ├── streamlit_app.py        # Streamlit web UI
│   └── fetchers/
│       ├── base.py             # Abstract BaseFetcher ABC
│       ├── geo.py              # NCBI GEO fetcher (GSE accessions)
│       └── ena.py              # EBI ENA fetcher (ERP accessions)
└── tests/
    ├── conftest.py             # Shared fixtures and mock payloads
    ├── test_cli.py
    ├── test_ena.py
    ├── test_geo.py
    ├── test_models.py
    ├── test_output.py
    └── test_pubmed.py
```

## Adding a new database fetcher

1. Create a new file in `src/metadata_grabber/fetchers/` (e.g., `arrayexpress.py`)
2. Implement the `BaseFetcher` interface:
   ```python
   from metadata_grabber.fetchers.base import BaseFetcher
   from metadata_grabber.models import MetadataRecord

   class ArrayExpressFetcher(BaseFetcher):
       def prefixes(self):
           return ["E-MTAB"]

       def fetch(self, accession):
           record = MetadataRecord(accession=accession)
           # ... query APIs and populate fields ...
           return record
   ```
3. Register it in `src/metadata_grabber/fetchers/__init__.py`:
   ```python
   from metadata_grabber.fetchers.arrayexpress import ArrayExpressFetcher
   FETCHER_CLASSES = [GEOFetcher, ENAFetcher, ArrayExpressFetcher]
   ```

## Testing

```bash
# Run all unit tests
pip install -e ".[dev]"
pytest tests/ -v

# Skip integration tests (tests that hit real APIs)
pytest tests/ -v -m "not integration"
```

## License

This project is provided as-is for research use.
