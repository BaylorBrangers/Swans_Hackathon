"""Medical chronology viewer — Streamlit app for personal injury case records."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data_loader import (
    load_chronology_from_bytes,
    split_multi_value,
    unique_body_parts,
    unique_providers,
)

SUMMARY_TRUNCATE = 120


@st.cache_data(show_spinner="Parsing chronology...")
def parse_uploaded_xlsx(xlsx_bytes: bytes) -> tuple[pd.DataFrame, dict]:
    """Parse uploaded xlsx bytes into a normalized chronology DataFrame."""
    return load_chronology_from_bytes(xlsx_bytes)


def render_upload_section() -> bool:
    """Show drag-and-drop uploader; return True when a file is loaded."""
    st.subheader("Upload chronology")
    uploaded = st.file_uploader(
        "Drag and drop your medical chronology xlsx here",
        type=["xlsx"],
        help="Expected format: Caldwell medical chronology with Encounter Date, Provider, Facility, and related columns.",
    )

    if uploaded is not None:
        st.session_state["xlsx_bytes"] = uploaded.getvalue()
        st.session_state["xlsx_name"] = uploaded.name

    if not st.session_state.get("xlsx_bytes"):
        st.info(
            "Upload an `.xlsx` file to explore the chronology. "
            "Google Drive connection can be configured later."
        )
        return False

    name = st.session_state.get("xlsx_name", "uploaded file")
    col1, col2 = st.columns([4, 1])
    with col1:
        st.success(f"**{name}**")
    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.pop("xlsx_bytes", None)
            st.session_state.pop("xlsx_name", None)
            parse_uploaded_xlsx.clear()
            st.rerun()

    return True


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df.copy()

    min_date = filtered["encounter_date"].min().date()
    max_date = filtered["encounter_date"].max().date()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered["encounter_date"].dt.date >= start)
            & (filtered["encounter_date"].dt.date <= end)
        ]

    record_types = st.sidebar.multiselect(
        "Record Type",
        options=sorted(filtered["record_type"].unique()),
        default=[],
    )
    if record_types:
        filtered = filtered[filtered["record_type"].isin(record_types)]

    medicine_types = st.sidebar.multiselect(
        "Medicine Type",
        options=sorted(filtered["medicine_type"].unique()),
        default=[],
    )
    if medicine_types:
        filtered = filtered[filtered["medicine_type"].isin(medicine_types)]

    facilities = st.sidebar.multiselect(
        "Facility",
        options=sorted(filtered["facility"].unique()),
        default=[],
    )
    if facilities:
        filtered = filtered[filtered["facility"].isin(facilities)]

    providers = st.sidebar.multiselect(
        "Primary Provider",
        options=unique_providers(filtered["primary_provider"]),
        default=[],
    )
    if providers:
        filtered = filtered[
            filtered["primary_provider"].apply(
                lambda value: any(p in split_multi_value(value, ";") for p in providers)
            )
        ]

    body_parts = st.sidebar.multiselect(
        "Body Parts",
        options=unique_body_parts(filtered["body_parts"]),
        default=[],
    )
    if body_parts:
        filtered = filtered[
            filtered["body_parts"].apply(
                lambda value: any(part in split_multi_value(value, ",") for part in body_parts)
            )
        ]

    search = st.sidebar.text_input("Search summary, provider, or facility")
    if search.strip():
        needle = search.strip().lower()
        filtered = filtered[
            filtered["summary"].str.lower().str.contains(needle, na=False)
            | filtered["primary_provider"].str.lower().str.contains(needle, na=False)
            | filtered["facility"].str.lower().str.contains(needle, na=False)
        ]

    sort_newest_first = st.sidebar.toggle("Newest first", value=True)
    filtered = filtered.sort_values(
        "encounter_date",
        ascending=not sort_newest_first,
    ).reset_index(drop=True)

    return filtered


def render_table_view(df: pd.DataFrame) -> None:
    display = df.copy()
    display["encounter_date"] = display["encounter_date"].dt.strftime("%m/%d/%Y")
    display["summary_short"] = display["summary"].apply(
        lambda text: text if len(text) <= SUMMARY_TRUNCATE else f"{text[:SUMMARY_TRUNCATE].rstrip()}…"
    )

    table_df = display[
        [
            "encounter_date",
            "primary_provider",
            "facility",
            "record_type",
            "medicine_type",
            "body_parts",
            "summary_short",
            "pdf_url",
        ]
    ].rename(
        columns={
            "encounter_date": "Date",
            "primary_provider": "Provider",
            "facility": "Facility",
            "record_type": "Record Type",
            "medicine_type": "Medicine Type",
            "body_parts": "Body Parts",
            "summary_short": "Summary",
            "pdf_url": "PDF",
        }
    )

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "PDF": st.column_config.LinkColumn("View PDF", display_text="View PDF"),
        },
    )

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Export filtered results to CSV",
        data=csv,
        file_name="medical_chronology_filtered.csv",
        mime="text/csv",
    )


def render_timeline_view(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No events match the current filters.")
        return

    for event_date, group in df.groupby(df["encounter_date"].dt.date, sort=False):
        label = pd.Timestamp(event_date).strftime("%A, %B %d, %Y")
        with st.expander(f"{label} ({len(group)} event{'s' if len(group) != 1 else ''})", expanded=False):
            for _, row in group.iterrows():
                st.markdown(f"**{row['record_type']}** · {row['medicine_type']}")
                st.caption(f"{row['primary_provider']} · {row['facility']}")
                if row["body_parts"]:
                    st.markdown(f"**Body parts:** {row['body_parts']}")
                st.write(row["summary"])
                if row["pdf_url"]:
                    st.link_button("View PDF", row["pdf_url"])
                st.divider()


def main() -> None:
    st.set_page_config(page_title="Medical Chronology", layout="wide")
    st.title("Medical Chronology")

    if not render_upload_section():
        return

    xlsx_bytes = st.session_state["xlsx_bytes"]

    try:
        df, stats = parse_uploaded_xlsx(xlsx_bytes)
    except Exception as exc:
        st.error(f"Could not read the uploaded file: {exc}")
        st.info(
            "Make sure the spreadsheet matches the Caldwell chronology format "
            "(Encounter Date, Primary Provider, Facility, Body Parts, Medicine Type, "
            "Record Type, Summary, Link To Pdf)."
        )
        return

    if stats.get("skipped_rows"):
        st.sidebar.warning(f"Skipped {stats['skipped_rows']} row(s) with unparseable dates.")

    min_date = df["encounter_date"].min().strftime("%m/%d/%Y")
    max_date = df["encounter_date"].max().strftime("%m/%d/%Y")
    st.caption(f"{len(df)} events · {min_date} to {max_date}")

    filtered = apply_filters(df)

    if filtered.empty:
        st.info("No events match the current filters.")
        return

    table_tab, timeline_tab = st.tabs(["Table", "Timeline"])
    with table_tab:
        render_table_view(filtered)
    with timeline_tab:
        render_timeline_view(filtered)


if __name__ == "__main__":
    main()
