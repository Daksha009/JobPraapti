"""JobPraapti CLI. Configuration and personal information stay outside source code."""

import asyncio
import json
import logging
import shutil
from pathlib import Path
import click
from filelock import FileLock, Timeout
from .config import BASE_DIR, CONFIG_DIR, DATA_DIR, settings
from .registry import PLATFORMS, platform_names


def emit(value):
    click.echo(json.dumps(value, indent=2, ensure_ascii=True))


def execute(awaitable):
    try:
        return asyncio.run(awaitable)
    except (ValueError, OSError, Timeout) as exc:
        raise click.ClickException(str(exc)) from exc


def platform_option(function):
    return click.option(
        "--platform",
        "-p",
        default="all",
        help="Platform name, or all enabled platforms",
    )(function)


def require_platform(platform):
    try:
        names = platform_names(platform)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--platform") from exc
    if not names:
        raise click.ClickException(
            "No selected platforms are enabled in config/platforms.yaml"
        )


def require_config(for_apply=False):
    errors = settings.validate(for_apply=for_apply)
    if errors:
        raise click.ClickException("; ".join(errors))


def report_exit(report):
    emit(report)
    rows = (
        report
        if isinstance(report, list)
        else report.get("scrapes", []) + report.get("applications", [])
    )
    if any(row.get("error") or row.get("success") is False for row in rows) or (
        isinstance(report, dict) and report.get("errors")
    ):
        raise click.exceptions.Exit(1)


@click.group()
@click.version_option("0.3.0", prog_name="JobPraapti")
def cli():
    """Discover, rank and apply to jobs with your own profile and saved sessions."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )


@cli.command()
def init():
    """Create configuration files without overwriting personal data."""
    templates = Path(__file__).resolve().parent.parent
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for source, destination in (
        (templates / "config/profile.example.yaml", CONFIG_DIR / "profile.yaml"),
        (templates / "config/platforms.yaml", CONFIG_DIR / "platforms.yaml"),
        (templates / ".env.example", BASE_DIR / ".env"),
    ):
        if not destination.exists():
            shutil.copyfile(source, destination)
            click.echo(f"Created {destination}")
    click.echo(
        "Edit config/profile.yaml, .env and config/platforms.yaml; then run doctor."
    )


@cli.command()
def install_browser():
    """Check the device's Chrome installation; no testing browser is downloaded."""
    from .browser import installed_chrome_path

    try:
        click.echo(f"Using installed Google Chrome: {installed_chrome_path()}")
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
def doctor():
    """Check local setup without connecting to job sites or exposing credentials."""
    errors = settings.validate(for_apply=True)
    from .browser import installed_chrome_path

    try:
        chrome = str(installed_chrome_path())
    except RuntimeError as exc:
        chrome = None
        errors.append(str(exc))
    emit(
        {
            "home": str(BASE_DIR),
            "browser": {"product": "Google Chrome", "executable": chrome},
            "errors": errors,
            "platforms": [
                {
                    "platform": name,
                    "credentials_present": all(settings.credentials(name)),
                    "session_directory_exists": (DATA_DIR / f"{name}_profile").exists(),
                }
                for name in PLATFORMS
            ],
            "matching": "gemini with offline fallback"
            if settings.gemini_api_key
            else "offline",
            "note": "Session directories do not prove that login is still valid.",
        }
    )
    if errors:
        raise click.exceptions.Exit(1)


@cli.command()
@platform_option
@click.option("--headless/--no-headless", default=True)
def scrape(platform, headless):
    """Discover and save listings from enabled platforms."""
    from .pipeline import scrape_platforms

    require_config()
    require_platform(platform)
    report_exit(execute(scrape_platforms(platform, headless)))


@cli.command()
@click.option("--limit", "-l", default=200, type=click.IntRange(1, 10000))
def match(limit):
    """Rank new jobs with optional Gemini or offline profile matching."""
    from .ai.matcher import JobMatcher
    from .database import db

    require_config()
    emit(
        {
            "scored": execute(
                JobMatcher().score_jobs(db.get_jobs(status="new", limit=limit))
            )
        }
    )


@cli.command()
@click.option("--status", "-s", default=None)
@click.option("--platform", "-p", default=None)
@click.option("--min-score", "-m", type=click.FloatRange(0, 100), default=None)
@click.option("--limit", "-l", default=30, type=click.IntRange(1, 10000))
def jobs(status, platform, min_score, limit):
    """Inspect stored jobs, including review and applying queues."""
    from .database import db

    emit(
        [
            job.to_dict() | {"id": job.id}
            for job in db.get_jobs(
                status=None if status == "all" else status,
                platform=platform,
                min_score=min_score,
                limit=limit,
            )
        ]
    )


@cli.command()
def stats():
    """Show database totals."""
    from .database import db

    emit(db.get_stats())


@cli.command()
@click.option("--platform", "-p", required=True)
def login(platform):
    """Save a session; complete SSO, CAPTCHA or 2FA in the browser."""
    from .applier import get_applier

    if platform not in PLATFORMS:
        raise click.BadParameter(f"Choose one of: {', '.join(PLATFORMS)}")
    if not execute(get_applier(platform).interactive_login()):
        raise click.ClickException(
            "Login could not be verified. Check the account and adapter auth selectors."
        )
    click.echo("Login verified; session saved.")


@cli.command()
@platform_option
@click.option("--dry-run/--live", default=True, show_default=True)
@click.option("--limit", "-l", default=20, type=click.IntRange(1, 1000))
@click.option("--min-score", "-m", default=None, type=click.FloatRange(0, 100))
@click.option("--min-exp", default=None, type=click.FloatRange(0))
@click.option("--max-exp", default=None, type=click.FloatRange(0))
@click.option("--headless/--no-headless", default=True)
def apply(platform, dry_run, limit, min_score, min_exp, max_exp, headless):
    """Apply to matched/shortlisted jobs. Dry runs never click Apply."""
    from .pipeline import apply_platforms

    require_config(for_apply=not dry_run)
    require_platform(platform)
    report_exit(
        execute(
            apply_platforms(
                platform,
                dry_run=dry_run,
                limit=limit,
                min_score=min_score,
                min_experience=min_exp,
                max_experience=max_exp,
                headless=headless,
            )
        )
    )


@cli.command(name="run-daily")
@platform_option
@click.option("--dry-run/--live", default=True, show_default=True)
@click.option("--apply/--no-apply", "do_apply", default=True)
@click.option("--limit", "-l", default=20, type=click.IntRange(1, 1000))
@click.option("--headless/--no-headless", default=True)
def run_daily(platform, dry_run, do_apply, limit, headless):
    """Run discovery, matching and application as one pipeline."""
    from .pipeline import run_pipeline

    require_platform(platform)
    report_exit(
        execute(
            run_pipeline(
                platform,
                dry_run=dry_run,
                do_apply=do_apply,
                apply_limit=limit,
                headless=headless,
            )
        )
    )


@cli.command()
@click.option("--time", "-t", default="09:00")
@click.option(
    "--timezone", default=lambda: settings.get_env("JOBPILOT_TIMEZONE", "UTC")
)
@click.option("--now", is_flag=True)
@click.option("--dry-run/--live", default=True, show_default=True)
@click.option("--limit", default=20, type=click.IntRange(1, 1000))
def schedule(time, timezone, now, dry_run, limit):
    """Run daily while this process stays open; timezone is explicit."""
    from .scheduler import start_scheduler

    require_config(for_apply=not dry_run)
    try:
        start_scheduler(
            time, now, timezone=timezone, dry_run=dry_run, apply_limit=limit
        )
    except (ValueError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--port", "-p", default=None, type=click.IntRange(1, 65535))
def dashboard(port):
    """Serve the dashboard on localhost."""
    from .dashboard.app import create_app

    from waitress import serve

    selected_port = port or settings.dashboard_port
    click.echo(f"JobPraapti is ready at http://127.0.0.1:{selected_port}")
    serve(
        create_app(),
        host="127.0.0.1",
        port=selected_port,
        threads=6,
        max_request_body_size=6 * 1024 * 1024,
    )


@cli.command(name="parse-resume")
@click.option("--pdf", type=click.Path(exists=True), default=None)
@click.option("--no-ai", is_flag=True)
def parse_resume(pdf, no_ai):
    """Extract resume keywords without modifying the profile."""
    from .ai.resume_parser import ResumeParser

    result = execute(ResumeParser(pdf).parse(use_ai=not no_ai))
    result.pop("raw_text", None)
    emit(result)


@cli.command()
@click.argument("job_id", type=int)
@click.option(
    "--status",
    required=True,
    type=click.Choice(["shortlisted", "review", "rejected", "applied"]),
)
def review(job_id, status):
    """Record a decision after inspecting a job or uncertain submission."""
    from .database import db

    try:
        if not db.manual_status(job_id, status):
            raise click.ClickException("Job not found")
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    emit({"id": job_id, "status": status})


@cli.command()
@click.argument("job_id", type=int)
def recover(job_id):
    """Move an interrupted applying job to review once its browser is stopped."""
    from .database import db

    job = db.get_job(job_id)
    if not job or job.status != "applying":
        raise click.ClickException("Job must exist with applying status")
    try:
        with FileLock(str(DATA_DIR / f"{job.platform}.browser.lock")).acquire(
            timeout=0
        ):
            db.finish_application(
                job_id,
                "review",
                "Recovered interrupted run; verify on platform before retrying",
            )
    except Timeout as exc:
        raise click.ClickException("Platform browser is still running") from exc
    emit({"id": job_id, "status": "review"})


if __name__ == "__main__":
    cli()
