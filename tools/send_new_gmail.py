"""
Usage:
python send_new_gmail.py --to "person@example.com" --subject "Test" --body "Hello"

Sends a new Gmail message using the official Gmail API.

Requires:
- google_auth.py
- google_token.json with Gmail send scope
"""

from __future__ import annotations

import argparse
import base64
from email.message import EmailMessage

from googleapiclient.errors import HttpError

from google_auth import build_service, safe_print


def create_message(to: str, subject: str, body: str) -> dict:
    """
    Create a Gmail API message payload.
    """

    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    return {
        "raw": encoded_message,
    }


def send_new_gmail(to: str, subject: str, body: str) -> dict:
    """
    Send a new Gmail message.
    """

    service = build_service("gmail", "v1")
    message_body = create_message(to=to, subject=subject, body=body)

    sent_message = (
        service.users()
        .messages()
        .send(userId="me", body=message_body)
        .execute()
    )

    return sent_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a new Gmail message."
    )

    parser.add_argument(
        "--to",
        required=True,
        help="Recipient email address.",
    )

    parser.add_argument(
        "--subject",
        required=True,
        help="Email subject.",
    )

    parser.add_argument(
        "--body",
        required=True,
        help="Plain-text email body.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        sent_message = send_new_gmail(
            to=args.to,
            subject=args.subject,
            body=args.body,
        )

        safe_print("[OK] Gmail sent.")
        safe_print(f"Message ID: {sent_message.get('id', 'unknown')}")
        safe_print(f"Thread ID: {sent_message.get('threadId', 'unknown')}")

    except HttpError as error:
        raise RuntimeError(f"Gmail API error: {error}") from error


if __name__ == "__main__":
    main()