"""Interactive visual timeline for filtered medical chronology events."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
import streamlit as st

TIMELINE_COLOR_FIELDS = {
    "Record Type": "record_type",
    "Medicine Type": "medicine_type",
    "Facility": "facility",
    "Primary Provider": "primary_provider",
}

# Repeating vertical lanes stagger event cards while preserving one shared time axis.
LANE_HEIGHTS = (1.05, 1.85, 2.65, 3.45, 2.25, 3.05, 1.45, 3.85)


def _truncate(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _category_series(df: pd.DataFrame, field: str) -> pd.Series:
    values = df[field].fillna("").astype(str).str.strip()
    return values.mask(values.eq(""), "Unspecified")


def _card_indices(total: int, max_cards: int) -> set[int]:
    """Choose evenly distributed labels while leaving every event marker visible."""
    if max_cards <= 0:
        return set()
    if total <= max_cards:
        return set(range(total))
    if max_cards == 1:
        return {0}

    step = (total - 1) / (max_cards - 1)
    return {min(total - 1, round(i * step)) for i in range(max_cards)}


def _build_hover_text(row: pd.Series) -> str:
    parts = [
        f"<b>{row['event_id']}</b>",
        row["encounter_date"].strftime("%B %d, %Y"),
        f"<b>Record type:</b> {row['record_type'] or '—'}",
        f"<b>Medicine type:</b> {row['medicine_type'] or '—'}",
        f"<b>Provider:</b> {row['primary_provider'] or '—'}",
        f"<b>Facility:</b> {row['facility'] or '—'}",
    ]
    if row["body_parts"]:
        parts.append(f"<b>Body parts:</b> {row['body_parts']}")
    if row["summary"]:
        parts.append(f"<br>{_truncate(row['summary'], 420)}")
    return "<br>".join(parts)


def build_event_timeline_figure(
    df: pd.DataFrame,
    *,
    color_field: str,
    max_cards: int,
) -> go.Figure:
    """Create a stem-and-card chronology similar to a litigation medical timeline."""
    timeline = df.sort_values(["encounter_date", "event_id"], ascending=True).copy()
    timeline["category"] = _category_series(timeline, color_field)
    timeline["lane"] = [LANE_HEIGHTS[i % len(LANE_HEIGHTS)] for i in range(len(timeline))]
    timeline["hover_text"] = timeline.apply(_build_hover_text, axis=1)

    categories = list(dict.fromkeys(timeline["category"].tolist()))
    palette = qualitative.Plotly
    color_map = {category: palette[i % len(palette)] for i, category in enumerate(categories)}

    fig = go.Figure()

    # Event stems are drawn first so markers and cards remain visually dominant.
    for _, row in timeline.iterrows():
        fig.add_shape(
            type="line",
            x0=row["encounter_date"],
            x1=row["encounter_date"],
            y0=0,
            y1=row["lane"],
            line={"color": color_map[row["category"]], "width": 1.5},
            opacity=0.65,
            layer="below",
        )

    for category in categories:
        group = timeline[timeline["category"] == category]
        fig.add_trace(
            go.Scatter(
                x=group["encounter_date"],
                y=group["lane"],
                mode="markers",
                name=category,
                marker={
                    "size": 9,
                    "color": color_map[category],
                    "line": {"width": 1, "color": "white"},
                },
                text=group["hover_text"],
                hovertemplate="%{text}<extra></extra>",
            )
        )

    selected_cards = _card_indices(len(timeline), max_cards)
    for position, (_, row) in enumerate(timeline.iterrows()):
        if position not in selected_cards:
            continue

        provider = _truncate(row["primary_provider"], 34)
        summary = _truncate(row["summary"], 76)
        card_lines = [
            f"<b>{row['encounter_date'].strftime('%m/%d/%Y')} · {row['event_id']}</b>",
            _truncate(row["record_type"], 34),
        ]
        if provider:
            card_lines.append(provider)
        if summary:
            card_lines.append(summary)

        fig.add_annotation(
            x=row["encounter_date"],
            y=row["lane"],
            text="<br>".join(card_lines),
            showarrow=False,
            xanchor="center",
            yanchor="bottom",
            yshift=8,
            align="left",
            bgcolor="rgba(250,250,250,0.96)",
            bordercolor=color_map[row["category"]],
            borderwidth=1.5,
            borderpad=5,
            font={"size": 10, "color": "#202124"},
        )

    fig.add_hline(y=0, line_width=2, line_color="rgba(100,100,100,0.65)")

    max_lane = max(timeline["lane"], default=1.0)
    fig.update_layout(
        height=650,
        margin={"l": 20, "r": 20, "t": 20, "b": 35},
        hovermode="closest",
        dragmode="pan",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "title": None,
        },
        xaxis={
            "title": None,
            "showgrid": True,
            "rangeslider": {"visible": True, "thickness": 0.08},
            "rangeselector": {
                "buttons": [
                    {"count": 1, "label": "1m", "step": "month", "stepmode": "backward"},
                    {"count": 6, "label": "6m", "step": "month", "stepmode": "backward"},
                    {"count": 1, "label": "1y", "step": "year", "stepmode": "backward"},
                    {"step": "all", "label": "All"},
                ]
            },
        },
        yaxis={
            "visible": False,
            "range": [-0.12, max_lane + 0.8],
            "fixedrange": True,
        },
    )
    return fig


def _count_providers(series: pd.Series) -> int:
    providers: set[str] = set()
    for value in series.fillna("").astype(str):
        providers.update(part.strip() for part in value.split(";") if part.strip())
    return len(providers)


def render_event_timeline_chart(df: pd.DataFrame) -> None:
    """Render a visual event timeline using the current filtered event selection."""
    st.subheader("Event timeline")

    provider_count = _count_providers(df["primary_provider"])
    facility_count = df["facility"].replace("", pd.NA).dropna().nunique()
    st.caption(
        f"{len(df)} filtered event{'s' if len(df) != 1 else ''} · "
        f"{provider_count} provider{'s' if provider_count != 1 else ''} · "
        f"{facility_count} facilit{'ies' if facility_count != 1 else 'y'}"
    )

    control_1, control_2 = st.columns(2)
    with control_1:
        color_label = st.selectbox(
            "Color events by",
            options=list(TIMELINE_COLOR_FIELDS),
            index=0,
            key="event_timeline_color_field",
        )
    with control_2:
        show_cards = st.toggle(
            "Show event cards",
            value=True,
            help=(
                "Cards resemble the reference timeline. Every event remains available "
                "by hover even when cards are limited."
            ),
        )

    if show_cards:
        upper = min(40, max(1, len(df)))
        default = min(18, upper)
        if upper == 1:
            max_cards = 1
        else:
            max_cards = st.slider(
                "Maximum event cards",
                min_value=1,
                max_value=upper,
                value=default,
                help=(
                    "Limit visible cards to reduce overlap. All filtered event markers "
                    "are still plotted."
                ),
            )
    else:
        max_cards = 0

    color_field = TIMELINE_COLOR_FIELDS[color_label]
    fig = build_event_timeline_figure(
        df,
        color_field=color_field,
        max_cards=max_cards,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        theme="streamlit",
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )
    st.caption(
        "All currently filtered events are plotted. Hover a marker for the full event details; "
        "drag or use the range slider to inspect a narrower time period."
    )
