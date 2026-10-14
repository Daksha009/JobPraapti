"""Regular Chrome consent, startup isolation and read-only authentication."""

from unittest.mock import AsyncMock, Mock
import pytest
from jobpilot import workspace_browser as workspace
from jobpilot import browser
from jobpilot.applier import get_applier


def test_missing_browser_does_not_launch_another_profile(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(workspace.subprocess, "Popen", launch)
    with pytest.raises(ValueError, match="chrome://inspect"):
        workspace.ensure_workspace()
    launch.assert_not_called()


def test_platform_login_uses_regular_chrome_without_debugging_flags(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(workspace.subprocess, "Popen", launch)
    workspace.open_platform("linkedin")
    args = launch.call_args.args[0]
    assert len(args) == 2
    assert args[1] == "https://www.linkedin.com/jobs/"
    assert not any(arg.startswith("--") for arg in args)
    with pytest.raises(ValueError):
        workspace.open_platform("https://evil.invalid/")


def test_endpoint_uses_exact_local_metadata_without_http_approval_probe(monkeypatch):
    profile = workspace.regular_profile()
    profile.mkdir()
    metadata = profile / "DevToolsActivePort"
    metadata.write_text("9222\n/devtools/browser/fixture-id\n")
    connection = Mock()
    connection.__enter__ = Mock()
    connection.__exit__ = Mock()
    monkeypatch.setattr(
        workspace.socket, "create_connection", Mock(return_value=connection)
    )
    assert workspace.endpoint() == "ws://127.0.0.1:9222/devtools/browser/fixture-id"
    for invalid in [
        "65536\n/devtools/browser/id",
        "9222\nhttps://evil.invalid",
        "9222\n/devtools/browser/../../evil",
    ]:
        metadata.write_text(invalid)
        assert workspace.endpoint() is None


def test_login_targets_the_users_selected_profile(monkeypatch):
    workspace.BROWSER_PREFERENCES.write_text('{"profile_directory":"Profile 2"}')
    launch = Mock()
    monkeypatch.setattr(workspace.subprocess, "Popen", launch)
    workspace.open_platform("linkedin")
    assert launch.call_args.args[0][1:] == [
        "--profile-directory=Profile 2",
        "https://www.linkedin.com/jobs/",
    ]
    assert not any("user-data-dir" in value for value in launch.call_args.args[0])


async def test_expired_session_never_submits_stored_password():
    applier = get_applier("linkedin")
    applier.is_logged_in = AsyncMock(return_value=False)
    applier._prefill_login = AsyncMock(
        side_effect=AssertionError("Must not fill credentials")
    )
    assert not await applier.authenticate()
    applier._prefill_login.assert_not_awaited()


async def test_pool_connects_once_and_only_closes_owned_tabs(monkeypatch):
    driver = Mock(stop=AsyncMock())
    connect = AsyncMock()
    context = Mock(
        new_page=AsyncMock(
            side_effect=[Mock(close=AsyncMock()), Mock(close=AsyncMock())]
        )
    )
    connect.return_value = Mock(contexts=[context])
    monkeypatch.setattr(
        browser, "async_playwright", lambda: Mock(start=AsyncMock(return_value=driver))
    )
    monkeypatch.setattr(browser, "connect_regular", connect)
    async with browser.reuse_browser():
        first = browser.BrowserSession("linkedin")
        await first.start()
        first_page = first.page
        await first.close()
        driver.stop.assert_not_awaited()
        second = browser.BrowserSession("wellfound")
        await second.start()
        await second.close()
    connect.assert_awaited_once()
    first_page.close.assert_awaited_once()
    driver.stop.assert_awaited_once()
    connect.return_value.close.assert_not_called()


async def test_denied_permission_does_not_repeat_prompts_for_every_platform(
    monkeypatch,
):
    driver = Mock(stop=AsyncMock())
    connect = AsyncMock(side_effect=ValueError("Chrome connection was not approved"))
    monkeypatch.setattr(
        browser, "async_playwright", lambda: Mock(start=AsyncMock(return_value=driver))
    )
    monkeypatch.setattr(browser, "connect_regular", connect)
    async with browser.reuse_browser():
        for platform in ("linkedin", "wellfound"):
            with pytest.raises(ValueError, match="not approved"):
                await browser.BrowserSession(platform).start()
    connect.assert_awaited_once()
    driver.stop.assert_awaited_once()


def test_open_platform_api_is_protected_and_rejects_arbitrary_urls(
    database, monkeypatch
):
    from jobpilot.dashboard.app import create_app

    client = create_app(database).test_client()
    opened = Mock()
    monkeypatch.setattr(workspace, "open_regular", opened)
    assert (
        client.post(
            "/api/browser/open-platform", json={"platform": "linkedin"}
        ).status_code
        == 403
    )
    auth = {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}
    assert (
        client.post(
            "/api/browser/open-platform", json={"platform": "linkedin"}, headers=auth
        ).status_code
        == 200
    )
    opened.assert_called_once_with("https://www.linkedin.com/jobs/")
    assert (
        client.post(
            "/api/browser/open-platform",
            json={"platform": "https://evil.invalid"},
            headers=auth,
        ).status_code
        == 400
    )
