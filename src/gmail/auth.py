from __future__ import annotations

from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from src.config.settings import settings
from src.config.logger import get_logger

logger = get_logger(__name__)


def get_gmail_service():
    """
    Authenticate with Gmail API and return a service client.
    Handles token creation and refresh automatically.
    """
    creds = None

    token_path       = settings.gmail_token_path
    credentials_path = settings.gmail_credentials_path

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_path), settings.gmail_scopes
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail token...")
            creds.refresh(Request())
        else:
            logger.info("Starting Gmail OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), settings.gmail_scopes
            )
            creds = flow.run_local_server(port=0)

        # L-2: create parent directory if needed and handle write errors
        try:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
            logger.info("Saved new Gmail token to %s", token_path)
        except OSError as exc:
            logger.error("Could not save Gmail token to %s: %s", token_path, exc)
            raise

    return build("gmail", "v1", credentials=creds)