"""
Glassdoor job scraper.
Scrapes job listings from Glassdoor using Playwright.
Glassdoor requires login for full job details; public search results are scraped.
"""

import logging
import re
from typing import List
from urllib.parse import urlencode

from .base import BaseScraper
from ..models import Job
from ..config import settings

logger = logging.getLogger(__name__)


class GlassdoorScraper(BaseScraper):
    """Scraper for Glassdoor job listings."""

    platform_name = "glassdoor"

    def _build_search_url(self, query: str = "", page: int = 1) -> str:
        """Build Glassdoor job search URL."""
        base = self.platform_config.get("search_url", "https://www.glassdoor.co.in/Job")
        roles = settings.search_queries
        locations = settings.user_locations

        search_query = query or (roles[0] if roles else "Software Engineer")
        location = locations[0] if locations else "India"

        # Glassdoor URL format: /Job/{location}-{query}-jobs-SRCH_...
        # Use their search endpoint for simplicity
        search_url = f"{base}/jobs.htm"
        params = {
            "sc.keyword": search_query,
            "locT": "N",
            "locKeyword": location,
            "fromAge": self.platform_config.get("filters", {}).get(
                "from_age", "7"
            ),  # Last 7 days
            "seniorityType": self.platform_config.get("filters", {}).get(
                "seniority_type", ""
            ),
        }

        url = f"{search_url}?{urlencode(params)}"
        if page > 1:
            url += f"&p={page}"
        return url

    async def login(self) -> bool:
        # The shared persistent profile contains the interactive login session.
        # Public listings may also work without authentication.
        return True

    async def scrape_jobs(self) -> List[Job]:
        """Scrape jobs from Glassdoor across multiple search queries."""
        jobs = []
        roles = settings.search_queries
        max_jobs = self.platform_config.get("max_jobs", 50)

        for role in roles[: self.platform_config.get("max_queries", 3)]:
            if len(jobs) >= max_jobs:
                break

            for page_num in range(1, self.max_pages + 1):
                if len(jobs) >= max_jobs:
                    break

                try:
                    url = self._build_search_url(query=role, page=page_num)
                    logger.info(f"[glassdoor] Scraping '{role}' page {page_num}")

                    await self.navigate(url, wait_until="domcontentloaded")
                    await self._random_delay(1.5)

                    # Dismiss popups
                    await self._dismiss_popups()

                    # Wait for job cards to load
                    try:
                        await self.page.wait_for_selector(
                            '[class*="JobCard"], [data-test="jobListing"], '
                            '[class*="jobCard"], .react-job-listing, '
                            'li[data-id], [class*="job-listing"]',
                            timeout=15000,
                        )
                    except Exception:
                        logger.warning(
                            f"[glassdoor] No job cards for '{role}' page {page_num}"
                        )
                        break

                    page_jobs = await self._extract_jobs_from_page()
                    if not page_jobs:
                        break

                    jobs.extend(page_jobs)
                    logger.info(
                        f"[glassdoor] '{role}' page {page_num}: "
                        f"found {len(page_jobs)} jobs (total: {len(jobs)})"
                    )

                    # Check for next page
                    next_btn = await self.page.query_selector(
                        '[data-test="pagination-next"], '
                        'button[aria-label="Next"], '
                        'a:has-text("Next")'
                    )
                    if not next_btn:
                        break

                except Exception as e:
                    logger.error(
                        f"[glassdoor] Error scraping '{role}' p{page_num}: {e}"
                    )
                    break

        # Deduplicate
        seen_urls = set()
        unique = []
        for j in jobs:
            if j.url not in seen_urls:
                seen_urls.add(j.url)
                unique.append(j)

        return unique

    async def _dismiss_popups(self):
        """Dismiss Glassdoor's notorious popups and modals."""
        try:
            for selector in [
                'button[class*="CloseButton"]',
                '[data-test="close-button"]',
                'button[aria-label="Close"]',
                ".modal_closeIcon",
                "#LoginModal button.close",
                'button:has-text("✕")',
                'button:has-text("×")',
                '[class*="hardsell"] button',
                'button:has-text("No Thanks")',
                'button:has-text("Maybe Later")',
                '[id*="onetrust"] button:has-text("Accept")',
            ]:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await self._random_delay(0.3)
                except Exception:
                    continue
        except Exception:
            pass

        # Also try pressing Escape key to dismiss modals
        try:
            await self.page.keyboard.press("Escape")
            await self._random_delay(0.3)
        except Exception:
            pass

    async def _extract_jobs_from_page(self) -> List[Job]:
        """Extract job listings from the current page."""
        jobs = []

        card_selectors = [
            '[class*="JobCard"]',
            '[data-test="jobListing"]',
            ".react-job-listing",
            "li[data-id]",
            '[class*="job-listing"]',
            '[class*="jobCard"]',
        ]

        cards = []
        for selector in card_selectors:
            cards = await self.page.query_selector_all(selector)
            if cards:
                break

        # Fallback: JS extraction
        if not cards:
            return await self._extract_jobs_js()

        for card in cards:
            try:
                job = await self._parse_job_card(card)
                if job and job.title:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"[glassdoor] Error parsing card: {e}")
                continue

        return jobs

    async def _parse_job_card(self, card) -> Job:
        """Parse a Glassdoor job card into a Job object."""
        # Title
        title_el = await card.query_selector(
            '[data-test="job-title"], [class*="jobTitle"], '
            '[class*="JobTitle"], a[class*="title"], h2 a'
        )
        title = (await title_el.inner_text()).strip() if title_el else ""

        if not title:
            text = await card.inner_text()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            title = lines[0] if lines else ""

        if not title:
            return None

        # Company
        company_el = await card.query_selector(
            '[data-test="emp-name"], [class*="companyName"], '
            '[class*="EmployerName"], [class*="employer"]'
        )
        company = (await company_el.inner_text()).strip() if company_el else "Unknown"
        # Clean company name (remove ratings like "3.5★")
        company = re.sub(r"\s*\d+\.?\d*\s*★?\s*$", "", company).strip()

        # URL
        link_el = await card.query_selector(
            'a[href*="job-listing"], a[href*="/job/"], '
            'a[href*="jobListingId"], a[data-test="job-title"]'
        )
        if not link_el:
            link_el = title_el  # Title element might be the link itself
        if not link_el:
            link_el = await card.query_selector("a[href]")

        url = ""
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                url = (
                    href
                    if href.startswith("http")
                    else f"https://www.glassdoor.co.in{href}"
                )

        # Location
        location_el = await card.query_selector(
            '[data-test="emp-location"], [class*="location"], [class*="Location"]'
        )
        location = (await location_el.inner_text()).strip() if location_el else ""

        # Salary
        salary_el = await card.query_selector(
            '[data-test="detailSalary"], [class*="salary"], [class*="Salary"]'
        )
        salary = (await salary_el.inner_text()).strip() if salary_el else ""

        # Posted date
        date_el = await card.query_selector(
            '[data-test="job-age"], [class*="listingAge"], [class*="posted"]'
        )
        posted_date = (await date_el.inner_text()).strip() if date_el else ""

        # Easy Apply badge
        easy_apply_el = await card.query_selector(
            '[data-test="easy-apply"], [class*="easyApply"], [class*="EasyApply"]'
        )
        job_type = "easy_apply" if easy_apply_el else "standard"

        # External ID
        external_id = ""
        if url:
            match = re.search(r"jobListingId=(\d+)", url)
            if not match:
                match = re.search(r"[-/](\d{7,})", url)
            if match:
                external_id = match.group(1)

        # Also try data attribute
        if not external_id:
            data_id = await card.get_attribute("data-id")
            if data_id:
                external_id = data_id

        return Job(
            title=title,
            company=company,
            platform="glassdoor",
            url=url,
            location=location,
            salary=salary,
            posted_date=posted_date,
            job_type=job_type,
            external_id=external_id,
        )

    async def _extract_jobs_js(self) -> List[Job]:
        """Fallback: extract job data via JavaScript."""
        try:
            raw_data = await self.page.evaluate("""() => {
                const results = [];
                
                // Glassdoor uses React — look for job listing anchors
                const anchors = Array.from(
                    document.querySelectorAll(
                        'a[href*="job-listing"], a[href*="/job/"], a[href*="jobListingId"]'
                    )
                );
                const seen = new Set();
                
                for (const anchor of anchors) {
                    const href = anchor.href;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    
                    // Walk up to find card container
                    let container = anchor;
                    for (let i = 0; i < 5; i++) {
                        if (container.parentElement) container = container.parentElement;
                    }
                    
                    const text = container.innerText || '';
                    const title = anchor.innerText.trim();
                    
                    if (title && href && title.length > 3) {
                        results.push({
                            title: title,
                            url: href,
                            text: text,
                        });
                    }
                }
                return results;
            }""")

            jobs = []
            for r in raw_data:
                title = r.get("title", "").strip()
                url_val = r.get("url", "")
                text = r.get("text", "")

                if not title or not url_val:
                    continue

                # Parse company, location from surrounding text
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                company = lines[1] if len(lines) > 1 else "Unknown"
                location = ""
                for line in lines:
                    if any(
                        city in line.lower()
                        for city in [
                            "bangalore",
                            "mumbai",
                            "delhi",
                            "hyderabad",
                            "pune",
                            "chennai",
                            "remote",
                            "india",
                            "bengaluru",
                            "noida",
                            "gurgaon",
                            "gurugram",
                        ]
                    ):
                        location = line
                        break

                external_id = ""
                match = re.search(r"jobListingId=(\d+)", url_val)
                if not match:
                    match = re.search(r"[-/](\d{7,})", url_val)
                if match:
                    external_id = match.group(1)

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        platform="glassdoor",
                        url=url_val,
                        location=location,
                        external_id=external_id,
                    )
                )

            return jobs

        except Exception as e:
            logger.error(f"[glassdoor] JS extraction failed: {e}")
            return []
