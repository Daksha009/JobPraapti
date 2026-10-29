"""Resume uploads and saved sessions, with synthetic PDFs and isolated Chrome."""

import io
from urllib.parse import parse_qs, urlsplit
import pytest
from jobpilot import sessions
from jobpilot.resume_insights import inspect_pdf
from jobpilot.config import settings
from jobpilot.dashboard.app import create_app
from jobpilot.scrapers import get_scraper


def pdf_bytes(lines):
    # Minimal real, selectable-text PDF; no optional PDF-generation dependency.
    text = "BT /F1 12 Tf 40 740 Td "
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text += f"({escaped}) Tj 0 -18 Td "
    content = (text + "ET").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = b"%PDF-1.4\n"
    offsets = [0]
    for index, item in enumerate(objects, 1):
        offsets.append(len(payload))
        payload += f"{index} 0 obj\n".encode() + item + b"\nendobj\n"
    xref = len(payload)
    payload += b"xref\n0 6\n0000000000 65535 f \n"
    payload += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        payload
        + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )


def test_local_resume_extraction_respects_tokens_and_aliases():
    data = inspect_pdf(
        pdf_bytes(
            [
                "Software Engineer",
                "GitHub portfolio",
                "Skills: JavaScript, C++, C#, Python, React.js, Reactjs, AWS",
                "Used MySQL and PostgreSQL.",
            ]
        )
    )
    assert {
        "JavaScript",
        "C++",
        "C#",
        "Python",
        "React",
        "AWS",
        "MySQL",
        "PostgreSQL",
    } <= set(data["skills"])
    assert "Java" not in data["skills"] and "SQL" not in data["skills"]
    assert data["skills"].count("React") == 1
    assert data["search_keywords"][0] == "JavaScript"
    assert data["method"] == "local" and not data["warning"]
    blank = inspect_pdf(pdf_bytes([]))
    assert not blank["skills"] and "no selectable text" in blank["warning"]
    with pytest.raises(ValueError):
        inspect_pdf(b"not a PDF")


def test_upload_merges_skills_and_keywords_and_drives_search(
    database, monkeypatch, tmp_path, profile
):
    from jobpilot.dashboard import web_api

    monkeypatch.setattr(web_api, "CONFIG_DIR", tmp_path / "config")
    profile["preferences"]["skills"] = ["Python", "Product strategy"]
    client = create_app(database).test_client()
    auth = {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}
    response = client.post(
        "/api/resume",
        data={
            "resume": (
                io.BytesIO(pdf_bytes(["Skills: JavaScript, Python, AWS"])),
                "fixture.pdf",
            )
        },
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json["preferences"]["skills"] == [
        "Python",
        "Product strategy",
        "JavaScript",
        "AWS",
    ]
    assert settings.search_queries[0] == "Software Engineer JavaScript"
    query = parse_qs(urlsplit(get_scraper("linkedin")._build_search_url()).query)
    assert query["keywords"] == ["Software Engineer JavaScript"]
    # A later manual edit is authoritative, including removal of extracted skills.
    current = client.get("/api/profile").json["profile"]
    current["preferences"]["skills"] = ["Python", "New custom skill"]
    current["preferences"]["search_keywords"] = ["Python"]
    assert (
        client.post("/api/profile", json={"profile": current}, headers=auth).status_code
        == 200
    )
    assert settings.user_skills == ["Python", "New custom skill"]
    assert settings.search_queries[0] == "Software Engineer Python"


def test_resume_extraction_requires_auth_and_preserves_file_on_invalid_upload(
    database, profile
):
    client = create_app(database).test_client()
    before = settings.resume_path.read_bytes()
    assert client.post("/api/resume/extract", json={}).status_code == 403
    auth = {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}
    response = client.post(
        "/api/resume",
        data={"resume": (io.BytesIO(b"%PDF-corrupt"), "bad.pdf")},
        headers=auth,
    )
    assert response.status_code == 400
    assert settings.resume_path.read_bytes() == before


async def test_sign_out_clears_only_selected_platform_and_blocks_auto_login(page):
    context = page.context
    await page.goto("http://localhost/")
    site = await context.new_page()
    await site.goto("https://www.linkedin.com/")
    await site.evaluate(
        "localStorage.setItem('fixture_login','active'); document.cookie='fixture_session=active; path=/'"
    )
    other = await context.new_page()
    await other.goto("https://wellfound.com/")
    await other.evaluate("document.cookie='other_session=active; path=/'")
    await context.add_cookies(
        [{"name": "unrelated", "value": "active", "url": "https://notlinkedin.com/"}]
    )
    await sessions.clear_platform(context, "linkedin")
    assert site.is_closed() and not page.is_closed() and not other.is_closed()
    assert not await context.cookies("https://www.linkedin.com/")
    assert await context.cookies("https://wellfound.com/")
    assert await context.cookies("https://notlinkedin.com/")
    check = await context.new_page()
    await check.goto("https://www.linkedin.com/")
    assert await check.evaluate("localStorage.getItem('fixture_login')") is None
    assert "linkedin" in sessions.preferences()["signed_out"]
    assert "wellfound" not in sessions.preferences()["signed_out"]
    sessions.mark_signed_out("linkedin", False)
    assert "linkedin" not in sessions.preferences()["signed_out"]


async def test_regular_chrome_never_clears_sessions_on_worker_start(page):
    from jobpilot.workspace_browser import identify_context

    context = page.context
    await context.add_cookies(
        [{"name": "fixture", "value": "active", "url": "https://www.linkedin.com/"}]
    )
    # Even a legacy opt-out must not sign the user out of their regular browser.
    sessions.update_preferences(remember=False)
    await identify_context(context)
    await identify_context(context)
    assert await context.cookies("https://www.linkedin.com/")
    with pytest.raises(ValueError, match="Regular Chrome manages"):
        await sessions.manage_sessions(remember=False)


async def test_explicit_sign_out_requires_reconnection_before_worker_authentication():
    from jobpilot.applier import get_applier
    from unittest.mock import AsyncMock

    applier = get_applier("linkedin")
    applier.is_logged_in = AsyncMock(return_value=True)
    sessions.mark_signed_out("linkedin")
    assert not await applier.authenticate()
    applier.is_logged_in.assert_not_awaited()
    sessions.mark_signed_out("linkedin", False)
    assert await applier.authenticate()


def test_session_controls_validate_requests_and_refuse_changes_during_run(
    database, monkeypatch
):
    from contextlib import closing

    client = create_app(database).test_client()
    calls = []

    async def manage(**kwargs):
        calls.append(kwargs)
        return {"remember": True}

    monkeypatch.setattr(sessions, "manage_sessions", manage)
    auth = {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}
    assert (
        client.post("/api/browser/sign-out", json={"platform": "linkedin"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/browser/sign-out", json={"platform": "evil.invalid"}, headers=auth
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/browser/preferences", json={"remember": "yes"}, headers=auth
        ).status_code
        == 400
    )
    assert not calls
    assert (
        client.post(
            "/api/browser/preferences", json={"remember": True}, headers=auth
        ).status_code
        == 200
    )
    with closing(database._get_connection()) as conn, conn:
        conn.execute(
            "INSERT INTO web_runs(id,action,platform,state,started_at,options) VALUES ('active','pipeline','all','running','2026-10-14','{}')"
        )
    assert (
        client.post(
            "/api/browser/sign-out", json={"platform": "all"}, headers=auth
        ).status_code
        == 400
    )
    assert client.post("/api/resume/extract", json={}, headers=auth).status_code == 400
    assert len(calls) == 1


def test_session_preferences_retry_transient_windows_lock(monkeypatch):
    from pathlib import Path

    original = Path.replace
    calls = []

    def locked_once(path, target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError("Synthetic transient Windows sharing lock")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", locked_once)
    sessions.mark_signed_out("cutshort", True)
    assert calls == [sessions.PREFERENCES, sessions.PREFERENCES]
    assert "cutshort" in sessions.preferences()["signed_out"]
