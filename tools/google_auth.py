"""
Shared Google OAuth + service builder.

Used by:
- send_new_gmail.py
- get_next_calendar_entries.py
- search_calendar_entries.py
- create_calendar_entries.py
- remove_calendar_entries.py
- read_sheet_entries.py
- write_sheet_entries.py

Expected files in same folder:
- credentials.json      Google OAuth Desktop Client JSON
- google_token.json     Generated combined token
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES: Final[list[str]] = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

BASE_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "Demo14_RPA"
CREDENTIALS_FILE: Final[Path] = BASE_DIR / "credentials.json"
TOKEN_FILE: Final[Path] = BASE_DIR / "google_token.json"


def load_credentials() -> Credentials:
    """
    Load, refresh, or create Google OAuth credentials.

    Uses google_token.json if present.
    Falls back to credentials.json or exactly one client_secret*.json file.
    """

    creds: Credentials | None = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        return creds

    credentials_path = _resolve_credentials_file()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path),
        SCOPES,
    )

    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds


def build_service(api_name: str, api_version: str):
    """
    Build an authenticated Google API service.

    Examples:
        gmail = build_service("gmail", "v1")
        calendar = build_service("calendar", "v3")
        sheets = build_service("sheets", "v4")
    """

    creds = load_credentials()
    return build(api_name, api_version, credentials=creds)


def resolve_default_calendar_id(prefer_family: bool = True) -> str:
    """
    Resolve the default calendar to use for RPA actions.

    Preference order:
    - Family calendar when present and prefer_family is True
    - primary calendar
    - first writable calendar
    """

    service = build_service("calendar", "v3")
    items = service.calendarList().list().execute().get("items", [])

    if prefer_family:
        for item in items:
            summary = (item.get("summary") or "").strip().lower()
            if summary == "family" and item.get("id"):
                return item["id"]

    for item in items:
        if item.get("primary") and item.get("id"):
            return item["id"]

    for item in items:
        if item.get("accessRole") in {"owner", "writer"} and item.get("id"):
            return item["id"]

    raise RuntimeError("No writable calendar found for the authenticated account.")


def list_writable_calendar_ids(prefer_family: bool = False) -> list[str]:
    """
    Return writable calendar IDs for the signed-in account.
    """

    service = build_service("calendar", "v3")
    items = service.calendarList().list().execute().get("items", [])

    ordered: list[str] = []
    if prefer_family:
        for item in items:
            summary = (item.get("summary") or "").strip().lower()
            if summary == "family" and item.get("id") and item.get("accessRole") in {"owner", "writer"}:
                ordered.append(item["id"])

    for item in items:
        if item.get("primary") and item.get("id") and item.get("accessRole") in {"owner", "writer"}:
            if item["id"] not in ordered:
                ordered.append(item["id"])

    for item in items:
        if item.get("accessRole") in {"owner", "writer"} and item.get("id"):
            if item["id"] not in ordered:
                ordered.append(item["id"])

    if not ordered:
        raise RuntimeError("No writable calendars found for the authenticated account.")

    return ordered


def _resolve_credentials_file() -> Path:
    """
    Resolve OAuth client file.

    Preferred:
        credentials.json

    Fallback:
        exactly one client_secret*.json in the same folder
    """

    if CREDENTIALS_FILE.exists():
        return CREDENTIALS_FILE

    matches = sorted(BASE_DIR.glob("client_secret*.json"))

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple OAuth JSON files found in {BASE_DIR}. "
            f"Rename one to {CREDENTIALS_FILE.name}."
        )

    raise RuntimeError(
        f"Missing OAuth client file: {CREDENTIALS_FILE}. "
        "Download a Desktop OAuth client JSON from Google Cloud and save it here, "
        "or keep exactly one client_secret*.json file in the folder."
    )


def safe_print(text: str) -> None:
    """
    Print UTF-8 safely on Windows terminals.
    """

    import sys

    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
