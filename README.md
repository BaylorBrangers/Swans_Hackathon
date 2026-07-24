# Medical Records Streamlit App

Streamlit webapp for personal injury lawyers to visualize and summarize medical chronology events from Excel.

## Features

- **Drag-and-drop upload** — drop an xlsx file to load data immediately
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar: date range, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with event IDs, truncated narratives, and CSV export
- **Timeline** view grouped by encounter date with full narratives and PDF links
- **Charts** view for plotting selected event fields over time
- **Summary** view using a MedGemma inference endpoint
- Stable event-level citations such as `[E000123]` for checking generated claims against source records
- Hierarchical chunk-and-synthesize summarization for larger chronologies

## Project Structure

```text
├── app.py                 # Main Streamlit UI
├── data_loader.py         # xlsx parsing + normalization + stable event IDs
├── summarizer.py          # grounded hierarchical LLM summarization
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

Each source row receives a stable event ID based on its Excel row number. Generated summaries are instructed to cite these IDs so claims can be checked against the table/timeline and original PDF.

## MedGemma Summarization

The Streamlit process does **not** load a 4B model into memory. Instead it calls a private Hugging Face Inference Endpoint running `google/medgemma-4b-it` (or another OpenAI-compatible model endpoint).

Create the endpoint in Hugging Face, then configure local `.streamlit/secrets.toml` or Streamlit Community Cloud **Settings → Secrets**:

```toml
[summarization]
endpoint_url = "https://YOUR-ENDPOINT.endpoints.huggingface.cloud"
api_token = "hf_YOUR_TOKEN"
```

The Hugging Face `InferenceClient` automatically uses the endpoint's chat-completions interface.

### Summary behavior

The Summary tab operates on the events selected by the existing sidebar filters. The prompt requires the model to:

- use only supplied record facts
- preserve chronology
- avoid inferring diagnoses, causes, treatment rationale, or outcomes
- cite factual statements with event IDs
- explicitly report conflicts or unknown information

For larger selections, events are divided into chronological chunks, summarized separately, and then synthesized into a final longitudinal summary while retaining event citations.

Generated summaries still require human review. The citation mechanism improves traceability but does not guarantee factual correctness.

## Deploy to Streamlit Community Cloud

1. Push the desired branch to GitHub.
2. Sign in at `share.streamlit.io` with the GitHub account that can access the repository.
3. Create an app using:
   - **Repository:** `BaylorBrangers/Swans_Hackathon`
   - **Branch:** your deployment branch
   - **Main file path:** `app.py`
4. Add the `[summarization]` secrets above if you want summary generation enabled.
5. Deploy.

Without summarization secrets, upload/search/timeline/chart functionality still works; the Summary tab displays configuration instructions instead of calling a model.

## Google Drive Setup (Optional)

`drive_client.py` remains available for automatic Drive loading. Configure a Google service account and grant it read access to the chronology file/folder before enabling that path.

## Security

- Never commit Hugging Face tokens, Google credentials, or `.streamlit/secrets.toml`.
- Uploaded medical records and selected event text are sent to the configured inference endpoint when a summary is generated.
- For identifiable health information, use infrastructure and contractual controls appropriate to the data and applicable privacy requirements; do not assume a default public/serverless endpoint is suitable.
- Generated text is for record review, not medical advice.
