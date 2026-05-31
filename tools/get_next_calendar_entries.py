"""
Usage:
python get_next_calendar_entries.py
python get_next_calendar_entries.py --max 10
python get_next_calendar_entries.py --calendar primary

Gets the next upcoming Google Calendar entries.

Requires:
- google_auth.py
- google_token.json with Calendar access
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from googleapiclient.errors import HttpError

from google_auth import build_service, list_writable_calendar_ids, resolve_default_calendar_id, safe_print


def get_next_calendar_entries(
    max_results: int = 10,
    calendar_id: str = "",
) -> list[dict]:
    """
    Return the next upcoming calendar events.
    """

    service = build_service("calendar", "v3")
    calendar_ids = [calendar_id] if calendar_id else list_writable_calendar_ids(prefer_family=True)

    now_utc = datetime.now(timezone.utc).isoformat()

    events: list[dict] = []
    for cal_id in calendar_ids:
        results = (
            service.events()
            .list(
                calendarId=cal_id,
                timeMin=now_utc,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events.extend(results.get("items", []))

    events.sort(key=lambda event: (event.get("start", {}).get("dateTime") or event.get("start", {}).get("date") or ""))

    entries: list[dict] = []

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})

        entries.append(
            {
                "id": event.get("id", ""),
                "summary": event.get("summary", "(No title)"),
                "description": event.get("description", ""),
                "location": event.get("location", ""),
                "start": start.get("dateTime") or start.get("date") or "",
                "end": end.get("dateTime") or end.get("date") or "",
                "html_link": event.get("htmlLink", ""),
                "status": event.get("status", ""),
            }
        )

    return entries


def print_entries(entries: list[dict]) -> None:
    """
    Print calendar entries in a console-friendly format.
    """

    if not entries:
        safe_print("No upcoming calendar entries found.")
        return

    for entry in entries:
        safe_print(f"Title: {entry['summary']}")
        safe_print(f"Start: {entry['start']}")
        safe_print(f"End: {entry['end']}")

        if entry.get("location"):
            safe_print(f"Location: {entry['location']}")

        if entry.get("description"):
            safe_print(f"Description: {entry['description']}")

        safe_print(f"Status: {entry['status']}")
        safe_print(f"Event ID: {entry['id']}")

        if entry.get("html_link"):
            safe_print(f"Link: {entry['html_link']}")

        safe_print("-" * 40)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Get the next upcoming Google Calendar entries."
    )

    parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="Maximum number of upcoming entries to return.",
    )

    parser.add_argument(
        "--calendar",
        default="",
        help="Google Calendar ID. Defaults to all writable calendars when omitted.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        entries = get_next_calendar_entries(
            max_results=args.max,
            calendar_id=args.calendar,
        )
        print_entries(entries)

    except HttpError as error:
        raise RuntimeError(f"Google Calendar API error: {error}") from error


if __name__ == "__main__":
    main()
