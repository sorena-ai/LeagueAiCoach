"""Append one Sensii waitlist signup to a Google Sheet.

The service-account JSON and spreadsheet id come from settings. A missing
key or a Sheets error is raised here; the route turns that into 503.
"""

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class WaitlistUnavailable(Exception):
    """The sheet is not configured, or Google rejected the append."""


def append_waitlist_row(row: list[str]) -> None:
    raw = settings.waitlist_google_credentials.strip()
    spreadsheet_id = settings.waitlist_spreadsheet_id.strip()
    if not raw or not spreadsheet_id:
        raise WaitlistUnavailable("waitlist sheet is not configured")

    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WaitlistUnavailable("waitlist credentials are not valid JSON") from exc

    tab = settings.waitlist_sheet_tab.strip() or "Sheet1"
    escaped = tab.replace("'", "''")
    range_name = f"'{escaped}'!A:J"

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
    except WaitlistUnavailable:
        raise
    except Exception as exc:
        logger.exception("Waitlist sheet append failed")
        raise WaitlistUnavailable("waitlist sheet append failed") from exc
