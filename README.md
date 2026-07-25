# Medical Records Streamlit App

Streamlit webapp for personal injury lawyers to visualize, search, and summarize medical chronology events from Excel.

## Features

- **Drag-and-drop upload** — drop an xlsx file to load data immediately
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar: date range, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with stable event IDs, truncated narratives, and CSV export
- **Timeline** view grouped by encounter date with full narratives and PDF links
- **Charts** view for plotting selected record types, medicine types, facilities, providers, or body parts by day, week, or month
- **Injury Progression** view with source-linked front/back body maps, separate severity and trend, confidence review, and manual overrides
- Google Drive auto-load (optional, configure later via Streamlit secrets)
- **Summary** view using Hugging Face hosted inference
- **Lost Income** demo using Pydantic validation and an in-session LightGBM regression pipeline

## Project Structure

```text
├── app.py                         # Main Streamlit UI
├── data_loader.py                 # xlsx parsing + normalization + stable event IDs
├── injury_progression.py          # deterministic injury severity/trend inference + body-map timeline
├── lost_income.py                 # validation, LightGBM training, and prediction UI
├── summarizer.py                  # Hugging Face medical summarization adapter
├── drive_client.py                # optional Google Drive download logic
├── pyproject.toml                 # uv/Python project dependencies
├── requirements.txt               # retained for Streamlit Community Cloud compatibility
├── Dockerfile
├── .dockerignore
├── tests/
├── .streamlit/
│   └── config.toml
└── scripts/
    └── create_sample_xlsx.py
```

## Local Development with uv

Install `uv`, then run:

```bash
uv sync --dev
uv run streamlit run app.py
```

Open `http://localhost:8501` and upload a medical chronology `.xlsx` file.

`pyproject.toml` is the dependency source of truth for local development and Docker. `requirements.txt` is retained because Streamlit Community Cloud can install it directly.

## Run with Docker

Build the image from the repository root:

```bash
docker build -t swans-medical-app .
```

Run it:

```bash
docker run --rm -p 8501:8501 swans-medical-app
```

Then open `http://localhost:8501`.

### Run with Hugging Face secrets

Do not copy or commit `.streamlit/secrets.toml`. Mount it into the running container instead:

```bash
docker run --rm \
  -p 8501:8501 \
  -v "$(pwd)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  swans-medical-app
```

Uploaded spreadsheets and the trained LightGBM pipeline remain in the running Streamlit process memory. They are not built into the Docker image and disappear when the container is stopped or restarted.

## Expected Excel Schema

| Column | Example |
| --- | --- |
| Encounter Date | 12/07/2024 |
| Primary Provider | Eric Mast, DO; Grant T. Olsen, NP |
| Facility | Fisher-Titus Medical Center |
| Body Parts | Hand, Neck, Back, Head, Shoulder |
| Medicine Type | Emergency Medicine |
| Record Type | Encounter Note |
| Summary | Clinical narrative |
| Link To Pdf | Cell text with hyperlink URL |

Each source row receives a stable event ID based on its Excel row number. These IDs remain visible in the table and timeline so generated outputs can be checked against the source records.

## Medical Summarization

The Summary tab sends selected chronology text to the configured Hugging Face inference provider. The Streamlit application does not load the language model into the Docker container.

### 1. Create a Hugging Face token

Create a Hugging Face access token with permission to use Inference Providers.

### 2. Add the token to Streamlit secrets

For local development, create `.streamlit/secrets.toml`. In Streamlit Community Cloud, open **App settings → Secrets**.

```toml
[huggingface]
api_token = "hf_YOUR_TOKEN"
```

Do not commit this token to GitHub.

## Injury Progression

The **Injury Progression** tab is designed as an auditable chronology aid rather than a clinical scoring system.

1. Choose whether to analyze the **entire chronology** or only the **currently filtered records**.
2. Select the **body part** to follow. All medicine types are selected by default so records form one continuous progression.
3. Every selected encounter remains on the timeline after severity has been established. If a later record has no new severity estimate, the prior severity is carried forward and labeled as such.
4. Severity and trend are inferred separately from body-specific sentences:
   - **Mild**: pain score 1–3/10 or mild/generic symptom evidence
   - **Moderate**: pain score 4–6/10 or functional findings such as limited range of motion or swelling
   - **Severe**: pain score 7–10/10 or strong findings such as fracture, dislocation, rupture, or neurological deficit
   - **Trend**: new, improving, stable, worsening, resolved, or unknown
5. Numeric change is compared across events. For example, 9/10 → 7/10 remains severe but is marked **improving**.
6. Negated findings such as “no fracture” are excluded from positive severity evidence.

Expand **Review and correct inferred progression** to inspect and manually override the inferred severity or trend. The rule-based inference can still miss unusual terminology and should be reviewed against the source record.

## Deploy to Streamlit Community Cloud

1. Push the desired branch to GitHub.
2. Sign in at `share.streamlit.io` with the GitHub account that can access the repository.
3. Create an app using:
   - **Repository:** `BaylorBrangers/Swans_Hackathon`
   - **Branch:** your deployment branch
   - **Main file path:** `app.py`
4. Add the `[huggingface]` secret shown above.
5. Deploy.

## Google Drive Setup (Optional)

`drive_client.py` remains available for automatic Drive loading. Configure a Google service account and grant it read access to the chronology file/folder before enabling that path.

## Security

- Never commit Hugging Face tokens, Google credentials, `.env`, or `.streamlit/secrets.toml`.
- When a summary is generated, selected medical-record text is sent to the configured external inference service.
- Use synthetic or appropriately de-identified data unless the infrastructure and agreements are appropriate for identifiable health information.
- Generated summaries and inferred injury progression must be checked against the source records.
