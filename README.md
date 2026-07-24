# Medical Records Streamlit App

Streamlit webapp for personal injury lawyers to visualize medical chronology events from an Excel file stored in Google Drive.

## Features

- **Drag-and-drop upload** — drop an xlsx file to load data immediately (works locally and on Streamlit Cloud)
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar: date range, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with truncated summaries and CSV export
- **Timeline** view grouped by encounter date with full narratives and PDF links
- **Charts** view for plotting selected record types, medicine types, facilities, providers, or body parts by day, week, or month
- Google Drive auto-load (optional, configure later via Streamlit secrets)

## Project Structure

```
├── app.py                 # Main Streamlit UI
├── drive_client.py        # Google Drive download logic
├── data_loader.py         # xlsx parsing + column normalization
├── requirements.txt
├── .streamlit/
│   └── config.toml        # Page title, layout
├── scripts/
│   └── create_sample_xlsx.py
└── README.md
```

## Quick Start (Local)

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

Open http://localhost:8501 and **drag and drop** your medical chronology `.xlsx` file onto the upload area. No Google Drive setup is required to get started.

### 3. Sample data (optional)

To try the app without your own file:

```bash
python scripts/create_sample_xlsx.py
```

Then upload `sample_data/Caldwell - Medical Chronology.xlsx` in the app.

## Google Drive Setup (Optional — Later)

Google Drive integration is available in `drive_client.py` for when you want to load files automatically instead of uploading each time. Setup steps:

1. Create a [Google Cloud project](https://console.cloud.google.com/).
2. Enable the **Google Drive API** (APIs & Services → Library → Google Drive API → Enable).
3. Create a **service account** (IAM & Admin → Service Accounts → Create).
4. Create and download a JSON key for the service account.
5. Upload your chronology xlsx to Google Drive.
6. Share the file (or its parent folder) with the service account email (`...@....iam.gserviceaccount.com`) as **Viewer**.
7. Copy the **file ID** from the Drive URL:
   ```
   https://drive.google.com/file/d/<FILE_ID>/view
   ```

## Expected Excel Schema

Single sheet with these columns (Caldwell chronology format):

| Column             | Example                             |
| ------------------ | ----------------------------------- |
| Encounter Date     | 12/07/2024                          |
| Primary Provider   | Eric Mast, DO; Grant T. Olsen, NP   |
| Facility           | Fisher-Titus Medical Center         |
| Body Parts         | Hand, Neck, Back, Head, Shoulder    |
| Medicine Type      | Emergency Medicine                  |
| Record Type        | Encounter Note                      |
| Summary            | Clinical narrative                  |
| Link To Pdf        | Cell text "pdf" with hyperlink URL  |

The app reads hyperlink targets from the **Link To Pdf** column using openpyxl.

## Deploy to Streamlit Community Cloud

No secrets are required for the current drag-and-drop workflow. Google Drive secrets can be added later when you enable that integration.

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with the same GitHub account that owns the repo.
2. Click **Create app**.
3. Fill in:
   - **Repository:** `BaylorBrangers/Swans_Hackathon`
   - **Branch:** `main` (or `cursor/medical-records-streamlit-56e5` if not merged yet)
   - **Main file path:** `app.py`
4. Click **Deploy**. Streamlit installs from `requirements.txt` automatically.
5. When the app loads, drag and drop your `.xlsx` file on the public URL (e.g. `https://your-app-name.streamlit.app`).

**Optional later:** Settings → Secrets → add Google Drive service account TOML when you want automatic Drive loading instead of manual upload.

## Troubleshooting

| Issue | Fix |
| ----- | --- |
| "Could not read the uploaded file" | Ensure the xlsx matches the Caldwell schema below |
| Missing columns error | Verify column names match exactly (see schema table) |
| Skipped rows warning | Some encounter dates could not be parsed (MM/DD/YYYY expected) |
| Drive 404 / file not found (optional) | Verify `file_id` and that the file is shared with the service account |
| Permission denied (optional) | Share the file/folder with the service account email as Viewer |

## Security

- Service account credentials live in Streamlit secrets only — never commit JSON keys or `secrets.toml`.
- The app uses read-only Drive scope (`drive.readonly`).
- `.gitignore` excludes secrets, credential JSON, and virtual environments.
