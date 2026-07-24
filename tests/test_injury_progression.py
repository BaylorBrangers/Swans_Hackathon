"""Tests for conservative, auditable injury progression inference."""

from __future__ import annotations

import unittest

import pandas as pd

from injury_progression import (
    SEVERITY_LABELS,
    available_body_parts,
    build_progression,
    canonical_body_part,
    extract_observations,
    infer_severity,
    marker_locations,
    render_progression_html,
)


def event(date, event_id, medicine_type, body_parts, summary, **kwargs):
    return {
        "encounter_date": pd.Timestamp(date),
        "event_id": event_id,
        "medicine_type": medicine_type,
        "body_parts": body_parts,
        "summary": summary,
        "record_type": kwargs.get("record_type", "Encounter Note"),
        "primary_provider": kwargs.get("primary_provider", "Provider"),
        "facility": kwargs.get("facility", "Facility"),
        "pdf_url": kwargs.get("pdf_url", f"https://example.com/{event_id}.pdf"),
    }


class SeverityInferenceTests(unittest.TestCase):
    def test_severe_pain(self):
        result = infer_severity("Severe shoulder pain rated 9/10.", "shoulder")
        self.assertEqual(result.severity, 3)
        self.assertEqual(result.pain_score, 9)

    def test_negated_fracture_does_not_make_severe(self):
        result = infer_severity(
            "Neck pain is present. No acute cervical fracture was seen.", "neck"
        )
        self.assertEqual(result.severity, 1)

    def test_no_cross_body_contamination(self):
        hand = infer_severity(
            "Severe neck pain rated 9/10. Hand imaging was unremarkable.", "hand"
        )
        self.assertIsNone(hand.severity)
        self.assertEqual(hand.confidence, "Low")

    def test_no_body_specific_sentence_is_unknown(self):
        result = infer_severity("Patient reports severe headache rated 9/10.", "knee")
        self.assertIsNone(result.severity)
        self.assertFalse(result.context_specific)

    def test_current_pain_score_beats_historical_score(self):
        result = infer_severity("Neck pain was 8/10 but is now 3/10.", "neck")
        self.assertEqual(result.pain_score, 3)
        self.assertEqual(result.severity, 1)

    def test_resolution(self):
        result = infer_severity(
            "Low back pain has resolved and the patient is pain-free.", "lower back"
        )
        self.assertEqual(result.severity, 0)
        self.assertEqual(result.trend_hint, "resolved")

    def test_laterality_front_and_back(self):
        left = marker_locations("left shoulder")
        right = marker_locations("right shoulder")
        self.assertEqual(len(left), 1)
        self.assertEqual(len(right), 1)
        self.assertNotEqual(left[0].x, right[0].x)
        left_back = marker_locations("left scapula")
        right_back = marker_locations("right scapula")
        self.assertLess(left_back[0].x, right_back[0].x)

    def test_unmapped_body_is_not_silently_placed(self):
        self.assertEqual(marker_locations("ear"), [])

    def test_alias_normalization(self):
        self.assertEqual(canonical_body_part("L lumbar spine"), "left lower back")
        self.assertEqual(canonical_body_part("SI joint"), "sacrum")
        self.assertEqual(canonical_body_part("L spine"), "lower back")


class ProgressionTests(unittest.TestCase):
    def test_explicit_lower_pain_lowers_severity(self):
        df = pd.DataFrame(
            [
                event("2024-01-01", "E1", "Emergency", "Neck", "Neck pain rated 9/10."),
                event("2024-02-01", "E2", "Orthopedic", "Neck", "Neck pain rated 3/10."),
            ]
        )
        snapshots, changes = build_progression(extract_observations(df, "neck"))
        self.assertEqual([snapshot["severity"] for snapshot in snapshots], [3, 1])
        self.assertEqual(snapshots[-1]["trend"], "improving")
        self.assertEqual(changes.iloc[-1]["Severity"], SEVERITY_LABELS[1])

    def test_same_bucket_pain_change_still_sets_trend(self):
        df = pd.DataFrame(
            [
                event("2024-01-01", "E1", "Emergency", "Neck", "Neck pain rated 9/10."),
                event("2024-02-01", "E2", "Orthopedic", "Neck", "Neck pain rated 7/10."),
            ]
        )
        snapshots, _ = build_progression(extract_observations(df, "neck"))
        self.assertEqual([snapshot["severity"] for snapshot in snapshots], [3, 3])
        self.assertEqual(snapshots[-1]["trend"], "improving")

    def test_progression_spans_medicine_types_by_default(self):
        df = pd.DataFrame(
            [
                event("2024-01-01", "E1", "Emergency", "Neck", "Neck pain rated 8/10."),
                event(
                    "2024-02-01",
                    "E2",
                    "Radiology",
                    "Neck",
                    "No cervical fracture. Neck pain rated 6/10.",
                ),
                event(
                    "2024-03-01",
                    "E3",
                    "Physical Therapy",
                    "Neck",
                    "Neck pain rated 3/10 and improving.",
                ),
            ]
        )
        observations = extract_observations(df, "neck")
        self.assertEqual(list(observations["event_id"]), ["E1", "E2", "E3"])
        snapshots, _ = build_progression(observations)
        self.assertEqual([snapshot["severity"] for snapshot in snapshots], [3, 2, 1])
        self.assertEqual(
            [snapshot["medicine_type"] for snapshot in snapshots],
            ["Emergency", "Radiology", "Physical Therapy"],
        )

    def test_unchanged_cross_specialty_encounters_are_not_dropped(self):
        df = pd.DataFrame(
            [
                event("2024-01-01", "E1", "Emergency", "Neck", "Neck pain rated 6/10."),
                event(
                    "2024-01-10",
                    "E2",
                    "Radiology",
                    "Neck",
                    "Cervical imaging shows no fracture.",
                ),
                event(
                    "2024-01-20",
                    "E3",
                    "Orthopedic",
                    "Neck",
                    "Neck pain rated 6/10 and unchanged.",
                ),
                event(
                    "2024-02-01",
                    "E4",
                    "Physical Therapy",
                    "Neck",
                    "Neck pain remains 6/10.",
                ),
            ]
        )
        snapshots, changes = build_progression(extract_observations(df, "neck"))
        self.assertEqual(len(snapshots), 4)
        self.assertEqual(
            [snapshot["medicine_type"] for snapshot in snapshots],
            ["Emergency", "Radiology", "Orthopedic", "Physical Therapy"],
        )
        self.assertTrue(snapshots[1]["carried_forward"])
        self.assertTrue(changes.iloc[1]["Carried Forward"])

    def test_multiple_medicine_types_can_be_selected_together(self):
        df = pd.DataFrame(
            [
                event("2024-01-01", "E1", "Emergency", "Neck", "Neck pain rated 8/10."),
                event("2024-02-01", "E2", "Radiology", "Neck", "Neck pain rated 6/10."),
                event("2024-03-01", "E3", "Physical Therapy", "Neck", "Neck pain rated 3/10."),
            ]
        )
        observations = extract_observations(
            df,
            "neck",
            medicine_types=["Emergency", "Physical Therapy"],
        )
        self.assertEqual(
            list(observations["medicine_type"]),
            ["Emergency", "Physical Therapy"],
        )
        snapshots, _ = build_progression(observations)
        self.assertEqual(
            [snapshot["medicine_type"] for snapshot in snapshots],
            ["Emergency", "Physical Therapy"],
        )

    def test_html_lists_all_medicine_types(self):
        df = pd.DataFrame(
            [
                event("2024-01-01", "E1", "Emergency", "Neck", "Neck pain rated 8/10."),
                event(
                    "2024-01-10",
                    "E2",
                    "Radiology",
                    "Neck",
                    "Cervical imaging shows no fracture.",
                ),
                event("2024-02-01", "E3", "Physical Therapy", "Neck", "Neck pain rated 4/10."),
            ]
        )
        snapshots, _ = build_progression(extract_observations(df, "neck"))
        output = render_progression_html(snapshots)
        self.assertIn("Emergency", output)
        self.assertIn("Radiology", output)
        self.assertIn("Physical Therapy", output)
        self.assertIn("Medicine types in this progression", output)

    def test_source_metadata_is_preserved(self):
        df = pd.DataFrame(
            [
                event(
                    "2024-01-01",
                    "E000042",
                    "Orthopedic",
                    "Shoulder",
                    "Shoulder pain rated 6/10.",
                )
            ]
        )
        observations = extract_observations(df, "shoulder")
        self.assertEqual(observations.iloc[0]["event_id"], "E000042")
        self.assertEqual(observations.iloc[0]["pdf_url"], "https://example.com/E000042.pdf")
        snapshots, changes = build_progression(observations)
        self.assertEqual(snapshots[0]["event_id"], "E000042")
        self.assertEqual(changes.iloc[0]["Event ID"], "E000042")

    def test_manual_override_wins(self):
        df = pd.DataFrame(
            [event("2024-01-01", "E1", "Orthopedic", "Neck", "Neck pain rated 2/10.")]
        )
        observations = extract_observations(df, "neck")
        observations.loc[:, "severity_override"] = "Severe"
        snapshots, _ = build_progression(observations)
        self.assertEqual(snapshots[0]["severity"], 3)

    def test_available_body_parts_are_canonical(self):
        df = pd.DataFrame(
            [
                event(
                    "2024-01-01",
                    "E1",
                    "Orthopedic",
                    "L Shoulder, SI joint",
                    "Left shoulder pain. SI joint pain.",
                )
            ]
        )
        self.assertEqual(available_body_parts(df), ["left shoulder", "sacrum"])


if __name__ == "__main__":
    unittest.main()
