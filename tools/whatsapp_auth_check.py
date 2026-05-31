"""Usage:
python whatsapp_auth_check.py

Opens WhatsApp Web in a dedicated persistent browser profile and waits for login.
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "Demo14_RPA"
PROFILE_DIR = SCRIPT_DIR / "runtime_data" / "whatsapp_profile"
WHATSAPP_URL = "https://web.whatsapp.com/"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check whether WhatsApp Web is authenticated in a dedicated profile."
    )

    parser.add_argument(
        "--slowmo",
        type=int,
        default=100,
        help="Slow motion delay in ms. Default: 100",
    )

    return parser.parse_args()


def get_profile_dir() -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILE_DIR


async def open_whatsapp(page):
    print(f"[OPEN] {WHATSAPP_URL}")
    await page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=120000)


async def is_logged_in(page) -> bool:
    selectors = [
        "div[aria-label='Chats list']",
        "div[aria-label='Chat list']",
        "span[data-icon='new-chat-outline']",
        "button[aria-label='New chat']",
        "div[aria-label='Search or start new chat']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)
            if await locator.count() and await locator.first.is_visible():
                return True
        except Exception:
            continue

    return False


async def wait_for_login(page, timeout_ms: int) -> bool:
    logged_in_selectors = [
        "div[aria-label='Chats list']",
        "div[aria-label='Chat list']",
        "span[data-icon='new-chat-outline']",
        "button[aria-label='New chat']",
        "div[aria-label='Search or start new chat']",
    ]
    qr_selectors = [
        "canvas[aria-label*='Scan me']",
        "div[aria-label*='Scan me']",
        "img[alt*='Scan me']",
        "div[data-testid='qrcode']",
    ]

    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    qr_notified = False

    while asyncio.get_running_loop().time() < deadline:
        if await is_logged_in(page):
            return True

        for selector in qr_selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() and await locator.first.is_visible():
                    if not qr_notified:
                        print("Scan the WhatsApp QR code, then leave the browser open until login completes.")
                        qr_notified = True
                    break
            except Exception:
                continue

        await page.wait_for_timeout(1000)

    return False


async def main():
    args = parse_args()
    profile_dir = get_profile_dir()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            slow_mo=args.slowmo,
            viewport={"width": 1400, "height": 900},
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await open_whatsapp(page)

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
            except PlaywrightTimeoutError:
                pass

            if await is_logged_in(page):
                print("[OK] WhatsApp Web profile is authenticated.")
                return

            if await wait_for_login(page, timeout_ms=120000):
                print("[OK] WhatsApp Web profile is authenticated.")
            else:
                print("[FAIL] WhatsApp Web login was not completed within 120 seconds.")
        finally:
            await context.close()


if __name__ == "__main__":
    asyncio.run(main())
