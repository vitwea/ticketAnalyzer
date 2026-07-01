"""
src/gmail/reader.py

Gmail message listing and attachment download.

Note on L-4: get_attachments_bytes() previously called get_message() as a
helper, which internally called get_gmail_service() again — two service
instantiations per call.  It now calls the service directly with the
single instance obtained at the top of the function.
"""

from __future__ import annotations

import base64
from typing import List, Tuple

from src.gmail.auth import get_gmail_service
from src.config.logger import get_logger

logger = get_logger(__name__)


def list_messages(query: str) -> list[dict]:
    """
    List Gmail messages matching a search query.
    Example query: 'from:mercadona'
    """
    service = get_gmail_service()
    results = service.users().messages().list(userId="me", q=query).execute()
    return results.get("messages", [])


def get_message(message_id: str) -> dict:
    """Retrieve a full Gmail message by ID."""
    service = get_gmail_service()
    return service.users().messages().get(userId="me", id=message_id).execute()


def get_attachments_bytes(message_id: str) -> List[Tuple[str, str, bytes]]:
    """
    Return all attachments from a Gmail message as in-memory bytes.

    Returns:
        List of (filename, mime_type, file_bytes) tuples.
    """
    # Single service instance for all API calls in this function (L-4).
    # Previously, calling get_message() here caused a second get_gmail_service()
    # call, initialising the OAuth flow twice per attachment download.
    service = get_gmail_service()
    msg = service.users().messages().get(userId="me", id=message_id).execute()

    attachments: List[Tuple[str, str, bytes]] = []

    for part in msg.get("payload", {}).get("parts", []):
        filename  = part.get("filename", "")
        mime_type = part.get("mimeType", "")

        if not filename:
            continue

        body   = part.get("body", {})
        att_id = body.get("attachmentId")
        if not att_id:
            continue

        att = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=att_id
        ).execute()

        file_bytes = base64.urlsafe_b64decode(att["data"])
        attachments.append((filename, mime_type, file_bytes))

        logger.info(
            "Loaded attachment '%s' (%s) — %d bytes",
            filename, mime_type, len(file_bytes),
        )

    return attachments