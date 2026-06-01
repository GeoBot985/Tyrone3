"""GoBook tools for Tyrone Personal Mode."""

from __future__ import annotations

import re
import tempfile
from datetime import datetime
from typing import Optional

from gobook_rpa import (
    cancel_booking,
    load_credentials,
    list_active_upcoming_bookings,
    login,
    normalize_court,
    normalize_date,
    open_booking_modal,
    open_new_booking_panel,
    open_upcoming_bookings,
    select_slot,
    set_booking_date,
    validate_booking_date,
)
from playwright.async_api import async_playwright


def detect_rpa_intent(message: str) -> str | None:
    text = message.lower().strip()
    if not text:
        return None
    if any(term in text for term in ("google calendar", "family calendar", "calendar", "gcal")):
        return None
    has_date = bool(re.search(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", text))
    has_time = bool(re.search(r"\b\d{1,2}:\d{2}\b", text))
    has_court = bool(re.search(r"\bcourt\s*#?\s*\d+\b", text, re.I))
    has_booking_shape = has_date or has_time or has_court
    has_gobook_marker = any(
        term in text
        for term in (
            "gobook",
            "squash booking",
            "squash bookings",
            "upcoming squash bookings",
            "upcoming bookings",
            "my bookings",
            "booking",
            "bookings",
        )
    )

    if any(term in text for term in ("cancel booking", "delete booking", "cancel my booking", "remove booking")):
        return "cancel"
    if re.search(r"\bcancel\b", text) and has_booking_shape:
        return "cancel"
    if any(
        term in text
        for term in (
            "open courts",
            "check for open courts",
            "available courts",
            "courts open",
            "what courts are open",
            "court availability",
        )
    ) or (("court" in text or "courts" in text) and "open" in text and has_booking_shape):
        return "open_courts"
    if any(term in text for term in ("upcoming bookings", "my bookings", "list bookings", "show bookings")):
        return "list"
    if has_gobook_marker and any(term in text for term in ("upcoming", "show", "check", "list", "my")):
        return "list"
    has_book_word = bool(re.search(r"\bbook\b", text))
    if any(term in text for term in ("book court", "make booking", "new booking", "book squash", "book the court", "please book")):
        return "book"
    if has_gobook_marker and (has_booking_shape or any(term in text for term in ("book court", "book squash", "book the court"))):
        return "book"
    if has_book_word and has_booking_shape:
        return "book"
    return None


def extract_rpa_details(message: str) -> dict:
    text = message.lower()
    dates = re.findall(r"(\d{4}[-/]\d{2}[-/]\d{2})", message)
    times = re.findall(r"(\d{1,2}:\d{2})", message)
    request_date = dates[0] if dates else None

    court_match = re.search(r"\bcourt\s*#?\s*(\d+)\b", text, re.I)
    court_value = f"Court {court_match.group(1)}" if court_match else "Court 1"

    start_time = None
    end_time = None

    range_match = re.search(r"(\d{1,2}:\d{2})\s*(?:-|to|until|through)\s*(\d{1,2}:\d{2})", text, re.I)
    if range_match:
        start_time, end_time = range_match.group(1), range_match.group(2)
    else:
        between_match = re.search(r"(?:between|from)\s+(\d{1,2}:\d{2})\s+(?:and|to)\s+(\d{1,2}:\d{2})", text, re.I)
        if between_match:
            start_time, end_time = between_match.group(1), between_match.group(2)
        elif len(times) >= 2:
            start_time, end_time = times[0], times[1]
        elif len(times) == 1:
            start_time = times[0]

    return {
        "date": request_date,
        "times": times,
        "start": start_time,
        "end": end_time,
        "court": court_value,
    }


def time_to_minutes(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def slot_within_range(slot_start: str, slot_end: str, range_start: str, range_end: str) -> bool:
    start_minutes = time_to_minutes(slot_start)
    end_minutes = time_to_minutes(slot_end)
    request_start_minutes = time_to_minutes(range_start)
    request_end_minutes = time_to_minutes(range_end)

    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    if request_end_minutes <= request_start_minutes:
        request_end_minutes += 24 * 60

    return start_minutes >= request_start_minutes and end_minutes <= request_end_minutes


async def rpa_book(date: str, time_value: str, court: str, confirm: bool, slowmo: int):
    validate_booking_date(date)
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_book_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_new_booking_panel(page)
                date_str = normalize_date(date)
                await set_booking_date(page, date_str)
                selection = await select_slot(page, time_value, court or "Court 1")
                if confirm:
                    await page.locator("input[type='submit'][value='Book']").click()
                    await page.wait_for_timeout(2000)
                return {"selection": selection, "confirmed": confirm}
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


async def rpa_cancel(date: str, time_value: str, court: str, confirm: bool, slowmo: int):
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_cancel_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_upcoming_bookings(page)
                rows = page.locator("#upcomings tbody tr")
                target_date = normalize_date(date)
                target_court = normalize_court(court or "Court 1")
                start_target, end_target = time_value.replace(" ", ""), None
                if "-" in start_target:
                    start_target, end_target = start_target.split("-", 1)

                row = None
                for i in range(await rows.count()):
                    candidate = rows.nth(i)
                    cells = candidate.locator("td")
                    if await cells.count() < 8:
                        continue
                    facility = (await cells.nth(2).inner_text()).strip()
                    date_text = (await cells.nth(3).inner_text()).strip()
                    start_text = (await cells.nth(4).inner_text()).strip()
                    end_text = (await cells.nth(5).inner_text()).strip()
                    status_text = (await cells.nth(6).inner_text()).strip()
                    if facility != target_court or date_text != target_date or status_text.lower() == "cancelled":
                        continue
                    if end_target is None and start_text == start_target:
                        row = candidate
                        break
                    if end_target is not None and start_text == start_target and end_text == end_target:
                        row = candidate
                        break

                if row is None:
                    return {"ok": False, "error": "Matching booking not found."}
                await open_booking_modal(page, row)
                result = await cancel_booking(page, confirm)
                return result
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


async def rpa_list(slowmo: int):
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_list_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_upcoming_bookings(page)
                rows = page.locator("#upcomings tbody tr")
                results = []
                for i in range(await rows.count()):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    if await cells.count() < 8:
                        continue
                    court = (await cells.nth(2).inner_text()).strip()
                    date_text = (await cells.nth(3).inner_text()).strip()
                    start_text = (await cells.nth(4).inner_text()).strip()
                    end_text = (await cells.nth(5).inner_text()).strip()
                    status_text = (await cells.nth(6).inner_text()).strip()
                    if status_text.lower() == "cancelled":
                        continue
                    results.append(f"{date_text} / {start_text}-{end_text} / {court}")
                return results
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()


async def rpa_open_courts(date: str, start: str, end: str, slowmo: int):
    validate_booking_date(date)
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_open_")
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                temp_profile.name,
                headless=False,
                slow_mo=slowmo,
                viewport={"width": 1600, "height": 1000},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await login(page, creds.username, creds.password)
                await open_new_booking_panel(page)
                date_str = normalize_date(date)
                await set_booking_date(page, date_str)
                table = page.locator("table").first
                headers = [h.strip() for h in await table.locator("th").all_inner_texts()]
                court_columns = [h for h in headers if h.startswith("Court #")]
                results = []
                rows = table.locator("tr")
                for i in range(await rows.count()):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    if await cells.count() == 0:
                        continue
                    row_text = (await row.inner_text()).strip()
                    match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", row_text)
                    if not match:
                        continue
                    slot_start, slot_end = match.group(1), match.group(2)
                    if not slot_within_range(slot_start, slot_end, start, end):
                        continue
                    for court_name in court_columns:
                        cell_index = headers.index(court_name)
                        checkboxes = cells.nth(cell_index).locator("input[type='checkbox']")
                        if await checkboxes.count() == 0:
                            continue
                        checkbox = checkboxes.first
                        if await checkbox.is_enabled() and not await checkbox.is_checked():
                            results.append(f"{date_str} / {slot_start}-{slot_end} / {court_name}")
                return results
            finally:
                await context.close()
    finally:
        temp_profile.cleanup()
