# SWANS Medical Chronology Demo

A Streamlit application for exploring medical chronologies used in personal-injury case review. The app loads a structured Excel chronology, provides searchable timeline and chart views, derives an auditable rule-based injury progression, can generate a medical-record summary through MedGemma, and includes a separate demonstration LightGBM model for estimated lost income.

This repository is a **demo / prototype**, not a clinical decision system, damages calculator, or production medical-record platform.

## What the app currently does

After a medical chronology `.xlsx` file is uploaded, the application exposes six tabs:

```text
Table | Timeline | Charts | Injury Progression | Summary | Lost Income
```

### Table

- Displays the filtered chronology as a structured table.
- Uses stable event IDs derived from the source Excel row number.
- Shows abbreviated narrative text and source PDF links where available.
- Supports CSV export of the filtered records.

### Timeline

- Displays events grouped chronologically.
- Retains full narrative text, provider/facility metadata, event IDs, and PDF links.
- Uses the same sidebar filters as the table and chart views.

### Charts

- Aggregates filtered events by day, week, or month.
- Can chart record type, medicine type, facility, provider, or body part.

### Injury Progression

The injury-progression module is **deterministic and rule-based**. It is not an ML model and does not call MedGemma.

For each body part, the module:

1. normalizes anatomy names and common aliases such as cervical spine → neck and lumbar spine → lower back;
2. isolates sentences that specifically mention that body part and, where possible, laterality;
3. ignores negated findings such as `no fracture` as positive severity evidence;
4. assigns a suggested severity from explicit pain scores and predefined textual/structural findings;
5. infers trend separately from severity;
6. processes encounters in chronological order and maintains the most recently established state for each body part;
7. carries the prior severity forward when a later encounter has no new severity evidence, while labeling that point as carried forward;
8. preserves the source event ID, provider, facility, medicine type, evidence text, confidence label, and PDF link for review.

Severity scale:

| Score | Label | Typical rule evidence |
| ---: | --- | --- |
| 0 | Resolved | pain-free, asymptomatic, resolved, 0/10 |
| 1 | Mild | pain 1–3/10, mild symptoms, tenderness, soreness, sprain/strain |
| 2 | Moderate | pain 4–6/10, moderate symptoms, limited range of motion, swelling, weakness |
| 3 | Severe | pain 7–10/10, severe symptoms, fracture, dislocation, rupture, neurological deficit |

Trend is independent of severity and can be:

```text
New | Improving | Stable | Worsening | Resolved | Unknown
```

Explicit trend language is used first. If no explicit trend is found, the module compares current and previous pain scores when both are available; otherwise it compares current and previous severity. For example, 9/10 → 7/10 remains **Severe** but is marked **Improving**.

The detailed progression includes a human-review table where severity and trend can be overridden. The heuristic is intended to make chronology review easier and auditable; it can still miss unusual terminology or clinical context and should be checked against the underlying records.

### Summary

The Summary tab sends the currently filtered chronology text to:

```text
google/medgemma-27b-text-it
```

through Hugging Face Inference Providers. The code currently configures:

```text
provider = featherless-ai
```

The MedGemma model is **not loaded into the Streamlit process or Docker container**. The application formats the selected chronology into chronological chunks, sends them to the external inference service, and recursively reduces partial summaries when required.

The prompt instructs the model to preserve event IDs, distinguish reported symptoms from objective findings, retain clinically relevant changes over time, and avoid inventing diagnoses or causation.

Generated summaries are model output and must be checked against the source records.

### Lost Income

The Lost Income tab is a separate demonstration ML workflow. It does not use the medical chronology as model-training data.

The user uploads labeled CSV or XLSX training data containing:

| Column | Type / role |
| --- | --- |
| Incident Type | categorical feature |
| Injury | categorical feature |
| Salary | numeric feature, non-negative |
| Dependents | integer feature, 0–20 |
| Age | integer feature, 0–120 |
| Residency | categorical feature |
| Personal/Commerical | categorical feature: Personal or Commercial |
| Lost Income | non-negative numeric training target |

`Personal/Commercial` is also accepted as an input header and normalized to the current internal spelling `Personal/Commerical`.

Every training row is validated with Pydantic before fitting. Categorical variables are one-hot encoded, numeric variables are passed through unchanged, and the model is a fixed LightGBM regressor:

```text
LGBMRegressor
objective = regression
n_estimators = 100
random_state = 42
```

There is currently **no hyperparameter optimization, train/test split, cross-validation, or model-performance reporting**. The purpose is to demonstrate an upload → validate → train → predict workflow, not to provide a defensible damages model.

The fitted sklearn/LightGBM pipeline and validated training DataFrame are stored in Streamlit session state. They are not persisted to a database or model registry. The displayed prediction currently uses a `$` prefix; the training schema itself does not contain currency metadata.

## Input chronology schema

The primary chronology upload must be an `.xlsx` file with the following columns:

| Column | Example |
| --- | --- |
| Encounter Date | 12/07/2024 |
| Primary Provider | Eric Mast, DO; Grant T. Olsen, NP |
| Facility | Fisher-Titus Medical Center |
| Body Parts | Hand, Neck, Back, Head, Shoulder |
| Medicine Type | Emergency Medicine |
| Record Type | Encounter Note |
| Summary | Clinical narrative |
| Link To Pdf | cell text and/or hyperlink URL |

Rows with unparseable encounter dates are skipped and reported in the sidebar.

Each valid source row receives a stable event ID based on its original Excel row number. These IDs are carried into the table, timeline, injury-progression output, and MedGemma prompt so generated outputs can be traced back to source events.

## Project structure

```text
├── app.py                    # Main Streamlit application and six-tab UI
├── data_loader.py            # XLSX parsing, normalization, hyperlinks, stable event IDs
├── injury_progression.py     # Rule-based severity/trend inference and body-map timeline
├── lost_income.py            # Pydantic validation + LightGBM upload/train/predict demo
├── summarizer.py             # MedGemma/Hugging Face inference adapter
├── drive_client.py           # Google Drive helper; not currently wired into the main upload flow
├── requirements.txt          # Dependency list used by Streamlit Community Cloud
├── pyproject.toml            # Python project/dependency definition for uv and Docker
├── Dockerfile                # Python 3.12 container running Streamlit on port 8501
├── .dockerignore             # Excludes secrets, local environments, caches, and data files
├── tests/
├── .streamlit/
│   └── config.toml
└── scripts/
    └── create_sample_xlsx.py
```

## Local development with uv

Python `>=3.11,<3.13` is declared in `pyproject.toml`.

Install [uv](https://docs.astral.sh/uv/) and run:

```bash
uv sync --dev
uv run streamlit run app.py
```

Open:

```text
http://localhost:8501
```

`pyproject.toml` currently defines the uv dependencies. A committed `uv.lock` is not yet included in this repository, so dependency resolution is not fully locked across installs.

`requirements.txt` is retained because the application can also be deployed directly through Streamlit Community Cloud.

## Hugging Face / MedGemma configuration

The Summary tab requires a Hugging Face token with access to the configured inference provider/model.

For local development, create:

```text
.streamlit/secrets.toml
```

with:

```toml
[huggingface]
api_token = "hf_YOUR_TOKEN"
```

Do not commit this file or the token.

Without the token, the rest of the application still runs; the Summary tab displays a configuration warning instead of making an inference request.

## Docker

The repository contains a Dockerfile for running the complete Streamlit application in a reproducible Linux environment.

Build from the repository root:

```bash
docker build -t swans-medical-app .
```

Run:

```bash
docker run --rm -p 8501:8501 swans-medical-app
```

Then open:

```text
http://localhost:8501
```

To make the Hugging Face Streamlit secret available without baking it into the image:

```bash
docker run --rm \
  -p 8501:8501 \
  -v "$(pwd)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  swans-medical-app
```

The image installs the GNU OpenMP runtime required by LightGBM and runs Streamlit on `0.0.0.0:8501`.

## Deployment

### Streamlit Community Cloud

Streamlit Community Cloud deploys directly from the GitHub repository; it does **not** build or run this repository's Dockerfile.

Configure:

```text
Repository:     BaylorBrangers/Swans_Hackathon
Branch:         desired deployment branch
Main file path: app.py
```

Add the Hugging Face token under the app's Streamlit Secrets configuration using the TOML block shown above.

### Container platforms / Google Cloud Run

The Docker image can be deployed to a container host such as Google Cloud Run, Render, Azure Container Apps, or another Docker-compatible service.

The current Dockerfile listens on port `8501`, so a platform deploying it without modification must route traffic to container port `8501`.

For Cloud Run, a straightforward configuration is:

```text
Source repository: BaylorBrangers/Swans_Hackathon
Build type:        Dockerfile
Container port:    8501
```

Secrets should be supplied at runtime rather than committed to the image. For example, on Cloud Run a Streamlit `secrets.toml` can be provided from Secret Manager as a mounted secret file.

## Data and model storage

There is currently **no application database, object store, or persistent model store**.

### Medical chronology

When a chronology is uploaded:

1. the uploaded XLSX bytes are stored in Streamlit session state;
2. the workbook is parsed into a pandas DataFrame;
3. the current `parse_uploaded_xlsx` function uses `st.cache_data`, so the parsed result may also remain in Streamlit's application cache beyond the immediate session.

The application does not intentionally write the uploaded chronology to GitHub or to a database.

### Lost-income training data and model

After training:

```text
validated training DataFrame → Streamlit session_state
trained sklearn/LightGBM pipeline → Streamlit session_state
```

Neither is intentionally persisted to disk or an external model registry. If the Streamlit process/container is replaced, the in-memory trained model is lost and must be trained again.

### External data transmission

The Table, Timeline, Charts, Injury Progression, and LightGBM training/prediction paths run within the Streamlit Python process.

When **Generate summary** is clicked, the selected chronology text is transmitted outside the Streamlit application through Hugging Face Inference Providers to the configured inference provider for MedGemma processing.

## Google Drive helper

`drive_client.py` contains code intended to support Google Drive downloads, but the current `app.py` upload workflow is based on the Streamlit file uploader. Google Drive auto-loading is therefore **not currently an active user-facing feature** of the main application.

## Tests

The repository contains tests covering the deterministic injury-progression logic and the lost-income validation/training workflow.

With the development dependencies installed:

```bash
uv run pytest
```

## Important limitations

- The injury-progression severity scale is a custom deterministic heuristic, not a validated clinical severity instrument.
- Trend inference is based on explicit language and/or changes in pain/severity state; it does not constitute a clinical prognosis.
- MedGemma summaries may omit or misstate information and must be checked against source records.
- The Lost Income model is a demonstration regressor and is not a legal, actuarial, economic, or financial damages methodology.
- The app has no user authentication, application database, durable upload storage, or durable model storage.
- The current app requires a chronology XLSX to be loaded before the six tabs, including Lost Income, are rendered.
- If sidebar filters produce zero chronology events, the current app returns before rendering the tabs.

## Security and privacy

- Never commit Hugging Face tokens, Google credentials, `.env`, or `.streamlit/secrets.toml`.
- `.dockerignore` excludes common secret files and spreadsheet/CSV data from the Docker build context.
- The application is a prototype and has not been presented as HIPAA-, GDPR-, or other health-data-compliance certified infrastructure.
- Use synthetic or appropriately de-identified data unless the deployment environment, external inference provider, access controls, retention behavior, and contractual arrangements have been reviewed for the intended data.

## Intended use

This project demonstrates how a medical chronology can be transformed into searchable, visual, auditable case-review views and combined with simple ML/LLM components. It is intended for prototyping, teaching, and hackathon/demo use rather than unsupervised clinical, legal, or financial decision-making.
