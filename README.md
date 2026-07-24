# Medical Records Streamlit App

Streamlit webapp for personal injury lawyers to visualize, search, and summarize medical chronology events from Excel.

## Features

- **Drag-and-drop upload** — drop an xlsx file to load data immediately
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar: date range, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with stable event IDs, truncated narratives, and CSV export
- **Timeline** view grouped by encounter date with full narratives and PDF links
- **Visual Timeline** view showing filtered events on a chronological stem-and-card timeline with hover details, zoom/pan, and a range slider
- **Charts** view for plotting selected event fields over time
- **Summary** view using `Falconsai/medical_summarization` through the Hugging Face serverless Inference API
- Recursive chunk-and-summarize handling for chronologies larger than the model input window

## Project Structure

```text
├── app.py                 # Main Streamlit UI
├── event_timeline.py      # Interactive Plotly event timeline
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

## Visual Event Timeline

The **Visual Timeline** tab uses the same DataFrame produced by the sidebar filters, so changes to date range, provider, facility, body part, record type, medicine type, or text search immediately change the events shown.

The timeline is designed to resemble a litigation-style medical chronology:

- encounter dates are positioned on the horizontal time axis;
- each event has a vertical stem and marker;
- event cards are staggered vertically to reduce overlap;
- cards show the date, event ID, record type, provider, and a short narrative excerpt;
- hovering over a marker shows fuller clinical details;
- events can be colored by record type, medicine type, facility, or provider;
- all filtered events remain plotted even when the number of visible cards is limited;
- the range slider and pan/zoom controls make dense or long chronologies easier to inspect.

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
