# Medical Records Streamlit App

Streamlit webapp for personal injury lawyers to visualize, search, and summarize medical chronology events from Excel.

## Features

- **Drag-and-drop upload** — drop an xlsx file to load data immediately
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar: date range, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with stable event IDs, truncated narratives, and CSV export
- **Timeline** view grouped by encounter date with full narratives and PDF links
- **Charts** view for plotting selected record types, medicine types, facilities, providers, or body parts by day, week, or month
- **Injury Progression** view with body-outline markers showing inferred injury severity over time
- Google Drive auto-load (optional, configure later via Streamlit secrets)
- **Summary** view using `Falconsai/medical_summarization` through the Hugging Face serverless Inference API
- Recursive chunk-and-summarize handling for chronologies larger than the model input window

## Project Structure

```text
├── app.py                 # Main Streamlit UI
├── data_loader.py         # xlsx parsing + normalization + stable event IDs
├── summarizer.py          # Hugging Face medical summarization adapter
├── drive_client.py        # optional Google Drive download logic
├── requirements.txt
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

Each source row receives a stable event ID based on its Excel row number. These IDs remain visible in the table and timeline so a generated summary can be checked against the source records.

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

The **Injury Progression** tab:

1. Filters the current events to one selected `Medicine Type`.
2. Uses `Body Parts` to position circles on a front-facing body outline.
3. Infers status from body-specific sentences in `Summary`:
   - Yellow: injury, pain, tenderness, sprain, strain, or pain score 1–5/10
   - Orange: worsening, increased/persistent symptoms, swelling, limited range of motion, or pain score 6–8/10
   - Red: severe/intractable symptoms, fracture, dislocation, neurological deficit, or pain score 9–10/10
4. Ignores negated findings such as “no fracture.”
5. Carries status forward, lowers it for improvement, and removes resolved injuries.
6. Displays a new body outline only when a status changes.

Expand **Review and correct inferred severity** to inspect the matched phrase and
manually override any result before using the figure. You may upload a PNG/JPEG
copy of the supplied body outline or use the built-in outline.

Keyword inference is an aid, not a clinical conclusion. Review all inferred
statuses against the source medical records.

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
