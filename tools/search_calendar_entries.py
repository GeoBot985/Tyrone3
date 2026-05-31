"""
Usage:
python search_calendar_entries.py --query "dentist"
python search_calendar_entries.py --query "meeting" --days 30
python search_calendar_entries.py --query "meeting" --calendar primary
python search_calendar_entries.py --query "meeting" --time-min "2026-04-01T00:00:00+02:00" --time-max "2026-04-30T23:59:59+02:00"

Searches Google Calendar entries by text and optional date range.

Requires:
- google_auth.py
- google_token.json with Calendar access
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from google_auth import build_service, list_writable_calendar_ids, resolve_default_calendar_id, safe_print


def search_calendar_entries(
    query: str = "",
    calendar_id: str = "",
    time_min: str | None = None,
    time_max: str | None = None,
    days: int | None = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Search calendar events using Google Calendar's free-text query.

    If no time_min/time_max/days is provided:
    - time_min defaults to now
    - time_max is left open
    """

    service = build_service("calendar", "v3")
    calendar_ids = [calendar_id] if calendar_id else list_writable_calendar_ids(prefer_family=True)

    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()

    if days is not None and not time_max:
        time_max = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    request_kwargs = {
        "calendarId": calendar_id,
        "timeMin": time_min,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if query.strip():
        request_kwargs["q"] = query.strip()
    if time_max:
        request_kwargs["timeMax"] = time_max

    events: list[dict] = []
    for cal_id in calendar_ids:
        request = service.events().list(calendarId=cal_id, **{k: v for k, v in request_kwargs.items() if k != "calendarId"})
        results = request.execute()
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
    Print calendar search results in a console-friendly format.
    """

    if not entries:
        safe_print("No matching calendar entries found.")
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
        description="Search Google Calendar entries."
    )

    parser.add_argument(
        "--query",
        default="",
        help="Text to search for in calendar events.",
    )

    parser.add_argument(
        "--calendar",
        default="",
        help="Google Calendar ID. Defaults to all writable calendars when omitted.",
    )

    parser.add_argument(
        "--time-min",
        default=None,
        help="Lower time bound in RFC3339 format, e.g. 2026-04-01T00:00:00+02:00.",
    )

    parser.add_argument(
        "--time-max",
        default=None,
        help="Upper time bound in RFC3339 format, e.g. 2026-04-30T23:59:59+02:00.",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Search from now until N days ahead. Ignored if --time-max is supplied.",
    )

    parser.add_argument(
        "--max",
        type=int,
        default=20,
        help="Maximum number of matching entries to return.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        entries = search_calendar_entries(
            query=args.query,
            calendar_id=args.calendar,
            time_min=args.time_min,
            time_max=args.time_max,
            days=args.days,
            max_results=args.max,
        )
        print_entries(entries)

    except HttpError as error:
        raise RuntimeError(f"Google Calendar API error: {error}") from error


if __name__ == "__main__":
    main()
