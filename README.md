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
- **Summary** view using `Falconsai/medical_summarization` through the Hugging Face serverless Inference API
- Recursive chunk-and-summarize handling for chronologies larger than the model input window

## Project Structure

```text
├── app.py                         # Main Streamlit UI
├── data_loader.py                 # xlsx parsing + normalization + stable event IDs
├── injury_progression.py          # deterministic injury severity/trend inference + body-map timeline
├── summarizer.py                  # Hugging Face medical summarization adapter
├── drive_client.py                # optional Google Drive download logic
├── requirements.txt
├── tests/
│   └── test_injury_progression.py
├── .streamlit/
│   └── config.toml
└── scripts/
    └── create_sample_xlsx.py
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` and upload a medical chronology `.xlsx` file.

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

The demo uses the Apache-2.0 `Falconsai/medical_summarization` model through Hugging Face's hosted `hf-inference` provider. The Streamlit app therefore does not load or host a language model itself and no dedicated GPU endpoint is required.

### 1. Create a Hugging Face token

Create a Hugging Face access token with permission to use Inference Providers.

### 2. Add the token to Streamlit secrets

For local development, create `.streamlit/secrets.toml`. In Streamlit Community Cloud, open **App settings → Secrets**.

```toml
[huggingface]
api_token = "hf_YOUR_TOKEN"
```

Do not commit this token to GitHub.

### Summary behavior

The Summary tab sends the events selected by the existing sidebar filters to the summarizer. Because the model has a relatively small input window, the application:

1. orders the selected events chronologically;
2. divides the record text into conservative model-sized chunks;
3. summarizes each chunk through Hugging Face Inference;
4. recursively summarizes the intermediate results until one summary remains.

This is intentionally a lightweight demo architecture. `Falconsai/medical_summarization` is a task-specific summarization model rather than an instruction-following medical LLM, so the application does not claim sentence-level citations, diagnosis reasoning, or medical advice. The Summary tab displays the exact source events used so the output can be manually checked.

For large chronologies, narrow the event selection with the sidebar filters before generating a summary. This reduces inference calls and usually produces a more focused result.

## Injury Progression

The **Injury Progression** tab is designed as an auditable chronology aid rather than a clinical scoring system.

1. Choose whether to analyze the **entire chronology** or only the **currently filtered records**. Entire chronology is the default so a text, provider, or facility filter does not silently remove later improvement or resolution records.
2. Select the **body part** to follow. All medicine types are included by default, so emergency, radiology, orthopedics, physical therapy, and other records can contribute to one progression.
3. Severity and trend are inferred separately from body-specific sentences:
   - **Mild**: pain score 1–3/10 or mild/generic symptom evidence
   - **Moderate**: pain score 4–6/10 or moderate/functional findings such as limited range of motion or swelling
   - **Severe**: pain score 7–10/10 or strong findings such as severe symptoms, fracture, dislocation, rupture, or neurological deficit
   - **Trend**: new, improving, stable, worsening, resolved, or unknown
4. Numeric change is compared across events. For example, 9/10 → 7/10 remains severe but is marked **improving**, while 9/10 → 3/10 changes from severe to mild and is also marked improving.
5. The inference engine uses only sentences that mention the selected anatomy. If the spreadsheet lists a body part but the summary has no body-specific severity statement, the result remains **Unknown / low confidence** instead of borrowing severity language from another injury.
6. Negated findings such as “no fracture” are excluded from positive severity evidence.
7. Front and back body maps are separate. Unrecognized anatomy is reported as unmapped rather than being silently placed at a default torso coordinate.
8. Timeline spacing is proportional to elapsed time, and each progression point carries the stable event ID plus a source PDF link when available.

Expand **Review and correct inferred progression** to inspect the event ID, date, provider, facility, medicine type, pain score, confidence, matched evidence, and inference reason. Severity and trend can each be manually overridden before the figure is used.

The keyword/rule-based inference is intentionally deterministic and explainable, but it can still miss context or unusual terminology. Review inferred results against the underlying medical records.

## Deploy to Streamlit Community Cloud

1. Push the desired branch to GitHub.
2. Sign in at `share.streamlit.io` with the GitHub account that can access the repository.
3. Create an app using:
   - **Repository:** `BaylorBrangers/Swans_Hackathon`
   - **Branch:** your deployment branch
   - **Main file path:** `app.py`
4. Add the `[huggingface]` secret shown above.
5. Deploy.

Without the Hugging Face token, upload/search/timeline/chart functionality still works; the Summary tab displays configuration instructions instead of calling the model.

## Google Drive Setup (Optional)

`drive_client.py` remains available for automatic Drive loading. Configure a Google service account and grant it read access to the chronology file/folder before enabling that path.

## Security

- Never commit Hugging Face tokens, Google credentials, or `.streamlit/secrets.toml`.
- When a summary is generated, selected medical-record text is sent to Hugging Face's hosted inference service.
- Use synthetic or appropriately de-identified data for this demo unless you have confirmed that the chosen infrastructure and agreements are appropriate for identifiable health information.
- Generated summaries can omit or misstate information and must be checked against the source records.
