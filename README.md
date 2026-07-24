# Medical Records Streamlit App

Streamlit webapp for personal injury lawyers to visualize medical chronology events from an Excel file stored in Google Drive.

## Features

- Loads medical chronology data from a Google Drive xlsx via service account
- Extracts embedded PDF hyperlinks from Excel cells
- Filterable sidebar: date range, record type, medicine type, facility, provider, body parts, and free-text search
- **Table** view with truncated summaries and CSV export
- **Timeline** view grouped by encounter date with full narratives and PDF links
- Local file fallback for development before Drive is configured

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

### 2. Create sample data (optional)

If you do not have the Caldwell sample file yet:

```bash
python scripts/create_sample_xlsx.py
```

This writes `sample_data/Caldwell - Medical Chronology.xlsx` with the expected schema.

### 3. Configure secrets

Create `.streamlit/secrets.toml` (never commit this file):

```toml
[drive]
file_id = "YOUR_GOOGLE_DRIVE_FILE_ID"

# Local dev — read from disk instead of Drive
local_xlsx_path = "sample_data/Caldwell - Medical Chronology.xlsx"

[google_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

For local testing with only the sample file, you can set `local_xlsx_path` and omit the Google service account fields until Drive is ready.

### 4. Run the app

```bash
streamlit run app.py
```

Open http://localhost:8501

## Google Cloud Setup (One-Time)

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

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Select your repo, branch, and main file `app.py`.
4. Open **Settings → Secrets** and paste your TOML (same structure as local secrets).
5. Remove `local_xlsx_path` from cloud secrets — production should use Drive only.
6. Deploy.

## Troubleshooting

| Issue | Fix |
| ----- | --- |
| "Configuration required" | Add `.streamlit/secrets.toml` locally or secrets in Streamlit Cloud |
| Drive 404 / file not found | Verify `file_id` and that the file is shared with the service account |
| Permission denied | Share the file/folder with the service account email as Viewer |
| Missing columns error | Ensure the xlsx matches the Caldwell schema above |
| Skipped rows warning | Some encounter dates could not be parsed (MM/DD/YYYY expected) |

## Security

- Service account credentials live in Streamlit secrets only — never commit JSON keys or `secrets.toml`.
- The app uses read-only Drive scope (`drive.readonly`).
- `.gitignore` excludes secrets, credential JSON, and virtual environments.
