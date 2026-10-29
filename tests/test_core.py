from concurrent.futures import ThreadPoolExecutor
import pytest
from click.testing import CliRunner
from jobpilot.models import Job, parse_experience, is_experience_eligible
from jobpilot.config import settings
from jobpilot.registry import PLATFORMS, platform_names, PlatformSpec, register_platform
from jobpilot.applier import get_applier
from jobpilot.scrapers import get_scraper
from jobpilot.__main__ import cli


def job(database, suffix="1", **kwargs):
    record = Job(
        title="Software Engineer",
        company="Test",
        platform="linkedin",
        url=f"https://www.linkedin.com/jobs/view/{suffix}",
        **kwargs,
    )
    record.id = database.add_job(record)
    return record


def test_duplicates_by_url_and_external_id(database):
    first = job(database, external_id="42")
    assert database.add_job(first) is None
    assert job(database, "other-url", external_id="42").id is None
    assert database.get_stats()["total_jobs"] == 1


def test_atomic_claims_and_daily_quota_survive_new_instances(database):
    from jobpilot.database import Database

    jobs = [job(database, str(i), status="matched") for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(
            pool.map(
                lambda j: Database(database.db_path).claim_application(j.id, 2), jobs
            )
        )
    assert sum(claims) == 2
    for record in jobs:
        if database.get_job(record.id).status == "applying":
            database.finish_application(record.id, "applied", "Confirmed")
            assert database.get_job(record.id).applied_at
            assert not database.claim_application(record.id, 99)
    assert not Database(database.db_path).claim_application(jobs[-1].id, 2)


def test_one_job_claimed_once(database):
    record = job(database, status="matched")
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert (
            sum(pool.map(lambda _: database.claim_application(record.id, 20), range(6)))
            == 1
        )


def test_matching_does_not_reset_terminal_state(database):
    record = job(database, status="applied")
    database.update_match_score(record.id, 90, "New score")
    assert database.get_job(record.id).status == "applied"
    with pytest.raises(ValueError):
        database.manual_status(record.id, "shortlisted")
    with pytest.raises(ValueError):
        database.update_match_score(record.id, float("nan"))


def test_db_validates_identifiers_and_combines_search_filters(database):
    job(database, status="matched", match_score=80)
    assert not database.get_jobs(search="Software", status="applied")
    assert len(database.get_jobs(search="Software", min_score=70)) == 1
    with pytest.raises(ValueError):
        database.get_jobs(order_by="id; DROP TABLE jobs")
    with pytest.raises(ValueError):
        database.update_job_status(1, "invented")
    with pytest.raises(ValueError):
        database.update_job_status(1, "matched", unexpected=123)


@pytest.mark.parametrize(
    "value, expected",
    [("6-18 months", (0.5, 1.5)), ("1–3 years", (1, 3)), ("", (None, None))],
)
def test_experience_parser(value, expected):
    assert parse_experience(value) == expected


def test_experience_range_is_configurable():
    assert is_experience_eligible("2+ years", 0, 2)[0]
    assert not is_experience_eligible("0-1 years", 3, 5)[0]
    assert Job(
        title="Senior Engineer",
        company="Test",
        platform="x",
        url="https://test.invalid",
        experience="5-8 years",
    ).is_experience_eligible(4, 8)[0]


def test_all_adapters_and_disabled_selection():
    for name in PLATFORMS:
        assert get_applier(name).platform_name == name
        assert get_scraper(name).platform_name == name
    settings._platforms["platforms"]["foundit"]["enabled"] = False
    assert "foundit" not in platform_names()
    assert not platform_names("foundit")
    with pytest.raises(ValueError):
        platform_names("unknown")


def test_register_platform_without_cli_changes():
    spec = PlatformSpec(
        "test_platform",
        "jobpilot.scrapers.linkedin:LinkedInScraper",
        "jobpilot.applier.linkedin_applier:LinkedInApplier",
    )
    register_platform(spec)
    try:
        settings._platforms["platforms"][spec.name] = {"enabled": True}
        assert spec.name in platform_names()
        assert get_scraper(spec.name).platform_name == "linkedin"
    finally:
        del PLATFORMS[spec.name]


def test_resume_path_does_not_silently_choose_someone_elses_file(profile):
    profile["resume"]["path"] = "config/missing.pdf"
    assert settings.resume_path.name == "missing.pdf"
    assert settings.validate(for_apply=True)


def test_cli_rejects_invalid_inputs_without_browser():
    runner = CliRunner()
    assert runner.invoke(cli, ["apply", "--limit", "-1"]).exit_code == 2
    assert runner.invoke(cli, ["apply", "-p", "unknown"]).exit_code != 0
    assert runner.invoke(cli, ["--help"]).exit_code == 0


async def test_offline_matching_without_api_key(profile):
    from jobpilot.ai.matcher import JobMatcher

    record = Job(
        title="Software Engineer",
        company="Test",
        platform="linkedin",
        url="https://test.invalid",
        skills=["Python"],
        experience="0-2 years",
    )
    result = await JobMatcher().score_job(record)
    assert result["score"] >= 40


def test_scheduler_validates_before_immediate_run(monkeypatch):
    from jobpilot import scheduler

    monkeypatch.setattr(
        scheduler, "run_daily_pipeline", lambda **kw: pytest.fail("must not run")
    )
    with pytest.raises(ValueError):
        scheduler.start_scheduler("99:99", True)


def test_browser_profile_lock():
    from jobpilot.browser import BrowserSession
    from filelock import Timeout

    first, second = BrowserSession("test"), BrowserSession("test")
    with first._lock.acquire(timeout=0):
        with pytest.raises(Timeout):
            second._lock.acquire(timeout=0)


def test_offline_matching_requires_actual_role_or_skill_overlap(profile):
    from jobpilot.ai.matcher import JobMatcher

    matcher = JobMatcher()
    unrelated = Job(
        title="Accountant",
        company="Example",
        platform="cutshort",
        url="https://cutshort.io/job/1",
    )
    one_skill = Job(
        title="Backend Developer",
        company="Example",
        platform="cutshort",
        url="https://cutshort.io/job/2",
        skills=["Python"],
    )
    assert matcher._rule_based_score(unrelated)["score"] == 0
    assert matcher._rule_based_score(one_skill)["score"] == 10
