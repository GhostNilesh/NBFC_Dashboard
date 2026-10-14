"""Direct-from-source Streamlit entry point.

This version does not create or read nbfc_parsed.xlsx. It parses the compiled
workbook in memory and passes the resulting DataFrame directly to the dashboard.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import APP_TITLE
from dashboard import render_dashboard
from parser import parse_workbook

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULT_WORKBOOK = "Financials- NBFC updated.xlsx"


@st.cache_data(
    show_spinner="Reading the compiled NBFC workbook and building the dashboard...",
    ttl=None,
)
def load_directly_from_workbook(
    workbook_path: str,
    workbook_modified_time: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse the source workbook directly into memory.

    workbook_modified_time is intentionally part of the cache key. Whenever the
    source Excel file is replaced or saved, Streamlit automatically builds a new
    in-memory dataset instead of reusing data from the earlier workbook version.
    """
    data, issues = parse_workbook(
        path=workbook_path,
        segment_sheet_prefix="NBFC-",
        include_blank_values=False,
    )

    required = {
        "Segment",
        "Company",
        "Section",
        "Metric",
        "Year",
        "ValueNumeric",
        "ValueKind",
        "Unit",
    }
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(
            "The direct parser did not return required columns: "
            + ", ".join(missing)
        )

    data["ValueNumeric"] = pd.to_numeric(
        data["ValueNumeric"],
        errors="coerce",
    )

    text_columns = [
        "Segment",
        "Company",
        "Section",
        "Metric",
        "Year",
        "ValueKind",
        "Unit",
    ]
    for column in text_columns:
        data[column] = (
            data[column]
            .fillna("")
            .astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )

    return data, issues


def show_data_source_panel() -> str:
    """Render the compact data-source controls in the sidebar."""
    with st.sidebar:
        st.header("Data source")
        workbook_path = st.text_input(
            "Compiled workbook",
            value=DEFAULT_WORKBOOK,
            help="The dashboard reads this workbook directly. No parsed Excel file is required.",
        )

        if st.button("Reload workbook", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.caption(
            "Save or replace the source workbook, then click Reload workbook. "
            "The dashboard will reconstruct its in-memory data directly from Excel."
        )

    return workbook_path


def main() -> None:
    workbook_path = show_data_source_panel()
    workbook = Path(workbook_path)

    if not workbook.exists():
        st.error(f"Source workbook not found: {workbook.resolve()}")
        st.info(
            "Place Financials- NBFC updated.xlsx in the same folder as app.py, "
            "or enter the full workbook path in the sidebar."
        )
        st.stop()

    try:
        data, issues = load_directly_from_workbook(
            workbook_path=str(workbook.resolve()),
            workbook_modified_time=workbook.stat().st_mtime,
        )
    except Exception as exc:
        st.error("The source workbook could not be parsed.")
        st.exception(exc)
        st.stop()

    with st.sidebar:
        st.divider()
        st.metric("Parsed records", f"{len(data):,}")
        st.metric("Segments", data["Segment"].nunique())
        st.metric("NBFCs", data["Company"].nunique())

        if issues is not None and not issues.empty:
            st.warning(f"{len(issues)} parser warning(s) found")
            with st.expander("Show parser warnings"):
                st.dataframe(issues, use_container_width=True, hide_index=True)
        else:
            st.success("Workbook read successfully")

    render_dashboard(data)


if __name__ == "__main__":
    main()
