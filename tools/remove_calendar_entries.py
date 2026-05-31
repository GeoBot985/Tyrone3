"""
Usage:
python remove_calendar_entries.py --event-id "abc123eventid"
python remove_calendar_entries.py --event-id "abc123eventid" --calendar primary

Deletes/removes a Google Calendar entry.

Requires:
- google_auth.py
- google_token.json with Calendar access
"""

from __future__ import annotations

import argparse

from googleapiclient.errors import HttpError

from google_auth import build_service, resolve_default_calendar_id, safe_print


def remove_calendar_entry(
    event_id: str,
    calendar_id: str = "",
) -> None:
    """
    Delete a Google Calendar event by event ID.
    """

    service = build_service("calendar", "v3")
    calendar_id = calendar_id or resolve_default_calendar_id(prefer_family=True)

    (
        service.events()
        .delete(
            calendarId=calendar_id,
            eventId=event_id,
        )
        .execute()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove/delete a Google Calendar entry."
    )

    parser.add_argument(
        "--event-id",
        required=True,
        help="Google Calendar event ID to delete.",
    )

    parser.add_argument(
        "--calendar",
        default="primary",
        help="Google Calendar ID. Defaults to the Family calendar when present.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        remove_calendar_entry(
            event_id=args.event_id,
            calendar_id=args.calendar,
        )

        safe_print("[OK] Calendar entry removed.")
        safe_print(f"Event ID: {args.event_id}")
        safe_print(f"Calendar: {args.calendar}")

    except HttpError as error:
        raise RuntimeError(f"Google Calendar API error: {error}") from error


if __name__ == "__main__":
    main()
