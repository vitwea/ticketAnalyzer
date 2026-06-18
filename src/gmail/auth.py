from __future__ import annotations

import os
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

    token_path = settings.gmail_token_path
    credentials_path = settings.gmail_credentials_path

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(
            token_path,
            settings.gmail_scopes
        )

    # If no valid token → login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail token...")
            creds.refresh(Request())
        else:
            logger.info("Starting Gmail OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path,
                settings.gmail_scopes
            )
            creds = flow.run_local_server(port=0)

        # Save token
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
            logger.info("Saved new Gmail token.")

    # Build Gmail client
    service = build("gmail", "v1", credentials=creds)
    return service
