"""
Usage:
python whatsapp_search_chat.py --chat "Contact or Group Name"
python whatsapp_search_chat.py --chat "Contact or Group Name" --slowmo 50

Searches for and opens a WhatsApp Web chat.

Requires:
- whatsapp_web.py
- Authenticated persistent profile at runtime_data/whatsapp_profile/
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
    require_login,
    safe_print,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search for and open a WhatsApp Web chat."
    )

    parser.add_argument(
        "--chat",
        required=True,
        help="Contact or group chat name to search for.",
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
        help="Keep browser open after opening the chat.",
    )

    return parser.parse_args()


async def run(chat_name: str, slowmo: int = 100, keep_open: bool = False) -> bool:
    async with async_playwright() as p:
        context = await launch_whatsapp_context(p, slowmo=slowmo)

        try:
            page = await get_or_create_page(context)

            await open_whatsapp(page)
            await require_login(page)

            found = await find_chat(page, chat_name)

            if found:
                safe_print(f"[OK] Chat opened: {chat_name}")
                if keep_open:
                    safe_print("Browser left open. Close it manually when done.")
                    await page.wait_for_timeout(24 * 60 * 60 * 1000)
                return True

            safe_print(f"[FAILED] Chat not found: {chat_name}")
            return False

        finally:
            if not keep_open:
                await context.close()


def main() -> None:
    args = parse_args()

    try:
        found = asyncio.run(
            run(
                chat_name=args.chat,
                slowmo=args.slowmo,
                keep_open=args.keep_open,
            )
        )

        if not found:
            raise SystemExit(1)

    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"WhatsApp Web timeout: {error}") from error


if __name__ == "__main__":
    main()