"""Session preferences and scoped local sign-out; never export browser tokens."""

import json
import re
import time
from urllib.parse import urlsplit
from filelock import FileLock
from .config import DATA_DIR

PREFERENCES = DATA_DIR / "session-preferences.json"


def preferences():
    if not PREFERENCES.exists():
        return {"remember": True, "signed_out": []}
    data = json.loads(PREFERENCES.read_text(encoding="utf-8"))
    return {
        "remember": data.get("remember", True) is True,
        "signed_out": data.get("signed_out", []),
    }


def update_preferences(**values):
    with FileLock(str(PREFERENCES.with_suffix(".lock")), timeout=5):
        data = {**preferences(), **values}
        _write_preferences(data)
    return data


def _write_preferences(data):
    temporary = PREFERENCES.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    # Windows indexers/sync clients can briefly hold the destination open.
    # Keep the old file intact and retry the atomic rename, never truncate it.
    for attempt in range(5):
        try:
            temporary.replace(PREFERENCES)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def mark_signed_out(name, value=True):
    with FileLock(str(PREFERENCES.with_suffix(".lock")), timeout=5):
        data = preferences()
        blocked = set(data["signed_out"])
        blocked.add(name) if value else blocked.discard(name)
        data["signed_out"] = sorted(blocked)
        _write_preferences(data)
        return data


async def clear_platform(context, name):
    from .applier import get_applier
    from .dashboard.connections import save_check

    applier = get_applier(name)
    domains = applier.allowed_domains

    def belongs(host):
        return any(host == domain or host.endswith("." + domain) for domain in domains)

    cookies = await context.cookies()
    origins = {
        urlsplit(url).scheme + "://" + urlsplit(url).netloc
        for url in (applier.HOME_URL, applier.LOGIN_URL, applier.AUTH_URL)
        if url and belongs(urlsplit(url).hostname or "")
    }
    for domain in domains:
        origins.update((f"https://{domain}", f"https://www.{domain}"))
    for cookie in cookies:
        domain = cookie["domain"].lstrip(".")
        if belongs(domain):
            origins.add(f"https://{domain}")
    tabs = [tab for tab in context.pages if belongs(urlsplit(tab.url).hostname or "")]
    origins.update(
        f"{urlsplit(tab.url).scheme}://{urlsplit(tab.url).netloc}" for tab in tabs
    )
    # Close this site's tabs so scripts cannot recreate cleared tokens. Other sites stay open.
    for tab in tabs:
        await tab.close()
    control_tab = await context.new_page()
    try:
        control = await context.new_cdp_session(control_tab)
        for origin in sorted(origins):
            await control.send(
                "Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"}
            )
        for domain in domains:
            await context.clear_cookies(
                domain=re.compile(r"(^|\.)" + re.escape(domain) + r"$", re.I)
            )
        await control.detach()
    finally:
        await control_tab.close()
    mark_signed_out(name)
    save_check(
        name, "signed_out", "Signed out in JobPraapti. Sign in again to reconnect."
    )


async def clear_platforms(context, names):
    for name in names:
        await clear_platform(context, name)


async def manage_sessions(*, remember=None, platform=None):
    if remember is False:
        raise ValueError(
            "Regular Chrome manages saved sign-ins. Use Sign out here to clear a platform "
            "explicitly; JobPraapti never clears your regular browser on startup."
        )
    if remember is True and platform is None:
        update_preferences(remember=True)
        return {"remember": True}
    from .browser import BrowserSession
    from .registry import PLATFORMS

    session = BrowserSession("session-settings")
    try:
        await session.start()
        if platform:
            await clear_platforms(
                session.context, list(PLATFORMS) if platform == "all" else [platform]
            )
    finally:
        await session.close()
    return {"remember": True}
