"""Shared sessions and progress use isolated data and the installed Chrome binary."""

import asyncio
import subprocess
import time

import pytest
from playwright.async_api import async_playwright
from jobpilot import workspace_browser as workspace
from jobpilot.browser import BrowserSession, installed_chrome_path
from jobpilot.dashboard.runner import Runner
from jobpilot.progress import emit


async def test_shared_chrome_reuses_login_and_preserves_user_tabs(
    monkeypatch, tmp_path
):
    profile = tmp_path / "chrome"
    monkeypatch.setattr(workspace, "regular_profile", lambda: profile)
    monkeypatch.setattr(workspace, "MARKER", tmp_path / "identity")
    process = subprocess.Popen(
        [
            str(installed_chrome_path()),
            f"--user-data-dir={profile}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            address = workspace.endpoint()
            if address:
                break
            await asyncio.sleep(0.1)
        assert address, "Installed Chrome must expose its owned loopback endpoint"
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(address)
            context = browser.contexts[0]
            user_tab = await context.new_page()
            await user_tab.route(
                "**/*",
                lambda r: r.fulfill(
                    body="<p>User sign-in tab</p>", content_type="text/html"
                ),
            )
            await user_tab.goto("https://auth.example.test/")
            await user_tab.evaluate(
                "document.cookie='fixture_session=signed-in; path=/; SameSite=Lax'"
            )
            first = BrowserSession("linkedin")
            await first.start()
            assert first.page != user_tab
            assert any(
                c["name"] == "fixture_session"
                for c in await first.context.cookies("https://auth.example.test/")
            )
            assert workspace.status(workspace.marker())["same_browser"]
            assert not workspace.status(None)["same_browser"]
            await first.close()
            assert not user_tab.is_closed()
            assert await user_tab.text_content("p") == "User sign-in tab"
            second = BrowserSession("wellfound")
            await second.start()
            assert any(
                c["name"] == "fixture_session"
                for c in await second.context.cookies("https://auth.example.test/")
            )
            await second.close()
            assert workspace.endpoint() == address
            assert (
                len(context.pages) == 2
            )  # original tab and user sign-in, worker tabs gone
            control = await browser.new_browser_cdp_session()
            await control.send("Browser.close")
    finally:
        if process.poll() is None:
            process.terminate()  # This test owns this process and isolated profile only.
        await asyncio.to_thread(process.wait, 10)


async def test_real_chrome_restart_retains_session_without_extending_expiry(
    monkeypatch, tmp_path
):
    profile = tmp_path / "persistent-chrome"
    monkeypatch.setattr(workspace, "regular_profile", lambda: profile)
    expires = int(time.time()) + 3600
    for iteration in range(2):
        # Test-owned profile only; production never launches with these switches.
        command = [
            str(installed_chrome_path()),
            f"--user-data-dir={profile}",
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
            "--restore-last-session",
            "about:blank",
        ]
        assert "--restore-last-session" in command
        process = subprocess.Popen(
            command[:-1] + ["--headless=new", command[-1]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                address = workspace.endpoint()
                if address:
                    break
                await asyncio.sleep(0.1)
            assert address
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(address)
                context = browser.contexts[0]
                if iteration == 0:
                    await context.add_cookies(
                        [
                            {
                                "name": "session_fixture",
                                "value": "signed-in",
                                "url": "https://example.test/",
                            },
                            {
                                "name": "persistent_fixture",
                                "value": "signed-in",
                                "url": "https://example.test/",
                                "expires": expires,
                            },
                            {
                                "name": "expired_fixture",
                                "value": "expired",
                                "url": "https://example.test/",
                                "expires": int(time.time()) - 60,
                            },
                        ]
                    )
                else:
                    cookies = {
                        c["name"]: c
                        for c in await context.cookies("https://example.test/")
                    }
                    assert "session_fixture" in cookies
                    assert cookies["persistent_fixture"]["expires"] == expires
                    assert "expired_fixture" not in cookies
                control = await browser.new_browser_cdp_session()
                await control.send("Browser.close")
            await asyncio.to_thread(process.wait, 10)
        finally:
            if process.poll() is None:
                process.terminate()
                await asyncio.to_thread(process.wait, 10)


@pytest.mark.parametrize("cancel", [False, True])
def test_progress_survives_completion_and_cancellation(monkeypatch, database, cancel):
    import threading

    entered = threading.Event()

    async def work(self, action, platform, options):
        emit(
            "discover",
            "Found fixtures",
            platform="linkedin",
            state="completed",
            metrics={"jobs_found": 3},
        )
        for n in range(205):
            emit(
                "apply",
                "Fixture progress",
                platform="linkedin",
                current=n,
                total=205,
                metrics={"dry_run": n},
            )
        entered.set()
        if cancel:
            await asyncio.sleep(60)
        emit(
            "apply",
            "Finished",
            platform="linkedin",
            state="completed",
            current=205,
            total=205,
            metrics={"dry_run": 205},
        )
        return {"jobs": [{"status": "dry_run", "success": False}]}

    monkeypatch.setattr(Runner, "_perform", work)
    runner = Runner(database)
    try:
        run_id = runner.start("pipeline", "linkedin", {"dry_run": True, "limit": 5})
        assert entered.wait(10)
        if cancel:
            assert runner.cancel()
        deadline = time.monotonic() + 10
        while (
            runner.list()[0]["state"] in ("queued", "running")
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        run = runner.list()[0]
        assert run["state"] == ("cancelled" if cancel else "completed")
        assert len(run["events"]) == 200
        assert run["event_count"] > 200
        assert run["progress"][0]["metrics"]["jobs_found"] == 3
        assert run["progress"][1]["metrics"]["dry_run"] == (204 if cancel else 205)
        assert len(runner.events(run_id)) == run["event_count"]
    finally:
        runner.executor.shutdown(wait=True)
