"""Infer and visualize auditable injury progression from medical chronology events."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from data_loader import split_multi_value

SEVERITY_LABELS = {0: "Resolved", 1: "Mild", 2: "Moderate", 3: "Severe"}
SEVERITY_COLORS = {0: "#16a34a", 1: "#facc15", 2: "#f97316", 3: "#dc2626"}
TREND_LABELS = {
    "new": "New",
    "improving": "Improving",
    "stable": "Stable",
    "worsening": "Worsening",
    "resolved": "Resolved",
    "unknown": "Unknown",
}
TREND_SYMBOLS = {
    "new": "+",
    "improving": "↓",
    "stable": "→",
    "worsening": "↑",
    "resolved": "✓",
    "unknown": "?",
}


@dataclass(frozen=True)
class BodyLocation:
    view: str
    x: float
    y: float


@dataclass(frozen=True)
class Inference:
    severity: int | None
    trend_hint: str
    pain_score: float | None
    reason: str
    matched_text: str
    context_specific: bool
    confidence: str
    severity_basis: str


BODY_COORDINATES: dict[str, list[BodyLocation]] = {
    "head": [BodyLocation("front", 50, 8)],
    "face": [BodyLocation("front", 50, 12)],
    "neck": [BodyLocation("front", 50, 18)],
    "shoulder": [BodyLocation("front", 34, 25), BodyLocation("front", 66, 25)],
    "chest": [BodyLocation("front", 50, 32)],
    "rib": [BodyLocation("front", 50, 36)],
    "abdomen": [BodyLocation("front", 50, 43)],
    "pelvis": [BodyLocation("front", 50, 51)],
    "hip": [BodyLocation("front", 40, 52), BodyLocation("front", 60, 52)],
    "upper arm": [BodyLocation("front", 28, 33), BodyLocation("front", 72, 33)],
    "arm": [BodyLocation("front", 24, 38), BodyLocation("front", 76, 38)],
    "elbow": [BodyLocation("front", 20, 43), BodyLocation("front", 80, 43)],
    "forearm": [BodyLocation("front", 18, 49), BodyLocation("front", 82, 49)],
    "wrist": [BodyLocation("front", 15, 54), BodyLocation("front", 85, 54)],
    "hand": [BodyLocation("front", 12, 58), BodyLocation("front", 88, 58)],
    "finger": [BodyLocation("front", 9, 60), BodyLocation("front", 91, 60)],
    "thigh": [BodyLocation("front", 42, 62), BodyLocation("front", 58, 62)],
    "knee": [BodyLocation("front", 42, 72), BodyLocation("front", 58, 72)],
    "leg": [BodyLocation("front", 42, 82), BodyLocation("front", 58, 82)],
    "calf": [BodyLocation("back", 42, 82), BodyLocation("back", 58, 82)],
    "shin": [BodyLocation("front", 43, 82), BodyLocation("front", 57, 82)],
    "ankle": [BodyLocation("front", 43, 91), BodyLocation("front", 57, 91)],
    "foot": [BodyLocation("front", 42, 96), BodyLocation("front", 58, 96)],
    "upper back": [BodyLocation("back", 50, 32)],
    "back": [BodyLocation("back", 50, 41)],
    "lower back": [BodyLocation("back", 50, 48)],
    "scapula": [BodyLocation("back", 38, 31), BodyLocation("back", 62, 31)],
    "sacrum": [BodyLocation("back", 50, 53)],
    "buttock": [BodyLocation("back", 42, 55), BodyLocation("back", 58, 55)],
    "achilles": [BodyLocation("back", 43, 91), BodyLocation("back", 57, 91)],
}

BODY_ALIASES: dict[str, tuple[str, ...]] = {
    "head": ("head", "headache", "cephalgia", "skull", "cranial"),
    "face": ("face", "facial", "jaw", "mandible", "tmj"),
    "neck": ("neck", "cervical spine", "cervical", "c-spine", "c spine"),
    "shoulder": ("shoulder", "shoulders", "rotator cuff", "glenohumeral"),
    "chest": ("chest", "sternum", "thorax"),
    "rib": ("rib", "ribs", "costal"),
    "upper back": ("upper back", "thoracic spine", "thoracic back", "t-spine", "t spine", "trapezius"),
    "lower back": ("lower back", "low back", "lumbar spine", "lumbar", "l-spine", "l spine"),
    "back": ("back",),
    "abdomen": ("abdomen", "abdominal", "stomach"),
    "pelvis": ("pelvis", "pelvic"),
    "sacrum": ("sacrum", "sacral", "sacroiliac", "si joint", "s-i joint", "coccyx", "coccygeal"),
    "scapula": ("scapula", "scapular", "shoulder blade"),
    "buttock": ("buttock", "buttocks", "gluteal", "glute"),
    "hip": ("hip", "hips", "acetabulum", "acetabular"),
    "upper arm": ("upper arm", "humerus", "humeral"),
    "forearm": ("forearm", "radius", "radial", "ulna", "ulnar"),
    "arm": ("arm", "arms"),
    "elbow": ("elbow", "elbows"),
    "wrist": ("wrist", "wrists", "carpal"),
    "hand": ("hand", "hands", "palm"),
    "finger": ("finger", "fingers", "thumb", "digit", "digits"),
    "thigh": ("thigh", "thighs", "femur", "femoral"),
    "knee": ("knee", "knees", "patella", "patellar"),
    "calf": ("calf", "calves"),
    "shin": ("shin", "shins", "tibia", "tibial", "fibula", "fibular"),
    "leg": ("leg", "legs"),
    "ankle": ("ankle", "ankles"),
    "foot": ("foot", "feet", "heel", "toe", "toes"),
    "achilles": ("achilles", "achilles tendon"),
}
ALIAS_TO_BODY = {alias: body for body, aliases in BODY_ALIASES.items() for alias in aliases}
SORTED_ALIASES = sorted(ALIAS_TO_BODY.items(), key=lambda item: len(item[0]), reverse=True)

RESOLVED_PATTERNS = (
    (r"\bresolved?\b", "resolved"),
    (r"\basymptomatic\b", "asymptomatic"),
    (r"\bpain[- ]free\b", "pain-free"),
    (r"\b(?:0|0\.0)\s*(?:/|out of)\s*10\b", "pain score 0/10"),
    (r"\bno longer (?:has|having|reports?|experiences?)\b", "no longer reported"),
    (r"\bdenies (?:any )?(?:pain|symptoms?)\b", "denies pain or symptoms"),
)
IMPROVING_PATTERNS = (
    (r"\bimprov(?:e[sd]?|ing|ement)\b", "improving"),
    (r"\b(?:pain|symptoms?) (?:has |have )?decreased\b", "decreased symptoms"),
    (r"\bfeels? better\b", "feels better"),
    (r"\bresolving\b", "resolving"),
)
WORSENING_PATTERNS = (
    (r"\bwors(?:e|ened|ening)\b", "worsening"),
    (r"\bincreas(?:e[sd]?|ing)\b", "increased"),
    (r"\baggravat(?:e[sd]?|ing|ion)\b", "aggravated"),
    (r"\bprogressive(?:ly)?\b", "progressive"),
)
STABLE_PATTERNS = (
    (r"\bunchanged\b", "unchanged"),
    (r"\bstable\b", "stable"),
    (r"\bno (?:significant )?change\b", "no significant change"),
)
SEVERE_PATTERNS = (
    (r"\bsevere(?:ly)?\b", "severe", "descriptor"),
    (r"\bexcruciating\b", "excruciating", "descriptor"),
    (r"\bintractable\b", "intractable", "descriptor"),
    (r"\bfracture[sd]?\b", "fracture", "structural"),
    (r"\bdislocat(?:e[sd]?|ion)\b", "dislocation", "structural"),
    (r"\bruptur(?:e[sd]?|ing)\b", "rupture", "structural"),
    (r"\bneurologic(?:al)? deficit\b", "neurological deficit", "structural"),
    (r"\bloss of function\b", "loss of function", "structural"),
)
MODERATE_PATTERNS = (
    (r"\bmoderate(?:ly)?\b", "moderate", "descriptor"),
    (r"\bmarked(?:ly)?\b", "marked", "descriptor"),
    (r"\b(?:reduced|decreased|limited) range of motion\b", "limited range of motion", "functional"),
    (r"\bswelling\b", "swelling", "functional"),
    (r"\bweakness\b", "weakness", "functional"),
    (r"\bpersistent(?:ly)?\b", "persistent symptoms", "functional"),
)
MILD_PATTERNS = (
    (r"\bmild(?:ly)?\b", "mild", "descriptor"),
    (r"\bpain(?:ful)?\b", "pain", "generic_symptom"),
    (r"\btender(?:ness)?\b", "tenderness", "generic_symptom"),
    (r"\bsore(?:ness)?\b", "soreness", "generic_symptom"),
    (r"\bsprain(?:ed)?\b", "sprain", "generic_symptom"),
    (r"\bstrain(?:ed)?\b", "strain", "generic_symptom"),
    (r"\bbruis(?:e[sd]?|ing)\b", "bruising", "generic_symptom"),
    (r"\bcontusion\b", "contusion", "generic_symptom"),
)
PAIN_SCORE_RE = re.compile(r"\b(10(?:\.0+)?|[0-9](?:\.\d+)?)\s*(?:/|out of)\s*10\b", re.I)

BODY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 374 568">
<rect width="374" height="568" fill="white"/>
<g fill="white" stroke="#171717" stroke-width="3.2" stroke-linejoin="round">
<path d="M187 7 C170 7 163 20 163 36 C163 46 166 58 173 65 L172 83 C165 91 147 94 130 101 C108 110 101 128 104 150 L99 179 C94 199 88 218 90 240 L85 267 L75 278 C70 286 75 289 80 284 L75 301 C73 309 80 311 83 304 L88 289 L84 307 C82 315 90 317 93 309 L98 291 L94 309 C93 317 101 318 104 311 L109 291 L107 305 C106 312 114 313 117 306 L123 283 C126 273 124 262 122 253 L130 219 L135 193 L142 172 L148 197 L145 226 L148 252 L139 310 C136 333 137 353 143 373 L145 402 L154 447 L151 482 L144 513 L136 543 C133 553 146 558 162 555 L174 539 L176 513 L171 491 L177 457 L181 425 L176 399 L181 368 L183 287 L191 287 L193 368 L198 399 L193 425 L197 457 L203 491 L198 513 L200 539 L212 555 C228 558 241 553 238 543 L230 513 L223 482 L220 447 L229 402 L231 373 C237 353 238 333 235 310 L226 252 L229 226 L226 197 L232 172 L239 193 L244 219 L252 253 C250 262 248 273 251 283 L257 306 C260 313 268 312 267 305 L265 291 L270 311 C273 318 281 317 280 309 L276 291 L281 309 C284 317 292 315 290 307 L286 289 L291 304 C294 311 301 309 299 301 L294 284 C299 289 304 286 299 278 L289 267 L284 240 C286 218 280 199 275 179 L270 150 C273 128 266 110 244 101 C227 94 209 91 202 83 L201 65 C208 58 211 46 211 36 C211 20 204 7 187 7 Z"/>
</g></svg>"""


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_side(value: str) -> tuple[str, str]:
    """Extract left/right notation without treating 'L spine' as left-sided anatomy."""
    text = _normalize_spaces(value.lower())
    side = ""
    left_prefix = re.search(r"^(?:l|lt)\s+(?!(?:spine|spinal)\b)(?=[a-z])", text)
    right_prefix = re.search(r"^(?:r|rt)\s+(?!(?:spine|spinal)\b)(?=[a-z])", text)
    if re.search(r"\bleft\b|\blt\.?\b", text) or left_prefix:
        side = "left"
    elif re.search(r"\bright\b|\brt\.?\b", text) or right_prefix:
        side = "right"
    text = re.sub(r"\b(?:left|right|bilateral|lt\.?|rt\.?)\b", " ", text)
    if side:
        text = re.sub(r"^(?:l|r)\s+(?!(?:spine|spinal)\b)(?=[a-z])", "", text)
    return side, _normalize_spaces(text.strip(" -"))


def canonical_body_part(raw_part: str) -> str:
    side, value = _extract_side(str(raw_part))
    body = next(
        (canonical for alias, canonical in SORTED_ALIASES if re.search(rf"\b{re.escape(alias)}\b", value, re.I)),
        value,
    )
    return f"{side} {body}".strip()


def available_body_parts(df: pd.DataFrame) -> list[str]:
    parts: set[str] = set()
    if "body_parts" not in df.columns:
        return []
    for value in df["body_parts"].fillna("").astype(str):
        for raw_part in split_multi_value(value, ","):
            canonical = canonical_body_part(raw_part)
            if canonical:
                parts.add(canonical)
    return sorted(parts)


def marker_locations(body_part: str) -> list[BodyLocation]:
    canonical = canonical_body_part(body_part)
    side = ""
    base = canonical
    if canonical.startswith("left "):
        side, base = "left", canonical[5:]
    elif canonical.startswith("right "):
        side, base = "right", canonical[6:]
    locations = BODY_COORDINATES.get(base, [])
    if not side or len(locations) <= 1:
        return locations
    location_view = locations[0].view
    if side == "left":
        chooser = max if location_view == "front" else min
    else:
        chooser = min if location_view == "front" else max
    return [chooser(locations, key=lambda location: location.x)]


def marker_coordinates(body_part: str) -> list[tuple[float, float]]:
    return [(location.x, location.y) for location in marker_locations(body_part)]


def _sentence_mentions_side(sentence: str, side: str) -> bool:
    pattern = r"\bleft\b|\blt\.?\b" if side == "left" else r"\bright\b|\brt\.?\b"
    return bool(re.search(pattern, sentence, re.I))


def _relevant_context(summary: str, body_part: str) -> tuple[str, bool]:
    canonical = canonical_body_part(body_part)
    side = ""
    base = canonical
    if canonical.startswith("left "):
        side, base = "left", canonical[5:]
    elif canonical.startswith("right "):
        side, base = "right", canonical[6:]
    aliases = BODY_ALIASES.get(base, (base,))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", str(summary)) if s.strip()]
    matching = [
        sentence
        for sentence in sentences
        if any(re.search(rf"\b{re.escape(alias)}\b", sentence, re.I) for alias in aliases)
    ]
    if side and matching:
        same_side = [s for s in matching if _sentence_mentions_side(s, side)]
        if same_side:
            matching = same_side
        else:
            opposite = "right" if side == "left" else "left"
            matching = [s for s in matching if not _sentence_mentions_side(s, opposite)]
    return (" ".join(matching), True) if matching else ("", False)


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 90) : start]
    after = text[end : min(len(text), end + 50)]
    before_negation = re.search(
        r"\b(?:no|not|without|denies|denied|negative for|absence of|free of)(?:\W+\w+){0,6}\W*$",
        before,
        re.I,
    )
    after_negation = re.search(
        r"^\W*(?:was |were |is |are )?(?:ruled out|not seen|not present|negative|absent)",
        after,
        re.I,
    )
    return bool(before_negation or after_negation)


def _first_match(text: str, patterns, *, allow_negated: bool = False):
    for pattern, reason in patterns:
        for match in re.finditer(pattern, text, re.I):
            if allow_negated or not _is_negated(text, match.start(), match.end()):
                return reason, match.group(0)
    return None


def _severity_match(text: str, patterns):
    for pattern, reason, basis in patterns:
        for match in re.finditer(pattern, text, re.I):
            if not _is_negated(text, match.start(), match.end()):
                return reason, match.group(0), basis
    return None


def _extract_current_pain_score(text: str) -> tuple[float | None, str]:
    matches = list(PAIN_SCORE_RE.finditer(text))
    if not matches:
        return None, ""
    ranked: list[tuple[int, int, re.Match[str]]] = []
    for match in matches:
        before = text[max(0, match.start() - 36) : match.start()].lower()
        priority = 1
        if re.search(r"\b(?:now|today|current(?:ly)?)\b", before):
            priority = 3
        elif re.search(r"\b(?:reports?|reported|rates?|rated)\b", before):
            priority = 2
        ranked.append((priority, -match.start(), match))
    _, _, chosen = max(ranked, key=lambda item: (item[0], item[1]))
    score = float(chosen.group(1))
    return (score, chosen.group(0)) if 0 <= score <= 10 else (None, "")


def _pain_severity(score: float) -> int:
    if score <= 0:
        return 0
    if score <= 3:
        return 1
    if score <= 6:
        return 2
    return 3


def infer_severity(summary: str, body_part: str) -> Inference:
    context, is_specific = _relevant_context(summary, body_part)
    if not is_specific:
        return Inference(None, "unknown", None, "body part listed, but no body-specific severity statement was found", "", False, "Low", "none")

    resolved = _first_match(context, RESOLVED_PATTERNS, allow_negated=True)
    if resolved:
        return Inference(0, "resolved", 0.0 if "0/10" in resolved[1] else None, resolved[0], context, True, "High", "resolved")

    improving = _first_match(context, IMPROVING_PATTERNS)
    worsening = _first_match(context, WORSENING_PATTERNS)
    stable = _first_match(context, STABLE_PATTERNS)
    trend_hint = "unknown"
    trend_reason = ""
    if improving:
        trend_hint, trend_reason = "improving", improving[0]
    elif worsening:
        trend_hint, trend_reason = "worsening", worsening[0]
    elif stable:
        trend_hint, trend_reason = "stable", stable[0]

    pain_score, _ = _extract_current_pain_score(context)
    candidates: list[tuple[int, str, str]] = []
    if pain_score is not None:
        candidates.append((_pain_severity(pain_score), f"pain score {pain_score:g}/10", "pain_score"))
    for level, patterns in ((3, SEVERE_PATTERNS), (2, MODERATE_PATTERNS), (1, MILD_PATTERNS)):
        match = _severity_match(context, patterns)
        if match:
            candidates.append((level, match[0], match[2]))

    if not candidates:
        reason = trend_reason or "body-specific statement found, but severity is not explicit"
        return Inference(None, trend_hint, pain_score, reason, context, True, "Medium" if trend_hint != "unknown" else "Low", "none")

    severity, severity_reason, basis = max(candidates, key=lambda item: item[0])
    reasons = [severity_reason]
    if trend_reason and trend_reason != severity_reason:
        reasons.append(trend_reason)
    confidence = "High" if basis in {"pain_score", "descriptor", "structural", "resolved"} else "Medium"
    return Inference(severity, trend_hint, pain_score, "; ".join(reasons), context, True, confidence, basis)


def extract_observations(
    df: pd.DataFrame,
    body_part: str | None = None,
    medicine_types: list[str] | tuple[str, ...] | set[str] | None = None,
) -> pd.DataFrame:
    """Create one observation per matching encounter; multiple medicine types are kept together."""
    selected = df.copy()
    if medicine_types is not None:
        selected = selected[selected["medicine_type"].isin(set(medicine_types))]
    selected = selected.sort_values(["encounter_date", "event_id"], ascending=True)
    selected_body = canonical_body_part(body_part) if body_part else None
    observations: list[dict[str, Any]] = []
    for event_order, (_, row) in enumerate(selected.iterrows()):
        event_parts = {
            canonical_body_part(raw)
            for raw in split_multi_value(str(row.get("body_parts", "")), ",")
            if canonical_body_part(raw)
        }
        if selected_body:
            event_parts = {part for part in event_parts if part == selected_body}
        for part_order, canonical in enumerate(sorted(event_parts)):
            inference = infer_severity(str(row.get("summary", "")), canonical)
            event_id = str(row.get("event_id", f"event-{event_order}"))
            observations.append(
                {
                    "observation_id": f"{event_id}:{canonical}:{part_order}",
                    "event_order": event_order,
                    "encounter_date": pd.Timestamp(row["encounter_date"]),
                    "event_id": event_id,
                    "body_part": canonical,
                    "medicine_type": str(row.get("medicine_type", "")),
                    "record_type": str(row.get("record_type", "")),
                    "primary_provider": str(row.get("primary_provider", "")),
                    "facility": str(row.get("facility", "")),
                    "pdf_url": str(row.get("pdf_url", "")),
                    "summary": str(row.get("summary", "")),
                    "suggested_severity": inference.severity,
                    "suggested_trend": inference.trend_hint,
                    "pain_score": inference.pain_score,
                    "reason": inference.reason,
                    "matched_text": inference.matched_text,
                    "context_specific": inference.context_specific,
                    "confidence": inference.confidence,
                    "severity_basis": inference.severity_basis,
                    "mapped": bool(marker_locations(canonical)),
                    "severity_override": "Auto",
                    "trend_override": "Auto",
                }
            )
    return pd.DataFrame(observations)


def _override_severity(value: str, suggested: int | None) -> int | None:
    if suggested is not None and pd.isna(suggested):
        suggested = None
    return {"Mild": 1, "Moderate": 2, "Severe": 3, "Resolved": 0, "No severity update": None}.get(value, suggested)


def _override_trend(value: str, suggested: str) -> str:
    if suggested is None or str(suggested).lower() == "nan":
        suggested = "unknown"
    return {"New": "new", "Improving": "improving", "Stable": "stable", "Worsening": "worsening", "Resolved": "resolved", "Unknown": "unknown"}.get(value, suggested)


def _trend_from_change(previous_severity, new_severity, previous_pain, new_pain) -> str:
    if previous_severity is None and new_severity not in (None, 0):
        return "new"
    if previous_pain is not None and new_pain is not None and pd.notna(new_pain):
        if float(new_pain) < float(previous_pain):
            return "improving"
        if float(new_pain) > float(previous_pain):
            return "worsening"
        return "stable"
    if previous_severity is not None and new_severity is not None:
        if new_severity < previous_severity:
            return "improving"
        if new_severity > previous_severity:
            return "worsening"
        return "stable"
    return "unknown"


def build_progression(observations: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Build one timeline point per encounter after severity is established.

    Encounters are not dropped just because severity is unchanged. This keeps Emergency,
    Radiology, Orthopedic, PT, and other selected medicine types in one continuous chronology.
    When an encounter has no new severity evidence, the last established severity is carried
    forward and marked as such rather than inventing a new severity estimate.
    """
    if observations.empty:
        return [], pd.DataFrame()

    ordered = observations.sort_values(["encounter_date", "event_order", "event_id"])
    state: dict[str, dict[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for _, observation in ordered.iterrows():
        body_part = str(observation["body_part"])
        previous = state.get(body_part, {})
        previous_severity = previous.get("severity")
        previous_pain = previous.get("pain_score")

        severity = _override_severity(str(observation.get("severity_override", "Auto")), observation.get("suggested_severity"))
        trend = _override_trend(str(observation.get("trend_override", "Auto")), str(observation.get("suggested_trend", "unknown")))
        basis = str(observation.get("severity_basis", "none"))

        if (
            severity is not None
            and previous_severity is not None
            and severity < previous_severity
            and basis in {"generic_symptom", "functional"}
            and str(observation.get("severity_override", "Auto")) == "Auto"
            and trend != "improving"
        ):
            severity = previous_severity

        if trend == "resolved" or severity == 0:
            severity = 0
            trend = "resolved"
        elif trend == "unknown":
            trend = _trend_from_change(previous_severity, severity, previous_pain, observation.get("pain_score"))

        carried_forward = False
        effective_severity = severity
        if effective_severity is None and previous_severity is not None:
            effective_severity = previous_severity
            carried_forward = True

        if effective_severity is None:
            continue

        new_pain = observation.get("pain_score")
        has_new_pain = new_pain is not None and pd.notna(new_pain)
        effective_pain = float(new_pain) if has_new_pain else previous_pain

        if effective_severity == 0:
            state.pop(body_part, None)
        else:
            state[body_part] = {"severity": int(effective_severity), "pain_score": effective_pain}

        reason = str(observation.get("reason", ""))
        if carried_forward:
            reason = f"No new severity estimate in this encounter; carried forward {SEVERITY_LABELS[int(effective_severity)].lower()} severity from the prior record. {reason}".strip()

        severity_label = SEVERITY_LABELS[int(effective_severity)]
        previous_label = SEVERITY_LABELS[int(previous_severity)] if previous_severity is not None else "Not established"
        snapshot = {
            "date": pd.Timestamp(observation["encounter_date"]),
            "body_part": body_part,
            "severity": int(effective_severity),
            "trend": trend,
            "pain_score": float(new_pain) if has_new_pain else None,
            "event_id": str(observation.get("event_id", "")),
            "medicine_type": str(observation.get("medicine_type", "")),
            "record_type": str(observation.get("record_type", "")),
            "primary_provider": str(observation.get("primary_provider", "")),
            "facility": str(observation.get("facility", "")),
            "pdf_url": str(observation.get("pdf_url", "")),
            "reason": reason,
            "matched_text": str(observation.get("matched_text", "")),
            "confidence": str(observation.get("confidence", "")),
            "mapped": bool(observation.get("mapped", False)),
            "carried_forward": carried_forward,
        }
        snapshots.append(snapshot)
        rows.append(
            {
                "Date": snapshot["date"],
                "Event ID": snapshot["event_id"],
                "Body Part": body_part.title(),
                "Previous Severity": previous_label,
                "Severity": severity_label,
                "Trend": TREND_LABELS.get(trend, trend.title()),
                "Pain Score": snapshot["pain_score"],
                "Medicine Type": snapshot["medicine_type"],
                "Provider": snapshot["primary_provider"],
                "Facility": snapshot["facility"],
                "Confidence": snapshot["confidence"],
                "Evidence": snapshot["matched_text"],
                "Reason": snapshot["reason"],
                "Carried Forward": carried_forward,
                "PDF": snapshot["pdf_url"],
            }
        )

    return snapshots, pd.DataFrame(rows)


def _image_data_uri() -> str:
    encoded = base64.b64encode(BODY_SVG.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _safe_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _marker_html(body_part: str, severity: int, tooltip: str) -> tuple[str, str]:
    front: list[str] = []
    back: list[str] = []
    for location in marker_locations(body_part):
        color = SEVERITY_COLORS[severity]
        content = "✓" if severity == 0 else ""
        marker = (
            f'<span class="marker" style="left:{location.x}%;top:{location.y}%;background:{color}" '
            f'title="{html.escape(tooltip, quote=True)}">{content}</span>'
        )
        (front if location.view == "front" else back).append(marker)
    return "".join(front), "".join(back)


def render_progression_html(snapshots: list[dict[str, Any]]) -> str:
    """Render all selected encounters on one date-proportional multi-specialty timeline."""
    if not snapshots:
        return "<p>No progression points.</p>"

    ordered = sorted(snapshots, key=lambda item: (pd.Timestamp(item["date"]), item["event_id"]))
    dates = [pd.Timestamp(item["date"]) for item in ordered]
    min_date, max_date = min(dates), max(dates)
    span_days = max(1, (max_date - min_date).days)
    canvas_width = max(1100, min(7000, max(420 + span_days * 8, 260 + len(ordered) * 190)))
    usable_width = canvas_width - 260
    lane_count = 4
    lane_height = 255
    axis_y = 28 + lane_count * lane_height
    canvas_height = axis_y + 80
    image_uri = _image_data_uri()

    points: list[str] = []
    for index, snapshot in enumerate(ordered):
        date = pd.Timestamp(snapshot["date"])
        day_offset = (date - min_date).days
        date_x = 130 + (day_offset / span_days) * usable_width if span_days else canvas_width / 2
        prior_same_date = sum(1 for prior in ordered[:index] if pd.Timestamp(prior["date"]).date() == date.date())
        x_pos = min(canvas_width - 130, max(130, date_x + prior_same_date * 38))
        lane = index % lane_count
        top = 10 + lane * lane_height
        severity = int(snapshot["severity"])
        trend = str(snapshot["trend"])
        pain_score = snapshot.get("pain_score")
        pain_label = f"{float(pain_score):g}/10" if pain_score is not None else "—"
        severity_label = SEVERITY_LABELS[severity]
        trend_label = TREND_LABELS.get(trend, trend.title())
        medicine_type = html.escape(str(snapshot.get("medicine_type", ""))) or "Unspecified"
        tooltip = f"{snapshot['body_part'].title()} — {severity_label}; {trend_label}. {snapshot.get('reason', '')}"
        front_markers, back_markers = _marker_html(snapshot["body_part"], severity, tooltip)
        mapped_note = "" if snapshot.get("mapped") else '<div class="unmapped">Unmapped anatomy — no body marker</div>'
        source_url = _safe_url(str(snapshot.get("pdf_url", "")))
        source_link = (
            f'<a class="source-link" href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">View source</a>'
            if source_url
            else ""
        )
        carried = '<span class="carried">carried forward</span>' if snapshot.get("carried_forward") else ""
        evidence = html.escape(str(snapshot.get("matched_text", "")))
        points.append(
            f'<div class="timepoint" style="left:{x_pos:.1f}px;top:{top}px">'
            f'<div class="medicine-badge">{medicine_type}</div>'
            '<div class="body-pair">'
            f'<div class="body-panel"><div class="view-label">Front</div><img src="{image_uri}" alt="Front body outline"/>{front_markers}</div>'
            f'<div class="body-panel"><div class="view-label">Back</div><img src="{image_uri}" alt="Back body outline"/>{back_markers}</div>'
            '</div>'
            f'<div class="date">{date.strftime("%b %d, %Y")}</div>'
            f'<div class="status"><strong>{severity_label}</strong> <span class="trend">{TREND_SYMBOLS.get(trend, "?")} {trend_label}</span></div>'
            f'<div class="meta">Pain: {pain_label} · {html.escape(str(snapshot.get("event_id", "")))}</div>'
            f'{carried}{mapped_note}{source_link}'
            f'<div class="evidence" title="{html.escape(evidence, quote=True)}">{evidence[:140]}{"…" if len(evidence) > 140 else ""}</div>'
            '</div>'
            f'<div class="stem" style="left:{x_pos:.1f}px;top:{top + 232}px;height:{max(12, axis_y - (top + 232))}px"></div>'
            f'<div class="axis-tick" style="left:{x_pos:.1f}px;top:{axis_y - 5}px"></div>'
        )

    medicine_types = sorted({str(item.get("medicine_type", "")).strip() or "Unspecified" for item in ordered})
    medicine_summary = " · ".join(html.escape(value) for value in medicine_types)
    return f"""<!doctype html>
<html><head><style>
* {{ box-sizing:border-box; }}
body {{ margin:0; color:#1f2937; font-family:Arial,sans-serif; background:white; }}
.legend {{ display:flex; flex-wrap:wrap; gap:14px; align-items:center; margin:4px 8px 7px; font-size:13px; }}
.specialties {{ margin:0 8px 12px; font-size:12px; color:#475569; }}
.legend-item {{ display:flex; align-items:center; gap:5px; }}
.swatch {{ width:13px; height:13px; border-radius:50%; border:1px solid rgba(0,0,0,.3); }}
.scroll {{ overflow-x:auto; overflow-y:hidden; padding:4px 8px 16px; }}
.canvas {{ position:relative; width:{canvas_width}px; height:{canvas_height}px; min-width:{canvas_width}px; }}
.axis {{ position:absolute; left:20px; right:20px; top:{axis_y}px; height:3px; background:#64748b; }}
.timepoint {{ position:absolute; width:220px; min-height:232px; transform:translateX(-50%); text-align:center; background:#fff; border:1px solid #dbe3ec; border-radius:10px; padding:5px 7px 7px; box-shadow:0 1px 5px rgba(15,23,42,.12); z-index:2; }}
.medicine-badge {{ font-size:10px; font-weight:700; color:#334155; background:#eef2f7; border-radius:8px; padding:2px 6px; margin:0 auto 2px; max-width:190px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.body-pair {{ display:flex; justify-content:center; gap:3px; height:126px; }}
.body-panel {{ width:80px; height:124px; position:relative; }}
.view-label {{ position:absolute; top:0; left:0; right:0; text-align:center; font-size:9px; color:#64748b; z-index:3; }}
.body-panel img {{ width:100%; height:100%; object-fit:contain; display:block; }}
.marker {{ position:absolute; width:16px; height:16px; border-radius:50%; transform:translate(-50%,-50%); border:2px solid rgba(255,255,255,.95); box-shadow:0 0 0 1px rgba(0,0,0,.55); color:white; font-size:11px; line-height:12px; font-weight:700; cursor:help; z-index:4; }}
.date {{ font-size:12px; font-weight:700; white-space:nowrap; margin-top:1px; }}
.status {{ font-size:12px; margin-top:2px; }}
.trend {{ margin-left:5px; color:#334155; }}
.meta {{ font-size:10.5px; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.carried {{ display:inline-block; font-size:9px; color:#475569; background:#f1f5f9; border-radius:7px; padding:1px 5px; margin-right:4px; }}
.unmapped {{ font-size:10px; color:#b45309; font-weight:700; }}
.source-link {{ font-size:10.5px; margin-right:6px; }}
.evidence {{ font-size:9.5px; color:#475569; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.stem {{ position:absolute; width:2px; background:#94a3b8; transform:translateX(-50%); z-index:1; }}
.axis-tick {{ position:absolute; width:3px; height:13px; background:#334155; transform:translateX(-50%); z-index:1; }}
</style></head><body>
<div class="legend">
  <strong>Severity:</strong>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[1]}"></span>Mild</span>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[2]}"></span>Moderate</span>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[3]}"></span>Severe</span>
  <span class="legend-item"><span class="swatch" style="background:{SEVERITY_COLORS[0]}"></span>Resolved</span>
  <span class="legend-item"><strong>Trend:</strong> ↑ worsening · → stable · ↓ improving · ✓ resolved</span>
</div>
<div class="specialties"><strong>Medicine types in this progression:</strong> {medicine_summary}</div>
<div class="scroll"><div class="canvas"><div class="axis"></div>{"".join(points)}</div></div>
</body></html>"""
