import pytest
from jobpilot.scrapers import get_scraper
from jobpilot.config import settings
from jobpilot.models import Job


CARDS = {
    "linkedin": '<article class="job-card-container"><h3>Software Engineer</h3><h4>Example</h4><a href="/jobs/view/123">View</a><span class="location">Remote</span></article>',
    "wellfound": '<article class="JobCard"><h2>Software Engineer</h2><span class="company">Example</span><a href="/jobs/123">View</a><span class="location">Remote</span></article>',
    "hirist": '<a href="/j/example-123"><h2>Example - Software Engineer</h2><span data-testid="job_experience">0-2 years</span><span data-testid="job_location">Remote</span></a>',
    "foundit": '<article class="jobCard"><a class="jobTitle" href="/job/123">Software Engineer</a><span class="companyName">Example</span><span class="location">Remote</span></article>',
    "glassdoor": '<article class="JobCard"><a data-test="job-title" href="/job-listing/example?jobListingId=123">Software Engineer</a><span data-test="emp-name">Example</span><span data-test="emp-location">Remote</span></article>',
    "cutshort": '<article><a href="https://cutshort.io/job/123">Software Engineer</a><div>at Example</div><div>Remote · 0-2 years</div><div>Python</div></article>',
}


@pytest.mark.parametrize("name", list(CARDS))
async def test_card_extraction_each_platform(page, name):
    scraper = get_scraper(name)
    scraper.page = page
    await page.set_content(CARDS[name])
    jobs = await scraper._extract_jobs_from_page()
    assert len(jobs) == 1
    assert jobs[0].title.endswith("Software Engineer")
    assert jobs[0].company == "Example"
    assert jobs[0].platform == name
    assert jobs[0].url.startswith("https://")
    assert jobs[0].external_id == "123"


async def test_cutshort_does_not_mix_adjacent_company_metadata(page):
    scraper = get_scraper("cutshort")
    scraper.page = page
    await page.set_content(
        CARDS["cutshort"]
        + CARDS["cutshort"].replace("123", "456").replace("Example", "Second")
    )
    assert [j.company for j in await scraper._extract_jobs_from_page()] == [
        "Example",
        "Second",
    ]


async def test_linkedin_current_card_keeps_title_company_and_location(page):
    scraper = get_scraper("linkedin")
    scraper.page = page
    await page.set_content("""<div class="job-card-container" data-job-id="123">
      <a class="job-card-list__title--link" href="/jobs/view/123/?tracking=test">
        <strong>Junior Software Engineer</strong></a>
      <div class="artdeco-entity-lockup__subtitle">Example Company</div>
      <ul class="job-card-container__metadata-wrapper"><li>Delhi, India (Remote)</li></ul>
      <li class="job-card-container__footer-item">Easy Apply</li>
    </div>""")
    [job] = await scraper._extract_jobs_from_page()
    assert job.title == "Junior Software Engineer"
    assert job.company == "Example Company"
    assert job.location == "Delhi, India (Remote)"
    assert job.job_type == "easy_apply"
    assert job.url == "https://www.linkedin.com/jobs/view/123/"


async def test_linkedin_stops_when_pagination_repeats_same_jobs(page, monkeypatch):
    from unittest.mock import AsyncMock

    scraper = get_scraper("linkedin")
    scraper.page = page
    scraper.platform_config["max_pages"] = 3
    scraper._random_delay = AsyncMock()
    scraper._scroll_job_list = AsyncMock()
    await page.route(
        "**/*", lambda r: r.fulfill(content_type="text/html", body=CARDS["linkedin"])
    )
    navigate = AsyncMock(wraps=scraper.navigate)
    monkeypatch.setattr(scraper, "navigate", navigate)
    jobs = await scraper.scrape_jobs()
    assert len(jobs) == 1
    assert navigate.await_count == 2


async def test_cutshort_signed_out_redirect_has_actionable_error(page):
    from unittest.mock import AsyncMock

    scraper = get_scraper("cutshort")
    scraper.page = page
    scraper.platform_config["search_urls"] = ["https://cutshort.io/profile/all-jobs"]
    scraper._random_delay = AsyncMock()

    async def redirect(*args, **kwargs):
        await page.goto("https://cutshort.io/?redirect_url=%2Fprofile%2Fall-jobs")

    scraper.navigate = redirect
    assert await scraper.scrape_jobs() == []
    assert "sign-in required" in scraper.navigation_errors[0]


async def test_ai_service_failure_falls_back_once_per_matcher(monkeypatch):
    from unittest.mock import AsyncMock
    from jobpilot.ai import matcher

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    generate = AsyncMock(side_effect=TimeoutError("synthetic timeout"))
    monkeypatch.setattr(matcher, "generate_text", generate)
    job = Job(
        title="Software Engineer",
        company="Fixture",
        platform="hirist",
        url="https://www.hirist.tech/j/fixture",
        skills=["Python"],
    )
    instance = matcher.JobMatcher()
    first = await instance.score_job(job)
    second = await instance.score_job(job)
    assert first["score"] == second["score"]
    assert generate.await_count == 1
    await matcher.JobMatcher().score_job(job)
    assert generate.await_count == 2


async def test_malformed_ai_response_does_not_disable_next_request(monkeypatch):
    from unittest.mock import AsyncMock
    from jobpilot.ai import matcher

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    generate = AsyncMock(side_effect=["invalid json", '{"score": 88}'])
    monkeypatch.setattr(matcher, "generate_text", generate)
    job = Job(
        title="Software Engineer",
        company="Fixture",
        platform="hirist",
        url="https://www.hirist.tech/j/fixture",
        skills=["Python"],
    )
    instance = matcher.JobMatcher()
    await instance.score_job(job)
    assert (await instance.score_job(job))["score"] == 88
    assert generate.await_count == 2


async def test_wellfound_ignores_sign_up_navigation_and_foreign_links(page):
    scraper = get_scraper("wellfound")
    scraper.page = page
    await page.set_content(
        '<a href="/jobs/signup">Create an account</a><a href="/jobs/home">Jobs</a><a href="https://foreign.invalid/jobs/123">False job</a><a href="/jobs/123-software-engineer">Software Engineer</a>'
    )
    jobs = await scraper._extract_jobs_from_page()
    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer" and jobs[0].external_id == "123"


async def test_wellfound_recommendations_include_card_metadata(page):
    scraper = get_scraper("wellfound")
    scraper.page = page
    await page.set_content("""<div class="styles_joblistingContainer_fixture">
      <div class="styles_information_fixture">
        <a href="/jobs/123-software-engineer"><h3>Software Engineer</h3></a>
        <a class="styles_company_fixture" href="/company/example">Example</a>
        <span class="styles_location_fixture">India · Remote</span>
        <span class="styles_salaryEstimate_fixture">₹12L – ₹24L</span>
      </div><button>Save</button></div>""")
    [job] = await scraper._extract_jobs_from_page()
    assert job.company == "Example"
    assert job.location == "India · Remote"
    assert job.salary == "₹12L – ₹24L"


async def test_full_pipeline_discovery_matching_submission_and_dedup(
    page, database, monkeypatch
):
    from jobpilot import scrapers, pipeline
    from jobpilot.scrapers import base as scraper_base
    from jobpilot.applier import base as applier_base
    from jobpilot.ai import matcher
    from test_browser import html

    for name, cfg in settings._platforms["platforms"].items():
        cfg["enabled"] = name == "linkedin"
    for module in (scraper_base, applier_base, matcher):
        monkeypatch.setattr(module, "db", database)

    class FixtureScraper(scraper_base.BaseScraper):
        platform_name = "linkedin"

        async def start_browser(self, **kwargs):
            self.page = page

        async def stop_browser(self):
            pass

        async def scrape_jobs(self):
            return [
                Job(
                    title="Software Engineer",
                    company="Example",
                    platform="linkedin",
                    url="https://www.linkedin.com/jobs/view/123",
                    skills=["Python"],
                )
            ]

    async def start(self, *args, **kwargs):
        self.page, self.context = page, page.context

    async def stop(self):
        pass

    async def auth(self):
        return True

    monkeypatch.setattr(scrapers, "get_scraper", lambda _: FixtureScraper())
    monkeypatch.setattr(applier_base.BaseApplier, "start_browser", start)
    monkeypatch.setattr(applier_base.BaseApplier, "stop_browser", stop)
    monkeypatch.setattr(applier_base.BaseApplier, "authenticate", auth)
    await page.route(
        "**/*",
        lambda route: route.fulfill(content_type="text/html", body=html("linkedin")),
    )
    report = await pipeline.run_pipeline(dry_run=False)
    assert report["scrapes"][0]["jobs_new"] == 1
    assert report["scored"] == 1
    assert report["applications"][0]["applied"] == 1
    record = database.get_jobs()[0]
    assert record.status == "applied" and record.applied_at
    assert [r["action"] for r in database.get_application_history(record.id)] == [
        "applied",
        "attempt_started",
    ]
    report = await pipeline.run_pipeline(dry_run=False)
    assert report["scrapes"][0]["jobs_duplicate"] == 1
    assert report["scored"] == report["applications"][0]["applied"] == 0


async def test_pipeline_matching_error_stops_apply(monkeypatch):
    from jobpilot import pipeline
    from jobpilot.ai.matcher import JobMatcher

    async def scrape(*args):
        return []

    async def fail(*args):
        raise RuntimeError("test matching failure")

    async def forbidden(*args, **kwargs):
        pytest.fail("must not submit after matching stage failure")

    monkeypatch.setattr(pipeline, "scrape_platforms", scrape)
    monkeypatch.setattr(JobMatcher, "score_jobs", fail)
    monkeypatch.setattr(pipeline, "apply_platforms", forbidden)
    assert (await pipeline.run_pipeline())["errors"]


def test_search_filters_use_configured_experience(profile):
    from urllib.parse import parse_qs, urlparse

    profile["preferences"]["min_experience_years"] = 4
    profile["preferences"]["max_experience_years"] = 7
    params = parse_qs(urlparse(get_scraper("foundit")._build_search_url()).query)
    assert params["experienceRanges"] == ["4~7"]
    linkedin = get_scraper("linkedin")
    linkedin.platform_config["easy_apply_only"] = False
    assert "f_AL" not in parse_qs(urlparse(linkedin._build_search_url()).query)


async def test_current_cutshort_card_keeps_experience_skills_and_company(page):
    scraper = get_scraper("cutshort")
    scraper.page = page
    await page.set_content("""<div class="sc-963106f5-1">
      <div class="sc-963106f5-15"><h3><a href="https://cutshort.io/job/backend-123">Backend Engineer</a></h3><div>Example</div></div>
      <div class="sc-963106f5-29">Remote only</div>
      <div class="sc-963106f5-26">2 - 5 yrs</div>
      <div class="sc-963106f5-26">₹10L / yr</div>
      <span class="sc-60b7a349-1">Python</span></div>""")
    [job] = await scraper._extract_jobs_from_page()
    assert (job.company, job.location, job.experience, job.skills) == (
        "Example",
        "Remote only",
        "2 - 5 yrs",
        ["Python"],
    )


async def test_current_foundit_cards_ignore_nested_title_and_company_links(page):
    scraper = get_scraper("foundit")
    scraper.page = page
    await page.set_content("""<div class="shadow-job-card">Navigation only</div>
      <div class="shadow-job-card"><h2 class="jobCardTitle"><a href="https://www.foundit.in/job/backend-123456">Python Engineer</a></h2>
      <span class="jobCardCompany"><a href="/company/example">Example</a></span>
      <div class="jobCardLocation">Remote, India</div><div class="jobCardExperience">0-2 yrs</div>
      <button class="jobCardSaveUnsaveBtn">Save</button></div>""")
    [job] = await scraper._extract_jobs_from_page()
    assert job.title == "Python Engineer"
    assert job.company == "Example"
    assert job.experience == "0-2 yrs"
    assert job.external_id == "123456"


def test_foundit_current_search_uses_encoded_query_and_result_offset():
    scraper = get_scraper("foundit")
    url = scraper._build_search_url("Python Engineer", page=2)
    assert "/search/python-engineer-jobs?" in url
    assert "query=Python%20Engineer" in url
    assert "start=21" in url
    assert "page=" not in url


async def test_foundit_fallback_does_not_mix_adjacent_jobs(page):
    scraper = get_scraper("foundit")
    scraper.page = page
    await page.set_content("""<main>
      <div><a href="https://www.foundit.in/job/111111">Junior Developer</a><p>Delhi</p><p>0-1 yrs</p></div>
      <div><a href="https://www.foundit.in/job/222222">Senior Engineer</a><p>Mumbai</p><p>8-10 yrs</p></div>
      </main>""")
    jobs = await scraper._extract_jobs_js()
    assert [(j.title, j.location, j.experience) for j in jobs] == [
        ("Junior Developer", "Delhi", "0-1 yrs"),
        ("Senior Engineer", "Mumbai", "8-10 yrs"),
    ]


@pytest.mark.parametrize(
    "status,should_retry", [(503, True), (401, False), (429, False)]
)
async def test_gemini_uses_alternate_model_only_for_unavailable_service(
    monkeypatch, status, should_retry
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from google import genai
    from jobpilot.ai import client as ai_client

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-primary")

    class SyntheticError(Exception):
        code = status

    generate = AsyncMock(
        side_effect=[SyntheticError(), SimpleNamespace(text='{"score": 50}')]
    )

    class Context:
        async def __aenter__(self):
            return SimpleNamespace(models=SimpleNamespace(generate_content=generate))

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        genai, "Client", lambda **kwargs: SimpleNamespace(aio=Context())
    )
    if should_retry:
        assert (
            await ai_client.generate_text("synthetic", json_output=True)
            == '{"score": 50}'
        )
        assert [call.kwargs["model"] for call in generate.await_args_list] == [
            "test-primary",
            ai_client.FALLBACK_MODEL,
        ]
        assert all(
            call.kwargs["config"] == {"response_mime_type": "application/json"}
            for call in generate.await_args_list
        )
    else:
        with pytest.raises(SyntheticError):
            await ai_client.generate_text("synthetic")
        assert generate.await_count == 1
