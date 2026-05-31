"""
Usage:
python whatsapp_read_recent_messages.py --chat "Contact or Group Name"
python whatsapp_read_recent_messages.py --chat "Contact or Group Name" --limit 10
python whatsapp_read_recent_messages.py --chat "Contact or Group Name" --limit 10 --slowmo 50
python whatsapp_read_recent_messages.py --chat "Contact or Group Name" --limit 10 --keep-open

Reads recent visible WhatsApp Web messages from one chat.

Supports best-effort detection of:
- text
- images
- documents
- audio / voice-note-like messages
- videos

Constraints:
- Visible messages only.
- Best-effort extraction.
- No full history scraping.
- Does not download attachments yet.
"""

from __future__ import annotations

import argparse
import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from whatsapp_web import (
    find_chat,
    get_or_create_page,
    launch_whatsapp_context,
    open_whatsapp,
    read_visible_messages,
    require_login,
    safe_print,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read recent visible WhatsApp Web messages from a chat."
    )

    parser.add_argument(
        "--chat",
        required=True,
        help="Contact or group chat name to open.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of visible messages to print. Default: 20.",
    )

    parser.add_argument(
        "--slowmo",
        type=int,
        default=100,
        help="Playwright slow motion delay in ms. Default: 100.",
    )

    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep browser open after reading messages.",
    )

    return parser.parse_args()


def print_messages(messages: list[dict[str, str]]) -> None:
    if not messages:
        safe_print("No visible messages found.")
        return

    for message in messages:
        direction = message.get("direction", "unknown") or "unknown"
        msg_type = message.get("type", "text") or "text"
        msg_time = message.get("time", "") or ""
        text = message.get("text", "") or ""
        filename = message.get("filename", "") or ""

        prefix = f"[{direction}] [{msg_type}]"

        if msg_time:
            prefix += f" {msg_time}:"
        else:
            prefix += ":"

        if filename and filename != text:
            safe_print(f"{prefix} {filename} | {text}")
        else:
            safe_print(f"{prefix} {text}")


async def run(
    chat_name: str,
    limit: int = 20,
    slowmo: int = 100,
    keep_open: bool = False,
) -> bool:
    async with async_playwright() as p:
        context = await launch_whatsapp_context(p, slowmo=slowmo)

        try:
            page = await get_or_create_page(context)

            await open_whatsapp(page)
            await require_login(page)

            found = await find_chat(page, chat_name)
            if not found:
                safe_print(f"[FAILED] Chat not found: {chat_name}")
                return False

            await page.wait_for_timeout(1500)

            messages = await read_visible_messages(page, limit=limit)
            print_messages(messages)

            if keep_open:
                safe_print("Browser left open. Close it manually when done.")
                await page.wait_for_timeout(24 * 60 * 60 * 1000)

            return True

        finally:
            if not keep_open:
                await context.close()


def main() -> None:
    args = parse_args()

    try:
        success = asyncio.run(
            run(
                chat_name=args.chat,
                limit=args.limit,
                slowmo=args.slowmo,
                keep_open=args.keep_open,
            )
        )

        if not success:
            raise SystemExit(1)

    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"WhatsApp Web timeout: {error}") from error


if __name__ == "__main__":
    main()