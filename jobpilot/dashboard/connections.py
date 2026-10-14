"""Account connection checks. No application clicks and no secret-valued responses."""

import asyncio
import json
import httpx
from ..config import DATA_DIR, settings
from ..registry import PLATFORMS

LINKS = {
    "wellfound": "https://wellfound.com/jobs/home",
    "hirist": "https://www.hirist.tech/",
    "cutshort": "https://cutshort.io/profile/all-jobs",
    "linkedin": "https://www.linkedin.com/jobs/",
    "glassdoor": "https://www.glassdoor.co.in/Job/index.htm",
    "foundit": "https://www.foundit.in/",
}


def save_check(platform, status, message):
    from datetime import datetime, timezone

    path = DATA_DIR / "connections" / f"{platform}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "platform": platform,
        "browser_mode": "regular",
        "status": status,
        "message": message,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result), encoding="utf-8")
    temporary.replace(path)
    return result


def connection_status():
    from ..applier import get_applier

    result = []
    for name in PLATFORMS:
        cfg = settings.platforms.get("platforms", {}).get(name, {})
        saved = DATA_DIR / "connections" / f"{name}.json"
        data = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {}
        if data.get("browser_mode") != "regular":
            data = {
                "message": "Verify your existing login in regular Chrome to connect."
            }
        email, password = settings.credentials(name)
        result.append(
            {
                "name": name,
                "platform": name,
                "enabled": cfg.get("enabled", False),
                "url": LINKS.get(name, cfg.get("base_url", "")),
                "login_url": get_applier(name).LOGIN_URL,
                "email_saved": bool(email),
                "password_saved": bool(password),
                "session_saved": data.get("status") == "connected",
                "status": data.get("status", "not_checked"),
                "checked_at": data.get("checked_at"),
                "message": data.get(
                    "message", "Check this account or sign in to connect."
                ),
                "daily_limit": cfg.get("daily_limit", 20),
            }
        )
    return result


async def check_gemini():
    key = settings.gemini_api_key
    if not key:
        return save_check(
            "gemini",
            "not_configured",
            "No API key saved. Offline matching is available.",
        )
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key},
            )
        if response.status_code == 200:
            models = response.json().get("models", [])
            available = any(
                m.get("name", "").removeprefix("models/") == settings.gemini_model
                for m in models
            )
            return save_check(
                "gemini",
                "connected" if available else "model_unavailable",
                "API key accepted; configured model is available."
                if available
                else "API key accepted, but the configured model was not listed. Offline matching remains available.",
            )
        return save_check(
            "gemini",
            "action_required",
            f"Google rejected the API check (HTTP {response.status_code}). Replace the key or check API access. Offline matching is available.",
        )
    except Exception as exc:
        return save_check(
            "gemini",
            "unavailable",
            f"Could not reach Google ({type(exc).__name__}). No model content request was made.",
        )


async def check_platform(name):
    from ..applier import get_applier

    applier = get_applier(name)
    try:
        await applier.start_browser(headless=True)
        applier.page.set_default_timeout(15000)
        authenticated = await asyncio.wait_for(applier.is_logged_in(), timeout=65)
        if authenticated:
            from ..sessions import mark_signed_out

            mark_signed_out(name, False)
        return save_check(
            name,
            "connected" if authenticated else "action_required",
            "Authenticated session verified. No applications were submitted."
            if authenticated
            else "Sign in in the browser to complete verification, SSO or a multi-step login.",
        )
    except ValueError as exc:
        return save_check(name, "action_required", str(exc))
    except Exception as exc:
        return save_check(
            name,
            "action_required",
            f"Login could not be verified ({type(exc).__name__}). Use Sign in to complete it manually.",
        )
    finally:
        await applier.stop_browser()


async def browser_login(name, done):
    from ..workspace_browser import open_platform

    open_platform(name)
    for _ in range(600):
        if done.is_set():
            return await check_platform(name)
        await asyncio.sleep(1)
    return save_check(
        name,
        "action_required",
        "Sign-in verification timed out. Your Chrome tab stays open.",
    )
