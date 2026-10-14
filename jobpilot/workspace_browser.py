"""Connect, with Chrome permission, to the user's regular browser profile.

Login pages open through Chrome normally. Never launch a replacement profile,
copy cookies, change browser security flags, or close the user's browser.
"""

import asyncio
import os
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
from .config import DATA_DIR, settings

MARKER = DATA_DIR / "chrome-workspace-id"
COOKIE = "jobpilot_workspace"
BROWSER_PREFERENCES = DATA_DIR / "browser-preferences.json"
SETUP_URL = "chrome://inspect/#remote-debugging"
SETUP_MESSAGE = (
    "Open your regular Chrome, enable remote debugging at "
    "chrome://inspect/#remote-debugging, then retry and allow Chrome's connection prompt. "
    "Sign in normally before starting automation."
)


def dashboard_url():
    return f"http://127.0.0.1:{settings.dashboard_port}"


def regular_profile():
    """Only locate Chrome's endpoint metadata; never read its cookie/password stores."""
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "google-chrome"
    )


def marker():
    if not MARKER.exists():
        MARKER.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    return MARKER.read_text(encoding="utf-8").strip()


def endpoint():
    try:
        lines = (regular_profile() / "DevToolsActivePort").read_text().splitlines()
        port = int(lines[0])
        # The permission-based endpoint can require approval before /json/version
        # is available. Connect directly to the exact websocket supplied by Chrome.
        if not 1 <= port <= 65535 or not re.fullmatch(
            r"/devtools/browser/[a-zA-Z0-9_-]+", lines[1]
        ):
            return None
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            pass
        return f"ws://127.0.0.1:{port}{lines[1]}"
    except (OSError, ValueError, IndexError, KeyError):
        return None


def ensure_workspace():
    address = endpoint()
    if not address:
        raise ValueError(SETUP_MESSAGE)
    return address


def profile_directory():
    if not BROWSER_PREFERENCES.is_file():
        return None
    selected = json.loads(BROWSER_PREFERENCES.read_text(encoding="utf-8")).get(
        "profile_directory"
    )
    if selected is not None and not re.fullmatch(r"Default|Profile [0-9]+", selected):
        raise ValueError("Choose a standard Chrome profile directory")
    return selected


def open_regular(url):
    from .browser import installed_chrome_path

    # No user-data-dir, automation or remote-debugging switches. Chrome routes
    # the new tab to its regular running profile (or opens the normal browser).
    subprocess.Popen(
        [
            str(installed_chrome_path()),
            *(
                [f"--profile-directory={profile_directory()}"]
                if profile_directory()
                else []
            ),
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def open_platform(name):
    from .dashboard.connections import LINKS
    from .registry import platform_names

    if name not in platform_names():
        raise ValueError("Choose an enabled platform")
    # Open the home/jobs page: an already-authenticated account needn't log in again.
    open_regular(LINKS[name])


async def identify_context(context):
    # Native Chrome owns session persistence. Never clear it on worker startup.
    await context.add_cookies(
        [
            {
                "name": COOKIE,
                "value": marker(),
                "url": dashboard_url(),
                "httpOnly": True,
                "sameSite": "Strict",
            }
        ]
    )


async def open_workspace():
    await asyncio.to_thread(open_regular, dashboard_url() + "/#platforms")


async def verify_browser():
    from .browser import BrowserSession

    session = BrowserSession("connection-check")
    try:
        await session.start()
        return {"connected": True}
    finally:
        await session.close()


def status(cookie):
    cookie = cookie if isinstance(cookie, str) and cookie.isascii() else ""
    ready = bool(endpoint())
    known = MARKER.read_text(encoding="utf-8").strip() if MARKER.exists() else ""
    return {
        "running": ready,
        "same_browser": bool(ready and known and secrets.compare_digest(cookie, known)),
        "product": "Google Chrome",
        "mode": "regular",
        "remember": True,
        "setup_required": not ready,
    }


def browser_identity():
    return (
        (regular_profile() / "DevToolsActivePort").read_text(encoding="utf-8").strip()
    )
