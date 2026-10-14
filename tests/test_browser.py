"""Installed Google Chrome with network requests fulfilled by synthetic fixtures."""

import pytest
from jobpilot.applier import get_applier
from jobpilot.applier.base import ApplicationResult
from jobpilot.applier.forms import fill_form, answer_for
from jobpilot.models import Job
from jobpilot.registry import PLATFORMS
from jobpilot.config import settings

LABELS = {
    "cutshort": "Apply now",
    "wellfound": "Apply",
    "hirist": "Apply now",
    "linkedin": "Easy Apply",
    "foundit": "Quick Apply",
    "glassdoor": "Easy Apply",
}


def html(name, *, unknown=False, confirmed=True):
    question = (
        '<label>Sponsorship needed?<select required><option value="">Choose</option><option>Yes</option><option>No</option></select></label>'
        if unknown
        else ""
    )
    confirmation = (
        "document.body.innerHTML='<div role=alert>Application submitted successfully</div>'"
        if confirmed
        else "document.querySelector('[role=dialog]').remove()"
    )
    return f"""<button id="entry" onclick="window.entries=(window.entries||0)+1; document.querySelector('[role=dialog]').hidden=false">{LABELS[name]}</button>
    <section role="dialog" hidden>
    <label>Full name<input required></label><label>Email<input type="email" required></label>
    <label>Resume<input type="file" accept=".pdf"></label>{question}
    <button onclick="window.submits=(window.submits||0)+1; {confirmation}">Submit application</button>
    </section>"""


async def adapter_page(page, name, body, database, dry_run=False):
    applier = get_applier(name, database=database, dry_run=dry_run)
    applier.page, applier.context = page, page.context
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    record = Job(
        title="Software Engineer",
        company="Test",
        platform=name,
        url=applier.HOME_URL + "/jobs/test",
    )
    return applier, record


@pytest.mark.parametrize("name", list(PLATFORMS))
async def test_every_adapter_can_submit_confirmed_form(page, name, database):
    unrelated = await page.context.new_page()
    applier, record = await adapter_page(page, name, html(name), database)
    result = await applier.apply_to_job(record)
    assert result.status == "applied"
    assert await page.evaluate("window.submits") == 1
    assert not unrelated.is_closed()


@pytest.mark.parametrize("name", list(PLATFORMS))
async def test_every_dry_run_makes_zero_application_clicks(page, name, database):
    applier, record = await adapter_page(page, name, html(name), database, dry_run=True)
    result = await applier.apply_to_job(record)
    assert result.status == "dry_run"
    assert await page.evaluate("window.entries || 0") == 0
    assert await page.evaluate("window.submits || 0") == 0


async def test_unknown_question_blocks_submit_and_reports_label(page, database):
    applier, record = await adapter_page(
        page, "linkedin", html("linkedin", unknown=True), database
    )
    result = await applier.apply_to_job(record)
    assert result.status == "review" and "Sponsorship needed?" in result.message
    assert await page.evaluate("window.submits || 0") == 0
    assert await page.locator("select").input_value() == ""


async def test_explicit_no_answer_is_used(page, profile, database):
    profile["application_defaults"]["answers"]["Sponsorship needed?"] = False
    applier, record = await adapter_page(
        page, "linkedin", html("linkedin", unknown=True), database
    )
    assert (await applier.apply_to_job(record)).status == "applied"


async def test_closing_modal_is_not_submission_evidence(page, database):
    applier, record = await adapter_page(
        page, "linkedin", html("linkedin", confirmed=False), database
    )
    result = await applier.apply_to_job(record)
    assert result.status == "review" and "confirmation" in result.message
    assert await page.evaluate("window.submits") == 1


async def test_external_url_is_not_opened(page, database):
    applier = get_applier("linkedin", database=database)
    applier.page = page
    record = Job(
        title="Test",
        company="Test",
        platform="linkedin",
        url="https://linkedin.com.evil.invalid/job",
    )
    assert (await applier.apply_to_job(record)).status == "review"
    assert page.url == "about:blank"


async def test_native_fields_explicit_answers_only(page, profile):
    await page.set_content("""<form>
    <label>Years of experience<input type=number required></label>
    <label>Work authorization<select><option>Yes</option><option>No</option></select></label>
    <fieldset><legend>Willing to relocate?</legend><label>Yes<input type=radio name=relocate value=Yes></label><label>No<input type=radio name=relocate value=No></label></fieldset>
    </form>""")
    unresolved = await fill_form(page.locator("form"), profile, settings.resume_path)
    assert "Work authorizationYesNo" in unresolved or any(
        "Work authorization" in v for v in unresolved
    )
    assert "Willing to relocate?" in unresolved
    assert await page.locator("input[type=number]").input_value() == "0"
    assert await page.locator("input:checked").count() == 0


def test_no_skill_specific_experience_guess(profile):
    assert (
        answer_for("How many years of Kubernetes experience do you have?", profile)
        is None
    )
    assert answer_for("years_of_experience", profile) == 0


async def test_select_preserves_meaningful_punctuation(page, profile):
    profile["application_defaults"]["answers"]["Preferred language"] = "C++"
    await page.set_content(
        "<form><label>Preferred language<select><option>C</option><option>C++</option><option>C#</option></select></label></form>"
    )
    assert not await fill_form(page.locator("form"), profile, settings.resume_path)
    assert await page.locator("select").input_value() == "C++"


async def test_multistep_flow_fills_final_questions_before_submit(
    page, database, profile
):
    profile["application_defaults"]["answers"]["Sponsorship needed?"] = False
    body = """<button onclick="document.getElementById('first').hidden=false">Easy Apply</button>
    <section role=dialog id=first hidden><label>Email<input type=email required></label>
    <button aria-label="Continue to next step" onclick="this.parentElement.hidden=true; document.getElementById('last').hidden=false">Next</button></section>
    <section role=dialog id=last hidden><label>Sponsorship needed?<select id=answer required><option value="">Choose</option><option>Yes</option><option>No</option></select></label>
    <button onclick="window.answer=document.getElementById('answer').value; document.body.innerHTML='<div role=alert>Application submitted successfully</div>'">Submit application</button></section>"""
    applier, record = await adapter_page(page, "linkedin", body, database)
    assert (await applier.apply_to_job(record)).status == "applied"
    assert await page.evaluate("window.answer") == "No"


async def test_login_needs_positive_authenticated_indicator(page, database):
    applier, record = await adapter_page(
        page, "linkedin", "<p>No login link here</p>", database
    )
    assert not await applier.is_logged_in()


async def test_browser_exception_keeps_job_in_review(database, monkeypatch):
    applier = get_applier("linkedin", database=database, dry_run=False)
    job_id = database.add_job(
        Job(
            title="Test",
            company="Test",
            platform="linkedin",
            url="https://www.linkedin.com/job/1",
            status="matched",
            match_score=90,
        )
    )

    async def nothing(*args, **kwargs):
        return True

    async def fail(job):
        raise RuntimeError("Possibly after submission")

    for method in ("start_browser", "stop_browser", "authenticate"):
        monkeypatch.setattr(applier, method, nothing)
    monkeypatch.setattr(applier, "apply_to_job", fail)
    assert (await applier.run())["review"] == 1
    assert database.get_job(job_id).status == "review"
    assert (await applier.run())["jobs"] == []


async def test_run_persists_only_confirmed_outcomes(database, monkeypatch):
    applier = get_applier("linkedin", database=database, dry_run=False)
    for idx in range(3):
        database.add_job(
            Job(
                title="Software Engineer",
                company="Test",
                platform="linkedin",
                url=f"https://www.linkedin.com/jobs/{idx}",
                status="matched",
                match_score=80,
            )
        )

    async def nothing(*args, **kwargs):
        return True

    async def apply(job):
        return (
            ApplicationResult("applied", "Confirmed")
            if job.id == 1
            else ApplicationResult("review", "Unknown question")
        )

    monkeypatch.setattr(applier, "start_browser", nothing)
    monkeypatch.setattr(applier, "stop_browser", nothing)
    monkeypatch.setattr(applier, "authenticate", nothing)
    monkeypatch.setattr(applier, "apply_to_job", apply)
    result = await applier.run()
    assert result["applied"] == result["review"] == 1
    assert database.get_job(1).applied_at
    assert database.get_job(2).status == "review"
    assert database.get_job(3).status == "matched"
    assert (await applier.run())["jobs"] == []


async def test_dry_run_does_not_mutate_jobs_or_application_history(
    database, monkeypatch
):
    applier = get_applier("linkedin", database=database)
    job_id = database.add_job(
        Job(
            title="Test",
            company="Test",
            platform="linkedin",
            url="https://www.linkedin.com/job/1",
            status="matched",
            match_score=90,
        )
    )

    async def nothing(*args, **kwargs):
        return True

    async def apply(job):
        return ApplicationResult("dry_run", "Checked")

    for method in ("start_browser", "stop_browser", "authenticate"):
        monkeypatch.setattr(applier, method, nothing)
    monkeypatch.setattr(applier, "apply_to_job", apply)
    result = await applier.run()
    assert result["applied"] == 0 and result["dry_run"] == 1
    assert database.get_job(job_id).status == "matched"
    assert database.get_application_history(job_id) == []
