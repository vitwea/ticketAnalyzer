import base64
from unittest.mock import patch

from src.gmail.reader import get_attachments_bytes


def test_get_attachments_bytes():
    # Fake PDF bytes
    fake_pdf_bytes = b"%PDF-1.4 FAKE PDF CONTENT"

    # Gmail API returns base64
    encoded = base64.urlsafe_b64encode(fake_pdf_bytes).decode()

    fake_message = {
        "payload": {
            "parts": [
                {
                    "filename": "ticket.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "123"}
                }
            ]
        }
    }

    fake_attachment = {"data": encoded}

    with patch("src.gmail.reader.get_gmail_service") as mock_service:
        service = mock_service.return_value

        # Mock message
        service.users().messages().get().execute.return_value = fake_message

        # Mock attachment
        service.users().messages().attachments().get().execute.return_value = fake_attachment

        result = get_attachments_bytes("fake_id")

        assert len(result) == 1
        filename, mime, data = result[0]

        assert filename == "ticket.pdf"
        assert mime == "application/pdf"
        assert data == fake_pdf_bytes
