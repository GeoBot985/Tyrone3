"""
Usage:
python write_sheet_entries.py --spreadsheet-id "spreadsheet_id_here" --range "Sheet1!A1" --values '[["Name","Value"],["Test","123"]]'

Append mode:
python write_sheet_entries.py --spreadsheet-id "spreadsheet_id_here" --range "Sheet1!A:D" --values '[["Test","123"]]' --mode append

Update mode:
python write_sheet_entries.py --spreadsheet-id "spreadsheet_id_here" --range "Sheet1!A1:B2" --values '[["Name","Value"],["Test","123"]]' --mode update

Writes values to a Google Sheet range.

Requires:
- google_auth.py
- google_token.json with Sheets access
"""

from __future__ import annotations

import argparse
import json

from googleapiclient.errors import HttpError

from google_auth import build_service, safe_print


def write_sheet_entries(
    spreadsheet_id: str,
    range_name: str,
    values: list[list[str]],
    mode: str = "append",
    value_input_option: str = "USER_ENTERED",
) -> dict:
    """
    Write values to a Google Sheet.

    Args:
        spreadsheet_id: Google Sheet ID from the sheet URL.
        range_name: A1 notation range, e.g. Sheet1!A1:D10.
        values: 2D list of row values.
        mode: "append" or "update".
        value_input_option:
            - "USER_ENTERED": Sheets parses numbers, dates, formulas.
            - "RAW": Values are stored exactly as provided.

    Returns:
        Google Sheets API response.
    """

    if mode not in {"append", "update"}:
        raise ValueError("mode must be either 'append' or 'update'.")

    service = build_service("sheets", "v4")

    body = {
        "values": values,
    }

    if mode == "append":
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )
        return result

    result = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption=value_input_option,
            body=body,
        )
        .execute()
    )
    return result


def parse_values_json(values_json: str) -> list[list[str]]:
    """
    Parse CLI JSON values into a 2D list.

    Expected:
        '[["Name","Value"],["Test","123"]]'
    """

    try:
        values = json.loads(values_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Invalid --values JSON. Expected format: "
            '\'[["Name","Value"],["Test","123"]]\'.'
        ) from error

    if not isinstance(values, list) or not all(isinstance(row, list) for row in values):
        raise ValueError(
            "Invalid --values structure. Expected a 2D list, e.g. "
            '\'[["Name","Value"],["Test","123"]]\'.'
        )

    return values


def print_result(result: dict, mode: str) -> None:
    """
    Print Google Sheets write result.
    """

    safe_print(f"[OK] Sheet {mode} completed.")

    updated_range = result.get("updates", {}).get("updatedRange") or result.get("updatedRange")
    updated_rows = result.get("updates", {}).get("updatedRows") or result.get("updatedRows")
    updated_columns = result.get("updates", {}).get("updatedColumns") or result.get("updatedColumns")
    updated_cells = result.get("updates", {}).get("updatedCells") or result.get("updatedCells")

    if updated_range:
        safe_print(f"Updated range: {updated_range}")

    if updated_rows is not None:
        safe_print(f"Updated rows: {updated_rows}")

    if updated_columns is not None:
        safe_print(f"Updated columns: {updated_columns}")

    if updated_cells is not None:
        safe_print(f"Updated cells: {updated_cells}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write values to a Google Sheet range."
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
        help='A1 notation range, e.g. "Sheet1!A1:D10" or "Sheet1!A:D".',
    )

    parser.add_argument(
        "--values",
        required=True,
        help='JSON 2D list of values, e.g. \'[["Name","Value"],["Test","123"]]\'.',
    )

    parser.add_argument(
        "--mode",
        choices=["append", "update"],
        default="append",
        help="Write mode. Defaults to append.",
    )

    parser.add_argument(
        "--value-input-option",
        choices=["USER_ENTERED", "RAW"],
        default="USER_ENTERED",
        help="How Google Sheets interprets values. Defaults to USER_ENTERED.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        values = parse_values_json(args.values)

        result = write_sheet_entries(
            spreadsheet_id=args.spreadsheet_id,
            range_name=args.range_name,
            values=values,
            mode=args.mode,
            value_input_option=args.value_input_option,
        )

        print_result(result, args.mode)

    except HttpError as error:
        raise RuntimeError(f"Google Sheets API error: {error}") from error


if __name__ == "__main__":
    main()