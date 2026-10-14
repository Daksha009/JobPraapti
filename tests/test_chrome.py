"""Browser selection must use installed Chrome and fail without a fallback."""

import pytest
from jobpilot.browser import installed_chrome_path, chrome_launch_options
from jobpilot.__main__ import cli
from click.testing import CliRunner


def test_explicit_chrome_path_is_shared_by_every_launcher(monkeypatch, tmp_path):
    executable = tmp_path / "chrome.exe"
    executable.write_bytes(b"fixture executable, never launched")
    monkeypatch.setenv("JOBPILOT_CHROME_PATH", str(executable))
    assert installed_chrome_path() == executable.resolve()
    assert chrome_launch_options() == {"executable_path": str(executable.resolve())}
    result = CliRunner().invoke(cli, ["install-browser"])
    assert result.exit_code == 0
    assert "Using installed Google Chrome" in result.output


def test_missing_configured_chrome_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPILOT_CHROME_PATH", str(tmp_path / "missing.exe"))
    with pytest.raises(RuntimeError, match="installed Chrome executable"):
        chrome_launch_options()
    assert CliRunner().invoke(cli, ["install-browser"]).exit_code == 1


async def test_installed_chrome_reports_browser_version(page):
    session = await page.context.new_cdp_session(page)
    info = await session.send("Browser.getVersion")
    assert info["product"].startswith(("Chrome/", "HeadlessChrome/"))
    await session.detach()
