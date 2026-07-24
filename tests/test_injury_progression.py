"""Tests for deterministic injury progression inference."""

from __future__ import annotations

import unittest

import pandas as pd

from injury_progression import (
    build_progression,
    extract_observations,
    infer_severity,
    marker_coordinates,
)


class SeverityInferenceTests(unittest.TestCase):
    def test_severe_pain_is_red(self) -> None:
        result = infer_severity("Severe shoulder pain rated 9/10.", "shoulder")
        self.assertEqual(result.action, "severe")
        self.assertEqual(result.suggested_level, 3)

    def test_negated_fracture_is_not_severe(self) -> None:
        result = infer_severity(
            "Neck pain is present. No acute cervical fracture was seen.", "neck"
        )
        self.assertEqual(result.action, "injury")
        self.assertEqual(result.suggested_level, 1)

    def test_body_specific_sentences_are_used(self) -> None:
        summary = "Neck pain is worsening to 7/10. Shoulder pain is severe at 9/10."
        neck = infer_severity(summary, "neck")
        shoulder = infer_severity(summary, "shoulder")
        self.assertEqual(neck.action, "worsening")
        self.assertEqual(shoulder.action, "severe")
        self.assertTrue(neck.context_specific)
        self.assertTrue(shoulder.context_specific)

    def test_improvement_and_resolution(self) -> None:
        self.assertEqual(
            infer_severity("Back symptoms are improving.", "back").action,
            "improving",
        )
        self.assertEqual(
            infer_severity("The patient is now pain-free in the back.", "back").action,
            "resolved",
        )

    def test_laterality_coordinates(self) -> None:
        self.assertEqual(len(marker_coordinates("shoulder")), 2)
        self.assertEqual(len(marker_coordinates("left shoulder")), 1)
        self.assertNotEqual(
            marker_coordinates("left shoulder"),
            marker_coordinates("right shoulder"),
        )


class ProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = pd.DataFrame(
            [
                {
                    "encounter_date": pd.Timestamp("2024-01-01"),
                    "medicine_type": "Orthopedic",
                    "body_parts": "Neck, Shoulder",
                    "summary": "Neck and shoulder pain with tenderness.",
                },
                {
                    "encounter_date": pd.Timestamp("2024-02-01"),
                    "medicine_type": "Orthopedic",
                    "body_parts": "Neck",
                    "summary": "Neck pain is worsening and rated 7/10.",
                },
                {
                    "encounter_date": pd.Timestamp("2024-03-01"),
                    "medicine_type": "Orthopedic",
                    "body_parts": "Neck",
                    "summary": "Severe neck pain rated 9/10.",
                },
                {
                    "encounter_date": pd.Timestamp("2024-04-01"),
                    "medicine_type": "Orthopedic",
                    "body_parts": "Shoulder",
                    "summary": "Shoulder pain has resolved.",
                },
            ]
        )

    def test_progression_changes_yellow_orange_red(self) -> None:
        observations = extract_observations(self.events, "Orthopedic")
        snapshots, changes = build_progression(observations)

        self.assertEqual(len(snapshots), 4)
        neck_levels = [
            snapshot["statuses"].get("neck", {}).get("level")
            for snapshot in snapshots
        ]
        self.assertEqual(neck_levels[:3], [1, 2, 3])
        self.assertNotIn("shoulder", snapshots[-1]["statuses"])
        self.assertIn("Resolved", set(changes["New Status"]))

    def test_manual_override_wins(self) -> None:
        observations = extract_observations(self.events.iloc[:1], "Orthopedic")
        observations.loc[observations["body_part"] == "neck", "override"] = (
            "Severe injury"
        )
        snapshots, _ = build_progression(observations)
        self.assertEqual(snapshots[0]["statuses"]["neck"]["level"], 3)


if __name__ == "__main__":
    unittest.main()
