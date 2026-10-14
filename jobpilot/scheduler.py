"""Timezone-explicit scheduling through the shared pipeline."""

import asyncio
import logging
import re
import time
import schedule
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)


def run_daily_pipeline(**kwargs):
    return asyncio.run(run_pipeline(**kwargs))


def start_scheduler(
    run_time="09:00", run_immediately=False, *, timezone="UTC", **kwargs
):
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", run_time):
        raise ValueError("Time must be HH:MM in 24-hour format")
    scheduler = schedule.Scheduler()

    def execute():
        try:
            logger.info("Pipeline report: %s", run_daily_pipeline(**kwargs))
        except Exception:
            logger.exception(
                "Scheduled pipeline failed; next daily run remains scheduled"
            )

    scheduler.every().day.at(run_time, timezone).do(execute)
    logger.info(
        "Daily schedule: %s (%s), dry_run=%s",
        run_time,
        timezone,
        kwargs.get("dry_run", True),
    )
    if run_immediately:
        execute()
    try:
        while True:
            scheduler.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")
