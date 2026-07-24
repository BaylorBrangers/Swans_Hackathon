"""Medical chronology viewer — Streamlit app for personal injury case records."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data_loader import (
    load_chronology_from_bytes,
    split_multi_value,
    unique_body_parts,
    unique_providers,
)
from injury_progression import (
    SEVERITY_LABELS,
    build_progression,
    extract_observations,
    render_progression_html,
)

SUMMARY_TRUNCATE = 120
PLOT_FIELDS = {
    "Record Type": ("record_type", None),
    "Medicine Type": ("medicine_type", None),
    "Facility": ("facility", None),
    "Primary Provider": ("primary_provider", ";"),
    "Body Parts": ("body_parts", ","),
}


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


def build_event_plot_data(
    df: pd.DataFrame,
    field: str,
    separator: str | None,
    selected_values: list[str],
    time_grouping: str,
) -> pd.DataFrame:
    """Aggregate event counts by date and selected categorical values."""
    plot_df = df[["encounter_date", field]].copy()
    if separator:
        plot_df["value"] = plot_df[field].apply(
            lambda value: split_multi_value(str(value), separator)
        )
    else:
        plot_df["value"] = plot_df[field].apply(
            lambda value: [str(value).strip()] if str(value).strip() else []
        )
    plot_df = plot_df.explode("value")
    plot_df = plot_df[plot_df["value"].notna() & (plot_df["value"] != "")]

    if selected_values:
        plot_df = plot_df[plot_df["value"].isin(selected_values)]

    if time_grouping == "Day":
        plot_df["period"] = plot_df["encounter_date"].dt.floor("D")
    elif time_grouping == "Week":
        plot_df["period"] = (
            plot_df["encounter_date"].dt.to_period("W").dt.start_time
        )
    else:
        plot_df["period"] = (
            plot_df["encounter_date"].dt.to_period("M").dt.start_time
        )

    chart_data = (
        plot_df.groupby(["period", "value"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    if selected_values:
        chart_data = chart_data.reindex(columns=selected_values, fill_value=0)
    return chart_data


def render_chart_view(df: pd.DataFrame) -> None:
    """Render an interactive event-count chart from selected field values."""
    st.subheader("Plot events")
    st.caption(
        "Choose a field and values to compare event counts over time. "
        "Events with multiple providers or body parts count once for each matching value."
    )

    control_1, control_2, control_3 = st.columns(3)
    with control_1:
        field_label = st.selectbox("Group events by", options=list(PLOT_FIELDS))
    field, separator = PLOT_FIELDS[field_label]

    if separator:
        value_options = sorted(
            {
                part
                for value in df[field]
                for part in split_multi_value(str(value), separator)
            }
        )
    else:
        value_options = sorted(
            value for value in df[field].dropna().astype(str).unique() if value
        )

    with control_2:
        selected_values = st.multiselect(
            "Values to plot",
            options=value_options,
            default=value_options[: min(5, len(value_options))],
        )
    with control_3:
        time_grouping = st.selectbox(
            "Group dates by", options=["Day", "Week", "Month"], index=2
        )

    chart_type = st.radio(
        "Chart type", options=["Line", "Bar"], horizontal=True
    )

    if not selected_values:
        st.info("Select at least one value to plot.")
        return

    chart_data = build_event_plot_data(
        df, field, separator, selected_values, time_grouping
    )
    if chart_data.empty or chart_data.to_numpy().sum() == 0:
        st.info("No events match the selected values and current sidebar filters.")
        return

    st.caption(
        f"{int(chart_data.to_numpy().sum())} plotted event-value occurrence(s)"
    )
    if chart_type == "Line":
        st.line_chart(chart_data, use_container_width=True)
    else:
        st.bar_chart(chart_data, use_container_width=True)

    with st.expander("View plotted data"):
        st.dataframe(
            chart_data.rename_axis("Date").reset_index(),
            use_container_width=True,
            hide_index=True,
        )


def render_injury_progression_view(df: pd.DataFrame) -> None:
    """Render inferred body-part severity changes along a time axis."""
    st.subheader("Injury progression")
    st.caption(
        "Severity is inferred from summary keywords and should be reviewed before "
        "presentation. Select one medicine type at a time."
    )

    medicine_types = sorted(
        value for value in df["medicine_type"].dropna().astype(str).unique() if value
    )
    if not medicine_types:
        st.info("No medicine types are available in the filtered events.")
        return

    medicine_type = st.selectbox(
        "Medicine Type",
        options=medicine_types,
        key="progression_medicine_type",
    )
    template = st.file_uploader(
        "Body outline template (optional)",
        type=["png", "jpg", "jpeg"],
        key="body_outline_template",
        help=(
            "Upload the supplied front-facing body outline, or leave empty to use "
            "the built-in outline."
        ),
    )

    observations = extract_observations(df, medicine_type)
    if observations.empty:
        st.info("No body-part observations exist for this medicine type.")
        return

    review = observations[
        [
            "encounter_date",
            "body_part",
            "suggested_action",
            "reason",
            "matched_text",
            "override",
        ]
    ].copy()
    review["encounter_date"] = review["encounter_date"].dt.date
    review["body_part"] = review["body_part"].str.title()
    review["suggested_action"] = review["suggested_action"].map(
        {
            "injury": SEVERITY_LABELS[1],
            "worsening": SEVERITY_LABELS[2],
            "severe": SEVERITY_LABELS[3],
            "improving": "Improving",
            "resolved": "Resolved",
        }
    )
    review = review.rename(
        columns={
            "encounter_date": "Date",
            "body_part": "Body Part",
            "suggested_action": "Suggested Status",
            "reason": "Reason",
            "matched_text": "Matched Text",
            "override": "Override",
        }
    )

    with st.expander("Review and correct inferred severity", expanded=False):
        st.write(
            "Use **Override** to correct an inference. Negated findings such as "
            "\"no fracture\" are excluded automatically."
        )
        reviewed = st.data_editor(
            review,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "Date",
                "Body Part",
                "Suggested Status",
                "Reason",
                "Matched Text",
            ],
            column_config={
                "Override": st.column_config.SelectboxColumn(
                    "Override",
                    options=[
                        "Auto",
                        "Injury",
                        "Worsening injury",
                        "Severe injury",
                        "Resolved",
                    ],
                    required=True,
                )
            },
            key=f"severity_review_{medicine_type}",
        )

    observations = observations.copy()
    observations["override"] = reviewed["Override"].tolist()
    snapshots, changes = build_progression(observations)
    if not snapshots:
        st.info("No injury status changes were inferred for this selection.")
        return

    image_bytes = template.getvalue() if template is not None else None
    mime_type = template.type if template is not None else None
    chart_height = 370
    components.html(
        render_progression_html(snapshots, image_bytes, mime_type),
        height=chart_height,
        scrolling=True,
    )

    st.caption(
        "Hover over a circle for its body part, severity, and inference reason. "
        "The timeline shows only dates when a status was added, changed, or resolved."
    )
    with st.expander("View progression changes"):
        display_changes = changes.copy()
        display_changes["Date"] = display_changes["Date"].dt.strftime("%m/%d/%Y")
        st.dataframe(
            display_changes,
            use_container_width=True,
            hide_index=True,
        )


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

    table_tab, timeline_tab, chart_tab, progression_tab = st.tabs(
        ["Table", "Timeline", "Charts", "Injury Progression"]
    )
    with table_tab:
        render_table_view(filtered)
    with timeline_tab:
        render_timeline_view(filtered)
    with chart_tab:
        render_chart_view(filtered)
    with progression_tab:
        render_injury_progression_view(filtered)


if __name__ == "__main__":
    main()
