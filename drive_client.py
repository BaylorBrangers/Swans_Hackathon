"""Google Drive download helpers for medical chronology xlsx files."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def build_drive_service(service_account_info: dict[str, Any]):
    """Authenticate with a service account and return a Drive API client."""
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def download_file_bytes(service, file_id: str) -> bytes:
    """Download a Drive file by ID and return its raw bytes."""
    request = service.files().get_media(fileId=file_id)
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    return buffer.getvalue()
