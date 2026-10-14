"""Reusable orchestration for CLI, dashboard and scheduler."""

from dataclasses import asdict
from filelock import FileLock
from .config import DATA_DIR, settings
from .registry import platform_names
from .progress import emit


async def scrape_platforms(platform="all", headless=True):
    from .scrapers import get_scraper

    results = []
    for name in platform_names(platform):
        emit("discover", "Opening job listings", platform=name)
        try:
            results.append(asdict(await get_scraper(name).run(headless=headless)))
        except Exception as exc:
            results.append(
                {"platform": name, "success": False, "errors": [type(exc).__name__]}
            )
        result = results[-1]
        emit(
            "discover",
            "Discovery finished"
            if result.get("success")
            else "Discovery needs attention; inspect the result",
            platform=name,
            state="completed" if result.get("success") else "attention",
            metrics={
                key: result.get(key, 0)
                for key in ("jobs_found", "jobs_new", "jobs_duplicate")
            },
        )
    return results


async def apply_platforms(
    platform="all", *, dry_run=True, limit=20, min_score=None, headless=True, **kwargs
):
    from .applier import get_applier

    results = []
    for name in platform_names(platform):
        emit(
            "apply",
            "Preparing dry-run candidates"
            if dry_run
            else "Preparing eligible applications",
            platform=name,
        )
        try:
            results.append(
                await get_applier(
                    name,
                    dry_run=dry_run,
                    daily_limit=limit,
                    min_score=min_score,
                    **kwargs,
                ).run(headless=headless)
            )
        except Exception as exc:
            results.append(
                {"platform": name, "applied": 0, "error": type(exc).__name__}
            )
        result = results[-1]
        emit(
            "apply",
            result.get("error") or result.get("message")
            or (
                "Application stage needs attention"
                if result.get("error")
                else "Application stage finished"
            ),
            platform=name,
            state="attention"
            if result.get("error") or result.get("review") or result.get("failed")
            else "completed",
            current=result.get("processed", 0),
            total=result.get("selected", 0),
            metrics={
                key: result.get(key, 0)
                for key in (
                    "applied",
                    "dry_run",
                    "review",
                    "failed",
                    "expired",
                    "already_applied",
                    "skipped",
                )
            },
        )
    return results


async def run_pipeline(
    platform="all", *, dry_run=True, apply_limit=20, do_apply=True, headless=True
):
    from .ai.matcher import JobMatcher

    errors = settings.validate(for_apply=do_apply and not dry_run)
    if errors:
        raise ValueError("; ".join(errors))
    with FileLock(str(DATA_DIR / "pipeline.lock")).acquire(timeout=0):
        report = {
            "mode": "dry_run" if dry_run else "live",
            "scrapes": [],
            "scored": 0,
            "applications": [],
            "errors": [],
        }
        report["scrapes"] = await scrape_platforms(platform, headless)
        try:
            emit("match", "Scoring discovered opportunities against your profile")
            report["scored"] = await JobMatcher().score_jobs()
            emit(
                "match",
                "Matching finished",
                state="completed",
                metrics={"scored": report["scored"]},
            )
        except Exception as exc:
            emit(
                "match",
                "Matching failed; application stage will not run",
                state="failed",
            )
            report["errors"].append(f"Matching failed: {type(exc).__name__}")
            return report
        if do_apply:
            report["applications"] = await apply_platforms(
                platform,
                dry_run=dry_run,
                limit=apply_limit,
                headless=headless,
                min_score=settings.min_match_score,
            )
        return report
