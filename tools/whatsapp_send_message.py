"""
Usage:
python whatsapp_send_message.py --chat "Contact or Group Name" --message "Hello from RPA"

Send image:
python whatsapp_send_message.py --chat "Contact or Group Name" --file "C:\\temp\\image.png" --caption "Image caption"

Send document:
python whatsapp_send_message.py --chat "Contact or Group Name" --file "C:\\temp\\file.pdf" --caption "Document caption"

Send file and force kind:
python whatsapp_send_message.py --chat "Contact or Group Name" --file "C:\\temp\\file.pdf" --kind document

Options:
python whatsapp_send_message.py --chat "Contact or Group Name" --message "Hello" --slowmo 50
python whatsapp_send_message.py --chat "Contact or Group Name" --file "C:\\temp\\image.png" --keep-open

Sends one WhatsApp Web text message or one attachment.

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
    send_attachment,
    send_text_message,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one WhatsApp Web text message or attachment."
    )

    parser.add_argument(
        "--chat",
        required=True,
        help="Contact or group chat name to send to.",
    )

    parser.add_argument(
        "--message",
        default="",
        help="Plain-text message. If --file is used, this becomes fallback caption.",
    )

    parser.add_argument(
        "--file",
        default="",
        help="Optional file path to send as image/document attachment.",
    )

    parser.add_argument(
        "--caption",
        default="",
        help="Optional attachment caption. Overrides --message as caption.",
    )

    parser.add_argument(
        "--kind",
        choices=["auto", "image", "document"],
        default="auto",
        help="Attachment type. Defaults to auto.",
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
        help="Keep browser open after sending.",
    )

    return parser.parse_args()


async def run(
    chat_name: str,
    message: str = "",
    file_path: str = "",
    caption: str = "",
    kind: str = "auto",
    slowmo: int = 100,
    keep_open: bool = False,
) -> bool:
    if not message.strip() and not file_path.strip():
        raise ValueError("Provide either --message or --file.")

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

            if file_path.strip():
                effective_caption = caption.strip() or message.strip()

                result = await send_attachment(
                    page=page,
                    file_path=file_path,
                    caption=effective_caption,
                    attachment_kind=kind,
                )

                safe_print(f"[OK] Attachment sent to: {chat_name}")
                safe_print(f"Type: {result['kind']}")
                safe_print(f"File: {result['filename']}")

            else:
                await send_text_message(page, message)
                safe_print(f"[OK] Message sent to: {chat_name}")

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
        sent = asyncio.run(
            run(
                chat_name=args.chat,
                message=args.message,
                file_path=args.file,
                caption=args.caption,
                kind=args.kind,
                slowmo=args.slowmo,
                keep_open=args.keep_open,
            )
        )

        if not sent:
            raise SystemExit(1)

    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"WhatsApp Web timeout: {error}") from error


if __name__ == "__main__":
    main()