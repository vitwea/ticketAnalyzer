from __future__ import annotations

import base64
from typing import List, Tuple

from src.gmail.auth import get_gmail_service
from src.config.logger import get_logger

logger = get_logger(__name__)


def list_messages(query: str):
    """
    List Gmail messages matching a search query.
    Example query: 'from:mercadona'
    """
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q=query
    ).execute()

    return results.get("messages", [])


def get_message(message_id: str):
    """
    Retrieve a full Gmail message by ID.
    """
    service = get_gmail_service()
    return service.users().messages().get(
        userId="me",
        id=message_id
    ).execute()


def get_attachments_bytes(message_id: str) -> List[Tuple[str, str, bytes]]:
    """
    Return ALL attachments (PDFs, images, etc.) from a Gmail message as in-memory bytes.

    Returns:
        List of tuples: (filename, mime_type, file_bytes)
    """
    service = get_gmail_service()
    msg = get_message(message_id)

    attachments = []

    for part in msg.get("payload", {}).get("parts", []):
        filename = part.get("filename", "")
        mime_type = part.get("mimeType", "")

        # Skip empty attachments
        if not filename:
            continue

        # Only process attachments with body + attachmentId
        body = part.get("body", {})
        att_id = body.get("attachmentId")
        if not att_id:
            continue

        att = service.users().messages().attachments().get(
            userId="me",
            messageId=message_id,
            id=att_id
        ).execute()

        file_bytes = base64.urlsafe_b64decode(att["data"])

        attachments.append((filename, mime_type, file_bytes))

        logger.info(
            f"Loaded attachment '{filename}' ({mime_type}) into memory "
            f"({len(file_bytes)} bytes)."
        )

    return attachments
