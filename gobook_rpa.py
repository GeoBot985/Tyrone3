"""GoBook RPA helpers for Tyrone Personal Mode.

Credentials are loaded from `Demo5/secrets.json`.
All browser actions use a temporary Playwright profile and are intended to be called only from
Tyrone's Personal Mode endpoints.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


BASE_DIR = Path(__file__).resolve().parent
SECRETS_FILE = BASE_DIR / "secrets.json"
LOGIN_URL = "https://gobook.co.za/"
BOOKINGS_URL = "https://gobook.co.za/Bookings/Client"


@dataclass
class GoBookCredentials:
    username: str
    password: str


def load_credentials() -> GoBookCredentials:
    if not SECRETS_FILE.exists():
        raise RuntimeError(f"Secrets file not found: {SECRETS_FILE}")
    data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    if not username or not password:
        raise RuntimeError(f"Secrets file is missing username/password: {SECRETS_FILE}")
    return GoBookCredentials(username=username, password=password)


def normalize_date(date_str: str) -> str:
    return datetime.strptime(date_str.replace("/", "-"), "%Y-%m-%d").strftime("%Y/%m/%d")


def validate_booking_date(date_str: str) -> None:
    target_date = datetime.strptime(date_str.replace("/", "-"), "%Y-%m-%d").date()
    today = datetime.now().date()
    latest_allowed = today + timedelta(days=7)
    if target_date < today:
        raise RuntimeError(f"Booking date {target_date:%Y-%m-%d} is in the past.")
    if target_date > latest_allowed:
        raise RuntimeError(
            f"Booking date {target_date:%Y-%m-%d} is more than 7 days ahead. "
            f"Latest allowed date is {latest_allowed:%Y-%m-%d}."
        )


def normalize_court(court: str) -> str:
    text = court.strip().replace("#", "")
    if text.lower().startswith("court"):
        number = text.split()[-1]
        return f"Court #{number}"
    return text


def parse_timeslot(value: str) -> tuple[str, Optional[str]]:
    normalized = value.replace(" ", "")
    if "-" in normalized:
        start_time, end_time = normalized.split("-", 1)
        return start_time, end_time
    return normalized, None


async def _launch_context(slowmo: int = 100):
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            temp_profile.name,
            headless=False,
            slow_mo=slowmo,
            viewport={"width": 1600, "height": 1000},
        )
        try:
            yield context
        finally:
            await context.close()
            temp_profile.cleanup()


async def login(page, username: str, password: str):
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    await page.locator("#UserName").fill(username)
    await page.locator("#Password").fill(password)
    await page.locator("input[type='submit'][value='Log In']").click()
    await page.wait_for_load_state("domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)


async def open_new_booking_panel(page):
    await page.goto(BOOKINGS_URL, wait_until="domcontentloaded", timeout=60000)
    await page.locator("a[href='#collapseB']").click()
    await page.locator("#BookingDate").wait_for(timeout=30000)
    await page.wait_for_timeout(1500)


async def open_upcoming_bookings(page):
    await page.goto(BOOKINGS_URL, wait_until="domcontentloaded", timeout=60000)
    await page.locator("a[href='#collapseF']").click()
    await page.locator("#upcomings").wait_for(timeout=30000)
    await page.wait_for_timeout(1500)


async def set_booking_date(page, date_str: str, date_label: Optional[str] = None):
    if date_label is None:
        parsed = datetime.strptime(date_str, "%Y/%m/%d")
        date_label = parsed.strftime("%a %d %b %Y")
    date_input = page.locator("#BookingDate")
    await date_input.fill(date_str)
    await page.evaluate(
        """
        () => {
            if (typeof NewBookingPostback === "function") {
                NewBookingPostback("date", "schedule");
            }
        }
        """
    )
    try:
        await page.get_by_text(date_label, exact=False).wait_for(timeout=10000)
    except PlaywrightTimeoutError:
        pass
    actual = await date_input.input_value()
    if actual != date_str:
        raise RuntimeError(f"Date input mismatch. Expected {date_str}, got {actual}")
    await page.wait_for_timeout(3000)


async def find_booking_table(page):
    tables = page.locator("table")
    for i in range(await tables.count()):
        candidate = tables.nth(i)
        headers = [h.strip() for h in await candidate.locator("th").all_inner_texts()]
        if "Time" in headers and any(h.startswith("Court #") for h in headers):
            return candidate
    raise RuntimeError("Could not find booking grid table.")


async def find_slot_row(page, timeslot: str):
    table = await find_booking_table(page)
    rows = table.locator("tr")
    start_target, end_target = parse_timeslot(timeslot)

    for i in range(await rows.count()):
        row = rows.nth(i)
        cells = row.locator("td")
        if await cells.count() == 0:
            continue
        row_text = (await row.inner_text()).strip()
        match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", row_text)
        if not match:
            continue
        row_start, row_end = match.group(1), match.group(2)
        if end_target is None:
            if row_start == start_target:
                return table, row
        elif row_start == start_target and row_end == end_target:
            return table, row

    raise RuntimeError(f"Could not find timeslot row: {timeslot}")


async def select_slot(page, timeslot: str, court: Optional[str]):
    table, row = await find_slot_row(page, timeslot)
    headers = [h.strip() for h in await table.locator("th").all_inner_texts()]
    cells = row.locator("td")

    if court:
        normalized_court = normalize_court(court)
        if normalized_court not in headers:
            raise RuntimeError(f"Court '{court}' not found. Available headers: {headers}")
        court_index = headers.index(normalized_court)
        target_cell = cells.nth(court_index)
        checkboxes = target_cell.locator("input[type='checkbox']")
        if await checkboxes.count() == 0:
            cell_text = (await target_cell.inner_text()).strip()
            raise RuntimeError(
                f"Court '{court}' is not open for {timeslot}. Cell content: {cell_text or 'occupied'}"
            )
        checkbox = checkboxes.first
        if not await checkbox.is_enabled():
            raise RuntimeError(f"Checkbox is disabled for {timeslot} / {court}")
        await checkbox.check()
        return f"Selected slot: {timeslot} / {normalized_court}"

    checkboxes = row.locator("input[type='checkbox']")
    for i in range(await checkboxes.count()):
        checkbox = checkboxes.nth(i)
        try:
            if await checkbox.is_enabled() and not await checkbox.is_checked():
                await checkbox.check()
                return f"Selected first available checkbox in row: {timeslot}"
        except Exception:
            continue
    raise RuntimeError(f"No available checkbox found for timeslot: {timeslot}")


async def open_booking_modal(page, row):
    await row.click()
    await page.locator("#bookingModal").wait_for(timeout=30000)
    await page.locator("input[type='submit'][value='Cancel Booking']").wait_for(timeout=30000)


async def cancel_booking(page, confirm: bool):
    if not confirm:
        return {"ok": True, "dry_run": True}

    async def handle_dialog(dialog):
        await dialog.accept()

    page.once("dialog", handle_dialog)
    await page.locator("input[type='submit'][value='Cancel Booking']").click()
    try:
        await page.locator("#bookingModal").wait_for(state="hidden", timeout=30000)
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_timeout(2500)
    return {"ok": True}


async def list_active_upcoming_bookings(slowmo: int = 100):
    creds = load_credentials()
    temp_profile = tempfile.TemporaryDirectory(prefix="gobook_tyrone_list_")
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
            temp_profile.cleanup()
