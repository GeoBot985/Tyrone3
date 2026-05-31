"""
Usage:
python check_gmail_new_mail.py
python check_gmail_new_mail.py --max 10

Checks Gmail for unread inbox messages using the official Gmail API.

Requires:
- google_auth.py
- google_token.json with Gmail access
"""

from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime

from googleapiclient.errors import HttpError

from google_auth import build_service, safe_print


def get_header(headers: list[dict], name: str) -> str:
    """
    Extract a header value from Gmail metadata headers.
    """

    for header in headers or []:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")

    return ""


def format_gmail_date(date_text: str) -> str:
    """
    Convert Gmail Date header to local readable datetime where possible.
    """

    if not date_text:
        return "unknown"

    try:
        received = parsedate_to_datetime(date_text).astimezone()
        return received.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_text


def check_gmail_new_mail(max_results: int = 5) -> list[dict]:
    """
    Return unread inbox messages with basic metadata.
    """

    service = build_service("gmail", "v1")

    results = (
        service.users()
        .messages()
        .list(
            userId="me",
            q="is:unread in:inbox",
            maxResults=max_results,
        )
        .execute()
    )

    message_refs = results.get("messages", [])

    messages: list[dict] = []

    for message_ref in message_refs:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        date_text = get_header(headers, "Date")

        messages.append(
            {
                "id": msg.get("id", ""),
                "thread_id": msg.get("threadId", ""),
                "from": get_header(headers, "From"),
                "subject": get_header(headers, "Subject"),
                "date": format_gmail_date(date_text),
                "snippet": msg.get("snippet", ""),
            }
        )

    return messages


def print_messages(messages: list[dict]) -> None:
    """
    Print messages in a console-friendly format.
    """

    if not messages:
        safe_print("No unread inbox mail.")
        return

    for message in messages:
        safe_print(f"From: {message['from']}")
        safe_print(f"Subject: {message['subject']}")
        safe_print(f"Date: {message['date']}")

        if message.get("snippet"):
            safe_print(f"Snippet: {message['snippet']}")

        safe_print(f"Message ID: {message['id']}")
        safe_print(f"Thread ID: {message['thread_id']}")
        safe_print("-" * 40)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Gmail for unread inbox messages."
    )

    parser.add_argument(
        "--max",
        type=int,
        default=5,
        help="Maximum number of unread inbox messages to return.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        messages = check_gmail_new_mail(max_results=args.max)
        print_messages(messages)

    except HttpError as error:
        raise RuntimeError(f"Gmail API error: {error}") from error


if __name__ == "__main__":
    main()