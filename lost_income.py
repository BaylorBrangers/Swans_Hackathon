"""Simple upload-train-predict demo for estimated lost income."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
from lightgbm import LGBMRegressor
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


INPUT_COLUMNS = [
    "Incident Type",
    "Injury",
    "Salary",
    "Dependents",
    "Age",
    "Residency",
    "Personal/Commerical",
]
TARGET_COLUMN = "Lost Income"
NUMERIC_COLUMNS = ["Salary", "Dependents", "Age"]
CATEGORICAL_COLUMNS = [
    "Incident Type",
    "Injury",
    "Residency",
    "Personal/Commerical",
]


class LostIncomeInput(BaseModel):
    """Validated feature row used for training and prediction."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    incident_type: str = Field(alias="Incident Type", min_length=1)
    injury: str = Field(alias="Injury", min_length=1)
    salary: float = Field(alias="Salary", ge=0)
    dependents: int = Field(alias="Dependents", ge=0, le=20)
    age: int = Field(alias="Age", ge=0, le=120)
    residency: str = Field(alias="Residency", min_length=1)
    personal_commercial: str = Field(
        validation_alias=AliasChoices("Personal/Commerical", "Personal/Commercial"),
        serialization_alias="Personal/Commerical",
        min_length=1,
    )

    @field_validator("personal_commercial")
    @classmethod
    def normalize_personal_commercial(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "personal":
            return "Personal"
        if normalized == "commercial":
            return "Commercial"
        raise ValueError("must be either Personal or Commercial")


class LostIncomeTrainingRow(LostIncomeInput):
    """Validated labeled row used to train the demo model."""

    lost_income: float = Field(alias=TARGET_COLUMN, ge=0)


class LostIncomePrediction(BaseModel):
    """Validated model output."""

    estimated_lost_income: float = Field(ge=0)


def _feature_dict(row: LostIncomeInput) -> dict[str, Any]:
    return {
        "Incident Type": row.incident_type,
        "Injury": row.injury,
        "Salary": row.salary,
        "Dependents": row.dependents,
        "Age": row.age,
        "Residency": row.residency,
        "Personal/Commerical": row.personal_commercial,
    }


def read_training_file(filename: str, data: bytes) -> pd.DataFrame:
    """Read uploaded CSV or XLSX training data."""
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        df = pd.read_csv(BytesIO(data))
    elif lower_name.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(data))
    else:
        raise ValueError("Training data must be a CSV or XLSX file.")

    df.columns = [str(column).strip() for column in df.columns]
    if "Personal/Commercial" in df.columns and "Personal/Commerical" not in df.columns:
        df = df.rename(columns={"Personal/Commercial": "Personal/Commerical"})
    return df


def validate_training_data(df: pd.DataFrame) -> pd.DataFrame:
    """Validate every uploaded row with Pydantic and return normalized data."""
    required = INPUT_COLUMNS + [TARGET_COLUMN]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")
    if df.empty:
        raise ValueError("Training data is empty.")

    normalized_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in df[required].iterrows():
        try:
            validated = LostIncomeTrainingRow.model_validate(row.to_dict())
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            errors.append(f"Row {index + 2}: {details}")
            continue

        normalized = _feature_dict(validated)
        normalized[TARGET_COLUMN] = validated.lost_income
        normalized_rows.append(normalized)

    if errors:
        preview = "\n".join(errors[:10])
        suffix = f"\n...and {len(errors) - 10} more error(s)." if len(errors) > 10 else ""
        raise ValueError(f"Training data failed validation:\n{preview}{suffix}")

    return pd.DataFrame(normalized_rows, columns=required)


def train_lost_income_model(df: pd.DataFrame) -> Pipeline:
    """Train a fixed, intentionally simple LightGBM regression pipeline."""
    if len(df) < 2:
        raise ValueError("Provide at least 2 valid training rows.")

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_COLUMNS,
            ),
            ("numeric", "passthrough", NUMERIC_COLUMNS),
        ]
    )
    model = LGBMRegressor(
        objective="regression",
        n_estimators=100,
        random_state=42,
        verbosity=-1,
    )
    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )
    pipeline.fit(df[INPUT_COLUMNS], df[TARGET_COLUMN])
    return pipeline


def predict_lost_income(model: Pipeline, values: dict[str, Any]) -> LostIncomePrediction:
    """Validate one case and return a non-negative lost-income estimate."""
    validated = LostIncomeInput.model_validate(values)
    features = pd.DataFrame([_feature_dict(validated)], columns=INPUT_COLUMNS)
    raw_prediction = float(model.predict(features)[0])
    return LostIncomePrediction(estimated_lost_income=max(0.0, raw_prediction))


def _category_options(df: pd.DataFrame, column: str) -> list[str]:
    return sorted(value for value in df[column].dropna().astype(str).unique() if value.strip())


def _template_csv() -> bytes:
    columns = INPUT_COLUMNS + [TARGET_COLUMN]
    return pd.DataFrame(columns=columns).to_csv(index=False).encode("utf-8")


def render_lost_income_view() -> None:
    """Render the demo training and prediction workflow in Streamlit."""
    st.subheader("Estimated lost income")
    st.caption(
        "Demo LightGBM regression model. Upload labeled historical examples, train once, "
        "then enter a case to generate an estimated lost-income amount."
    )
    st.info(
        "Training data must contain the seven input columns plus a numeric `Lost Income` target. "
        "This demo estimate is model output only and should not be treated as a legal or financial calculation."
    )

    st.download_button(
        "Download training-data template",
        data=_template_csv(),
        file_name="lost_income_training_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader(
        "Upload lost-income training data",
        type=["csv", "xlsx"],
        key="lost_income_training_upload",
    )

    if uploaded is not None:
        try:
            raw_df = read_training_file(uploaded.name, uploaded.getvalue())
            st.dataframe(raw_df.head(20), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Could not read training data: {exc}")
            raw_df = None

        if raw_df is not None and st.button("Train model", type="primary", key="train_lost_income_model"):
            try:
                with st.spinner("Validating data and training LightGBM..."):
                    training_df = validate_training_data(raw_df)
                    model = train_lost_income_model(training_df)
                st.session_state["lost_income_model"] = model
                st.session_state["lost_income_training_df"] = training_df
                st.success(f"Model trained on {len(training_df)} validated row(s).")
            except Exception as exc:
                st.error(str(exc))

    model = st.session_state.get("lost_income_model")
    training_df = st.session_state.get("lost_income_training_df")
    if model is None or training_df is None:
        st.caption("Train a model above to enable predictions.")
        return

    st.divider()
    st.markdown("### Generate estimate")

    incident_options = _category_options(training_df, "Incident Type")
    injury_options = _category_options(training_df, "Injury")
    residency_options = _category_options(training_df, "Residency")
    type_options = _category_options(training_df, "Personal/Commerical")

    with st.form("lost_income_prediction_form"):
        col1, col2 = st.columns(2)
        with col1:
            incident_type = st.selectbox("Incident Type", incident_options)
            injury = st.selectbox("Injury", injury_options)
            salary = st.number_input("Salary", min_value=0.0, step=1_000.0, format="%.2f")
            dependents = st.number_input("Dependents", min_value=0, max_value=20, step=1)
        with col2:
            age = st.number_input("Age", min_value=0, max_value=120, step=1)
            residency = st.selectbox("Residency", residency_options)
            personal_commercial = st.selectbox("Personal/Commerical", type_options)

        submitted = st.form_submit_button("Estimate lost income", type="primary")

    if submitted:
        try:
            prediction = predict_lost_income(
                model,
                {
                    "Incident Type": incident_type,
                    "Injury": injury,
                    "Salary": salary,
                    "Dependents": dependents,
                    "Age": age,
                    "Residency": residency,
                    "Personal/Commerical": personal_commercial,
                },
            )
            st.metric(
                "Estimated lost income",
                f"${prediction.estimated_lost_income:,.2f}",
            )
        except ValidationError as exc:
            st.error(f"Prediction input failed validation: {exc}")
        except Exception as exc:
            st.error(f"Prediction failed: {exc}")
