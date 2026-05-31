"""
Usage:
python read_sheet_entries.py --spreadsheet-id "spreadsheet_id_here" --range "Sheet1!A1:D10"

Reads values from a Google Sheet range.

Requires:
- google_auth.py
- google_token.json with Sheets access
"""

from __future__ import annotations

import argparse

from googleapiclient.errors import HttpError

from google_auth import build_service, safe_print


def read_sheet_entries(
    spreadsheet_id: str,
    range_name: str,
) -> list[list[str]]:
    """
    Read values from a Google Sheet range.

    Args:
        spreadsheet_id: Google Sheet ID from the sheet URL.
        range_name: A1 notation range, e.g. Sheet1!A1:D10.

    Returns:
        2D list of row values.
    """

    service = build_service("sheets", "v4")

    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        )
        .execute()
    )

    return result.get("values", [])


def print_rows(rows: list[list[str]]) -> None:
    """
    Print sheet rows in a console-friendly format.
    """

    if not rows:
        safe_print("No sheet values found.")
        return

    for index, row in enumerate(rows, start=1):
        safe_print(f"{index}: {row}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read values from a Google Sheet range."
    )

    parser.add_argument(
        "--spreadsheet-id",
        required=True,
        help="Google Sheet spreadsheet ID.",
    )

    parser.add_argument(
        "--range",
        required=True,
        dest="range_name",
        help='A1 notation range, e.g. "Sheet1!A1:D10".',
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        rows = read_sheet_entries(
            spreadsheet_id=args.spreadsheet_id,
            range_name=args.range_name,
        )

        print_rows(rows)

    except HttpError as error:
        raise RuntimeError(f"Google Sheets API error: {error}") from error


if __name__ == "__main__":
    main()