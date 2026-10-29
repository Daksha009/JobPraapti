"""Current Cutshort and Foundit application surfaces, with synthetic data only."""

from unittest.mock import AsyncMock
import pytest

from jobpilot.applier import get_applier
from jobpilot.applier.answers import AnswerComposer
from jobpilot.config import settings
from jobpilot.models import Job


async def test_cutshort_uses_main_apply_not_offscreen_sticky_or_recommendation(page):
    await page.set_content("""<button style="position:fixed;top:-400px">Apply to this job</button>
      <button class="sc-8c2323fe-0">Apply to this job</button><button>Apply now</button>""")
    a = get_applier("cutshort")
    a.page = page
    button = await a.visible(a.apply_selectors)
    assert await button.get_attribute("class") == "sc-8c2323fe-0"
    await page.locator('button:has-text("Apply to this job")').evaluate_all(
        "items => items.forEach(item => item.remove())"
    )
    assert await a.visible(a.apply_selectors) is None


async def test_cutshort_upload_message_and_optional_follow(page, profile):
    profile["application_defaults"]["intro_message"] = (
        "Reviewed candidate introduction."
    )
    await page.set_content("""<div role="dialog"><span id="filename" class="sc-d023fd03-8">old_cv</span>
      <button onclick="document.querySelector('input').remove();const f=document.createElement('input');f.type='file';f.onchange=()=>document.querySelector('#filename').textContent='resume_Ab12';document.body.append(f)">Upload another resume</button>
      <textarea name="message"></textarea>
      <label onclick="this.querySelector('img').remove()">Follow Example to get alerts for new job openings<img src="success_icon_p.png"></label>
      <button>Send</button></div><input type=file>""")
    a = get_applier("cutshort")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="cutshort",
            url="https://cutshort.io/job/test",
        ),
    )
    assert await a.prepare_form(await a.form_scope()) == ""
    assert a.composer.record["resume_uploaded"] == settings.resume_path.name
    assert (
        await page.locator("textarea").input_value()
        == "Reviewed candidate introduction."
    )
    assert not await page.locator("label img").count()


@pytest.mark.parametrize("complete", [True, False])
async def test_foundit_preserves_existing_employment_and_only_uses_confirmed_facts(
    page, profile, complete
):
    profile["application_defaults"].update(
        current_ctc="14 LPA", notice_period="Immediate"
    )
    await page.set_content("""<form id="employmentDetailsForm">
      <input id=jobTitle value=Engineer><input id=company value=Example>
      <input id=startYear value=2025><input id=startMonth value=March>
      <input id=checkbox type=checkbox checked><input id=country-dropdown value=INR readonly>
      <input placeholder="Enter Salary"><input id=notice readonly onclick="document.querySelector('#options').hidden=false">
      <div id=options hidden><span onclick="document.querySelector('#notice').value=this.textContent;this.parentElement.hidden=true">Immediately available</span></div>
      <button>Save</button></form>""")
    if not complete:
        await page.locator("#company").fill("")
    a = get_applier("foundit")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="foundit",
            url="https://www.foundit.in/job/test",
        ),
    )
    result = await a.prepare_form(await a.form_scope())
    if complete:
        assert result == ""
        assert await page.get_by_placeholder("Enter Salary").input_value() == "1400000"
        assert await page.locator("#notice").input_value() == "Immediately available"
        assert await page.locator("#company").input_value() == "Example"
    else:
        assert "missing employment history" in result
        assert await page.get_by_placeholder("Enter Salary").input_value() == ""


async def test_cutshort_portal_button_is_scoped_to_the_requested_job(page):
    a = get_applier("cutshort")
    a.page = page
    await page.goto("https://cutshort.io/profile/all-jobs?jobid=abc")
    await page.set_content("""<div class="sc-963106f5-1"><h3>Target Engineer</h3><button>Apply now</button></div>
      <div class="sc-963106f5-1"><h3>Other role</h3><button>Apply now</button></div>""")
    job = Job(
        title="Target Engineer",
        company="Example",
        platform="cutshort",
        url="https://cutshort.io/job/test",
    )
    entry = await a.portal_entry(job)
    assert entry is not None
    assert (
        await entry.evaluate("e=>e.closest('div').querySelector('h3').textContent")
        == "Target Engineer"
    )
    await page.goto("https://cutshort.io/profile/all-jobs")
    assert await a.portal_entry(job) is None


async def test_foundit_dismisses_only_its_blocking_cookie_notice(page):
    await page.set_content("""<div id="cookieBannerWrapper"><div class="cookie-content"><button id="acceptAll" onclick="this.closest('#cookieBannerWrapper').remove()">Okay</button></div></div>
      <button id="other">Accept</button>""")
    a = get_applier("foundit")
    a.page = page
    await a.dismiss_cookie_banner()
    assert not await page.locator("#cookieBannerWrapper").count()
    assert await page.locator("#other").count() == 1


async def test_foundit_final_form_uses_inr_salary_and_matches_job(page, profile):
    profile["application_defaults"].update(
        current_ctc="14 LPA", notice_period="Immediate"
    )
    await page.set_content("""<div id="resumeUploadDetailsForm"><h4 class="apop__jobCardTitle">Engineer</h4>
      <input id="country-dropdown" value="INR" readonly><input placeholder="Enter Annual Salary" required>
      <input id="notice" value="Immediately available" readonly><button>Confirm &amp; Apply</button></div>""")
    a = get_applier("foundit")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="foundit",
            url="https://www.foundit.in/job/test",
        ),
    )
    scope = await a.form_scope()
    assert await a.prepare_form(scope) == ""
    assert (
        await page.get_by_placeholder("Enter Annual Salary").input_value() == "1400000"
    )
    a.composer.job.title = "Different Job"
    assert "differs" in await a.prepare_form(scope)


async def test_foundit_employer_handoff_is_not_counted_as_applied(page, profile):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    a = get_applier("foundit")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="foundit",
            url="https://www.foundit.in/job/test",
        ),
    )
    external = SimpleNamespace(
        url="https://www.foundit.in/srp/applied-success",
        opener=AsyncMock(return_value=page),
        get_by_text=lambda text, **kwargs: SimpleNamespace(
            count=AsyncMock(
                return_value=int(text == "Redirecting you to apply on company site.")
            )
        ),
    )
    a.context = SimpleNamespace(pages=[page, external])
    a.visible = AsyncMock(return_value=None)
    result = await a.post_submit()
    assert result.status == "review"
    assert "employer site" in result.message
    assert a.session.extra_pages == [external]


async def test_cutshort_post_submit_confirms_only_the_selected_job_conversation(
    page, profile
):
    a = get_applier("cutshort")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="cutshort",
            url="https://cutshort.io/job/test",
        ),
    )
    await page.set_content("""<div class="sc-963106f5-1"><h3>Engineer</h3>
      <a href="/profile/conversations/candidate?thread=x&amp;stage=awaiting">View conversation</a></div>""")
    result = await a.post_submit()
    assert result.status == "applied"
    assert "awaiting recruiter conversation" in result.message


async def test_foundit_resume_form_uploads_current_file(page, profile):
    await page.set_content("""<div id="resumeUploadDetailsForm"><h4 class="apop__jobCardTitle">Engineer</h4>
      <input type="file" name="resume" onchange="document.querySelector('#filename').textContent=this.files[0].name">
      <div id="filename">old.pdf</div><button>Confirm &amp; Apply</button></div>""")
    a = get_applier("foundit")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="foundit",
            url="https://www.foundit.in/job/test",
        ),
    )
    assert await a.prepare_form(await a.form_scope()) == ""
    assert await page.locator("#filename").inner_text() == settings.resume_path.name
    assert a.composer.record["resume_uploaded"] == settings.resume_path.name


async def test_foundit_success_in_new_tab_must_match_job_and_company(page, profile):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    a = get_applier("foundit")
    a.page = page
    a.composer = AnswerComposer(
        profile,
        Job(
            title="Engineer",
            company="Example",
            platform="foundit",
            url="https://www.foundit.in/job/test",
        ),
    )
    success = "You have successfully applied to Engineer at Example"
    child = SimpleNamespace(
        url="https://www.foundit.in/srp/applied-success",
        opener=AsyncMock(return_value=page),
        get_by_text=lambda text, **kwargs: SimpleNamespace(
            count=AsyncMock(return_value=int(text == success))
        ),
    )
    a.context = SimpleNamespace(pages=[page, child])
    a.visible = AsyncMock(return_value=None)
    outcome = await a.post_submit()
    assert outcome.status == "applied"
    assert a.session.extra_pages == [child]


async def test_listing_description_can_exclude_mislabelled_senior_job(page, database):
    body = """<div id="descriptionContent" class="job-description__content">
      <p>We build analytics for enterprise teams using Python and SQL across many challenging projects.</p>
      <p>5+ Years of Relevant experience.</p></div><button onclick="window.applied=1">Apply Now</button>"""
    await page.route("**/*", lambda r: r.fulfill(content_type="text/html", body=body))
    a = get_applier("foundit", database=database, dry_run=False)
    a.page = page
    a.context = page.context
    job = Job(
        title="Data Analyst",
        company="Example",
        platform="foundit",
        url="https://www.foundit.in/job/test",
        experience="Fresher",
    )
    job.id = database.add_job(job)
    result = await a.apply_to_job(job)
    assert result.status == "review" and result.continue_queue
    assert "experience requirement" in result.message
    assert await page.evaluate("window.applied || 0") == 0


async def test_foundit_one_click_confirmation_survives_its_new_tab(page):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    a = get_applier("foundit")
    a.page = page
    child = SimpleNamespace(
        url="https://www.foundit.in/srp/applied-success",
        opener=AsyncMock(return_value=page),
    )
    a.context = SimpleNamespace(pages=[page, child])
    a.visible = AsyncMock(return_value=object())
    assert await a.follow_handoff() == ""
    assert a.session.extra_pages == [child]


async def test_missing_listing_is_expired_without_application_click(page, database):
    await page.route(
        "**/*",
        lambda route: route.fulfill(
            status=404, content_type="text/html", body="<h1>Listing not found</h1>"
        ),
    )
    adapter = get_applier("cutshort", database=database, dry_run=False)
    adapter.page, adapter.context = page, page.context
    job = Job(
        title="Engineer",
        company="Fixture",
        platform="cutshort",
        url="https://cutshort.io/job/not-found",
    )
    result = await adapter.apply_to_job(job)
    assert result.status == "expired"
