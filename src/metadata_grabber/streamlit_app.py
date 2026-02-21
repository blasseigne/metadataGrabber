"""Streamlit web UI for metadata-grabber."""

import os
import sys
from pathlib import Path

# Ensure the src/ directory is on the Python path so that
# metadata_grabber is importable on Streamlit Community Cloud
# (which doesn't pip-install the package itself).
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st

from metadata_grabber.core import MetadataGrabber
from metadata_grabber.models import OUTPUT_COLUMNS
from metadata_grabber.output import records_to_bytes


def main():
    st.set_page_config(page_title="Metadata Grabber", layout="wide")
    st.title("Genomic Metadata Grabber")
    st.markdown(
        "Fetch metadata for **GEO** (GSE) and **ENA** (ERP) accessions "
        "and download a TSV/CSV report."
    )

    # Sidebar
    with st.sidebar:
        st.header("Settings")
        ncbi_api_key = st.text_input(
            "NCBI API Key (optional)",
            value=os.environ.get("NCBI_API_KEY", ""),
            type="password",
            help="Increases NCBI rate limit from 3 to 10 requests/sec",
        )
        output_format = st.selectbox("Output format", ["TSV", "CSV"])

    # Input
    accession_text = st.text_area(
        "Enter accession numbers (one per line or comma-separated)",
        placeholder="GSE149739\nERP119049",
        height=150,
    )
    uploaded_file = st.file_uploader(
        "Or upload a file with accessions", type=["txt", "csv", "tsv"]
    )

    # Parse
    accessions = _parse_accessions(accession_text, uploaded_file)

    if accessions:
        st.caption(f"{len(accessions)} accession(s) detected: {', '.join(accessions)}")

    # Fetch
    if st.button("Fetch Metadata", type="primary", disabled=len(accessions) == 0):
        api_key = ncbi_api_key.strip() or None
        grabber = MetadataGrabber(ncbi_api_key=api_key)
        progress = st.progress(0)
        status = st.empty()
        records = []

        for i, acc in enumerate(accessions):
            status.text(f"Fetching {acc} ({i + 1}/{len(accessions)})...")
            result = grabber.fetch_one(acc)
            records.append(result)
            progress.progress((i + 1) / len(accessions))

        status.text("Done!")
        st.session_state["records"] = records
        st.session_state["output_format"] = output_format

    # Display results
    if "records" in st.session_state:
        records = st.session_state["records"]
        fmt = st.session_state.get("output_format", output_format)

        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(records))
        col2.metric("Succeeded", sum(1 for r in records if r.fetch_status == "success"))
        col3.metric("Errors", sum(1 for r in records if r.fetch_status == "error"))

        # Table
        import pandas as pd

        df = pd.DataFrame([r.to_dict() for r in records])
        st.dataframe(df, use_container_width=True)

        # Download
        fmt_lower = fmt.lower()
        file_bytes = records_to_bytes(records, fmt=fmt_lower)
        st.download_button(
            label=f"Download {fmt.upper()}",
            data=file_bytes,
            file_name=f"metadata_report.{fmt_lower}",
            mime="text/tab-separated-values" if fmt_lower == "tsv" else "text/csv",
        )


def _parse_accessions(text: str, uploaded_file) -> list:
    accessions = []
    if text:
        for line in text.strip().split("\n"):
            for item in line.split(","):
                item = item.strip()
                if item:
                    accessions.append(item)
    if uploaded_file:
        content = uploaded_file.read().decode("utf-8")
        for line in content.strip().split("\n"):
            for item in line.split(","):
                item = item.strip()
                if item and not item.startswith("#"):
                    accessions.append(item)
    return accessions


if __name__ == "__main__":
    main()
