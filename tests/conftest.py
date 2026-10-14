"""Tests never read personal configuration, credentials or the production database."""

import os
import tempfile
import pytest
import pytest_asyncio

TEST_HOME = tempfile.TemporaryDirectory(prefix="jobpilot-tests-")
os.environ["JOBPILOT_HOME"] = TEST_HOME.name
for key in list(os.environ):
    if key == "GEMINI_API_KEY" or key.endswith(("_EMAIL", "_PASSWORD")):
        os.environ.pop(key)

from jobpilot.config import settings
from jobpilot.registry import PLATFORMS
from jobpilot.database import Database
from jobpilot.browser import chrome_launch_options


@pytest.fixture(autouse=True)
def profile(monkeypatch, tmp_path):
    from jobpilot import sessions, workspace_browser

    monkeypatch.setattr(
        workspace_browser, "regular_profile", lambda: tmp_path / "chrome"
    )
    monkeypatch.setattr(workspace_browser, "MARKER", tmp_path / "browser-marker")
    monkeypatch.setattr(
        workspace_browser, "BROWSER_PREFERENCES", tmp_path / "browser-preferences.json"
    )
    from jobpilot.dashboard import connections

    monkeypatch.setattr(connections, "DATA_DIR", tmp_path / "connection-data")

    monkeypatch.setattr(sessions, "PREFERENCES", tmp_path / "session-preferences.json")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\nSynthetic resume fixture")
    profile = {
        "personal": {
            "full_name": "Test Candidate",
            "email": "candidate@test.invalid",
            "phone": "+910000000000",
        },
        "preferences": {
            "roles": ["Software Engineer"],
            "skills": ["Python"],
            "locations": ["Remote"],
            "min_experience_years": 0,
            "max_experience_years": 2,
            "min_match_score": 40,
        },
        "resume": {"path": str(resume)},
        "application_defaults": {"years_of_experience": 0, "answers": {}},
    }
    monkeypatch.setattr(settings, "_profile", profile)
    monkeypatch.setattr(
        settings,
        "_platforms",
        {
            "platforms": {
                name: {"enabled": True, "daily_limit": 2, "delay_seconds": 0}
                for name in PLATFORMS
            }
        },
    )
    return profile


@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / "isolated.db")


@pytest_asyncio.fixture
async def page():
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chrome_launch_options())
        context = await browser.new_context()
        await context.route(
            "**/*",
            lambda route: route.fulfill(
                status=200, content_type="text/html", body="<html><body></body></html>"
            ),
        )
        page = await context.new_page()
        yield page
        await browser.close()
