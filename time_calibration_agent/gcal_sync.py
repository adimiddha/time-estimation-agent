"""
Google Calendar OAuth sync helpers.
"""

import json
import os
from datetime import datetime
from typing import Optional, Tuple

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def build_flow(redirect_uri: str) -> Flow:
    client_config = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    return flow


def get_auth_url(redirect_uri: str, state: str) -> Tuple[str, Optional[str]]:
    """Returns (auth_url, code_verifier). code_verifier must be stored in
    the session and passed back to exchange_code() in the callback."""
    flow = build_flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return auth_url, flow.code_verifier


def exchange_code(redirect_uri: str, code: str, code_verifier: Optional[str] = None) -> Credentials:
    flow = build_flow(redirect_uri)
    flow.fetch_token(code=code, code_verifier=code_verifier)
    return flow.credentials


def load_credentials(tokens_path: str) -> Optional[Credentials]:
    if not os.path.exists(tokens_path):
        return None
    try:
        with open(tokens_path) as f:
            creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
    except Exception:
        return None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds, tokens_path)
    return creds if creds and creds.valid else None


def _save_credentials(creds: Credentials, tokens_path: str) -> None:
    os.makedirs(os.path.dirname(tokens_path), exist_ok=True)
    with open(tokens_path, "w") as f:
        f.write(creds.to_json())


def push_events(credentials: Credentials, time_blocks: list, session_date: str, timezone: str = "UTC") -> int:
    service = build("calendar", "v3", credentials=credentials)
    count = 0
    for block in time_blocks:
        event = build_event(block, session_date, timezone)
        if event:
            service.events().insert(calendarId="primary", body=event).execute()
            count += 1
    return count


def build_event(block: dict, date_str: str, timezone: str = "UTC") -> Optional[dict]:
    try:
        start_str = block["start"]  # "HH:MM"
        end_str = block["end"]
        task = block.get("task", "Task").replace("\r", "").replace("\n", " ")
    except KeyError:
        return None

    year, month, day = date_str.split("-")
    sh, sm = start_str.split(":")
    eh, em = end_str.split(":")

    dt_start = f"{year}-{month}-{day}T{sh}:{sm}:00"
    dt_end = f"{year}-{month}-{day}T{eh}:{em}:00"

    kind = block.get("kind", "task")
    color_map = {"task": "9", "fixed": "6", "break": "2"}
    color_id = color_map.get(kind, "9")

    return {
        "summary": task,
        "start": {"dateTime": dt_start, "timeZone": timezone},
        "end": {"dateTime": dt_end, "timeZone": timezone},
        "colorId": color_id,
    }
