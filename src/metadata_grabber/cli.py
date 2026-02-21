"""Command-line interface for metadata-grabber."""

import argparse
import logging
import os
import sys
from typing import List, Optional

from metadata_grabber.core import MetadataGrabber
from metadata_grabber.output import write_csv, write_tsv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metadata-grabber",
        description="Fetch metadata for genomic accessions (GEO, ENA) and produce a TSV/CSV report.",
    )
    parser.add_argument(
        "accessions",
        nargs="*",
        help="One or more accession numbers (e.g., GSE149739 ERP119049)",
    )
    parser.add_argument(
        "-f", "--file", type=str, default=None,
        help="File containing accession numbers, one per line",
    )
    parser.add_argument(
        "-o", "--output", type=str, default="metadata_report.tsv",
        help="Output file path (default: metadata_report.tsv)",
    )
    parser.add_argument(
        "--format", choices=["tsv", "csv"], default="tsv", dest="fmt",
        help="Output format (default: tsv)",
    )
    parser.add_argument(
        "--ncbi-api-key", type=str, default=None,
        help="NCBI API key for higher rate limits (env: NCBI_API_KEY)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose/debug logging",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Collect accessions
    accessions = list(args.accessions or [])
    if args.file:
        try:
            with open(args.file) as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        accessions.append(stripped)
        except FileNotFoundError:
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)

    if not accessions:
        parser.error("No accessions provided. Supply them as arguments or via --file.")

    api_key = args.ncbi_api_key or os.environ.get("NCBI_API_KEY")

    grabber = MetadataGrabber(ncbi_api_key=api_key)

    print(f"Fetching metadata for {len(accessions)} accession(s)...")
    records = grabber.fetch_all(accessions)

    # Write output
    if args.fmt == "csv":
        write_csv(records, args.output)
    else:
        write_tsv(records, args.output)

    success = sum(1 for r in records if r.fetch_status == "success")
    partial = sum(1 for r in records if r.fetch_status == "partial")
    errors = sum(1 for r in records if r.fetch_status == "error")
    print(f"Done. {success} succeeded, {partial} partial, {errors} failed.")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
