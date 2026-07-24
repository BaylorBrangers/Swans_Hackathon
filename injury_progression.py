"""Infer and visualize injury progression from medical chronology events."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from data_loader import split_multi_value

SEVERITY_LABELS = {1: "Injury", 2: "Worsening injury", 3: "Severe injury"}
SEVERITY_COLORS = {1: "#facc15", 2: "#f97316", 3: "#dc2626"}

# Coordinates are percentages of the supplied front-facing body outline.
# Unspecified paired body parts are marked on both sides.
BODY_COORDINATES: dict[str, list[tuple[float, float]]] = {
    "head": [(50, 8)],
    "face": [(50, 11)],
    "neck": [(50, 18)],
    "shoulder": [(34, 25), (66, 25)],
    "chest": [(50, 31)],
    "rib": [(50, 35)],
    "upper back": [(50, 32)],
    "back": [(50, 42)],
    "lower back": [(50, 48)],
    "abdomen": [(50, 42)],
    "pelvis": [(50, 51)],
    "hip": [(40, 51), (60, 51)],
    "arm": [(24, 37), (76, 37)],
    "upper arm": [(28, 32), (72, 32)],
    "elbow": [(20, 43), (80, 43)],
    "forearm": [(18, 48), (82, 48)],
    "wrist": [(15, 53), (85, 53)],
    "hand": [(12, 57), (88, 57)],
    "finger": [(9, 59), (91, 59)],
    "thigh": [(42, 61), (58, 61)],
    "knee": [(42, 72), (58, 72)],
    "leg": [(42, 81), (58, 81)],
    "calf": [(42, 82), (58, 82)],
    "shin": [(43, 82), (57, 82)],
    "ankle": [(43, 91), (57, 91)],
    "foot": [(42, 96), (58, 96)],
}

LEFT_COORDINATES = {
    part: [coords[-1]] for part, coords in BODY_COORDINATES.items() if len(coords) == 2
}
RIGHT_COORDINATES = {
    part: [coords[0]] for part, coords in BODY_COORDINATES.items() if len(coords) == 2
}

BODY_ALIASES: dict[str, tuple[str, ...]] = {
    "head": ("head", "headache", "cephalgia", "skull", "cranial"),
    "face": ("face", "facial", "jaw", "mandible"),
    "neck": ("neck", "cervical", "c-spine"),
    "shoulder": ("shoulder", "rotator cuff", "glenohumeral"),
    "chest": ("chest", "sternum", "thorax", "thoracic"),
    "rib": ("rib", "ribs", "costal"),
    "upper back": ("upper back", "thoracic spine", "t-spine"),
    "lower back": ("lower back", "low back", "lumbar", "l-spine"),
    "back": ("back", "spine", "spinal"),
    "abdomen": ("abdomen", "abdominal", "stomach"),
    "pelvis": ("pelvis", "pelvic", "sacrum", "sacral"),
    "hip": ("hip", "acetabulum"),
    "upper arm": ("upper arm", "humerus"),
    "forearm": ("forearm", "radius", "ulna"),
    "arm": ("arm",),
    "elbow": ("elbow",),
    "wrist": ("wrist", "carpal"),
    "hand": ("hand", "palm"),
    "finger": ("finger", "fingers", "thumb", "digit"),
    "thigh": ("thigh", "femur"),
    "knee": ("knee", "patella"),
    "calf": ("calf",),
    "shin": ("shin", "tibia", "fibula"),
    "leg": ("leg",),
    "ankle": ("ankle",),
    "foot": ("foot", "feet", "heel", "toe", "toes"),
}

ALIAS_TO_BODY = {
    alias: body for body, aliases in BODY_ALIASES.items() for alias in aliases
}

RESOLVED_PATTERNS = (
    (r"\bresolved?\b", "resolved"),
    (r"\basymptomatic\b", "asymptomatic"),
    (r"\bpain[- ]free\b", "pain-free"),
    (r"\bno longer (?:has|having|reports?|experiences?)\b", "no longer reported"),
    (r"\bdenies (?:any )?(?:pain|symptoms?)\b", "denies pain or symptoms"),
)
IMPROVING_PATTERNS = (
    (r"\bimprov(?:e[sd]?|ing|ement)\b", "improving"),
    (r"\b(?:pain|symptoms?) (?:has |have )?decreased\b", "decreased symptoms"),
    (r"\bfeels? better\b", "feels better"),
    (r"\bresolving\b", "resolving"),
)
SEVERE_PATTERNS = (
    (r"\b(?:9|10)(?:\.\d+)?\s*(?:/|out of)\s*10\b", "pain score 9–10/10"),
    (r"\bsevere(?:ly)?\b", "severe"),
    (r"\bexcruciating\b", "excruciating"),
    (r"\bintractable\b", "intractable"),
    (r"\bmarked(?:ly)?\b", "marked"),
    (r"\bfracture[sd]?\b", "fracture"),
    (r"\bdislocat(?:e[sd]?|ion)\b", "dislocation"),
    (r"\bruptur(?:e[sd]?|ing)\b", "rupture"),
    (r"\bneurologic(?:al)? deficit\b", "neurological deficit"),
    (r"\bloss of function\b", "loss of function"),
)
WORSENING_PATTERNS = (
    (r"\b(?:6|7|8)(?:\.\d+)?\s*(?:/|out of)\s*10\b", "pain score 6–8/10"),
    (r"\bwors(?:e|ened|ening)\b", "worsening"),
    (r"\bincreas(?:e[sd]?|ing)\b", "increased"),
    (r"\baggravat(?:e[sd]?|ing|ion)\b", "aggravated"),
    (r"\bprogressive(?:ly)?\b", "progressive"),
    (r"\bpersistent(?:ly)?\b", "persistent"),
    (
        r"\b(?:reduced|decreased|limited) range of motion\b",
        "reduced range of motion",
    ),
    (r"\bswelling\b", "swelling"),
)
INJURY_PATTERNS = (
    (r"\b[1-5](?:\.\d+)?\s*(?:/|out of)\s*10\b", "pain score 1–5/10"),
    (r"\bpain(?:ful)?\b", "pain"),
    (r"\btender(?:ness)?\b", "tenderness"),
    (r"\bsore(?:ness)?\b", "soreness"),
    (r"\bsprain(?:ed)?\b", "sprain"),
    (r"\bstrain(?:ed)?\b", "strain"),
    (r"\bbruis(?:e[sd]?|ing)\b", "bruising"),
    (r"\bcontusion\b", "contusion"),
)

DEFAULT_BODY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 374 568">
<rect width="374" height="568" fill="white"/>
<g fill="white" stroke="#171717" stroke-width="3.2" stroke-linejoin="round">
<path d="M187 7 C170 7 163 20 163 36 C163 46 166 58 173 65 L172 83
C165 91 147 94 130 101 C108 110 101 128 104 150 L99 179
C94 199 88 218 90 240 L85 267 L75 278 C70 286 75 289 80 284
L75 301 C73 309 80 311 83 304 L88 289 L84 307 C82 315 90 317 93 309
L98 291 L94 309 C93 317 101 318 104 311 L109 291 L107 305
C106 312 114 313 117 306 L123 283 C126 273 124 262 122 253
L130 219 L135 193 L142 172 L148 197 L145 226 L148 252
L139 310 C136 333 137 353 143 373 L145 402 L154 447 L151 482
L144 513 L136 543 C133 553 146 558 162 555 L174 539 L176 513
L171 491 L177 457 L181 425 L176 399 L181 368 L183 287
L191 287 L193 368 L198 399 L193 425 L197 457 L203 491 L198 513
L200 539 L212 555 C228 558 241 553 238 543 L230 513 L223 482
L220 447 L229 402 L231 373 C237 353 238 333 235 310 L226 252
L229 226 L226 197 L232 172 L239 193 L244 219 L252 253
C250 262 248 273 251 283 L257 306 C260 313 268 312 267 305 L265 291
L270 311 C273 318 281 317 280 309 L276 291 L281 309
C284 317 292 315 290 307 L286 289 L291 304 C294 311 301 309 299 301
L294 284 C299 289 304 286 299 278 L289 267 L284 240
C286 218 280 199 275 179 L270 150 C273 128 266 110 244 101
C227 94 209 91 202 83 L201 65 C208 58 211 46 211 36
C211 20 204 7 187 7 Z"/>
</g></svg>"""


@dataclass(frozen=True)
class Inference:
    action: str
    suggested_level: int
    reason: str
    matched_text: str
    context_specific: bool


def canonical_body_part(raw_part: str) -> str:
    """Normalize a body-part value while preserving documented laterality."""
    value = re.sub(r"\s+", " ", str(raw_part).strip().lower())
    side = ""
    if re.search(r"\bleft\b", value):
        side = "left"
    elif re.search(r"\bright\b", value):
        side = "right"
    value = re.sub(r"\b(?:left|right|bilateral)\b", "", value).strip(" -")

    if value in BODY_COORDINATES:
        body = value
    else:
        body = next(
            (
                canonical
                for alias, canonical in sorted(
                    ALIAS_TO_BODY.items(), key=lambda item: len(item[0]), reverse=True
                )
                if re.search(rf"\b{re.escape(alias)}\b", value)
            ),
            value,
        )
    return f"{side} {body}".strip()


def marker_coordinates(body_part: str) -> list[tuple[float, float]]:
    """Return normalized marker coordinates for a canonical body part."""
    canonical = canonical_body_part(body_part)
    side = ""
    base = canonical
    if canonical.startswith("left "):
        side, base = "left", canonical[5:]
    elif canonical.startswith("right "):
        side, base = "right", canonical[6:]

    if side == "left" and base in LEFT_COORDINATES:
        return LEFT_COORDINATES[base]
    if side == "right" and base in RIGHT_COORDINATES:
        return RIGHT_COORDINATES[base]
    return BODY_COORDINATES.get(base, [(50, 40)])


def _relevant_context(summary: str, body_part: str) -> tuple[str, bool]:
    """Prefer sentences that mention the current body part or a synonym."""
    canonical = canonical_body_part(body_part)
    base = re.sub(r"^(?:left|right) ", "", canonical)
    aliases = BODY_ALIASES.get(base, (base,))
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?;])\s+", str(summary))
        if sentence.strip()
    ]
    matching = [
        sentence
        for sentence in sentences
        if any(re.search(rf"\b{re.escape(alias)}\b", sentence, re.I) for alias in aliases)
    ]
    return (" ".join(matching), True) if matching else (str(summary), False)


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 70) : start]
    after = text[end : min(len(text), end + 40)]
    before_negation = re.search(
        r"\b(?:no|not|without|denies|denied|negative for|absence of)"
        r"(?:\W+\w+){0,5}\W*$",
        before,
        re.I,
    )
    after_negation = re.search(
        r"^\W*(?:was |were |is |are )?(?:ruled out|not seen|not present|negative)",
        after,
        re.I,
    )
    return bool(before_negation or after_negation)


def _match_pattern(
    text: str, patterns: tuple[tuple[str, str], ...], allow_negated: bool = False
) -> tuple[str, str] | None:
    for pattern, reason in patterns:
        for match in re.finditer(pattern, text, re.I):
            if allow_negated or not _is_negated(text, match.start(), match.end()):
                return reason, match.group(0)
    return None


def infer_severity(summary: str, body_part: str) -> Inference:
    """Infer a status action for one body part from clinical summary text."""
    context, is_specific = _relevant_context(summary, body_part)

    match = _match_pattern(context, RESOLVED_PATTERNS, allow_negated=True)
    if match:
        return Inference("resolved", 0, match[0], match[1], is_specific)

    match = _match_pattern(context, IMPROVING_PATTERNS)
    if match:
        return Inference("improving", 1, match[0], match[1], is_specific)

    match = _match_pattern(context, SEVERE_PATTERNS)
    if match:
        return Inference("severe", 3, match[0], match[1], is_specific)

    match = _match_pattern(context, WORSENING_PATTERNS)
    if match:
        return Inference("worsening", 2, match[0], match[1], is_specific)

    match = _match_pattern(context, INJURY_PATTERNS)
    if match:
        return Inference("injury", 1, match[0], match[1], is_specific)

    return Inference(
        "injury",
        1,
        "body part listed; no explicit severity phrase found",
        "",
        is_specific,
    )


def extract_observations(
    df: pd.DataFrame, medicine_type: str
) -> pd.DataFrame:
    """Create one auditable severity observation per event and body part."""
    selected = df[df["medicine_type"] == medicine_type].sort_values(
        "encounter_date", ascending=True
    )
    observations: list[dict[str, Any]] = []
    for event_order, (_, row) in enumerate(selected.iterrows()):
        for raw_part in split_multi_value(str(row["body_parts"]), ","):
            body_part = canonical_body_part(raw_part)
            inference = infer_severity(str(row["summary"]), body_part)
            observations.append(
                {
                    "event_order": event_order,
                    "encounter_date": pd.Timestamp(row["encounter_date"]),
                    "body_part": body_part,
                    "suggested_action": inference.action,
                    "suggested_level": inference.suggested_level,
                    "reason": inference.reason,
                    "matched_text": inference.matched_text,
                    "context_specific": inference.context_specific,
                    "summary": str(row["summary"]),
                    "override": "Auto",
                }
            )
    return pd.DataFrame(observations)


def _next_level(current: int, action: str) -> int:
    if action == "resolved":
        return 0
    if action == "severe":
        return 3
    if action == "worsening":
        return max(current, 2)
    if action == "improving":
        return max(1, current - 1) if current else 1
    return current or 1


def build_progression(observations: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Apply inferred actions and overrides to produce changed-state snapshots."""
    if observations.empty:
        return [], pd.DataFrame()

    current: dict[str, dict[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []

    ordered = observations.sort_values(["encounter_date", "event_order"])
    for event_date, date_group in ordered.groupby("encounter_date", sort=True):
        date_changes: list[dict[str, Any]] = []
        for _, observation in date_group.iterrows():
            body_part = str(observation["body_part"])
            old_level = int(current.get(body_part, {}).get("level", 0))
            override = str(observation.get("override", "Auto"))
            if override == "Resolved":
                new_level, action = 0, "resolved"
            elif override in ("Injury", "Worsening injury", "Severe injury"):
                new_level = {"Injury": 1, "Worsening injury": 2, "Severe injury": 3}[override]
                action = "manual override"
            else:
                action = str(observation["suggested_action"])
                new_level = _next_level(old_level, action)

            if new_level == old_level:
                continue

            reason = (
                f"Manual override: {override}"
                if override != "Auto"
                else str(observation["reason"])
            )
            if new_level == 0:
                current.pop(body_part, None)
                status = "Resolved"
            else:
                current[body_part] = {
                    "level": new_level,
                    "reason": reason,
                    "date": pd.Timestamp(event_date),
                }
                status = SEVERITY_LABELS[new_level]

            change = {
                "Date": pd.Timestamp(event_date),
                "Body Part": body_part.title(),
                "Previous Status": SEVERITY_LABELS.get(old_level, "Not shown"),
                "New Status": status,
                "Reason": reason,
                "Matched Text": str(observation.get("matched_text", "")),
            }
            date_changes.append(change)
            change_rows.append(change)

        if date_changes:
            snapshots.append(
                {
                    "date": pd.Timestamp(event_date),
                    "statuses": {
                        body_part: details.copy()
                        for body_part, details in current.items()
                    },
                    "changes": date_changes,
                }
            )

    return snapshots, pd.DataFrame(change_rows)


def _image_data_uri(image_bytes: bytes | None, mime_type: str | None) -> str:
    if image_bytes:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        mime = mime_type if mime_type in ("image/png", "image/jpeg") else "image/png"
        return f"data:{mime};base64,{encoded}"
    encoded = base64.b64encode(DEFAULT_BODY_SVG.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def render_progression_html(
    snapshots: list[dict[str, Any]],
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> str:
    """Render progression snapshots as a horizontally scrollable HTML timeline."""
    image_uri = _image_data_uri(image_bytes, mime_type)
    cards: list[str] = []
    for snapshot in snapshots:
        markers: list[str] = []
        for body_part, status in snapshot["statuses"].items():
            level = int(status["level"])
            color = SEVERITY_COLORS[level]
            tooltip = html.escape(
                f"{body_part.title()}: {SEVERITY_LABELS[level]} — {status['reason']}",
                quote=True,
            )
            for x_coord, y_coord in marker_coordinates(body_part):
                markers.append(
                    f'<span class="marker level-{level}" style="left:{x_coord}%;'
                    f'top:{y_coord}%;background:{color}" title="{tooltip}"></span>'
                )

        date_label = pd.Timestamp(snapshot["date"]).strftime("%b %d, %Y")
        change_count = len(snapshot["changes"])
        cards.append(
            '<div class="timepoint">'
            '<div class="body-frame">'
            f'<img src="{image_uri}" alt="Body outline"/>'
            f'{"".join(markers)}'
            "</div>"
            f'<div class="date">{html.escape(date_label)}</div>'
            f'<div class="change-count">{change_count} change{"s" if change_count != 1 else ""}</div>'
            '<div class="tick"></div>'
            "</div>"
        )

    return f"""<!doctype html>
<html><head><style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #1f2937; font-family: Arial, sans-serif; }}
.legend {{ display:flex; gap:18px; align-items:center; margin:4px 6px 14px; font-size:13px; }}
.legend-item {{ display:flex; align-items:center; gap:6px; }}
.swatch {{ width:13px; height:13px; border-radius:50%; border:1px solid rgba(0,0,0,.25); }}
.scroll {{ overflow-x:auto; padding:4px 8px 22px; }}
.timeline {{ display:flex; align-items:flex-end; min-width:max-content; position:relative; padding-bottom:20px; }}
.timeline::after {{ content:""; position:absolute; left:0; right:0; bottom:17px; height:3px; background:#64748b; z-index:0; }}
.timepoint {{ width:185px; flex:0 0 185px; text-align:center; position:relative; padding:0 10px 21px; }}
.body-frame {{ width:145px; height:220px; margin:0 auto 7px; position:relative; }}
.body-frame img {{ width:100%; height:100%; object-fit:contain; display:block; }}
.marker {{ position:absolute; width:15px; height:15px; border-radius:50%; transform:translate(-50%,-50%);
  border:2px solid rgba(255,255,255,.95); box-shadow:0 0 0 1px rgba(0,0,0,.5), 0 1px 4px rgba(0,0,0,.35); cursor:help; }}
.date {{ font-size:13px; font-weight:700; white-space:nowrap; }}
.change-count {{ font-size:11px; color:#64748b; margin-top:2px; }}
.tick {{ position:absolute; bottom:10px; left:50%; width:3px; height:15px; background:#334155; z-index:1; }}
</style></head><body>
<div class="legend">
  <strong>Severity:</strong>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[1]}"></span>Injury</span>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[2]}"></span>Worsening</span>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[3]}"></span>Severe</span>
</div>
<div class="scroll"><div class="timeline">{"".join(cards)}</div></div>
</body></html>"""
