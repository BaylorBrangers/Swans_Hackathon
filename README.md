# Medical Records Streamlit App

Streamlit web application for personal injury lawyers to visualize, search, summarize, and analyze medical chronology events from Excel files.

## Features

- **Drag-and-drop upload** for medical chronology `.xlsx` files
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar for dates, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with stable event IDs, truncated narratives, and CSV export
- **Timeline** view grouped by encounter date with narratives and PDF links
- **Charts** view for plotting selected event fields over time
- **Injury Progression** view with deterministic severity/trend inference, source-linked body maps, confidence review, and manual overrides
- **Summary** view using `google/medgemma-27b-text-it` through Hugging Face Inference Providers
- **Lost Income** demo using validated uploaded training data and an in-session LightGBM regression pipeline
- Optional Google Drive loading

## Project Structure

```text
├── app.py                         # Main Streamlit UI
├── data_loader.py                 # XLSX parsing, normalization, and stable event IDs
├── injury_progression.py          # Deterministic severity/trend inference and body-map timeline
├── lost_income.py                 # Pydantic validation and LightGBM demo model
├── summarizer.py                  # Hugging Face medical summarization adapter
├── drive_client.py                # Optional Google Drive download logic
├── tests/
│   ├── test_injury_progression.py
│   └── test_lost_income.py
├── pyproject.toml                 # Primary Python dependency definition for uv
├── requirements.txt               # Compatibility file for Streamlit Community Cloud
├── .python-version                # Python 3.12
├── Dockerfile
├── .dockerignore
└── .streamlit/
    └── config.toml
```

## Local Development with uv

Install `uv`, then run:

```bash
uv sync
uv run streamlit run app.py
```

Open `http://localhost:8501`.

The first project sync creates `uv.lock`. Commit that file after generating it so future installs can use the exact dependency graph:

```bash
uv lock
uv sync --locked
```

The existing pip workflow remains available if needed:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Docker

### Build the image

```bash
docker build -t swans-medical-chronology .
```

### Run without external summarization

```bash
docker run --rm -p 8501:8501 swans-medical-chronology
```

Open `http://localhost:8501`.

### Run with Hugging Face credentials

Create a local `.streamlit/secrets.toml` file:

```toml
[huggingface]
api_token = "hf_YOUR_TOKEN"
```

Then mount it read-only when starting the container:

```bash
docker run --rm \
  -p 8501:8501 \
  -v "$PWD/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  swans-medical-chronology
```

Do not copy API tokens or credentials into the Dockerfile or image.

### Container data behavior

Uploaded medical files, uploaded lost-income training data, parsed DataFrames, and the trained LightGBM pipeline remain in the running Streamlit process/container memory. They are not persisted by this Docker setup. Restarting or replacing the container removes that in-memory state.

The MedGemma Summary feature is different: when the user requests a summary, selected chronology text is sent to the configured external Hugging Face inference provider.

## Expected Medical Chronology Schema

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

Each source row receives a stable event ID based on its Excel row number. These IDs remain visible so generated outputs can be checked against the source records.

## Lost Income Training Schema

The demo training upload accepts CSV or XLSX data with these columns:

| Input/target column |
| --- |
| Incident Type |
| Injury |
| Salary |
| Dependents |
| Age |
| Residency |
| Personal/Commerical |
| Lost Income |

The corrected spelling `Personal/Commercial` is also accepted and normalized. The model is a deliberately simple LightGBM regressor stored only in Streamlit session state. Its output is synthetic/demo functionality, not a legal, actuarial, or financial damages calculation.

## Medical Summarization

The Summary tab sends the events selected by the sidebar filters to `google/medgemma-27b-text-it` through Hugging Face Inference Providers. The application does not host the language model inside Streamlit or inside the Docker container.

For large chronologies, the application orders records chronologically, divides them into chunks, summarizes each chunk, and recursively reduces the intermediate summaries.

Without a Hugging Face token, the local table, timeline, charts, injury progression, and lost-income features remain available.

## Injury Progression

The **Injury Progression** tab is an auditable chronology aid rather than a clinical scoring system.

1. Choose the entire chronology or the currently filtered records.
2. Select the body part and medicine types to include.
3. Severity and trend are inferred separately from body-specific sentences.
4. Pain scores map to resolved, mild, moderate, or severe categories.
5. Explicit improvement, worsening, stability, and resolution language informs trend.
6. When appropriate, numeric pain/severity changes are compared across events.
7. Negated findings such as “no fracture” are excluded from positive severity evidence.
8. Once severity is established, a later encounter without new severity evidence can carry forward the previous state and is explicitly marked as carried forward.
9. Every progression point retains event IDs, evidence, provider/facility metadata, medicine type, and source links when available.

Review inferred results against the underlying records. The rules are intentionally deterministic and explainable, but they can miss unusual terminology or context.

## Tests

Run the test suite with:

```bash
uv run python -m unittest discover -s tests -v
```

## Deploy to Streamlit Community Cloud

1. Push the desired branch to GitHub.
2. Create the app at `share.streamlit.io` using:
   - **Repository:** `BaylorBrangers/Swans_Hackathon`
   - **Branch:** the desired deployment branch
   - **Main file:** `app.py`
3. Add the `[huggingface]` secret if the Summary feature should be enabled.
4. Deploy.

`requirements.txt` is retained so the existing Community Cloud deployment path continues to work.

## Google Drive Setup (Optional)

`drive_client.py` remains available for automatic Drive loading. Configure a Google service account and grant it read access to the required chronology file or folder before enabling that path.

## Security

- Never commit Hugging Face tokens, Google credentials, `.env`, or `.streamlit/secrets.toml`.
- `.dockerignore` excludes common credential files and Excel/CSV data from image builds.
- Use synthetic or appropriately de-identified medical data unless the deployment infrastructure and contractual controls are suitable for identifiable health information.
- Generated summaries and inferred severity/progression results must be checked against source records.
