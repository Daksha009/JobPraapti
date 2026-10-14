"""Web integration tests: isolated candidate data and no external services."""

import asyncio
from contextlib import closing
import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jobpilot.config import settings
from jobpilot.dashboard.app import create_app
from jobpilot.dashboard.analytics import applications, overview, csv_export
from jobpilot.dashboard.runner import Runner
from jobpilot.models import Job
from jobpilot.vault import Vault


@pytest.fixture
def client(database):
    app = create_app(database)
    app.config["TESTING"] = True
    return app.test_client()


def auth(client):
    return {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}


def test_open_workspace_requires_token_and_returns_actionable_failure(
    client, monkeypatch
):
    from jobpilot import workspace_browser

    calls = []

    async def opened():
        calls.append(True)

    monkeypatch.setattr(workspace_browser, "open_workspace", opened)
    assert client.post("/api/browser/open", json={}).status_code == 403
    assert not calls
    assert client.post("/api/browser/open", json={}, headers=auth(client)).json[
        "opened"
    ]
    assert calls == [True]

    async def unavailable():
        raise RuntimeError("Internal resource detail should not be returned")

    monkeypatch.setattr(workspace_browser, "open_workspace", unavailable)
    response = client.post("/api/browser/open", json={}, headers=auth(client))
    assert response.status_code == 503
    assert "regular Chrome" in response.json["error"]
    assert b"Internal resource detail" not in response.data


async def test_verify_connection_only_checks_existing_session(monkeypatch):
    from jobpilot.applier import get_applier
    from jobpilot import applier as factory
    from jobpilot.dashboard.connections import check_platform

    instance = get_applier("linkedin")
    from unittest.mock import AsyncMock, Mock

    instance.start_browser = AsyncMock()
    instance.stop_browser = AsyncMock()
    instance.page = Mock()
    instance.is_logged_in = AsyncMock(return_value=True)
    instance.authenticate = AsyncMock(
        side_effect=AssertionError("Must not resubmit credentials")
    )
    monkeypatch.setattr(factory, "get_applier", lambda name: instance)
    assert (await check_platform("linkedin"))["status"] == "connected"
    instance.is_logged_in.assert_awaited_once()
    instance.authenticate.assert_not_awaited()
    instance.stop_browser.assert_awaited_once()


def add(database, suffix="1", **values):
    return database.add_job(
        Job(
            title="Software Engineer",
            company="Example Labs",
            platform="linkedin",
            url=f"https://www.linkedin.com/jobs/view/{suffix}",
            **values,
        )
    )


def test_local_date_filters_csv_and_undated_history(database):
    job_id = add(database, status="applied")
    second = add(database, "2", status="applied")
    with closing(database._get_connection()) as conn, conn:
        conn.execute(
            "UPDATE jobs SET applied_at=? WHERE id=?",
            ("2026-10-12T20:00:00+00:00", job_id),
        )
        conn.execute(
            "UPDATE jobs SET title=? WHERE id=?", ('=HYPERLINK("example")', second)
        )
    rows = applications(database, start="2026-10-13", end="2026-10-13")
    assert len(rows) == 1 and rows[0]["id"] == job_id
    assert applications(database, start="2026-10-12", end="2026-10-12") == []
    report = overview(database)
    assert report["total_applications"] == 2
    assert report["undated_applications"] == 1
    assert report["by_platform"] == {"linkedin": 2}
    assert "'=HYPERLINK" in csv_export(applications(database))
    with pytest.raises(ValueError):
        applications(database, start="2026-10-14", end="2026-10-13")


def test_manual_confirmation_is_idempotent(database):
    job_id = add(database)
    database.manual_status(job_id, "applied")
    stamp = database.get_job(job_id).applied_at
    database.manual_status(job_id, "applied")
    assert database.get_job(job_id).applied_at == stamp
    assert len(database.get_application_history(job_id)) == 1


def test_api_pagination_filter_and_export(client, database):
    for n in range(25):
        add(database, str(n), status="applied", applied_at="2026-10-13T10:00:00+00:00")
    response = client.get("/api/jobs?limit=20")
    assert response.json["total"] == 25 and response.json["count"] == 20
    response = client.get("/api/applications?page=2")
    assert response.json["total"] == 25 and len(response.json["applications"]) == 5
    assert client.get("/api/applications?platform=unknown").status_code == 400
    assert (
        client.get("/api/applications?from=2026-10-30&to=2026-10-01").status_code == 400
    )
    export = client.get("/api/applications/export")
    assert "attachment" in export.headers["Content-Disposition"]
    assert export.data.startswith(b"Role,Company,Platform")


def test_secret_api_is_write_only_and_csrf_protected(client, monkeypatch):
    captured = {}

    def save(self, values):
        captured.update(values)

    monkeypatch.setattr(Vault, "update", save)
    monkeypatch.setattr(Vault, "read", lambda self: captured)
    response = client.post(
        "/api/credentials",
        json={"platform": "linkedin", "password": "SYNTHETIC-SECRET"},
    )
    assert response.status_code == 403 and not captured
    response = client.post(
        "/api/credentials",
        json={"platform": "linkedin", "password": "SYNTHETIC-SECRET"},
        headers=auth(client),
    )
    assert response.status_code == 200
    connection = client.get("/api/connections")
    assert b"SYNTHETIC-SECRET" not in connection.data
    assert next(p for p in connection.json["platforms"] if p["name"] == "linkedin")[
        "password_saved"
    ]
    for path in ("/api/bootstrap", "/api/profile", "/api/overview", "/api/runs"):
        assert b"SYNTHETIC-SECRET" not in client.get(path).data
    assert client.get("/api/bootstrap").headers["Cache-Control"] == "no-store"


def test_vault_roundtrip_is_encrypted_and_merges(tmp_path):
    import os

    if os.name != "nt":
        pytest.skip("Windows DPAPI")
    vault = Vault(tmp_path / "credentials.dpapi")
    vault.update({"LINKEDIN_PASSWORD": "SYNTHETIC-SECRET"})
    vault.update({"HIRIST_EMAIL": "test@invalid.test"})
    assert b"SYNTHETIC-SECRET" not in vault.path.read_bytes()
    assert vault.read()["LINKEDIN_PASSWORD"] == "SYNTHETIC-SECRET"
    vault.update({"LINKEDIN_PASSWORD": ""})
    assert "LINKEDIN_PASSWORD" not in vault.read()
    with pytest.raises(ValueError):
        vault.update({"ARBITRARY_KEY": "value"})


def test_live_runs_require_deliberate_confirmation(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        Runner, "start", lambda self, *args: calls.append(args) or "test-run"
    )
    for body in (
        {"action": "apply", "dry_run": False},
        {"limit": 0},
        {"platform": "bad"},
        {"action": "login", "platform": "all"},
    ):
        assert (
            client.post("/api/runs", json=body, headers=auth(client)).status_code == 400
        )
    assert not calls
    assert (
        client.post(
            "/api/runs", json={"action": "apply"}, headers=auth(client)
        ).status_code
        == 202
    )
    assert calls[-1][-1]["dry_run"] is True


def test_profile_validation_does_not_mutate_running_configuration(
    client, monkeypatch, tmp_path
):
    import jobpilot.dashboard.web_api as module

    monkeypatch.setattr(module, "CONFIG_DIR", tmp_path)
    before = json.dumps(settings.profile)
    assert (
        client.post(
            "/api/profile",
            json={"profile": {"preferences": {"skills": "wrong type"}}},
            headers=auth(client),
        ).status_code
        == 400
    )
    assert json.dumps(settings.profile) == before
    response = client.post(
        "/api/profile",
        json={"profile": {"personal": {"full_name": "Changed Candidate"}}},
        headers=auth(client),
    )
    assert response.status_code == 200
    assert settings.profile["personal"]["full_name"] == "Changed Candidate"
    assert (
        client.post(
            "/api/resume",
            data={"resume": (__import__("io").BytesIO(b"not PDF"), "resume.pdf")},
            headers=auth(client),
        ).status_code
        == 400
    )


def test_worker_persists_and_cancels_without_duplicate_dispatch(database, monkeypatch):
    entered = threading.Event()

    async def slow(self, *args):
        entered.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(Runner, "_perform", slow)
    runner = Runner(database)
    try:
        runner.start("scrape", "linkedin", {"dry_run": True, "limit": 5})
        assert entered.wait(5)
        with pytest.raises(ValueError):
            runner.start("scrape", "linkedin", {})
        assert runner.cancel()
        deadline = time.monotonic() + 5
        while (
            runner.list()[0]["state"] in ("queued", "running")
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert runner.list()[0]["state"] == "cancelled"
    finally:
        runner.executor.shutdown(wait=True)


async def test_react_website_end_to_end(page, client, database, tmp_path, monkeypatch):
    from jobpilot import workspace_browser, sessions
    from test_resume_sessions import pdf_bytes

    browser_state = {"same_browser": True, "running": True, "remember": True}
    session_calls = []
    opened_platforms = []
    monkeypatch.setattr(workspace_browser, "open_platform", opened_platforms.append)

    async def manage(**kwargs):
        session_calls.append(kwargs)
        if "remember" in kwargs:
            browser_state["remember"] = kwargs["remember"]
        return {"remember": browser_state["remember"]}

    monkeypatch.setattr(sessions, "manage_sessions", manage)

    monkeypatch.setattr(
        workspace_browser,
        "status",
        lambda cookie: browser_state,
    )
    with closing(database._get_connection()) as conn, conn:
        conn.execute(
            "INSERT INTO web_runs(id, action, platform, state, started_at, finished_at, options, message) VALUES (?,?,?,?,?,?,?,?)",
            (
                "fixture-run",
                "pipeline",
                "linkedin",
                "attention",
                "2026-10-13T10:00:00Z",
                "2026-10-13T10:02:00Z",
                json.dumps({"dry_run": True, "limit": 5}),
                "Fixture run needs sign-in",
            ),
        )
    runner = Runner(database)
    runner.event(
        "fixture-run",
        {
            "stage": "discover",
            "platform": "linkedin",
            "state": "completed",
            "message": "Discovered fixture listings",
            "metrics": {"jobs_found": 4, "jobs_new": 3, "jobs_duplicate": 1},
        },
    )
    runner.event(
        "fixture-run",
        {
            "stage": "match",
            "state": "completed",
            "message": "Scored fixture listings",
            "current": 3,
            "total": 3,
            "metrics": {"scored": 3},
        },
    )
    runner.event(
        "fixture-run",
        {
            "stage": "apply",
            "platform": "linkedin",
            "state": "attention",
            "message": "Sign in required",
            "metrics": {"review": 1},
        },
    )
    runner.executor.shutdown(wait=True)
    if not (Path(__file__).parents[1] / "jobpilot/dashboard/web/index.html").exists():
        pytest.fail("Build the frontend before the browser integration test")
    job_id = add(
        database,
        status="matched",
        match_score=89,
        description="Synthetic role for browser integration tests.",
    )
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    async def local(route):
        req = route.request
        url = urlsplit(req.url)
        response = await asyncio.to_thread(
            client.open,
            url.path + ("?" + url.query if url.query else ""),
            method=req.method,
            data=req.post_data,
            headers=req.headers,
        )
        await route.fulfill(
            status=response.status_code,
            headers=dict(response.headers),
            body=response.data,
        )

    await page.route("http://localhost/**", local)
    await page.emulate_media(reduced_motion="reduce")
    await page.set_viewport_size({"width": 1440, "height": 1100})
    await page.goto("http://localhost/")
    await page.get_by_role("heading", name="Your latest applications").wait_for()
    assert (await page.title()).startswith("JobPraapti")
    assert "JobPraapti" in await page.locator(".brand").inner_text()
    assert await page.locator(".opportunity-scene").count() == 1
    assert "Made by Daksh" in await page.locator(".maker-footer").inner_text()
    await page.get_by_role("button", name="Opportunities", exact=True).click()
    await page.get_by_text("Example Labs", exact=True).wait_for()
    await page.get_by_role("button", name="View Software Engineer", exact=True).click()
    await page.get_by_role("button", name="Shortlist", exact=True).click()
    await page.get_by_role("status").wait_for()
    assert database.get_job(job_id).status == "shortlisted"
    await page.get_by_role("button", name="View Software Engineer", exact=True).click()
    await page.get_by_role("button", name="Mark as applied", exact=True).click()
    async with page.expect_response(
        lambda response: response.request.method == "POST" and "/status" in response.url
    ):
        await page.get_by_role("button", name="Confirm application submitted").click()
    assert database.get_job(job_id).status == "applied"
    await (
        page.get_by_role("button", name="Applications", exact=False)
        .filter(has=page.locator("svg"))
        .first.click()
    )
    await page.get_by_role("heading", name="Application history").wait_for()
    await page.get_by_text("Example Labs", exact=True).wait_for()
    await page.get_by_role("button", name="Platforms", exact=True).click()
    await page.get_by_role("heading", name="Expand your possibilities.").wait_for()
    sign_in = page.get_by_role("button", name="Sign in", exact=True).first
    await sign_in.click()
    await page.get_by_text(
        "Opened in regular Chrome. Sign in there, then select Verify sign-in.",
        exact=True,
    ).wait_for()
    assert opened_platforms == ["cutshort"]
    await page.get_by_text("Keep me signed in · always on", exact=True).wait_for()
    assert not session_calls
    await page.get_by_role("button", name="Sign out here", exact=True).first.click()
    await (
        page.get_by_role("dialog")
        .get_by_role("button", name="Sign out here", exact=True)
        .click()
    )
    await page.get_by_text("Signed out of Cutshort here.", exact=True).wait_for()
    assert session_calls[-1] == {"platform": "cutshort"}
    await page.get_by_role("button", name="Credentials", exact=True).first.click()
    assert await page.get_by_label("Password", exact=True).input_value() == ""
    await page.get_by_role("button", name="Close dialog").click()
    await page.get_by_role("button", name="My profile", exact=True).click()
    await page.get_by_label("Full name", exact=True).wait_for()
    assert (
        await page.get_by_label("Full name", exact=True).input_value()
        == "Test Candidate"
    )
    await page.locator('input[type="file"]').set_input_files(
        {
            "name": "resume.pdf",
            "mimeType": "application/pdf",
            "buffer": pdf_bytes(["Skills: JavaScript, Python, AWS, React.js"]),
        }
    )
    await page.get_by_text("4 skills found", exact=True).wait_for()
    assert "JavaScript" in await page.locator('input[name="skills"]').input_value()
    assert (
        "JavaScript"
        in await page.locator('input[name="search_keywords"]').input_value()
    )
    await page.get_by_role("button", name="Remove AWS skill", exact=True).click()
    assert "AWS" not in await page.locator('input[name="skills"]').input_value()
    await page.locator('input[name="skills"]').fill("Python, Rust, Custom skill")
    await page.locator('input[name="search_keywords"]').fill("Rust")
    await page.get_by_role("button", name="Save profile", exact=True).first.click()
    await page.get_by_text(
        "Profile saved. Future runs will use these details.", exact=True
    ).wait_for()
    assert settings.user_skills == ["Python", "Rust", "Custom skill"]
    assert settings.search_keywords == ["Rust"]
    await page.screenshot(path=str(tmp_path / "resume-desktop.png"), full_page=True)
    await page.get_by_role("button", name="Automation", exact=True).click()
    await page.get_by_role("heading", name="Your run, at a glance.").wait_for()
    assert (
        await page.locator(".run-counters > div").first.locator("strong").inner_text()
        == "4"
    )
    await page.get_by_label("Filter run events by platform").select_option("linkedin")
    assert await page.locator(".event-stream li").count() == 2
    await page.get_by_label("Filter run events by platform").select_option("all")
    assert await page.locator(".event-stream li").count() == 3
    await page.screenshot(path=str(tmp_path / "progress-desktop.png"), full_page=True)
    await page.set_viewport_size({"width": 390, "height": 844})
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    await page.screenshot(path=str(tmp_path / "progress-mobile.png"), full_page=True)
    await page.set_viewport_size({"width": 1440, "height": 1100})
    await page.get_by_role("button", name="New run").click()
    await page.get_by_role("button", name="Live applications", exact=False).click()
    assert await page.get_by_role("button", name="Start run", exact=True).is_disabled()
    await page.get_by_role("button", name="Close dialog").click()
    await page.get_by_role("button", name="Overview", exact=True).click()
    await page.screenshot(path=str(tmp_path / "web-desktop.png"), full_page=True)
    await page.set_viewport_size({"width": 390, "height": 844})
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    await page.get_by_role("button", name="Open navigation").click()
    await page.get_by_role("button", name="My profile", exact=True).click()
    await page.get_by_label("Full name", exact=True).wait_for()
    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    await page.screenshot(path=str(tmp_path / "web-mobile.png"), full_page=True)
    assert not errors
