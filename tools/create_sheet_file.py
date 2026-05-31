"""
Usage:
python create_sheet_file.py --title "Demo14_RPA Test Sheet"

Creates a new Google Spreadsheet file.

Requires:
- google_auth.py
- google_token.json with Sheets access
"""

from __future__ import annotations

import argparse

from googleapiclient.errors import HttpError

from google_auth import build_service, safe_print


def create_sheet_file(title: str) -> dict:
    """
    Create a new Google Spreadsheet file.
    """

    service = build_service("sheets", "v4")

    result = (
        service.spreadsheets()
        .create(
            body={
                "properties": {
                    "title": title,
                }
            }
        )
        .execute()
    )

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new Google Spreadsheet file."
    )

    parser.add_argument(
        "--title",
        required=True,
        help="Spreadsheet title.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        sheet = create_sheet_file(args.title)
        safe_print("[OK] Spreadsheet created.")
        safe_print(f"Title: {sheet.get('properties', {}).get('title', '(unknown)')}")
        safe_print(f"Spreadsheet ID: {sheet.get('spreadsheetId', 'unknown')}")
        safe_print(f"URL: {sheet.get('spreadsheetUrl', 'unknown')}")
    except HttpError as error:
        raise RuntimeError(f"Google Sheets API error: {error}") from error


if __name__ == "__main__":
    main()
