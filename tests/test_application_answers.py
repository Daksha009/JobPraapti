"""Grounded answers, per-job editing, and asynchronous application transitions."""

from unittest.mock import AsyncMock
import pytest

from jobpilot.applier import get_applier
from jobpilot.applier.answers import AnswerComposer, load_answer_record
from jobpilot.applier.forms import answer_for, fill_form
from jobpilot.config import settings
from jobpilot.dashboard.app import create_app
from jobpilot.models import Job


async def test_optional_company_follow_is_not_opted_into(page, profile):
    await page.set_content(
        '<form><label>Follow Example to stay up to date with their page<input type="checkbox" checked></label><button>Submit application</button></form>'
    )
    assert not await fill_form(page.locator("form"), profile, settings.resume_path)
    assert not await page.locator("input").is_checked()
    await page.locator("input").evaluate("el => el.required = true")
    assert await fill_form(page.locator("form"), profile, settings.resume_path) == [
        "Follow Example to stay up to date with their page"
    ]


async def test_site_rejected_text_answers_are_reported(page, profile):
    profile["application_defaults"]["expected_ctc"] = "15-25 LPA"
    profile["application_defaults"]["notice_period"] = "Immediate"
    await page.set_content("""<form>
      <input aria-label="What is your expected CTC?" aria-describedby="salary-help" onblur="document.getElementById('salary-help').textContent='Invalid input'">
      <div id="salary-help">Enter salary</div>
      <input aria-label="Notice period" aria-describedby="notice-help">
      <div id="notice-help" hidden>Invalid input</div>
      <p>Unrelated example: invalid input</p>
    </form>""")
    answers = composer(profile)
    unresolved = await fill_form(
        page.locator("form"), profile, settings.resume_path, answers
    )
    assert unresolved == ["What is your expected CTC?"]
    assert answers.record["validation_errors"] == unresolved
    assert await page.locator("input").first.input_value() == "15-25 LPA"


async def test_exact_button_name_matches_nested_spans_not_similar_names(page):
    await page.set_content(
        "<section><button><span><span>Next</span></span></button><button>Next job</button></section>"
    )
    adapter = get_applier("linkedin")
    adapter.page = page
    control = await adapter.visible(adapter.next_selectors, page.locator("section"))
    assert control is not None and await control.inner_text() == "Next"
    await page.locator("button").first.evaluate("el => el.remove()")
    assert (
        await adapter.visible(adapter.next_selectors, page.locator("section")) is None
    )


async def test_separate_country_code_uses_national_phone(page, profile):
    await page.set_content("""<form><label>Phone country code<select><option value=us>United States (+1)</option><option value=in>India (+91)</option></select></label>
      <label>Mobile phone number<input type=tel maxlength=10></label></form>""")
    assert not await fill_form(page.locator("form"), profile, settings.resume_path)
    assert await page.locator("select").input_value() == "in"
    assert await page.locator("input").input_value() == "0000000000"
    await page.set_content(
        "<form><label>Mobile phone number<input type=tel></label></form>"
    )
    assert not await fill_form(page.locator("form"), profile, settings.resume_path)
    assert await page.locator("input").input_value() == "+910000000000"


async def test_linkedin_sdui_form_wins_over_unrelated_dialog(page):
    await page.set_content("""<div role=dialog>Video caption settings<input><button>Continue</button></div>
      <dialog open><div data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply"><label>Email<input></label><button>Next</button></div></dialog>""")
    adapter = get_applier("linkedin")
    adapter.page = page
    scope = await adapter.form_scope()
    assert "Video" not in await scope.inner_text()
    assert (
        await scope.get_attribute("data-sdui-screen")
        == "com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply"
    )


async def test_linkedin_uploads_profile_resume_and_verifies_selected_file(
    page, profile
):
    await page.set_content("""<section data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply">
      <button onclick="document.getElementById('upload').click()"><span>Upload resume</span></button>
      <input id=upload type=file style="display:none" onchange="document.getElementById('choices').innerHTML='<input id=chosen type=radio name=resume aria-label=resume.pdf checked style=display:none><label for=chosen>Selected resume</label>';this.remove()">
      <div id=choices><input id=old type=radio name=resume checked aria-label=old.pdf style="display:none"><label for=old>Old resume</label></div>
      <button>Next</button></section>""")
    adapter = get_applier("linkedin")
    adapter.page = page
    adapter.composer = composer(profile)
    scope = await adapter.form_scope()
    assert await adapter.prepare_form(scope) == ""
    assert adapter.composer.record["resume_uploaded"] == "resume.pdf"
    assert not await fill_form(scope, profile, settings.resume_path, adapter.composer)


async def test_hidden_associated_label_unknown_answer_is_not_ignored(page, profile):
    await page.set_content(
        '<form><input type=radio id=yes name=question value=yes style="display:none"><label for=yes>Yes</label></form>'
    )
    assert await fill_form(page.locator("form"), profile, settings.resume_path) == [
        "question"
    ]


async def test_sdui_radio_uses_shared_question_and_adjacent_option_text(page, profile):
    profile["application_defaults"]["answers"]["Are you currently based in Mumbai?"] = (
        False
    )
    await page.set_content("""<form><div><p>Are you currently based in Mumbai?</p>
      <div><div><input id=yes name=city type=radio aria-label="Are you currently based in Mumbai?" style="display:none"><label for=yes></label></div><span>Yes</span></div>
      <div><div><input id=no name=city type=radio aria-label="Are you currently based in Mumbai?" style="display:none"><label for=no>No</label></div></div></div></form>""")
    assert not await fill_form(page.locator("form"), profile, settings.resume_path)
    assert await page.locator("#no").is_checked()


def test_prepared_drafts_survive_a_later_live_attempt(profile):
    import json

    entry = {
        "question": "Why this role?",
        "answer": "A reviewed draft",
        "source": "user",
    }
    instance = composer(
        profile,
        generated_answers=json.dumps(
            {"version": 1, "entries": [entry], "resume_uploaded": "old.pdf"}
        ),
    )
    assert instance.record["entries"] == [entry]
    assert "resume_uploaded" not in instance.record


def job(**values):
    return Job(
        **dict(
            title="Python Engineer",
            company="Example",
            platform="linkedin",
            url="https://www.linkedin.com/jobs/view/123/",
            description="Build APIs with Python.",
            **values,
        )
    )


def composer(profile, **values):
    profile["application_defaults"]["compose_narrative_answers"] = True
    return AnswerComposer(
        profile,
        job(**values),
        "PROJECTS\n• Built Python APIs with automated tests.\nEDUCATION\nExample University 2027",
    )


def test_narrative_uses_actual_resume_evidence_and_role(profile):
    instance = composer(profile)
    answer = instance.resolve(
        {"label": "Why are you interested in this role?", "type": "textarea"}, None
    )
    assert "Python Engineer at Example" in answer
    assert "Built Python APIs with automated tests." in answer
    assert "University" not in answer
    assert instance.record["entries"][0]["source"] == "resume_and_job"
    profile["application_defaults"]["compose_narrative_answers"] = False
    assert (
        instance.narrative("Why are you interested in this role?", "textarea") is None
    )


@pytest.mark.parametrize(
    "question",
    [
        "Describe your years of professional Python experience",
        "Why should we hire you and what is your salary expectation?",
        "Describe your background check consent",
        "Describe your certifications",
        "Which country are you authorized to work in?",
        "Do you have 3 years of Golang experience?",
    ],
)
def test_narrative_never_invents_screening_facts(profile, question):
    assert composer(profile).narrative(question, "textarea") is None


def test_no_evidence_no_narrative_and_explicit_job_override_wins(profile):
    instance = composer(profile)
    instance.resume_text = (
        "Python developer"  # No supporting project/experience bullet.
    )
    assert instance.narrative("Why are you interested?", "textarea") is None
    instance.record["overrides"] = {"Do you require visa sponsorship?": False}
    assert (
        instance.resolve(
            {"label": "Do you require visa sponsorship?", "type": "radio"}, True
        )
        is False
    )
    assert instance.record["entries"][0]["source"] == "user"


def test_only_explicit_countries_and_consent_are_answered(profile):
    defaults = profile["application_defaults"]
    assert answer_for("Do you consent to a background check?", profile) is None
    defaults.update(
        work_authorization={"India": True},
        visa_sponsorship_required=True,
        background_check_consent=True,
        expected_ctc="15-25 LPA",
    )
    assert answer_for("Are you legally authorized to work in India?", profile) is True
    assert (
        answer_for("Are you legally authorized to work in the United States?", profile)
        is None
    )
    assert answer_for("Do you require visa sponsorship?", profile) is True
    assert answer_for("Do you consent to a background check?", profile) is True
    assert answer_for("Expected salary range", profile) == "15-25 LPA"


def test_location_and_notice_options_require_explicit_equivalence():
    from jobpilot.applier.forms import choice_matches

    assert choice_matches(
        "Which state/city are you based in?", "Delhi, India", "Delhi: Delhi"
    )
    assert not choice_matches(
        "Which state/city are you based in?", "Ghaziabad, India", "Delhi: Delhi"
    )
    assert choice_matches(
        "What is your notice period?", "Immediate", "Immedidately Available"
    )
    assert not choice_matches(
        "What is your notice period?", "30 days", "Immedidately Available"
    )


async def test_hidden_radio_uses_question_label_and_explicit_consent(page, profile):
    profile["application_defaults"]["background_check_consent"] = True
    await page.set_content("""<form><div><p>Do you consent to a background check?</p>
      <label>Yes<input type=radio name=q17 value=yes style="display:none"></label>
      <label>No<input type=radio name=q17 value=no style="display:none"></label></div></form>""")
    instance = composer(profile)
    assert (
        await fill_form(page.locator("form"), profile, settings.resume_path, instance)
        == []
    )
    assert await page.locator("input[value=yes]").is_checked()
    assert (
        instance.record["entries"][0]["question"]
        == "Do you consent to a background check?"
    )


async def test_range_is_not_coerced_to_numeric_salary_and_long_answer_is_not_truncated(
    page, profile
):
    profile["application_defaults"]["expected_ctc"] = "15-25 LPA"
    await page.set_content("""<form><label>Expected salary<input type=number></label>
      <label>Why are you interested in this role?<textarea maxlength=20></textarea></label></form>""")
    instance = composer(profile)
    assert (
        len(
            await fill_form(
                page.locator("form"), profile, settings.resume_path, instance
            )
        )
        == 2
    )
    assert await page.locator("textarea").input_value() == ""
    assert instance.record["entries"][1]["evidence"]


def test_job_answer_api_preserves_evidence_and_status_requires_csrf(database):
    identity = database.add_job(job(status="review"))
    record = {
        "version": 1,
        "entries": [
            {
                "question": "Why?",
                "answer": "Draft",
                "source": "resume_and_job",
                "evidence": "Evidence",
            }
        ],
        "unresolved": ["Sponsorship?"],
        "submission_started": True,
    }
    database.save_application_answers(identity, record)
    client = create_app(database).test_client()
    path = f"/api/jobs/{identity}/answers"
    assert client.post(path, json={"answers": {}}).status_code == 403
    headers = {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}
    assert (
        client.post(
            path, json={"answers": {"Sponsorship?": True}}, headers=headers
        ).status_code
        == 200
    )
    saved = database.get_job(identity)
    assert saved.status == "review"
    actual = load_answer_record(saved.generated_answers)
    assert actual["entries"] == record["entries"] and actual["submission_started"]
    assert actual["overrides"] == {"Sponsorship?": True}
    assert (
        client.post(
            path, json={"answers": {"Why?": ["nested"]}}, headers=headers
        ).status_code
        == 400
    )
    database.manual_status(identity, "applied")
    assert client.post(path, json={"answers": {}}, headers=headers).status_code == 400


async def test_delayed_next_is_clicked_once(page, database):
    body = """<button aria-label="Easy Apply to this job" onclick="document.querySelector('dialog').showModal()">Easy Apply</button>
    <dialog><label>Email<input type=email></label><button onclick="window.nexts=(window.nexts||0)+1;setTimeout(()=>{document.querySelector('dialog').innerHTML='<p>Review application</p><button onclick=submitApplication()>Submit application</button>'},900)">Next</button></dialog>
    <script>function submitApplication(){window.submits=(window.submits||0)+1;document.body.innerHTML='Application submitted successfully'}</script>"""
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    adapter = get_applier("linkedin", database=database, dry_run=False)
    adapter.page, adapter.context = page, page.context
    assert (await adapter.apply_to_job(job())).status == "applied"
    assert await page.evaluate("window.nexts") == 1
    assert await page.evaluate("window.submits") == 1


async def test_recognized_handoff_waits_for_form_but_unknown_site_stops(page, profile):
    await page.goto("https://www.glassdoor.com/job")
    adapter = get_applier("glassdoor")
    adapter.page, adapter.context = page, page.context
    adapter.composer = composer(profile)
    await page.evaluate(
        "window.open('https://smartapply.indeed.com/beta/indeedapply/form/resume')"
    )
    await page.wait_for_timeout(250)
    popup = page.context.pages[-1]
    await popup.set_content(
        "<form><label>Email<input></label><button>Continue</button></form>"
    )
    assert await adapter.follow_handoff() == ""
    assert adapter.page == popup and popup in adapter.session.extra_pages
    assert adapter.allowed_url(popup.url)
    await popup.goto("https://unknown.invalid/application")
    assert "External application" in await adapter.blocked()


def test_linkedin_canonical_url_retains_identity():
    adapter = get_applier("linkedin")
    record = job()
    record.url = "https://in.linkedin.com/jobs/view/software-engineer-python-at-company-4475553293/?trackingId=123"
    assert (
        adapter.application_url(record)
        == "https://www.linkedin.com/jobs/view/4475553293/"
    )


async def test_review_stops_platform_and_keeps_form(database):
    from jobpilot.applier.base import ApplicationResult

    first = database.add_job(job(status="matched", match_score=90))
    other = job(status="matched", match_score=80)
    other.url += "other"
    second = database.add_job(other)
    adapter = get_applier("linkedin", database=database, dry_run=False)
    adapter.start_browser = adapter.stop_browser = AsyncMock()
    adapter.authenticate = AsyncMock(return_value=True)
    adapter.apply_to_job = AsyncMock(
        return_value=ApplicationResult("review", "Unknown answer")
    )
    result = await adapter.run()
    assert result["review"] == 1 and result["processed"] == 1
    assert database.get_job(first).status == "review"
    assert database.get_job(second).status == "matched"
    assert adapter.apply_to_job.await_count == 1


async def test_known_question_blocker_preserves_tab_and_continues_queue(page, database):
    first = database.add_job(job(status="matched", match_score=90))
    other = job(status="matched", match_score=80)
    other.url = "https://www.linkedin.com/jobs/view/456/"
    second = database.add_job(other)

    async def route_response(route):
        question = (
            "Tax identification number" if "/123/" in route.request.url else "Email"
        )
        body = f"""<button aria-label="Easy Apply to this job" onclick="document.querySelector('dialog').showModal()">Easy Apply</button>
        <dialog><label>{question}<input></label><button onclick="document.body.innerHTML='Application submitted successfully'">Submit application</button></dialog>"""
        await route.fulfill(content_type="text/html", body=body)

    await page.context.route("**/*", route_response)
    adapter = get_applier("linkedin", database=database, dry_run=False)
    adapter.page, adapter.context = page, page.context
    adapter.session.page = page
    adapter.start_browser = adapter.stop_browser = AsyncMock()
    adapter.authenticate = AsyncMock(return_value=True)
    result = await adapter.run()
    assert result["review"] == 1 and result["applied"] == 1
    assert result["processed"] == 2
    assert database.get_job(first).status == "review"
    assert database.get_job(second).status == "applied"
    assert await page.get_by_label("Tax identification number").is_visible()
    assert not page.is_closed() and adapter.session.keep_page


async def test_wellfound_reads_bounded_description_before_composing(
    page, profile, database, monkeypatch
):
    from jobpilot.applier import answers

    profile["application_defaults"]["compose_narrative_answers"] = True
    monkeypatch.setattr(
        answers, "read_resume", lambda path: "• Built Python APIs with automated tests."
    )
    record = job(status="matched")
    record.platform = "wellfound"
    record.url = "https://wellfound.com/jobs/123-python-engineer"
    record.description = ""
    record.id = database.add_job(record)
    description = "We build reliable Python APIs with automated tests. Join our team to develop and maintain backend services."
    body = f"""<div class="styles_description__hash">{description}</div><p>Other job: unrelated Java skills</p>
      <button onclick="document.querySelector('dialog').showModal()">Apply</button>
      <dialog><label>What interests you about working for this company?<textarea></textarea></label><button onclick="document.body.innerHTML='Application submitted successfully'">Submit application</button></dialog>"""
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    adapter = get_applier("wellfound", database=database, dry_run=False)
    adapter.page, adapter.context = page, page.context
    assert (await adapter.apply_to_job(record)).status == "applied"
    assert database.get_job(record.id).description == description
    assert adapter.composer.record["entries"][0]["source"] == "resume_and_job"


def test_profile_fact_variants_do_not_invent_positive_skill_experience(profile):
    assert answer_for("First name*", profile) == "Test"
    assert answer_for("Last name*", profile) == "Candidate"
    assert (
        answer_for("How many years of work experience do you have with Java?", profile)
        == 0
    )
    profile["application_defaults"]["years_of_experience"] = 3
    assert (
        answer_for("How many years of work experience do you have with Java?", profile)
        is None
    )
    profile["application_defaults"]["notice_period"] = "Immediate"
    assert answer_for("Your Official Notice Period (In-Days)", profile) == 0
    assert (
        answer_for(
            "Are you comfortable working in a hybrid setting from Pune?", profile
        )
        is None
    )


async def test_passive_recaptcha_badge_is_not_an_interactive_challenge(page):
    await page.goto("https://smartapply.indeed.com/beta/indeedapply/form/review-module")
    adapter = get_applier("glassdoor")
    adapter.page = page
    adapter._active_handoff = True
    await page.set_content(
        '<iframe src="https://www.recaptcha.net/recaptcha/enterprise/anchor?size=invisible"></iframe>'
    )
    assert await adapter.blocked() == ""
    await page.set_content(
        '<iframe src="https://www.recaptcha.net/recaptcha/enterprise/bframe?size=invisible"></iframe>'
    )
    assert "verification" in await adapter.blocked()
    await page.set_content(
        '<iframe src="https://www.recaptcha.net/recaptcha/enterprise/anchor?size=normal"></iframe>'
    )
    assert "verification" in await adapter.blocked()


def test_explicit_salary_and_indian_workplace_preferences_are_scoped(profile):
    defaults = profile["application_defaults"]
    defaults["expected_salary_single_lpa"] = 18
    defaults["willing_to_work_hybrid_or_onsite_india"] = True
    assert answer_for("What is your expected CTC?", profile) == 18
    assert answer_for("Expected salary in USD", profile) is None
    question = "Are you comfortable working in a hybrid setting from Pune?(2 Days WFO & 3 Days WFH)"
    assert (
        answer_for(question, profile, job_location="Pune District, Maharashtra, India")
        is True
    )
    assert answer_for(question, profile, job_location="London, United Kingdom") is None
    assert (
        answer_for(
            "Are you currently based in Mumbai?", profile, job_location="Mumbai, India"
        )
        is None
    )
    assert (
        answer_for(
            "Are you comfortable working hybrid night shifts?",
            profile,
            job_location="India",
        )
        is None
    )
    assert answer_for(
        "Are you comfortable working onsite weekends?", profile, job_location="India"
    ) is None


@pytest.mark.parametrize("invalid", [True, -1, float("inf"), "18"])
def test_single_salary_requires_a_finite_nonnegative_number(profile, invalid):
    profile["application_defaults"]["expected_salary_single_lpa"] = invalid
    assert any("expected_salary_single_lpa" in error for error in settings.validate())


async def test_indeed_resume_upload_is_verified_before_generic_filling(page, profile):
    await page.set_content("""<main>
      <div data-testid="resume-selection-file-resume-radio-card"><input type=radio checked data-testid="resume-selection-file-resume-radio-card-input"><span id=filename>old.pdf</span></div>
      <input type=file data-testid="resume-selection-file-resume-radio-card-file-input" onchange="document.querySelector('#filename').textContent=this.files[0].name">
      <button>Continue</button></main>""")
    adapter = get_applier("glassdoor")
    adapter.page = page
    adapter._active_handoff = True
    adapter.composer = composer(profile)
    scope = await adapter.form_scope()
    assert await adapter.prepare_form(scope) == ""
    assert adapter.composer.record["resume_uploaded"] == settings.resume_path.name
    assert not await fill_form(
        scope,
        profile,
        settings.resume_path,
        adapter.composer,
        handled_selectors=adapter.handled_form_selectors,
    )


async def test_indeed_preview_checks_identity_and_resume(page, profile):
    import html

    preview = '<p data-testid="fullName">Test Candidate</p><p data-testid="email">candidate@test.invalid</p><p data-testid="phone">+910000000000</p><p data-testid="fileName">resume.pdf</p>'
    await page.set_content(
        f'<main><iframe data-testid="application-preview" srcdoc="{html.escape(preview, quote=True)}"></iframe><button data-testid="submit-application-button">Submit your application</button></main>'
    )
    adapter = get_applier("glassdoor")
    adapter.page = page
    adapter._active_handoff = True
    adapter.composer = composer(profile)
    adapter.composer.record["resume_uploaded"] = settings.resume_path.name
    scope = await adapter.form_scope()
    assert scope is not None
    assert await adapter.prepare_form(scope) == ""
    profile["personal"]["email"] = "different@test.invalid"
    assert "email differs" in await adapter.prepare_form(scope)


async def test_wellfound_confirmation_and_applied_badge_are_specific(page):
    adapter = get_applier("wellfound")
    adapter.page = page
    await page.set_content(
        "<nav>Applied</nav><p>We look forward to receiving your application!</p>"
    )
    assert await adapter.visible(adapter.success_selectors) is None
    assert await adapter.visible(adapter.already_selectors) is None
    await page.set_content(
        "<p>SUCCESS! YOUR APPLICATION HAS BEEN SENT.</p><span>✓&nbsp; Applied</span>"
    )
    assert await adapter.visible(adapter.success_selectors) is not None
    assert await adapter.visible(adapter.already_selectors) is not None


async def test_preparation_can_replace_the_form_before_filling(page, database):
    body = """<button aria-label="Easy Apply to this job" onclick="document.querySelector('dialog').showModal()">Easy Apply</button>
      <dialog><section id=old>Choose resume<button>Continue</button></section></dialog>"""
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    adapter = get_applier("linkedin", database=database, dry_run=False)
    adapter.page, adapter.context = page, page.context
    adapter.form_selectors = ("#old", "#new")

    async def prepare(scope):
        await page.locator("dialog").evaluate(
            "el => el.innerHTML = `<section id=new><label>Email<input></label><button onclick=\"if(document.querySelector('input').value)document.body.innerHTML='Application submitted successfully'\">Submit application</button></section>`"
        )
        return ""

    adapter.prepare_form = prepare
    assert (await adapter.apply_to_job(job())).status == "applied"


async def test_linkedin_company_confirmation_and_existing_status(page):
    adapter = get_applier("linkedin")
    adapter.page = page
    await page.set_content(
        "<h2>\n    Your application was sent to Example!\n   </h2><p>Application submitted</p>"
    )
    assert await adapter.visible(adapter.success_selectors) is not None
    assert await adapter.visible(adapter.already_selectors) is not None
    await page.set_content("<p>Resume uploaded successfully</p>")
    assert await adapter.visible(adapter.success_selectors) is None


async def test_confirmation_can_arrive_after_submit_without_a_second_click(
    page, database
):
    body = """<button aria-label="Easy Apply to this job" onclick="document.querySelector('dialog').showModal()">Easy Apply</button>
      <dialog><button onclick="window.submits=(window.submits||0)+1;setTimeout(()=>{document.body.innerHTML='<h2>Your application was sent to Example!</h2>'},800)">Submit application</button></dialog>"""
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    adapter = get_applier("linkedin", database=database, dry_run=False)
    adapter.page, adapter.context = page, page.context
    assert (await adapter.apply_to_job(job())).status == "applied"
    assert await page.evaluate("window.submits") == 1


async def test_glassdoor_waits_for_hydration_and_rejects_only_optional_cookies(page):
    await page.goto("https://smartapply.indeed.com/beta/indeedapply/form/review-module")
    await page.set_content("""<button id=onetrust-reject-all-handler onclick="window.rejected=true;this.remove()">Reject All</button>
      <script>setTimeout(()=>{document.body.insertAdjacentHTML('beforeend','<main><button data-testid="submit-application-button">Submit your application</button></main>')},500)</script>""")
    adapter = get_applier("glassdoor")
    adapter.page, adapter.context = page, page.context
    adapter._active_handoff = True
    await adapter.wait_for_application_surface()
    assert await page.evaluate("window.rejected") is True
    assert await adapter.form_scope() is not None


def test_description_extraction_stops_before_recommendations():
    from jobpilot.applier.descriptions import description_from_text

    jd = "Build Python services and REST APIs with automated tests. Work with the engineering team on reliable backend software."
    page_text = f"Recommended Java jobs\nAbout the job\n{jd}\nSet alert for similar jobs\nUnrelated Golang role"
    result = description_from_text("linkedin", page_text)
    assert jd in result and "Golang" not in result and "Java" not in result
    assert description_from_text("linkedin", "About the job\n" + jd) == ""
    assert (
        description_from_text(
            "wellfound",
            f"Who we are:\n{jd}\nApply now\nSimilar jobs to other companies",
        )
        == "Who we are:\n" + jd
    )


def test_manual_question_preparation_preserves_submit_audit(
    database, profile, monkeypatch
):
    from jobpilot.applier import answers

    profile["application_defaults"]["compose_narrative_answers"] = True
    monkeypatch.setattr(
        answers, "read_resume", lambda path: "• Built Python APIs with automated tests."
    )
    identity = database.add_job(job(status="review"))
    database.save_application_answers(
        identity,
        {
            "version": 1,
            "submission_started": True,
            "entries": [],
            "unresolved": [],
            "overrides": {},
        },
    )
    client = create_app(database).test_client()
    path = f"/api/jobs/{identity}/answers/prepare"
    headers = {"X-JobPilot-Token": client.get("/api/bootstrap").json["token"]}
    assert (
        client.post(path, json={"question": "Why are you interested?"}).status_code
        == 403
    )
    response = client.post(
        path, json={"question": "Why are you interested?"}, headers=headers
    )
    assert response.json["prepared"] and response.json["record"]["submission_started"]
    assert database.get_job(identity).status == "review"
    response = client.post(
        path,
        json={"question": "Do you have 3 years of Golang experience?"},
        headers=headers,
    )
    assert (
        not response.json["prepared"] and len(response.json["record"]["entries"]) == 1
    )
    assert response.json["record"]["unresolved"] == [
        "Do you have 3 years of Golang experience?"
    ]
