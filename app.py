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
    TREND_LABELS,
    available_body_parts,
    build_progression,
    extract_observations,
    marker_locations,
    render_progression_html,
)
from lost_income import render_lost_income_view
from summarizer import DEFAULT_MODEL, summarize_events

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
        help=(
            "Expected format: Caldwell medical chronology with Encounter Date, "
            "Provider, Facility, and related columns."
        ),
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
            st.session_state.pop("generated_summary", None)
            st.session_state.pop("generated_summary_event_ids", None)
            parse_uploaded_xlsx.clear()
            st.rerun()

    return True


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply sidebar filters and exact substring search."""
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
                lambda value: any(
                    provider in split_multi_value(value, ";") for provider in providers
                )
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
                lambda value: any(
                    part in split_multi_value(value, ",") for part in body_parts
                )
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
    """Render the filtered chronology as a table."""
    display = df.copy()
    display["encounter_date"] = display["encounter_date"].dt.strftime("%m/%d/%Y")
    display["summary_short"] = display["summary"].apply(
        lambda text: (
            text
            if len(text) <= SUMMARY_TRUNCATE
            else f"{text[:SUMMARY_TRUNCATE].rstrip()}…"
        )
    )

    table_df = display[
        [
            "event_id",
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
            "event_id": "Event ID",
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
    """Render events grouped by encounter date."""
    if df.empty:
        st.info("No events match the current filters.")
        return

    for event_date, group in df.groupby(df["encounter_date"].dt.date, sort=False):
        label = pd.Timestamp(event_date).strftime("%A, %B %d, %Y")
        count = len(group)
        suffix = "s" if count != 1 else ""
        with st.expander(f"{label} ({count} event{suffix})", expanded=False):
            for _, row in group.iterrows():
                st.markdown(
                    f"**{row['event_id']} · {row['record_type']}** · {row['medicine_type']}"
                )
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
        plot_df["period"] = plot_df["encounter_date"].dt.to_period("W").dt.start_time
    else:
        plot_df["period"] = plot_df["encounter_date"].dt.to_period("M").dt.start_time

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
            "Group dates by",
            options=["Day", "Week", "Month"],
            index=2,
        )

    chart_type = st.radio(
        "Chart type",
        options=["Line", "Bar"],
        horizontal=True,
    )

    if not selected_values:
        st.info("Select at least one value to plot.")
        return

    chart_data = build_event_plot_data(
        df,
        field,
        separator,
        selected_values,
        time_grouping,
    )
    if chart_data.empty or chart_data.to_numpy().sum() == 0:
        st.info("No events match the selected values and current sidebar filters.")
        return

    st.caption(f"{int(chart_data.to_numpy().sum())} plotted event-value occurrence(s)")
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


def render_injury_summary_chart(source_df: pd.DataFrame, scope_label: str) -> None:
    """Plot inferred injury severity over time for multiple body parts at once."""
    all_observations = extract_observations(source_df)
    if all_observations.empty:
        st.info("No body-part observations are available for the summary chart.")
        return

    snapshots, _ = build_progression(all_observations)
    if not snapshots:
        st.info("No sufficiently specific injury severity data are available for the summary chart.")
        return

    summary_df = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp(snapshot["date"]),
                "Body Part": str(snapshot["body_part"]).title(),
                "Severity": int(snapshot["severity"]),
                "Trend": TREND_LABELS.get(
                    str(snapshot["trend"]), str(snapshot["trend"]).title()
                ),
                "Medicine Type": str(snapshot.get("medicine_type", "")),
                "Event ID": str(snapshot.get("event_id", "")),
                "Carried Forward": bool(snapshot.get("carried_forward", False)),
            }
            for snapshot in snapshots
        ]
    ).sort_values(["Date", "Event ID"])

    # Multiple encounters can occur for the same body part on the same date. For the
    # line graph, use the last chronological state for that date while retaining the
    # complete event-level progression in the detailed view below.
    summary_df = (
        summary_df.groupby(["Date", "Body Part"], as_index=False, sort=True)
        .agg(
            Severity=("Severity", "last"),
            Trend=("Trend", "last"),
            **{
                "Medicine Types": (
                    "Medicine Type",
                    lambda values: ", ".join(
                        dict.fromkeys(value for value in values if value)
                    ),
                ),
                "Event IDs": (
                    "Event ID",
                    lambda values: ", ".join(
                        dict.fromkeys(value for value in values if value)
                    ),
                ),
                "Carried Forward": ("Carried Forward", "max"),
            },
        )
    )

    counts = summary_df["Body Part"].value_counts()
    body_options = counts.index.tolist()
    default_parts = body_options[: min(8, len(body_options))]
    selected_parts = st.multiselect(
        "Body parts to plot",
        options=body_options,
        default=default_parts,
        help=(
            "The most frequently documented body parts are shown by default. "
            "All medicine types are combined into each body-part progression."
        ),
        key=f"injury_summary_body_parts_{scope_label}",
    )

    if not selected_parts:
        st.info("Select at least one body part to plot.")
        return

    chart_df = summary_df[summary_df["Body Part"].isin(selected_parts)].copy()
    st.line_chart(
        chart_df[["Date", "Body Part", "Severity"]],
        x="Date",
        y="Severity",
        color="Body Part",
        height=440,
        use_container_width=True,
    )
    st.caption(
        "Severity scale: 0 = Resolved · 1 = Mild · 2 = Moderate · 3 = Severe. "
        "Each line combines the selected body part's encounters across all medicine types."
    )

    with st.expander("View summary progression data"):
        display = chart_df.sort_values(["Body Part", "Date"]).copy()
        display["Date"] = display["Date"].dt.strftime("%m/%d/%Y")
        display["Severity Label"] = display["Severity"].map(SEVERITY_LABELS)
        st.dataframe(
            display[
                [
                    "Date",
                    "Body Part",
                    "Severity",
                    "Severity Label",
                    "Trend",
                    "Medicine Types",
                    "Event IDs",
                    "Carried Forward",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


def render_injury_progression_view(
    full_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
) -> None:
    """Render conservative, source-linked injury severity and trend progression."""
    st.subheader("Injury progression")
    st.caption(
        "Severity and trend are inferred separately from body-specific text. "
        "The heuristic is intended for chronology review, not clinical diagnosis."
    )

    scope_label = st.radio(
        "Records to analyze",
        options=["Entire chronology", "Current filtered records"],
        index=0,
        horizontal=True,
        help=(
            "Use the entire chronology to avoid a text/provider filter silently removing "
            "later improvement or resolution records."
        ),
        key="progression_scope",
    )
    source_df = full_df if scope_label == "Entire chronology" else filtered_df
    if source_df.empty:
        st.info("No records are available in this analysis scope.")
        return

    body_options = available_body_parts(source_df)
    if not body_options:
        st.info("No body parts are available in this analysis scope.")
        return

    st.markdown("### Injury severity summary")
    st.caption(
        "This chart combines all medicine types and plots one severity line per body part over time."
    )
    render_injury_summary_chart(source_df, scope_label)
    st.divider()

    st.markdown("### Detailed body-part progression")
    body_part = st.selectbox(
        "Body part to display",
        options=body_options,
        format_func=lambda value: value.title(),
        key="progression_body_part",
    )

    all_observations = extract_observations(source_df, body_part=body_part)
    if all_observations.empty:
        st.info("No source events list this body part.")
        return

    medicine_options = sorted(
        value
        for value in all_observations["medicine_type"].dropna().astype(str).unique()
        if value
    )
    selected_medicine_types = st.multiselect(
        "Medicine types to include",
        options=medicine_options,
        default=medicine_options,
        help="All specialties are included by default so the progression spans the full care pathway.",
        key=f"progression_medicine_types_{body_part}",
    )
    if not selected_medicine_types:
        st.info("Select at least one medicine type to analyze.")
        return

    observations = all_observations[
        all_observations["medicine_type"].isin(selected_medicine_types)
    ].reset_index(drop=True)
    if observations.empty:
        st.info("No observations remain for the selected medicine types.")
        return

    if not marker_locations(body_part):
        st.warning(
            f"{body_part.title()} is not mapped to the built-in body outline. "
            "The evidence and progression table remain available, but no marker will be placed."
        )

    summary_cols = st.columns(3)
    summary_cols[0].metric("Source events", len(observations))
    summary_cols[1].metric(
        "Body-specific evidence",
        int(observations["context_specific"].sum()),
    )
    summary_cols[2].metric(
        "Low-confidence events",
        int((observations["confidence"] == "Low").sum()),
    )

    review = observations[
        [
            "event_id",
            "encounter_date",
            "medicine_type",
            "record_type",
            "primary_provider",
            "facility",
            "suggested_severity",
            "suggested_trend",
            "pain_score",
            "confidence",
            "matched_text",
            "reason",
            "pdf_url",
            "severity_override",
            "trend_override",
        ]
    ].copy()
    review["encounter_date"] = review["encounter_date"].dt.date
    review["suggested_severity"] = review["suggested_severity"].map(
        lambda value: "Unknown" if pd.isna(value) else SEVERITY_LABELS[int(value)]
    )
    review["suggested_trend"] = review["suggested_trend"].map(
        lambda value: TREND_LABELS.get(str(value), str(value).title())
    )
    review = review.rename(
        columns={
            "event_id": "Event ID",
            "encounter_date": "Date",
            "medicine_type": "Medicine Type",
            "record_type": "Record Type",
            "primary_provider": "Provider",
            "facility": "Facility",
            "suggested_severity": "Suggested Severity",
            "suggested_trend": "Suggested Trend",
            "pain_score": "Pain Score",
            "confidence": "Confidence",
            "matched_text": "Evidence",
            "reason": "Reason",
            "pdf_url": "PDF",
            "severity_override": "Severity Override",
            "trend_override": "Trend Override",
        }
    )

    with st.expander("Review and correct inferred progression", expanded=False):
        st.write(
            "Only body-specific sentences are used. A listed body part with no matching "
            "severity statement remains **Unknown** instead of inheriting language from another injury."
        )
        reviewed = st.data_editor(
            review,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "Event ID",
                "Date",
                "Medicine Type",
                "Record Type",
                "Provider",
                "Facility",
                "Suggested Severity",
                "Suggested Trend",
                "Pain Score",
                "Confidence",
                "Evidence",
                "Reason",
                "PDF",
            ],
            column_config={
                "PDF": st.column_config.LinkColumn("PDF", display_text="View PDF"),
                "Severity Override": st.column_config.SelectboxColumn(
                    "Severity Override",
                    options=[
                        "Auto",
                        "Mild",
                        "Moderate",
                        "Severe",
                        "Resolved",
                        "No severity update",
                    ],
                    required=True,
                ),
                "Trend Override": st.column_config.SelectboxColumn(
                    "Trend Override",
                    options=[
                        "Auto",
                        "New",
                        "Improving",
                        "Stable",
                        "Worsening",
                        "Resolved",
                        "Unknown",
                    ],
                    required=True,
                ),
            },
            key=(
                f"progression_review_{scope_label}_{body_part}_"
                f"{len(observations)}_{observations.iloc[0]['event_id']}_"
                f"{observations.iloc[-1]['event_id']}"
            ),
        )

    observations = observations.copy()
    observations["severity_override"] = reviewed["Severity Override"].tolist()
    observations["trend_override"] = reviewed["Trend Override"].tolist()
    snapshots, changes = build_progression(observations)
    if not snapshots:
        st.info(
            "No sufficiently specific severity progression could be established from these records. "
            "Review the evidence table or apply a manual override where appropriate."
        )
        return

    components.html(
        render_progression_html(snapshots),
        height=940,
        scrolling=True,
    )
    st.caption(
        "Color represents severity; arrows represent trend. Horizontal distance is proportional "
        "to elapsed time. Front and back anatomy are mapped separately, and each point is linked "
        "to its source event when a PDF URL is available."
    )

    with st.expander("View progression changes"):
        display_changes = changes.copy()
        display_changes["Date"] = display_changes["Date"].dt.strftime("%m/%d/%Y")
        st.dataframe(
            display_changes,
            use_container_width=True,
            hide_index=True,
            column_config={
                "PDF": st.column_config.LinkColumn("PDF", display_text="View PDF"),
            },
        )


def _huggingface_token() -> str:
    """Read the HF token, accepting the old secret location as a fallback."""
    try:
        huggingface = st.secrets.get("huggingface", {})
        token = str(huggingface.get("api_token", ""))
        if token:
            return token
        legacy = st.secrets.get("summarization", {})
        return str(legacy.get("api_token", ""))
    except FileNotFoundError:
        return ""


def _source_events_table(df: pd.DataFrame) -> pd.DataFrame:
    source_df = df[
        [
            "event_id",
            "encounter_date",
            "record_type",
            "primary_provider",
            "facility",
            "summary",
            "pdf_url",
        ]
    ].copy()
    source_df["encounter_date"] = source_df["encounter_date"].dt.strftime("%m/%d/%Y")
    return source_df.rename(
        columns={
            "event_id": "Event ID",
            "encounter_date": "Date",
            "record_type": "Record Type",
            "primary_provider": "Provider",
            "facility": "Facility",
            "summary": "Source narrative",
            "pdf_url": "PDF",
        }
    )


def render_summary_view(df: pd.DataFrame) -> None:
    """Summarize the currently filtered events with a serverless HF model."""
    st.subheader("Medical summary")
    st.caption(
        f"Summarize the {len(df)} events currently selected by the sidebar filters "
        f"using `{DEFAULT_MODEL}` on Hugging Face Inference."
    )
    st.info(
        "This is a demo summarizer. The generated text may omit or misstate details; "
        "verify it against the source events below."
    )

    api_token = _huggingface_token()
    if not api_token:
        st.warning(
            "Summarization is not configured. Add your Hugging Face token to "
            "Streamlit secrets as `[huggingface] api_token = \"hf_...\"`."
        )
        return

    if len(df) > 50:
        st.caption(
            "Large selections require multiple summarization requests. For a faster demo, "
            "use the sidebar filters to narrow the chronology first."
        )

    event_ids = tuple(sorted(df["event_id"].astype(str)))
    if st.button("Generate summary", type="primary"):
        try:
            with st.spinner("Generating medical summary..."):
                st.session_state["generated_summary"] = summarize_events(
                    df,
                    api_token=api_token,
                )
                st.session_state["generated_summary_event_ids"] = event_ids
        except Exception as exc:
            st.error(f"Summary generation failed: {exc}")

    summary = st.session_state.get("generated_summary")
    summary_event_ids = st.session_state.get("generated_summary_event_ids")
    if summary and summary_event_ids == event_ids:
        st.markdown(summary)
        st.download_button(
            "Download summary",
            data=summary.encode("utf-8"),
            file_name="medical_summary.txt",
            mime="text/plain",
        )
    elif summary:
        st.info("The filters changed. Generate a new summary for the current event selection.")

    with st.expander("Source events used for summarization"):
        st.dataframe(
            _source_events_table(df),
            use_container_width=True,
            hide_index=True,
            column_config={
                "PDF": st.column_config.LinkColumn("View PDF", display_text="View PDF"),
            },
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

    table_tab, timeline_tab, chart_tab, progression_tab, summary_tab, lost_income_tab = st.tabs(
        ["Table", "Timeline", "Charts", "Injury Progression", "Summary", "Lost Income"]
    )
    with table_tab:
        render_table_view(filtered)
    with timeline_tab:
        render_timeline_view(filtered)
    with chart_tab:
        render_chart_view(filtered)
    with progression_tab:
        render_injury_progression_view(df, filtered)
    with summary_tab:
        render_summary_view(filtered)
    with lost_income_tab:
        render_lost_income_view()


if __name__ == "__main__":
    main()
