"""Capture the local web UI without opening profile or credential forms."""

import asyncio
import json
from jobpilot.config import DATA_DIR
from jobpilot.browser import chrome_launch_options
from playwright.async_api import async_playwright


async def main():
    target = DATA_DIR / "preview"
    target.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(**chrome_launch_options())
        page = await browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda e: errors.append(type(e).__name__))
        await page.goto("http://127.0.0.1:5000/")
        await page.get_by_role("heading", name="Your latest applications").wait_for()
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(target / "desktop.png"), full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(target / "mobile.png"), full_page=True)
        overflow = await page.evaluate(
            "document.documentElement.scrollWidth > innerWidth"
        )
        print(
            json.dumps(
                {
                    "errors": errors,
                    "overflow": overflow,
                    "screenshots": str(target),
                }
            )
        )
        await browser.close()


asyncio.run(main())
