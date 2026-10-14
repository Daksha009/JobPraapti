"""Use the device's installed Google Chrome with private persistent sessions."""

import os
from pathlib import Path
import shutil
import sys
from contextlib import asynccontextmanager
from contextvars import ContextVar

from filelock import FileLock
from playwright.async_api import async_playwright

from .config import DATA_DIR, settings

_pool = ContextVar("jobpraapti_browser_pool", default=None)


async def connect_regular(playwright):
    import asyncio
    from .workspace_browser import ensure_workspace, identify_context, SETUP_MESSAGE

    address = await asyncio.to_thread(ensure_workspace)
    try:
        browser = await playwright.chromium.connect_over_cdp(address, timeout=60000)
        if not browser.contexts:
            raise ValueError("Chrome did not expose a regular browser context")
        await identify_context(browser.contexts[0])
        return browser
    except Exception as exc:
        # Never surface the endpoint (which can contain an authorization token).
        raise ValueError(
            "Chrome connection was not approved or is unavailable. " + SETUP_MESSAGE
        ) from exc


@asynccontextmanager
async def reuse_browser():
    """One permission request per run; release the connection without closing Chrome."""
    if _pool.get() is not None:
        yield
        return
    resources = {}
    token = _pool.set(resources)
    try:
        yield
    finally:
        _pool.reset(token)
        if resources.get("playwright"):
            await resources["playwright"].stop()


def installed_chrome_path() -> Path:
    """Resolve Google Chrome; never silently use Playwright's testing browser."""
    configured = os.environ.get("JOBPILOT_CHROME_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise RuntimeError(
                "JOBPILOT_CHROME_PATH does not point to an installed Chrome executable"
            )
        return path.resolve()
    if sys.platform == "win32":
        candidates = [
            Path(root) / "Google/Chrome/Application/chrome.exe"
            for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
            if (root := os.environ.get(name))
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:
        candidates = [
            Path(path)
            for name in ("google-chrome", "google-chrome-stable")
            if (path := shutil.which(name))
        ]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise RuntimeError(
        "Google Chrome is not installed. Install it from https://www.google.com/chrome/ or set JOBPILOT_CHROME_PATH to your installed Chrome executable."
    )


def chrome_launch_options() -> dict:
    """Common executable selection for application sessions and automated tests."""
    return {"executable_path": str(installed_chrome_path())}


class BrowserSession:
    def __init__(self, platform: str):
        self.platform = platform
        self.context = self.page = self._playwright = None
        self._browser = None
        self._pooled = False
        self.keep_page = False
        self._lock = FileLock(str(DATA_DIR / f"{platform}.browser.lock"))

    async def start(self, headless=True):
        self._lock.acquire(timeout=0)
        try:
            pool = _pool.get()
            self._pooled = pool is not None
            if pool is not None:
                if pool.get("error"):
                    raise ValueError(pool["error"])
                if not pool.get("browser"):
                    pool["playwright"] = await async_playwright().start()
                    try:
                        pool["browser"] = await connect_regular(pool["playwright"])
                    except ValueError as exc:
                        pool["error"] = str(exc)
                        raise
                self._browser = pool["browser"]
            else:
                self._playwright = await async_playwright().start()
                self._browser = await connect_regular(self._playwright)
            self.context = self._browser.contexts[0]
            # Each operation owns only its tab; user tabs and shared sessions stay open.
            self.page = await self.context.new_page()
            self.page.set_default_timeout(
                settings.platforms.get("scraping", {}).get("timeout_seconds", 30) * 1000
            )
            return self
        except BaseException:
            await self.close()
            raise

    async def close(self):
        try:
            if self.page and not self.keep_page:
                await self.page.close()
        finally:
            try:
                if self._playwright:
                    await self._playwright.stop()
            finally:
                self.context = self.page = self._playwright = self._browser = None
                self._lock.release()
