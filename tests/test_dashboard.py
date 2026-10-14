import pytest
from jobpilot.dashboard.app import create_app
from jobpilot.models import Job


@pytest.fixture
def client(database):
    app = create_app(database)
    app.config["TESTING"] = True
    return app.test_client()


def headers(client):
    return {"X-JobPilot-Token": client.application.config["JOBPILOT_TOKEN"]}


def test_local_dashboard_and_csrf(client):
    assert client.get("/").status_code == 200
    assert client.get("/", headers={"Host": "evil.invalid"}).status_code == 403
    assert client.post("/api/apply", json={}).status_code == 403
    assert (
        client.post(
            "/api/apply",
            json={},
            headers=headers(client) | {"Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )
    assert b"jobpilot-token" in client.get("/legacy").data
    assert "script-src 'self';" in client.get("/").headers["Content-Security-Policy"]
    assert (
        "script-src 'self' 'unsafe-inline';"
        in client.get("/legacy").headers["Content-Security-Policy"]
    )


@pytest.mark.parametrize(
    "body",
    [
        {"platform": "bad"},
        {"dry_run": "false"},
        {"limit": -1},
        {"limit": 1.5},
        {"min_score": 101},
    ],
)
def test_invalid_application_requests(client, body):
    assert (
        client.post("/api/apply", json=body, headers=headers(client)).status_code == 400
    )


def test_status_validation_and_missing_jobs(client, database):
    assert (
        client.post(
            "/api/jobs/999/status", json={"status": "applied"}, headers=headers(client)
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/jobs/999/status", json={"status": "invalid"}, headers=headers(client)
        ).status_code
        == 400
    )
    record = Job(
        title="Test", company="Test", platform="linkedin", url="https://test.invalid"
    )
    record.id = database.add_job(record)
    assert (
        client.post(
            f"/api/jobs/{record.id}/status",
            json={"status": "applied"},
            headers=headers(client),
        ).status_code
        == 200
    )
    detail = client.get(f"/api/jobs/{record.id}").json
    assert detail["applied_at"] and detail["application_history"]


@pytest.mark.parametrize(
    "query", ["limit=-1", "limit=bad", "offset=-1", "min_score=nan", "status=nonsense"]
)
def test_invalid_job_filters(client, query):
    assert client.get("/api/jobs?" + query).status_code == 400


def test_apply_defaults_to_dry_run(client, monkeypatch):
    from jobpilot import pipeline

    async def apply(platform, **kwargs):
        assert kwargs["dry_run"] is True
        return [{"platform": platform, "dry_run": 1, "applied": 0}]

    monkeypatch.setattr(pipeline, "apply_platforms", apply)
    response = client.post("/api/apply", json={}, headers=headers(client))
    assert response.status_code == 200 and response.json["results"][0]["applied"] == 0


async def test_dashboard_browser_controls_use_valid_token_and_render_history(
    page, client, database, tmp_path
):
    from urllib.parse import urlsplit

    record = Job(
        title="Software Engineer",
        company="Fixture Company",
        platform="linkedin",
        url="https://www.linkedin.com/jobs/view/123",
        status="matched",
        match_score=90,
    )
    job_id = database.add_job(record)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    async def local_server(route):
        req = route.request
        parsed = urlsplit(req.url)
        response = client.open(
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            method=req.method,
            data=req.post_data,
            headers=req.headers,
        )
        await route.fulfill(
            status=response.status_code,
            headers=dict(response.headers),
            body=response.data,
        )

    await page.route("http://localhost/**", local_server)
    await page.goto("http://localhost/legacy")
    await page.get_by_text("Fixture Company", exact=True).first.wait_for()
    assert await page.locator("#apply-dry-run").is_checked()
    await page.evaluate("openJobModal", job_id)
    assert await page.locator("#job-modal").evaluate(
        "el => el.classList.contains('active')"
    )
    await page.evaluate("id => updateStatus(id, 'shortlisted')", job_id)
    assert database.get_job(job_id).status == "shortlisted"
    assert await page.evaluate("safeUrl('javascript:alert(1)')") == "#"
    assert await page.evaluate("escapeHtml('a\"b')") == "a&quot;b"
    assert not errors
    await page.screenshot(path=str(tmp_path / "dashboard.png"), full_page=True)
