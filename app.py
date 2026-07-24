"""Medical chronology viewer — Streamlit app for personal injury case records."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from data_loader import (
    load_chronology_from_bytes,
    load_chronology_from_path,
    split_multi_value,
    unique_body_parts,
    unique_providers,
)
from drive_client import build_drive_service, download_file_bytes

SUMMARY_TRUNCATE = 120
CACHE_TTL_SECONDS = 300


def _secrets_ready() -> bool:
    try:
        st.secrets["drive"]["file_id"]
        st.secrets["google_service_account"]["client_email"]
        return True
    except (KeyError, FileNotFoundError):
        return False


def _local_path_configured() -> str | None:
    try:
        path = st.secrets.get("drive", {}).get("local_xlsx_path")
        if path:
            return str(path)
    except (KeyError, FileNotFoundError):
        pass
    return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading medical chronology...")
def fetch_chronology(source_key: str) -> tuple[pd.DataFrame, dict]:
    """Load chronology data from local file or Google Drive."""
    local_path = _local_path_configured()
    if local_path and Path(local_path).exists():
        return load_chronology_from_path(local_path)

    if not _secrets_ready():
        raise RuntimeError("missing_secrets")

    service = build_drive_service(dict(st.secrets["google_service_account"]))
    file_id = st.secrets["drive"]["file_id"]
    xlsx_bytes = download_file_bytes(service, file_id)
    return load_chronology_from_bytes(xlsx_bytes)


def show_setup_instructions() -> None:
    st.error("Configuration required")
    st.markdown(
        """
Create `.streamlit/secrets.toml` (local) or add secrets in Streamlit Cloud with:

```toml
[drive]
file_id = "YOUR_GOOGLE_DRIVE_FILE_ID"
# local_xlsx_path = "/path/to/Caldwell - Medical Chronology.xlsx"

[google_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

See the README for Google Cloud setup and deployment steps.
"""
    )


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

    if st.sidebar.button("Refresh now"):
        fetch_chronology.clear()
        st.rerun()

    try:
        df, stats = fetch_chronology("default")
    except RuntimeError as exc:
        if str(exc) == "missing_secrets":
            show_setup_instructions()
            return
        raise
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.info("Set `drive.local_xlsx_path` in secrets or configure Google Drive access.")
        return
    except Exception as exc:
        st.error(f"Failed to load chronology: {exc}")
        st.info("Check the README troubleshooting section for Drive API and secrets setup.")
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
