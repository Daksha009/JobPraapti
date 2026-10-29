"""Application selection and actionable pre-submission reporting."""

from unittest.mock import AsyncMock
import pytest
from jobpilot.applier import get_applier
from jobpilot.models import Job
from jobpilot.progress import reporting_to


def add(database, **values):
    return database.add_job(
        Job(
            **{
                "title": "Software Engineer",
                "company": "Fixture",
                "platform": "hirist",
                "url": f"https://www.hirist.tech/j/fixture-{len(database.get_jobs(limit=1000))}",
                "match_score": 75,
                "status": "matched",
                "experience": "0-2 years",
                **values,
            }
        )
    )


def test_candidate_filters_explained_without_loosening_preferences(database, profile):
    profile["preferences"]["exclude_keywords"] = ["Excluded"]
    add(database, match_score=20)
    add(database, experience="5-8 years")
    add(database, title="Excluded Engineer")
    eligible = add(database)
    add(database, status="applied")
    candidates, summary = get_applier(
        "hirist", database=database, min_score=50
    ).select_candidates()
    assert [job.id for job in candidates] == [eligible]
    assert summary == {
        "considered": 4,
        "below_score": 1,
        "experience_mismatch": 1,
        "excluded_title": 1,
        "eligible": 1,
        "selected": 1,
        "min_score": 50,
    }


async def test_empty_queue_explains_filter_without_opening_browser(database):
    add(database, match_score=20)
    adapter = get_applier("hirist", database=database, min_score=50)
    adapter.start_browser = AsyncMock()
    result = await adapter.run()
    assert "1 below score 50" in result["message"]
    assert result["selected"] == result["processed"] == 0
    adapter.start_browser.assert_not_awaited()


def test_saved_ten_point_threshold_includes_boundary_without_requeueing(
    database, profile
):
    profile["preferences"]["min_match_score"] = 10
    boundary = add(database, match_score=10)
    add(database, match_score=9)
    add(database, match_score=80, status="applied")
    add(database, match_score=80, status="review")
    add(database, match_score=80, experience="5-8 years")
    candidates, summary = get_applier("hirist", database=database).select_candidates()
    assert [job.id for job in candidates] == [boundary]
    assert summary["min_score"] == 10
    assert summary["below_score"] == 1
    assert summary["experience_mismatch"] == 1


async def test_authentication_block_preserves_queue_and_emits_reason(
    database, monkeypatch
):
    from jobpilot import applier as factory
    from jobpilot.pipeline import apply_platforms

    candidate = add(database)
    adapter = get_applier("hirist", database=database, dry_run=False)
    adapter.start_browser = AsyncMock()
    adapter.stop_browser = AsyncMock()
    adapter.authenticate = AsyncMock(return_value=False)
    monkeypatch.setattr(factory, "get_applier", lambda *args, **kwargs: adapter)
    events = []
    with reporting_to(events.append):
        [result] = await apply_platforms("hirist", dry_run=False)
    assert result["blocker"] == "authentication"
    assert result["selected"] == 1 and result["processed"] == 0
    assert database.get_job(candidate).status == "matched"
    assert events[-1]["total"] == 1
    assert "Verify sign-in" in events[-1]["message"]
    assert events[-1]["state"] == "attention"


async def test_hirist_current_avatar_after_hydration(page):
    body = """<div id="root"></div><script>setTimeout(() => {
      document.getElementById('root').innerHTML = '<header><img data-testid="header-profile-avatar-image" alt="user_profile" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></header>';
    }, 600)</script>"""
    await page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html", body=body)
    )
    adapter = get_applier("hirist")
    adapter.page = page
    assert await adapter.is_logged_in()


async def test_connection_failure_explains_approval_without_claiming_job(database):
    from jobpilot.browser import BrowserConnectionError

    candidate = add(database)
    adapter = get_applier("hirist", database=database, dry_run=False)
    adapter.start_browser = AsyncMock(
        side_effect=BrowserConnectionError("Chrome connection was not approved.")
    )
    adapter.stop_browser = AsyncMock()
    result = await adapter.run()
    assert result["blocker"] == "browser_connection"
    assert "not approved" in result["error"]
    assert result["selected"] == 1 and result["processed"] == 0
    assert database.get_job(candidate).status == "matched"


@pytest.mark.parametrize(
    ("platform", "body"),
    [
        (
            "wellfound",
            '<a href="/profile/edit/overview">Profile</a><a href="/jobs/applications">Applied</a><a href="/jobs/messages">Messages</a>',
        ),
        (
            "glassdoor",
            '<button data-test="utility-nav-profile-button" aria-label="profile"></button><div>Post anonymously as</div><button>Create post</button>',
        ),
    ],
)
async def test_current_member_controls_verify_session(page, platform, body):
    await page.route("**/*", lambda r: r.fulfill(content_type="text/html", body=body))
    adapter = get_applier(platform)
    adapter.page = page
    assert await adapter.is_logged_in()


@pytest.mark.parametrize(
    ("platform", "body"),
    [
        ("wellfound", '<a href="/jobs/applications">Applied</a>'),
        (
            "glassdoor",
            '<button data-test="utility-nav-profile-button" aria-label="profile"></button>',
        ),
    ],
)
async def test_single_public_control_is_not_member_evidence(page, platform, body):
    adapter = get_applier(platform)
    adapter.page = page
    await page.set_content(body)
    assert await adapter.visible(adapter.auth_selectors) is None


async def test_run_limit_does_not_replace_daily_quota(database):
    from jobpilot.applier.base import ApplicationResult

    first = add(database)
    assert database.claim_application(first, 2)
    database.finish_application(first, "applied", "Fixture confirmation")
    second = add(database)
    adapter = get_applier("hirist", database=database, dry_run=False, daily_limit=1)
    adapter.start_browser = AsyncMock()
    adapter.stop_browser = AsyncMock()
    adapter.authenticate = AsyncMock(return_value=True)
    adapter.apply_to_job = AsyncMock(
        return_value=ApplicationResult("applied", "Fixture confirmation")
    )
    result = await adapter.run()
    assert result["applied"] == 1 and result["skipped"] == 0
    assert database.get_job(second).status == "applied"
    third = add(database)
    result = await adapter.run()
    assert result["applied"] == 0 and result["skipped"] == 1
    assert database.get_job(third).status == "matched"
    assert adapter.apply_to_job.await_count == 1


def test_legacy_unmatched_offline_score_cannot_enter_ten_point_queue(database):
    reason = "Matched role keywords and 0 core skills (general). Strengths: none."
    old = add(database, title="Unrelated job", match_score=15, match_reason=reason)
    eligible = add(
        database, title="Software Engineer", match_score=15, match_reason="Employer fit"
    )
    shortlisted = add(
        database,
        title="Manually chosen job",
        match_score=15,
        match_reason=reason,
        status="shortlisted",
    )
    candidates, summary = get_applier(
        "hirist", database=database, min_score=10
    ).select_candidates()
    assert {job.id for job in candidates} == {eligible, shortlisted}
    assert summary["below_score"] == 1
    assert old not in {job.id for job in candidates}
