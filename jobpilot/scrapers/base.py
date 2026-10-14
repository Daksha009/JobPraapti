"""
Base scraper class.
All platform-specific scrapers inherit from this.
"""

import asyncio
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from playwright.async_api import (
    Browser,
    Page,
    BrowserContext,
    TimeoutError as BrowserTimeout,
)
from ..browser import BrowserSession

from ..config import settings
from ..models import Job, ScrapeResult
from ..database import db
from ..progress import emit

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base scraper. Provides shared functionality:
    - Browser lifecycle management (Playwright)
    - Configurable pacing and shared authenticated sessions
    - Error handling & retries
    - Deduplication via database
    """

    platform_name: str = "base"

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session = BrowserSession(self.platform_name)
        self.platform_config = self._get_platform_config()
        self.navigation_errors = []

    def _get_platform_config(self) -> dict:
        """Get config for this specific platform."""
        platforms = settings.platforms.get("platforms", {})
        return platforms.get(self.platform_name, {})

    @property
    def is_enabled(self) -> bool:
        return self.platform_config.get("enabled", False)

    @property
    def max_pages(self) -> int:
        return self.platform_config.get("max_pages", 5)

    @property
    def delay_seconds(self) -> int:
        return self.platform_config.get("delay_seconds", 3)

    async def _random_delay(self, multiplier: float = 1.0):
        """Pace read requests using the platform's configured delay."""
        base = self.delay_seconds
        delay = random.uniform(base * 0.7, base * 1.5) * multiplier
        await asyncio.sleep(delay)

    async def start_browser(self, headless: Optional[bool] = None):
        """Launch a Playwright browser instance."""
        scraping_config = settings.platforms.get("scraping", {})
        if headless is None:
            headless = scraping_config.get("headless", True)

        await self.session.start(headless)
        self.context, self.page = self.session.context, self.session.page

    async def stop_browser(self):
        await self.session.close()

    async def navigate(self, url, **kwargs):
        """Retry read-only navigation; never retry application submissions."""
        from urllib.parse import urlsplit

        target = urlsplit(url)
        emit(
            "discover",
            f"Reading {target.hostname}{target.path}",
            platform=self.platform_name,
        )
        attempts = settings.platforms.get("scraping", {}).get("max_retries", 3)
        for attempt in range(attempts):
            try:
                response = await self.page.goto(url, **kwargs)
                if response and response.status >= 400:
                    raise RuntimeError(f"Platform returned HTTP {response.status}")
                if any(
                    part in self.page.url.lower()
                    for part in ("/checkpoint/", "/challenge/", "/login")
                ):
                    raise RuntimeError(
                        "Login or verification required; use the login command"
                    )
                return response
            except BrowserTimeout:
                if attempt + 1 < attempts:
                    emit(
                        "discover",
                        f"Page timed out; retry {attempt + 1} of {attempts - 1}",
                        platform=self.platform_name,
                    )
                    await asyncio.sleep(min(2**attempt, 8))
                    continue
                self.navigation_errors.append("Page navigation timed out")
                raise
            except Exception as exc:
                self.navigation_errors.append(str(exc))
                raise

    @abstractmethod
    async def scrape_jobs(self) -> List[Job]:
        """
        Scrape jobs from the platform.
        Must be implemented by each platform-specific scraper.
        Returns a list of Job objects.
        """
        pass

    async def login(self) -> bool:
        """
        Optional login step for platforms that require authentication.
        Override in subclass if needed. Returns True if login successful.
        """
        return True

    def _filter_by_preferences(self, jobs: List[Job]) -> List[Job]:
        """
        Pre-filter jobs based on user preferences (exclude keywords, etc.)
        This is a quick filter before AI matching.
        """
        filtered = []
        exclude = [kw.lower() for kw in settings.exclude_keywords]

        for job in jobs:
            if not job.url or not job.title:
                continue
            title_lower = job.title.lower()

            # Check exclude keywords
            excluded = False
            for kw in exclude:
                if kw in title_lower:
                    excluded = True
                    break

            if excluded:
                continue

            # Check experience eligibility (e.g. 0-2 years)
            ok, exp_reason = job.is_experience_eligible(
                min_allowed=settings.min_experience_years,
                max_allowed=settings.max_experience_years,
            )
            if not ok:
                logger.debug(
                    f"[{self.platform_name}] Filtered out '{job.title}' ({job.experience}): {exp_reason}"
                )
                continue

            filtered.append(job)

        removed = len(jobs) - len(filtered)
        if removed > 0:
            logger.info(
                f"[{self.platform_name}] Filtered out {removed} jobs by preferences (keywords & experience)"
            )
        # Feed/category platforms do not expose a reliable keyword search URL.
        # Prioritize matching extracted/manual skills before applying the page limit.
        import re

        keywords = settings.search_keywords or settings.user_skills
        if keywords:

            def relevance(job):
                text = f"{job.title} {job.description} {' '.join(job.skills)}".lower()
                return sum(
                    bool(
                        re.search(
                            r"(?<![\w+#])" + re.escape(keyword.lower()) + r"(?![\w+#])",
                            text,
                        )
                    )
                    for keyword in keywords
                )

            filtered.sort(key=relevance, reverse=True)
        return filtered

    async def run(self, headless: Optional[bool] = None) -> ScrapeResult:
        """
        Full scrape pipeline:
        1. Start browser
        2. Login (if needed)
        3. Scrape jobs
        4. Filter by preferences
        5. Save to database (with dedup)
        6. Log results
        """
        result = ScrapeResult(platform=self.platform_name)

        if not self.is_enabled:
            logger.warning(f"[{self.platform_name}] Platform is disabled in config")
            result.success = False
            result.errors.append("Platform disabled")
            result.finish()
            return result

        try:
            await self.start_browser(headless=headless)

            # Login if needed
            logged_in = await self.login()
            if not logged_in:
                result.success = False
                result.errors.append("Login failed")
                result.finish()
                return result

            # Scrape
            logger.info(f"[{self.platform_name}] Starting scrape...")
            jobs = await self.scrape_jobs()
            result.jobs_found = len(jobs)
            emit(
                "discover",
                f"Extracted {len(jobs)} listings; checking your preferences",
                platform=self.platform_name,
                metrics={"jobs_found": len(jobs)},
            )
            if self.navigation_errors:
                result.success = False
                result.errors.extend(self.navigation_errors)
            if not jobs:
                result.success = False
                result.errors.append(
                    "No listings extracted; the page may be empty, blocked, or changed"
                )
            logger.info(f"[{self.platform_name}] Found {len(jobs)} jobs")

            # Filter
            jobs = self._filter_by_preferences(jobs)[
                : self.platform_config.get("max_jobs", settings.max_jobs_per_platform)
            ]
            if not jobs:
                result.errors.append(
                    "No eligible listings extracted; inspect filters, authentication and selectors"
                )

            # Save to database
            inserted, duplicates = db.add_jobs(jobs)
            result.jobs_new = inserted
            result.jobs_duplicate = duplicates
            logger.info(
                f"[{self.platform_name}] Saved: {inserted} new, {duplicates} duplicates"
            )

        except Exception as e:
            logger.error(f"[{self.platform_name}] Scrape error: {e}", exc_info=True)
            result.success = False
            result.errors.append(str(e))
        finally:
            await self.stop_browser()
            result.finish()

            # Log to database
            db.log_scrape(
                platform=result.platform,
                jobs_found=result.jobs_found,
                jobs_new=result.jobs_new,
                jobs_duplicate=result.jobs_duplicate,
                errors=result.errors,
                started_at=result.started_at,
                completed_at=result.completed_at,
                success=result.success,
            )

        return result
