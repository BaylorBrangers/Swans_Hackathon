"""Tests for the demo lost-income estimator."""

import unittest

import pandas as pd
from pydantic import ValidationError

from lost_income import (
    LostIncomeInput,
    predict_lost_income,
    train_lost_income_model,
    validate_training_data,
)


class LostIncomeTests(unittest.TestCase):
    def _training_data(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Incident Type": "Auto",
                    "Injury": "Neck strain",
                    "Salary": 50000,
                    "Dependents": 0,
                    "Age": 30,
                    "Residency": "Portugal",
                    "Personal/Commerical": "Personal",
                    "Lost Income": 6000,
                },
                {
                    "Incident Type": "Auto",
                    "Injury": "Shoulder injury",
                    "Salary": 80000,
                    "Dependents": 2,
                    "Age": 45,
                    "Residency": "Portugal",
                    "Personal/Commerical": "Commercial",
                    "Lost Income": 18000,
                },
                {
                    "Incident Type": "Workplace",
                    "Injury": "Back injury",
                    "Salary": 65000,
                    "Dependents": 1,
                    "Age": 38,
                    "Residency": "Spain",
                    "Personal/Commerical": "Personal",
                    "Lost Income": 12000,
                },
            ]
        )

    def test_validates_and_normalizes_training_rows(self) -> None:
        validated = validate_training_data(self._training_data())
        self.assertEqual(len(validated), 3)
        self.assertEqual(validated.loc[0, "Personal/Commerical"], "Personal")

    def test_accepts_corrected_personal_commercial_alias(self) -> None:
        row = LostIncomeInput.model_validate(
            {
                "Incident Type": "Auto",
                "Injury": "Neck strain",
                "Salary": 50000,
                "Dependents": 0,
                "Age": 30,
                "Residency": "Portugal",
                "Personal/Commercial": "commercial",
            }
        )
        self.assertEqual(row.personal_commercial, "Commercial")

    def test_rejects_invalid_personal_commercial_value(self) -> None:
        with self.assertRaises(ValidationError):
            LostIncomeInput.model_validate(
                {
                    "Incident Type": "Auto",
                    "Injury": "Neck strain",
                    "Salary": 50000,
                    "Dependents": 0,
                    "Age": 30,
                    "Residency": "Portugal",
                    "Personal/Commerical": "Unknown",
                }
            )

    def test_train_and_predict(self) -> None:
        training = validate_training_data(self._training_data())
        model = train_lost_income_model(training)
        prediction = predict_lost_income(
            model,
            {
                "Incident Type": "Auto",
                "Injury": "Neck strain",
                "Salary": 55000,
                "Dependents": 1,
                "Age": 35,
                "Residency": "Portugal",
                "Personal/Commerical": "Personal",
            },
        )
        self.assertGreaterEqual(prediction.estimated_lost_income, 0)


if __name__ == "__main__":
    unittest.main()
