"""
Usage:
python create_calendar_entries.py --title "Test meeting" --start "2026-04-29T10:00:00+02:00" --end "2026-04-29T10:30:00+02:00"

Optional:
python create_calendar_entries.py ^
  --title "Test meeting" ^
  --start "2026-04-29T10:00:00+02:00" ^
  --end "2026-04-29T10:30:00+02:00" ^
  --description "Demo calendar event" ^
  --location "Cape Town" ^
  --calendar primary

Creates a Google Calendar entry.

Requires:
- google_auth.py
- google_token.json with Calendar access
"""

from __future__ import annotations

import argparse

from googleapiclient.errors import HttpError

from google_auth import build_service, resolve_default_calendar_id, safe_print


SQUASH_COLOR_ID = "6"


def detect_event_color_id(title: str, description: str = "", location: str = "") -> str | None:
    """
    Return a Google Calendar event color ID for known event types.

    Squash bookings should appear orange in Google Calendar.
    """

    haystack = " ".join([title, description, location]).lower()
    if "squash" in haystack:
        return SQUASH_COLOR_ID
    return None


def create_calendar_entry(
    title: str,
    start: str,
    end: str,
    calendar_id: str = "",
    description: str = "",
    location: str = "",
) -> dict:
    """
    Create a Google Calendar event.

    Args:
        title: Event title.
        start: Event start datetime in RFC3339 format.
        end: Event end datetime in RFC3339 format.
        calendar_id: Google Calendar ID. Defaults to the Family calendar when present.
        description: Optional event description.
        location: Optional event location.

    Example datetime:
        2026-04-29T10:00:00+02:00
    """

    service = build_service("calendar", "v3")
    calendar_id = calendar_id or resolve_default_calendar_id(prefer_family=True)

    event_body: dict = {
        "summary": title,
        "start": {
            "dateTime": start,
        },
        "end": {
            "dateTime": end,
        },
    }

    if description:
        event_body["description"] = description

    if location:
        event_body["location"] = location

    color_id = detect_event_color_id(title, description, location)
    if color_id:
        event_body["colorId"] = color_id

    created_event = (
        service.events()
        .insert(
            calendarId=calendar_id,
            body=event_body,
        )
        .execute()
    )

    return created_event


def print_created_event(event: dict) -> None:
    """
    Print created event details.
    """

    start = event.get("start", {})
    end = event.get("end", {})

    safe_print("[OK] Calendar entry created.")
    safe_print(f"Title: {event.get('summary', '(No title)')}")
    safe_print(f"Start: {start.get('dateTime') or start.get('date') or ''}")
    safe_print(f"End: {end.get('dateTime') or end.get('date') or ''}")
    safe_print(f"Event ID: {event.get('id', 'unknown')}")
    if event.get("colorId"):
        safe_print(f"Color ID: {event['colorId']}")

    if event.get("htmlLink"):
        safe_print(f"Link: {event['htmlLink']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Google Calendar entry."
    )

    parser.add_argument(
        "--title",
        required=True,
        help="Calendar event title.",
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start datetime in RFC3339 format, e.g. 2026-04-29T10:00:00+02:00.",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End datetime in RFC3339 format, e.g. 2026-04-29T10:30:00+02:00.",
    )

    parser.add_argument(
        "--description",
        default="",
        help="Optional event description.",
    )

    parser.add_argument(
        "--location",
        default="",
        help="Optional event location.",
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
        event = create_calendar_entry(
            title=args.title,
            start=args.start,
            end=args.end,
            calendar_id=args.calendar,
            description=args.description,
            location=args.location,
        )

        print_created_event(event)

    except HttpError as error:
        raise RuntimeError(f"Google Calendar API error: {error}") from error


if __name__ == "__main__":
    main()
