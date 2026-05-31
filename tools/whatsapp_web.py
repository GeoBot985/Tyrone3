"""
Shared WhatsApp Web Playwright helpers.

Used by:
- whatsapp_auth_check.py
- whatsapp_search_chat.py
- whatsapp_send_message.py
- whatsapp_read_recent_messages.py

Design:
- Uses a dedicated persistent Chromium profile.
- Does not use the user's normal Chrome/Edge profile.
- Does not store WhatsApp credentials.
- Does not bypass QR login.
"""

from __future__ import annotations

import mimetypes
import re
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Locator
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


WHATSAPP_URL = "https://web.whatsapp.com/"

BASE_DIR = Path(__file__).resolve().parents[2] / "Demo14_RPA"
PROFILE_DIR = BASE_DIR / "runtime_data" / "whatsapp_profile"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DOCUMENT_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".zip",
    ".rar",
    ".7z",
    ".ppt",
    ".pptx",
}


def safe_print(text: str) -> None:
    import sys

    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def get_profile_dir() -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILE_DIR


async def launch_whatsapp_context(playwright: Any, slowmo: int = 100):
    return await playwright.chromium.launch_persistent_context(
        user_data_dir=str(get_profile_dir()),
        headless=False,
        slow_mo=slowmo,
        viewport={"width": 1400, "height": 900},
    )


async def get_or_create_page(context: Any) -> Page:
    if context.pages:
        return context.pages[0]
    return await context.new_page()


async def open_whatsapp(page: Page) -> None:
    await page.goto(
        WHATSAPP_URL,
        wait_until="domcontentloaded",
        timeout=60000,
    )
    await page.wait_for_timeout(2500)


async def is_logged_in(page: Page) -> bool:
    checks = [
        page.get_by_text("Search or start new chat", exact=False),
        page.get_by_text("Search", exact=False),
        page.locator("[aria-label='Chat list']"),
        page.locator("[aria-label='Search input textbox']"),
        page.locator("div[role='grid']"),
        page.locator("div[contenteditable='true'][role='textbox']"),
        page.locator("#pane-side"),
    ]

    for locator in checks:
        try:
            if await locator.first.is_visible(timeout=1500):
                return True
        except Exception:
            continue

    return False


async def is_login_screen(page: Page) -> bool:
    checks = [
        page.get_by_text("Use WhatsApp on your computer", exact=False),
        page.get_by_text("Log into WhatsApp Web", exact=False),
        page.get_by_text("Scan this QR code", exact=False),
        page.get_by_text("Link with phone number", exact=False),
        page.locator("canvas"),
    ]

    for locator in checks:
        try:
            if await locator.first.is_visible(timeout=1500):
                return True
        except Exception:
            continue

    return False


async def wait_for_login(page: Page, timeout_ms: int = 120000) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        if await is_logged_in(page):
            return True
        await page.wait_for_timeout(1000)

    return False


async def require_login(page: Page, timeout_ms: int = 120000) -> None:
    if await is_logged_in(page):
        return

    if await is_login_screen(page):
        safe_print("Scan the WhatsApp QR code, then leave the browser open until login completes.")

    if await wait_for_login(page, timeout_ms=timeout_ms):
        return

    raise RuntimeError(
        "WhatsApp Web is not authenticated. "
        "Run whatsapp_auth_check.py and scan the QR code first."
    )


async def clear_search_box(page: Page) -> None:
    search_candidates = [
        page.locator("[aria-label='Search input textbox']"),
        page.get_by_role("textbox", name="Search input textbox"),
        page.get_by_role("textbox").first,
    ]

    for locator in search_candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=2000):
                await candidate.click()
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                return
        except Exception:
            continue

    raise RuntimeError("Could not find WhatsApp search box.")


async def type_search_text(page: Page, search_box: Locator, text: str, delay_ms: int = 250) -> None:
    await search_box.click()
    try:
        await search_box.press_sequentially(text, delay=delay_ms)
    except Exception:
        for ch in text:
            await page.keyboard.type(ch, delay=delay_ms)


def chat_search_candidates(chat_name: str) -> list[str]:
    candidates: list[str]
    if "/" in chat_name:
        candidates = [
            chat_name.replace("/", " ").strip(),
            chat_name.replace("/", "").strip(),
        ]
    else:
        candidates = [chat_name.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


async def first_visible_chat_result(page: Page, query: str) -> Locator | None:
    result_candidates = [
        page.get_by_title(query, exact=True),
        page.get_by_text(query, exact=True),
        page.get_by_text(query, exact=False),
    ]

    for locator in result_candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=500):
                return candidate
        except Exception:
            continue
    return None


async def find_chat(page: Page, chat_name: str, timeout_ms: int = 30000) -> bool:
    chat_name = chat_name.strip()
    if not chat_name:
        raise ValueError("chat_name cannot be empty.")

    await require_login(page)

    search_box = None
    search_candidates = [
        page.locator("[aria-label='Search input textbox']"),
        page.get_by_role("textbox", name="Search input textbox"),
        page.get_by_role("textbox").first,
    ]

    for locator in search_candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=2000):
                search_box = candidate
                break
        except Exception:
            continue

    if search_box is None:
        return False

    deadline = time.monotonic() + (timeout_ms / 1000)

    for candidate_name in chat_search_candidates(chat_name):
        try:
            await clear_search_box(page)
        except RuntimeError:
            return False

        last_visible_result: Locator | None = None
        while time.monotonic() < deadline:
            typed = ""
            for ch in candidate_name:
                await search_box.click()
                await page.keyboard.type(ch, delay=250)
                typed += ch
                await page.wait_for_timeout(600)

                current_result = await first_visible_chat_result(page, typed)
                if current_result is not None:
                    last_visible_result = current_result
                    if typed == candidate_name:
                        await current_result.click()
                        await page.wait_for_timeout(1500)
                        return True
                else:
                    if last_visible_result is not None:
                        await page.keyboard.press("Backspace")
                        await page.wait_for_timeout(600)
                        try:
                            if await last_visible_result.is_visible(timeout=500):
                                await last_visible_result.click()
                                await page.wait_for_timeout(1500)
                                return True
                        except Exception:
                            pass

            await page.wait_for_timeout(1000)

    return False


async def get_message_box(page: Page) -> Locator:
    candidates = [
        page.locator("footer div[contenteditable='true'][role='textbox']"),
        page.locator("div[aria-label='Type a message']"),
        page.get_by_role("textbox", name="Type a message"),
        page.locator("div[contenteditable='true'][data-tab]").last,
    ]

    for locator in candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=3000):
                return candidate
        except Exception:
            continue

    raise RuntimeError("Could not find WhatsApp message input box. Is a chat open?")


async def send_text_message(page: Page, message: str) -> None:
    message = message.strip()
    if not message:
        raise ValueError("message cannot be empty.")

    message_box = await get_message_box(page)

    await message_box.click()
    await message_box.fill(message)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1500)


def classify_attachment(file_path: str | Path, requested_kind: str = "auto") -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if requested_kind in {"image", "document"}:
        return requested_kind

    if suffix in IMAGE_SUFFIXES:
        return "image"

    return "document"


async def open_attachment_menu(page: Page) -> None:
    candidates = [
        page.locator("button[title='Attach']"),
        page.locator("span[data-icon='plus']"),
        page.locator("span[data-icon='clip']"),
        page.locator("[aria-label='Attach']"),
        page.get_by_label("Attach"),
    ]

    for locator in candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=2000):
                await candidate.click()
                await page.wait_for_timeout(700)
                return
        except Exception:
            continue

    raise RuntimeError("Could not find WhatsApp attachment button.")


async def select_attachment_file(page: Page, file_path: Path, attachment_kind: str) -> None:
    """
    Set file input after opening the attachment menu.

    WhatsApp Web commonly exposes multiple hidden file inputs.
    We try image/video inputs first for images, and broader document inputs for documents.
    """

    menu_labels = (
        ["Photos & videos", "Photo & video", "Photos and videos"]
        if attachment_kind == "image"
        else ["Document"]
    )

    for label in menu_labels:
        try:
            async with page.expect_file_chooser(timeout=5000) as file_chooser_info:
                await page.get_by_text(label, exact=True).click(timeout=5000)

            file_chooser = await file_chooser_info.value
            await file_chooser.set_files(str(file_path))
            await page.wait_for_timeout(2500)
            return
        except Exception:
            continue

    inputs = page.locator("input[type='file']")
    count = await inputs.count()

    if count == 0:
        raise RuntimeError("Could not find WhatsApp file input after opening attachment menu.")

    scored_inputs: list[tuple[int, Locator]] = []

    for i in range(count):
        candidate = inputs.nth(i)
        accept = (await candidate.get_attribute("accept")) or ""

        score = 0
        accept_lower = accept.lower()

        if attachment_kind == "image":
            if "image" in accept_lower or "video" in accept_lower:
                score += 10
            if not accept_lower:
                score += 1
        else:
            if not accept_lower:
                score += 10
            if "image" not in accept_lower and "video" not in accept_lower:
                score += 5

        scored_inputs.append((score, candidate))

    scored_inputs.sort(key=lambda item: item[0], reverse=True)

    last_error: Exception | None = None

    for _, candidate in scored_inputs:
        try:
            await candidate.set_input_files(str(file_path))
            await page.wait_for_timeout(2000)
            return
        except Exception as error:
            last_error = error
            continue

    raise RuntimeError(f"Could not attach file: {file_path}") from last_error


async def fill_attachment_caption(page: Page, caption: str) -> None:
    caption = caption.strip()
    if not caption:
        return

    candidates = [
        page.locator("div[aria-label='Add a caption']"),
        page.locator("div[aria-placeholder='Add a caption']"),
        page.locator("div[contenteditable='true'][aria-label='Add a caption']"),
        page.locator("div[contenteditable='true'][aria-placeholder='Add a caption']"),
        page.get_by_role("textbox", name="Add a caption"),
        page.locator("div[contenteditable='true'][role='textbox']").last,
    ]

    for locator in candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=3000):
                await candidate.click()
                await page.keyboard.insert_text(caption)
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue

    # Caption is optional. Do not fail the whole send if unavailable.
    safe_print("[WARN] Could not find attachment caption box. Sending file without caption.")


async def click_attachment_send(page: Page) -> None:
    candidates = [
        page.locator("span[data-icon='send']"),
        page.locator("[aria-label='Send']"),
        page.get_by_label("Send"),
        page.get_by_role("button", name="Send"),
    ]

    for locator in candidates:
        try:
            candidate = locator.first
            if await candidate.is_visible(timeout=10000):
                await candidate.click()
                await page.wait_for_timeout(2500)
                return
        except Exception:
            continue

    # Fallback: Enter sometimes sends from preview dialog.
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2500)


async def send_attachment(
    page: Page,
    file_path: str | Path,
    caption: str = "",
    attachment_kind: str = "auto",
) -> dict[str, str]:
    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Attachment file not found: {path}")

    if not path.is_file():
        raise RuntimeError(f"Attachment path is not a file: {path}")

    kind = classify_attachment(path, requested_kind=attachment_kind)

    await open_attachment_menu(page)
    await select_attachment_file(page, path, kind)
    await fill_attachment_caption(page, caption)
    await click_attachment_send(page)

    mime_type, _ = mimetypes.guess_type(str(path))

    return {
        "path": str(path),
        "filename": path.name,
        "kind": kind,
        "mime_type": mime_type or "",
    }


async def read_visible_messages(page: Page, limit: int = 20) -> list[dict[str, str]]:
    if limit <= 0:
        return []

    message_selectors = [
        "div.message-in",
        "div.message-out",
        "div[data-testid='msg-container']",
        "div[role='row']",
    ]

    raw_messages: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for selector in message_selectors:
        try:
            nodes = page.locator(selector)
            count = await nodes.count()

            if count == 0:
                continue

            start_index = max(0, count - (limit * 4))

            for index in range(start_index, count):
                node = nodes.nth(index)

                try:
                    if not await node.is_visible(timeout=500):
                        continue
                except Exception:
                    continue

                direction = await infer_message_direction(node)
                item_type = await infer_message_type(node)
                raw_text = await safe_inner_text(node)
                cleaned_text, msg_time = split_message_text_and_time(raw_text)

                filename = await extract_possible_filename(node)
                media_label = build_media_label(item_type, filename, cleaned_text)

                if item_type != "text":
                    final_text = media_label
                else:
                    final_text = cleaned_text

                if not final_text:
                    continue

                key = (direction, item_type, msg_time, final_text)
                if key in seen:
                    continue

                seen.add(key)

                raw_messages.append(
                    {
                        "type": item_type,
                        "text": final_text,
                        "direction": direction,
                        "time": msg_time,
                        "filename": filename,
                    }
                )

            if raw_messages:
                break

        except Exception:
            continue

    return raw_messages[-limit:]


async def safe_inner_text(locator: Locator) -> str:
    try:
        return (await locator.inner_text(timeout=1000)).strip()
    except Exception:
        return ""


async def infer_message_direction(node: Locator) -> str:
    try:
        class_name = await node.get_attribute("class")
        if class_name:
            if "message-in" in class_name:
                return "incoming"
            if "message-out" in class_name:
                return "outgoing"
    except Exception:
        pass

    return "unknown"


async def infer_message_type(node: Locator) -> str:
    """
    Best-effort visible message type detection.

    Returns:
    - text
    - image
    - document
    - audio
    - video
    - media
    """

    try:
        if await node.locator("img").count() > 0:
            # Emoji/profile images can exist inside text messages, so only call this image
            # if the node text is sparse or it has media-ish controls.
            text = await safe_inner_text(node)
            if not text or len(text) < 80:
                return "image"
    except Exception:
        pass

    try:
        if await node.locator("audio").count() > 0:
            return "audio"
    except Exception:
        pass

    try:
        if await node.locator("video").count() > 0:
            return "video"
    except Exception:
        pass

    text = await safe_inner_text(node)
    text_lower = text.lower()

    filename = await extract_possible_filename(node)
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return "image"
        if suffix in DOCUMENT_SUFFIXES:
            return "document"

    document_markers = [
        ".pdf",
        ".docx",
        ".xlsx",
        ".csv",
        ".txt",
        "pages",
        "kb",
        "mb",
        "download",
    ]

    if any(marker in text_lower for marker in document_markers):
        if re.search(r"\.[a-z0-9]{2,5}\b", text_lower):
            return "document"

    audio_markers = ["voice message", "audio", ".mp3", ".ogg", ".m4a", ".wav"]
    if any(marker in text_lower for marker in audio_markers):
        return "audio"

    return "text"


async def extract_possible_filename(node: Locator) -> str:
    text = await safe_inner_text(node)

    if not text:
        return ""

    # Find common filename-looking token.
    match = re.search(
        r"([A-Za-z0-9_\- ().]+?\.(pdf|docx?|xlsx?|csv|txt|zip|rar|7z|pptx?|jpg|jpeg|png|gif|webp|mp3|ogg|m4a|wav|mp4|mov))",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return ""


def build_media_label(item_type: str, filename: str, cleaned_text: str) -> str:
    if item_type == "text":
        return cleaned_text

    if filename:
        return filename

    if cleaned_text:
        return cleaned_text

    return f"<{item_type} message>"


def split_message_text_and_time(raw_text: str) -> tuple[str, str]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    if not lines:
        return "", ""

    msg_time = ""

    last = lines[-1]
    parts = last.split()

    if parts:
        maybe_time = parts[0]
        if _looks_like_time(maybe_time):
            msg_time = maybe_time
            lines = lines[:-1]

    text = "\n".join(lines).strip()

    if not text and raw_text.strip():
        text = raw_text.strip()

    return text, msg_time


def _looks_like_time(value: str) -> bool:
    if len(value) != 5:
        return False

    if value[2] != ":":
        return False

    hh = value[:2]
    mm = value[3:]

    if not hh.isdigit() or not mm.isdigit():
        return False

    hour = int(hh)
    minute = int(mm)

    return 0 <= hour <= 23 and 0 <= minute <= 59
